"""Read-only chart projections from the original recorded input snapshots."""
from collections import Counter
from decimal import Decimal, InvalidOperation
import json
from zoneinfo import ZoneInfo

from .contracts import utc
from .store import StoreError, digest


def _view(batch, signal, events, cutoff):
    reasons, by_time, conflicts = Counter(), {}, set()
    if batch is None:
        return {"status": "empty", "candles": [], "events": [], "reason_counts": {"SNAPSHOT_UNAVAILABLE": 1}, "as_of": None}
    instant = utc(cutoff)
    factor = signal.get("evidence", {}).get("adjustment_factor")
    for quote in batch["minute_history"] + batch["quotes"]:
        if quote["instrument_id"] != signal["instrument_id"]:
            continue
        event = utc(quote["event_time"])
        if event.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat() != signal["trading_date"]:
            continue
        available, ingested = utc(quote["available_at"]), utc(quote["ingested_at"])
        if not event <= available <= ingested <= instant:
            reasons["NOT_VISIBLE_AT_VIEW_TIME"] += 1
            continue
        if not quote["is_complete"] or quote["quality"] != "good":
            reasons["INCOMPLETE_OR_BAD_QUALITY"] += 1
            continue
        if factor is None or quote["adjustment_factor"] is None or Decimal(str(quote["adjustment_factor"])) != Decimal(str(factor)):
            reasons["ADJUSTMENT_BASIS_CHANGED"] += 1
            continue
        try:
            values = {key: Decimal(str(quote[key])) for key in ("open", "high", "low", "close")}
            if any(not v.is_finite() or v <= 0 for v in values.values()) or not values["low"] <= min(values["open"], values["close"]) <= max(values["open"], values["close"]) <= values["high"]:
                raise ValueError()
        except (InvalidOperation, ValueError, TypeError):
            reasons["OHLC_UNKNOWN_OR_INVALID"] += 1
            continue
        candle = {key: quote[key] for key in ("event_time", "available_at", "ingested_at", "open", "high", "low", "close", "amount_cny", "source", "revision")}
        previous = by_time.get(event)
        if previous and previous["revision"] == candle["revision"] and previous != candle:
            conflicts.add(event)
        elif previous is None or previous["revision"] < candle["revision"]:
            by_time[event] = candle
    candles = [q for at, q in sorted(by_time.items()) if at not in conflicts]
    reasons["CONFLICTING_SAME_REVISION"] += len(conflicts)
    limited = len(candles) > 120
    candles = candles[-120:]
    markers = [{"at": event["at"], "status": event["to_status"], "revision": event["revision"],
                "reason_codes": event.get("reason_codes", [])} for event in events if utc(event["at"]) <= instant]
    return {"status": "available" if candles else "empty", "as_of": cutoff, "snapshot_id": batch["snapshot_id"],
            "input_hash": digest(batch), "candles": candles, "events": markers, "limited": limited,
            "reason_counts": {key: count for key, count in reasons.items() if count}}


def signal_chart(store, signal):
    """A trigger view stays tied to its immutable input; latest is separate."""
    evidence = signal.get("evidence") or {}
    # The episode's trigger can precede its first alert. Never reconstruct that
    # earlier view from a later alert snapshot, even with timestamp filtering.
    trigger_id = evidence.get("snapshot_id") or evidence.get("prealert_snapshot_id")
    with store.connect() as db:
        trigger = db.execute("SELECT input FROM scans WHERE version=? AND snapshot_id=?", (signal["strategy_version"], trigger_id)).fetchone()
        latest = db.execute("SELECT input FROM scans WHERE version=? ORDER BY seq DESC LIMIT 1", (signal["strategy_version"],)).fetchone()
    trigger_batch = json.loads(trigger[0]) if trigger else None
    latest_batch = json.loads(latest[0]) if latest else None
    events = signal.get("events", [])
    return {"schema_version": 1, "interval_seconds": 60, "simulated": bool(signal.get("simulated", evidence.get("simulated", True))),
            "trading_date": signal["trading_date"], "adjustment_factor": evidence.get("adjustment_factor"),
            "levels": {"breakout": signal.get("breakout_price"), "invalidation": signal.get("invalidation_price"),
                       "trigger": signal.get("trigger_price"), "frozen_at": signal.get("trigger_time")},
            "trigger": _view(trigger_batch, signal, events, signal["trigger_time"]),
            "latest": _view(latest_batch, signal, events, latest_batch["as_of"] if latest_batch else signal["trigger_time"]),
            "limitations": ["只展示已保存且在对应视图时点可见的完成分钟，不补齐缺失K线",
                            "累计成交额按原输入展示，不当作单分钟成交量",
                            "价格与冻结结构位仅在相同复权基准下绘制；最新视图不改写触发证据"]}


SECTOR_TIMELINE_SLICES = 48


def sector_timeline(store, version, sector_id):
    """Project stage changes from committed scans for one immutable version."""
    if not isinstance(sector_id, str) or not sector_id.strip():
        raise ValueError("请选择板块")
    observations, name, limited = [], None, False
    shanghai = ZoneInfo("Asia/Shanghai")
    with store.connect() as db:
        rows = db.execute(
            "SELECT snapshot_id, as_of, result FROM scans WHERE version=? ORDER BY seq DESC LIMIT ?",
            (version, SECTOR_TIMELINE_SLICES + 1),
        )
        for index, row in enumerate(rows):
            if index == SECTOR_TIMELINE_SLICES:
                limited = True
                break
            result = json.loads(row["result"])
            quality = result["quality"]
            sector = next((item for item in result["sectors"] if item["id"] == sector_id), None)
            if sector is not None and name is None:
                name = sector.get("name") or sector_id
            state = sector or {}
            members = sorted(
                (member for member in state.get("active_members", []) if type(member.get("return")) in (int, float)),
                key=lambda member: (-member["return"], member["id"]),
            )
            observations.append({
                "snapshot_id": row["snapshot_id"], "as_of": row["as_of"],
                "trading_date": utc(row["as_of"]).astimezone(shanghai).date().isoformat(),
                "source": quality.get("source"), "simulated": quality.get("simulated"),
                "status": state.get("status"), "quality": state.get("quality") if sector is not None else "missing",
                "candidate_gate": state.get("candidate_gate"), "confirm_gate": state.get("confirm_gate"),
                "reason_codes": sorted(set(state.get("reason_codes", [])) | set(quality.get("reason_codes", []))),
                "member_hash": digest(sorted(state.get("members", []))) if sector is not None else None,
                "metrics": {key: state.get(key) for key in ("rs", "delta_rs", "breadth", "rvol", "coverage",
                            "valid_count", "member_count", "historical_coverage", "breakout_count")},
                "leaders": [{key: member.get(key) for key in ("code", "name", "return")} for member in members[:3]],
            })
    if name is None:
        raise StoreError("NOT_FOUND", "最近扫描中没有该热点")
    events, previous = [], None
    tracked = ("trading_date", "status", "quality", "candidate_gate", "confirm_gate", "member_hash", "source", "reason_codes")
    for point in reversed(observations):
        if previous is None and point["quality"] == "missing":
            continue
        changes = [key for key in tracked if previous is not None and point[key] != previous[key]]
        if previous is None or changes:
            events.append(dict(point, changes=changes))
        previous = point
    if previous["snapshot_id"] != events[-1]["snapshot_id"]:
        events.append(dict(previous, changes=[]))
    return {"sector_id": sector_id, "name": name, "strategy_version": version,
            "scanned_slices": len(observations), "limited": limited, "events": events}
