"""Transactional delivery with revalidation and conservative crash recovery.

The fixture worker can explicitly opt into an isolated local simulation channel.
Real delivery still requires a released live version and exclusive recovery.
"""
import json
from datetime import date, datetime, timedelta, timezone
from time import monotonic

from .notifier import MAX_MESSAGE_BYTES, SimulationNotifier, build_group_message, build_message
from .store import StoreError, digest, dumps, now


MAX_ATTEMPTS = 3
STALE_SECONDS = 90
MAX_SENDS_PER_MINUTE = 20
SIMULATION_CHANNEL = "dingtalk_simulation"


def _channel(channel):
    if channel not in ("dingtalk", SIMULATION_CHANNEL):
        raise StoreError("CHANNEL_UNSUPPORTED", "只支持钉钉及明确标记的本地投递演练")


def _instant(value):
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("missing timezone")
    return result.astimezone(timezone.utc)


def enqueue(db, signal, event, channel="dingtalk", *, created_at=None, simulation_context=None):
    """Insert in the same caller-owned transaction as SignalEvent.

    The function deliberately neither commits nor opens a second connection.
    """
    _channel(channel)
    if channel == "dingtalk" and (created_at is not None or simulation_context is not None):
        raise StoreError("INVALID_TIME", "真实渠道不能指定模拟入队时间")
    if channel == SIMULATION_CHANNEL:
        from .contracts import fields, string
        fields(simulation_context, ("plan_id", "clock_mode"), "模拟投递上下文")
        string(simulation_context["plan_id"], "模拟投递计划ID")
        if simulation_context["clock_mode"] not in ("wall", "simulated") or created_at is None:
            raise StoreError("INVALID_TIME", "模拟投递须明确时钟域和入队时间")
    if (not signal.get("id") or event.get("signal_id") != signal["id"] or
            type(event.get("revision")) is not int or event["revision"] < 1 or
            signal.get("revision") != event["revision"]):
        raise StoreError("EVENT_MISMATCH", "信号与事件的标识或修订不一致")
    if signal.get("status") == "DETECTED":
        raise StoreError("INTERNAL_SIGNAL", "内部发现记录不得进入外部通知队列")
    notification_id = digest([signal["id"], event["revision"], channel])
    payload = {"signal": signal, "event": event, "payload_hash": digest([signal, event])}
    if channel == SIMULATION_CHANNEL:
        payload.update(simulation_transport="local", simulation_context=simulation_context,
                       wall_enqueued_at=now(), title="本地投递演练 · " + str(signal.get("name", "信号更新")))
    existing = db.execute("SELECT payload FROM outbox WHERE id=?", (notification_id,)).fetchone()
    if existing:
        previous = json.loads(existing[0])
        if previous.get("payload_hash") != payload["payload_hash"]:
            raise StoreError("IDEMPOTENCY_CONFLICT", "同一通知修订不能替换原始载荷")
        return notification_id
    timestamp = _instant(created_at).isoformat() if created_at is not None else now()
    aggregation = _aggregation(db, signal, event, timestamp, channel)
    if aggregation:
        payload["aggregation"] = aggregation
    db.execute("INSERT INTO outbox(id,signal_id,revision,channel,status,created_at,updated_at,payload) "
               "VALUES(?,?,?,?,'pending',?,?,?)",
               (notification_id, signal["id"], event["revision"], channel, timestamp, timestamp, dumps(payload)))
    return notification_id


def _aggregation(db, signal, event, timestamp, channel="dingtalk"):
    # Confirmation/resumption and risk updates are never delayed or grouped.
    if event.get("from_status") != "DETECTED" or event.get("to_status") not in {"PREALERT", "CONFIRMED"}:
        return None
    version = db.execute("SELECT config FROM versions WHERE id=?", (signal.get("strategy_version"),)).fetchone()
    config = json.loads(version[0]) if version else {}
    window = config.get("runtime", {}).get("group_window_seconds")
    if type(window) is not int or not 0 <= window < 60:
        raise StoreError("CONFIG_INCOMPLETE", "通知聚合需要显式的group_window_seconds（0至59秒整数）")
    group = (signal.get("evidence") or {}).get("notification_group")
    # Older signals have no frozen grouping evidence. Do not guess from names
    # or today's memberships; they remain individual notifications.
    if window == 0 or group is None:
        return None
    if (not isinstance(group, dict) or
            any(not isinstance(group.get(key), str) or not group[key] for key in ("id", "version"))):
        raise StoreError("INPUT_INCOMPLETE", "通知聚合缺少冻结的热点分组ID或版本")
    try:
        trading_day = signal["trading_date"]
        date.fromisoformat(trading_day)
        if len(trading_day) != 10:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise StoreError("INPUT_INCOMPLETE", "通知聚合缺少有效的首次交易日期") from None
    key = [signal["strategy_version"], trading_day, group["id"], group["version"]]
    instant = _instant(timestamp)
    deadline = instant + timedelta(seconds=window)
    # Persist the first member's deadline on every member. Even if that first
    # member is cancelled before dispatch/restart, survivors keep the window.
    # Retain cancelled rows as anchors until their original window has ended.
    lower = (instant - timedelta(seconds=window)).isoformat()
    for row in db.execute("SELECT payload FROM outbox WHERE channel=? AND created_at>=? AND created_at<=?",
                          (channel, lower, timestamp)):
        previous = json.loads(row["payload"]).get("aggregation")
        if previous and previous["key"] == key:
            previous_deadline = _instant(previous["ready_at"])
            if instant < previous_deadline:
                deadline = min(deadline, previous_deadline)
    return {"key": key, "ready_at": deadline.isoformat()}


def _is_risk(payload):
    signal, event = payload.get("signal", {}), payload.get("event", {})
    if signal.get("status") in {"INVALIDATED", "EXPIRED"}:
        return True
    return (event.get("from_status") in {"PREALERT", "CONFIRMED"} and
            signal.get("actionability") in {"paused", "extended"})


def _rejection(db, row, payload, as_of):
    stored = db.execute("SELECT data,version FROM signals WHERE id=?", (row["signal_id"],)).fetchone()
    if stored is None:
        return "SIGNAL_MISSING", None
    signal = json.loads(stored["data"])
    simulation = row["channel"] == SIMULATION_CHANNEL
    if simulation:
        try:
            if _instant(payload["event"]["at"]) > as_of or (signal.get("latest_time") is not None and _instant(signal["latest_time"]) > as_of):
                return "SIMULATION_NOT_DUE", signal
        except (ValueError, TypeError, KeyError):
            return "INPUT_INCOMPLETE", signal
    if signal.get("revision") != row["revision"]:
        return "SUPERSEDED_REVISION", signal
    version = db.execute("SELECT config FROM versions WHERE id=?", (stored["version"],)).fetchone()
    config = json.loads(version[0]) if version else {}
    evidence = signal.get("evidence") or {}
    if config.get("status") != "frozen" or config.get("mode") not in (("fixture", "replay", "shadow") if simulation else ("live_alert",)):
        return "MODE_FORBIDDEN", signal
    if simulation:
        flags = (signal.get("simulated", evidence.get("simulated")), evidence.get("simulated"),
                 payload.get("signal", {}).get("evidence", {}).get("simulated"))
        if payload.get("simulation_transport") != "local" or any(type(v) is not bool for v in flags) or len(set(flags)) != 1:
            return "SIMULATION_LABEL_INVALID", signal
        if (config.get("mode") == "fixture" and flags[0] is not True) or (config.get("mode") == "shadow" and flags[0] is not False):
            return "SIMULATION_LABEL_INVALID", signal
        if payload.get("signal", {}).get("strategy_version") != stored["version"]:
            return "VERSION_MISMATCH", signal
    elif (signal.get("simulated", evidence.get("simulated")) is not False or
            evidence.get("simulated") is not False or
            payload.get("signal", {}).get("evidence", {}).get("simulated") is not False):
        return "SIMULATION_BLOCKED", signal
    try:
        if _instant(payload["event"]["at"]) > as_of:
            return "FUTURE_EVENT", signal
        if _is_risk(payload):
            # Data-paused and expiry updates must survive the opportunity's TTL.
            # They communicate a risk state, never a current entry opportunity.
            if signal.get("status") != payload["signal"].get("status") or signal.get("actionability") != payload["signal"].get("actionability"):
                return "STATE_CHANGED", signal
            return None, signal
        if db.execute("SELECT 1 FROM runtime_flags WHERE version=?", (stored["version"],)).fetchone():
            return "PROVIDER_PAUSED", signal
        if signal.get("status") not in {"PREALERT", "CONFIRMED"}:
            return "SIGNAL_NOT_ACTIONABLE", signal
        if signal.get("actionability") != "eligible":
            return "NOT_ELIGIBLE", signal
        if _instant(signal["expires_at"]) <= as_of:
            return "ENTRY_TTL_EXPIRED", signal
        age = (as_of - _instant(signal["latest_time"])).total_seconds()
        if age < 0:
            return "FUTURE_QUOTE", signal
        if age > config.get("runtime", {}).get("stale_after_seconds", STALE_SECONDS):
            return "DATA_STALE", signal
        from decimal import Decimal
        price = Decimal(str(signal["latest_price"]))
        low, high = Decimal(str(signal["entry_low"])), Decimal(str(signal["entry_high"]))
        if not price.is_finite() or not low.is_finite() or not high.is_finite() or not low < price <= high:
            return "PRICE_OUTSIDE_RANGE", signal
    except (ValueError, TypeError, KeyError, ArithmeticError):
        return "INPUT_INCOMPLETE", signal
    return None, signal


def recover_inflight(store, *, channel="dingtalk", strategy_version=None, as_of=None):
    """Call once only after acquiring exclusive ownership of the dispatcher.

    An interrupted request may have reached DingTalk. These rows remain unknown
    and dispatch_pending never retries them automatically.
    """
    _channel(channel)
    if channel == "dingtalk" and as_of is not None:
        raise StoreError("INVALID_TIME", "真实渠道恢复不能指定模拟时间")
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        rows = [r for r in db.execute("SELECT id,payload FROM outbox WHERE channel=? AND status='sending'", (channel,))
                if strategy_version is None or json.loads(r["payload"]).get("signal", {}).get("strategy_version") == strategy_version]
        timestamp = _instant(as_of).isoformat() if as_of is not None else now()
        for row in rows:
            result = {"status": "unknown", "error": "进程中断，平台可能已受理；禁止自动重发",
                      "retryable": False, "reason_code": "DELIVERY_UNKNOWN", "phase": "recovered"}
            if channel == SIMULATION_CHANNEL:
                result.update(simulation=True, transport="local", recovered_wall_at=now(), error="本地演练进程中断，模拟结果未知；禁止自动重试")
            db.execute("UPDATE outbox SET status='unknown',response=?,updated_at=?,next_attempt_at=NULL WHERE id=?",
                       (dumps(result), timestamp, row["id"]))
            db.execute("INSERT INTO attempts(notification_id,at,data) VALUES(?,?,?)", (row["id"], timestamp, dumps(result)))
    return len(rows)


def _count_recent_starts(db, as_of, channel="dingtalk"):
    # This query is intentionally independent of business opportunity quotas.
    deliveries = set()
    lower = (as_of - timedelta(seconds=60)).isoformat()
    for row in db.execute("SELECT id,at,data FROM attempts WHERE at>=? AND at<=?", (lower, as_of.isoformat())):
        data = json.loads(row["data"])
        if data.get("phase") != "started" or data.get("channel") != channel:
            continue
        age = (as_of - _instant(row["at"])).total_seconds()
        if 0 <= age < 60:
            # Each aggregate has one HTTP request but a trace on every member.
            # Legacy starts without a delivery_id are individual requests.
            deliveries.add(data.get("delivery_id") or "legacy-" + str(row["id"]))
    return len(deliveries)


def _expire(db, row, reason, timestamp):
    result = {"id": row["id"], "status": "expired", "reason_code": reason, "retryable": False}
    db.execute("UPDATE outbox SET status='expired',response=?,updated_at=?,next_attempt_at=NULL WHERE id=?",
               (dumps(result), timestamp, row["id"]))
    return result


def _ready_batches(db, cutoff, results, channel="dingtalk", strategy_version=None):
    """Revalidate every member, then select immutable, non-sliding windows."""
    singles, grouped, retries = [], {}, {}
    rows = db.execute("SELECT * FROM outbox WHERE channel=? AND status IN ('pending','failed') AND attempts<?",
                      (channel, MAX_ATTEMPTS)).fetchall()
    for row in rows:
        response = json.loads(row["response"]) if row["response"] else {}
        if row["status"] == "failed" and not response.get("retryable"):
            continue
        payload = json.loads(row["payload"])
        if strategy_version is not None and payload.get("signal", {}).get("strategy_version") != strategy_version:
            continue
        reason, signal = _rejection(db, row, payload, cutoff)
        if reason == "SIMULATION_NOT_DUE":
            continue
        if reason:
            results.append(_expire(db, row, reason, cutoff.isoformat()))
            continue
        # A newer revision cannot overtake an already-started request for the
        # same signal. Other signals' risk updates can still take priority.
        if db.execute("SELECT 1 FROM outbox WHERE channel=? AND signal_id=? AND status='sending'",
                      (channel, row["signal_id"])).fetchone():
            continue
        if row["next_attempt_at"] and _instant(row["next_attempt_at"]) > cutoff:
            continue
        member = (row, payload, signal)
        aggregation = payload.get("aggregation")
        if _is_risk(payload):
            singles.append([member])
        elif row["attempts"]:
            # Explicit failures retry only with surviving members of that
            # original request, never with newly queued opportunities.
            key = (response.get("delivery_id") or row["id"], row["attempts"])
            retries.setdefault(key, []).append(member)
        elif aggregation:
            grouped.setdefault(tuple(aggregation["key"]), []).append(member)
        else:
            singles.append([member])
    batches = singles + list(retries.values())
    for members in grouped.values():
        members.sort(key=lambda m: (_instant(m[0]["created_at"]), m[0]["id"]))
        while members:
            deadline = _instant(members[0][1]["aggregation"]["ready_at"])
            if cutoff < deadline:
                break
            window = [m for m in members if _instant(m[0]["created_at"]) < deadline]
            batches.append(window)
            members = members[len(window):]
    for batch in batches:
        batch.sort(key=lambda m: (_instant(m[0]["created_at"]), m[0]["id"]))
    return sorted(batches, key=lambda batch: (not _is_risk(batch[0][1]),
                  min(_instant(m[0]["created_at"]) for m in batch), batch[0][0]["id"]))


def _fit_message(db, members, timestamp, results):
    selected, messages, payload = [], [], None
    for member in members:
        row, event_payload, signal = member
        message = build_message(signal, event_payload["event"])
        combined = build_group_message(messages + [message])
        if row["channel"] == SIMULATION_CHANNEL:
            combined = {**combined, "markdown": dict(combined["markdown"])}
            combined["markdown"]["title"] = "【本地投递演练】" + combined["markdown"]["title"]
            combined["markdown"]["text"] = "仅本地模拟，未访问钉钉。\n\n" + combined["markdown"]["text"]
        if len(json.dumps(combined, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_MESSAGE_BYTES:
            if not selected:
                results.append(_expire(db, row, "MESSAGE_TOO_LARGE", timestamp))
                continue
            break
        selected.append(member)
        messages.append(message)
        payload = combined
    return selected, payload


def dispatch_pending(store, notifier, as_of, max_messages=20, *, channel="dingtalk", strategy_version=None, should_stop=None):
    """Claim under SQLite write lock, send outside the transaction, then record.

    notifier is injectable. Offline tests use a fake; no implicit notifier or
    external URL is constructed here. Only explicitly released live versions
    can pass the delivery check. max_messages bounds HTTP requests, while
    results are per notification. Call again at/after a window deadline;
    this function never sleeps or starts a background scheduler.
    """
    _channel(channel)
    if channel == SIMULATION_CHANNEL and not isinstance(notifier, SimulationNotifier):
        raise StoreError("SIMULATION_TRANSPORT_REQUIRED", "本地演练仅允许SimulationNotifier，不调用真实通知适配器")
    if should_stop is not None and not callable(should_stop):
        raise StoreError("INVALID_INPUT", "停止条件须为可调用对象")
    try:
        cutoff = _instant(as_of)
    except (ValueError, TypeError):
        raise StoreError("INVALID_TIME", "投递截止时间必须包含时区") from None
    if type(max_messages) is not int or not 1 <= max_messages <= 100:
        raise StoreError("INVALID_INPUT", "单批投递数量必须在1至100之间")
    timestamp = cutoff.isoformat()
    results = []
    for _ in range(max_messages):
        if should_stop is not None and should_stop():
            break
        claim = None
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if should_stop is not None and should_stop():
                break
            batches = _ready_batches(db, cutoff, results, channel, strategy_version)
            if not batches:
                break
            if _count_recent_starts(db, cutoff, channel) >= MAX_SENDS_PER_MINUTE:
                break
            members, message = _fit_message(db, batches[0], timestamp, results)
            if not members:
                continue
            notification_ids = [m[0]["id"] for m in members]
            delivery_id = digest([[m[0]["id"], m[0]["attempts"] + 1] for m in members])
            for row, payload, signal in members:
                attempt = row["attempts"] + 1
                db.execute("UPDATE outbox SET status='sending',attempts=?,updated_at=?,next_attempt_at=NULL WHERE id=?",
                           (attempt, timestamp, row["id"]))
                started = {"phase": "started", "channel": channel, "attempt": attempt, "revision": row["revision"],
                           "signal_id": row["signal_id"], "checked_at": timestamp,
                           "request_started_at": now(),
                           "delivery_id": delivery_id, "notification_ids": notification_ids,
                           "dispatch_snapshot": signal, "message_hash": digest(message)}
                db.execute("INSERT INTO attempts(notification_id,at,data) VALUES(?,?,?)", (row["id"], timestamp, dumps(started)))
            claim = (members, message, delivery_id, notification_ids)
        if claim is None:
            continue
        members, message, delivery_id, notification_ids = claim
        start = monotonic()
        try:
            # Trigger evidence stays frozen; current price and time come from
            # the latest persisted signal used for the dispatch check.
            result = notifier.send(message, notification_ids[0] if len(members) == 1 else delivery_id)
            if not isinstance(result, dict) or result.get("status") not in {"accepted", "failed", "unknown"}:
                raise ValueError("invalid delivery result")
            result = {key: result.get(key) for key in ("status", "response_code", "receipt", "error", "retryable")}
        except Exception:
            result = {"status": "unknown", "response_code": None, "receipt": None,
                      "error": "投递调用异常，结果无法确认；禁止自动重发", "retryable": False}
        result.update(phase="completed", elapsed_seconds=round(monotonic() - start, 6),
                      delivery_id=delivery_id, notification_ids=notification_ids, request_completed_at=now())
        if channel == SIMULATION_CHANNEL:
            result.update(simulation=True, transport="local")
            if result["status"] == "unknown":
                result["error"] = "本地模拟器返回不确定结果；禁止自动重试"
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # A separate crash-recovery operation cannot turn an uncertain
            # attempt back into a retryable one while a worker is still alive.
            for row, payload, signal in members:
                attempt = row["attempts"] + 1
                member_result = {**result, "attempt": attempt,
                                 "retryable": bool(result.get("retryable") and result["status"] == "failed" and attempt < MAX_ATTEMPTS)}
                next_attempt = (cutoff + timedelta(seconds=30 * 2 ** (attempt - 1))).isoformat() if member_result["retryable"] else None
                changed = db.execute("UPDATE outbox SET status=?,response=?,updated_at=?,next_attempt_at=? WHERE id=? AND status='sending'",
                                     (member_result["status"], dumps(member_result), timestamp, next_attempt, row["id"])).rowcount
                db.execute("INSERT INTO attempts(notification_id,at,data) VALUES(?,?,?)", (row["id"], timestamp, dumps(member_result)))
                results.append({"id": row["id"], **member_result, "next_attempt_at": next_attempt, "committed": bool(changed)})
    return results
