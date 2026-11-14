"""Deterministic minute-slice engine. No I/O, network calls, clock reads or LLMs.

All prices are calculated with Decimal and serialized as strings. Input records
remain immutable; a persisted state is sufficient to continue after a restart.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
import json
from statistics import mean, median, pstdev
from zoneinfo import ZoneInfo

from .config import MARKET_PAIRS, config_hash, validate_config
from .temporal import effective_interval

SHANGHAI = ZoneInfo("Asia/Shanghai")
UTC = timezone.utc


class DataError(ValueError):
    code = "DATA_INVALID"


def timestamp(value):
    if not isinstance(value, str):
        raise DataError("时间必须使用含时区的 ISO 8601 字符串")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DataError("无效时间: " + value) from exc
    if parsed.tzinfo is None:
        raise DataError("时间缺少时区")
    return parsed.astimezone(UTC)


def iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def decimal(value):
    if value is None or isinstance(value, bool):
        raise DataError("数值缺失")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise DataError("无效数值") from exc
    if not result.is_finite():
        raise DataError("数值必须有限")
    return result


def price(value):
    return str(decimal(value).quantize(Decimal("0.000001")).normalize())


def _id(*parts):
    return sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:24]


def _visible(record, cutoff):
    try:
        return timestamp(record["available_at"]) <= cutoff and ("event_time" not in record or timestamp(record["event_time"]) <= cutoff)
    except (KeyError, DataError):
        return False


def _valid_at(record, cutoff):
    try:
        start, end = effective_interval(record)
    except ValueError as exc:
        raise DataError(str(exc)) from exc
    return (_visible(record, cutoff) and (start is None or start <= cutoff)
            and (end is None or cutoff < end))


def _group_sectors(sectors, threshold, feature_version):
    """Canonical connected groups of the thresholded Jaccard graph."""
    parents = {s["id"]: s["id"] for s in sectors}
    members = {s["id"]: set(s["members"]) for s in sectors}

    def root(sid):
        while parents[sid] != sid:
            parents[sid] = parents[parents[sid]]
            sid = parents[sid]
        return sid

    ids = sorted(parents)
    for index, left in enumerate(ids):
        for right in ids[index + 1:]:
            union = members[left] | members[right]
            if union and len(members[left] & members[right]) / len(union) >= threshold:
                a, b = sorted((root(left), root(right)))
                parents[b] = a
    for sector in sectors:
        sector["group_id"] = root(sector["id"])
        sector["group_version"] = "jaccard-connected-v1:" + feature_version


def _minute_number(dt, calendar):
    local = dt.astimezone(SHANGHAI)
    dates = sorted(set(calendar["trading_dates"]))
    day = local.date().isoformat()
    if day not in dates or local.second or local.microsecond:
        return None
    minute = local.hour * 60 + local.minute
    total, result = 0, None
    for start, end in calendar["sessions"]:
        sh, sm = map(int, start.split(":"))
        eh, em = map(int, end.split(":"))
        begin, finish = sh * 60 + sm, eh * 60 + em
        if begin < minute <= finish:
            result = total + minute - begin
        total += finish - begin
    return None if result is None else dates.index(day) * total + result


def _quote_error(q, cutoff, config, check_freshness=True):
    if not _visible(q, cutoff):
        return "NOT_YET_AVAILABLE"
    try:
        event = timestamp(q["event_time"])
        if not q["is_complete"] or q["interval"] != config["runtime"]["slice_seconds"]:
            return "INCOMPLETE_SLICE"
        if check_freshness and (cutoff - event).total_seconds() > config["runtime"]["stale_after_seconds"]:
            return "DATA_STALE"
        if q.get("quality") != "good":
            return "DATA_QUALITY"
        o, h, low, c = (decimal(q[k]) for k in ("open", "high", "low", "close"))
        if min(o, h, low, c, decimal(q["prev_close"]), decimal(q["adjustment_factor"])) <= 0:
            return "PRICE_INVALID"
        if not low <= min(o, c) <= max(o, c) <= h:
            return "OHLC_INVALID"
        if decimal(q["amount_cny"]) < 0 or decimal(q["volume_shares"]) < 0:
            return "VOLUME_INVALID"
        if timestamp(q["ingested_at"]) < timestamp(q["available_at"]) or timestamp(q["available_at"]) < event:
            return "TIMESTAMP_INVALID"
    except (KeyError, DataError):
        return "DATA_INCOMPLETE"
    return None


def _daily_rows(rows, instrument_id, day, cutoff, calendar):
    latest = {}
    for row in rows:
        if (row.get("instrument_id") == instrument_id and row.get("date", day) < day and
                row.get("date") in calendar["trading_dates"] and _visible(row, cutoff)):
            try:
                values = {k: decimal(row[k]) for k in ("high", "low", "close", "prev_close", "amount_cny", "adjustment_factor")}
                if (min(values[k] for k in ("high", "low", "close", "prev_close", "adjustment_factor")) <= 0 or
                        values["amount_cny"] < 0 or not values["low"] <= values["close"] <= values["high"]):
                    continue
            except (KeyError, DataError):
                continue
            old = latest.get(row["date"])
            if old is None or row.get("revision", 1) >= old.get("revision", 1):
                latest[row["date"]] = row
    return [latest[k] for k in sorted(latest)]


def _shape(rows, q, settings):
    needed = max(settings["lookback_days"], settings["atr_days"])
    if len(rows) < needed:
        return None, "HISTORY_INSUFFICIENT"
    try:
        current_factor = decimal(q["adjustment_factor"])
        adjusted = [{k: decimal(r[k]) * decimal(r["adjustment_factor"]) / current_factor for k in ("high", "low", "close", "prev_close")} for r in rows[-needed:]]
        high = max(r["high"] for r in adjusted[-settings["lookback_days"]:])
        low = min(r["low"] for r in adjusted[-settings["lookback_days"]:])
        tr = [max(r["high"] - r["low"], abs(r["high"] - r["prev_close"]), abs(r["low"] - r["prev_close"])) for r in adjusted[-settings["atr_days"]:]]
        atr = sum(tr) / Decimal(len(tr))
        if min(high, low, atr) <= 0:
            return None, "ZERO_DENOMINATOR"
        if high / low - 1 > decimal(settings["max_range_width"]):
            return None, "RANGE_TOO_WIDE"
        if median(float(decimal(r["amount_cny"])) for r in rows[-settings["lookback_days"]:]) < settings["min_daily_amount_cny"]:
            return None, "LOW_LIQUIDITY"
        trigger = high + decimal(settings["breakout_buffer_atr"]) * atr
        stop = high - decimal(settings["invalidation_buffer_atr"]) * atr
        return {"high": high, "low": low, "atr": atr, "trigger": trigger, "stop": stop}, None
    except (KeyError, DataError, InvalidOperation, ZeroDivisionError):
        return None, "HISTORY_INVALID"


def _all_minutes(batch, state, cutoff, config):
    by_key = {}
    for q in batch.get("minute_history", []) + state.get("minute_cache", []) + batch.get("quotes", []):
        if _quote_error(q, cutoff, config, check_freshness=False):
            continue
        if _minute_number(timestamp(q["event_time"]), batch["calendar"]) is None:
            continue
        key = q.get("instrument_id"), q.get("event_time")
        if key not in by_key or q.get("revision", 1) > by_key[key].get("revision", 1):
            by_key[key] = q
    result = defaultdict(list)
    for q in by_key.values():
        result[q["instrument_id"]].append(q)
    for values in result.values():
        values.sort(key=lambda q: q["event_time"])
    return result


def _window_returns(q, history, calendar, length):
    try:
        index = _minute_number(timestamp(q["event_time"]), calendar)
        if index is None:
            return None
        targets = {index - length, index - length * 2}
        refs = {}
        for row in history:
            n = _minute_number(timestamp(row["event_time"]), calendar)
            if n in targets:
                refs[n] = decimal(row["close"]) * decimal(row["adjustment_factor"])
        if len(refs) != 2 or any(v <= 0 for v in refs.values()):
            return None
        current = decimal(q["close"]) * decimal(q["adjustment_factor"])
        middle, first = refs[index - length], refs[index - length * 2]
        return float(current / middle - 1), float(middle / first - 1)
    except (KeyError, DataError):
        return None


def _same_minute_amounts(q, history, days, day):
    minute = timestamp(q["event_time"]).astimezone(SHANGHAI).strftime("%H:%M")
    amounts = {}
    for row in history:
        local = timestamp(row["event_time"]).astimezone(SHANGHAI)
        row_day = local.date().isoformat()
        if row_day < day and local.strftime("%H:%M") == minute:
            value = decimal(row["amount_cny"])
            if value > 0:
                amounts[row_day] = float(value)
    selected = sorted(amounts)[-days:]
    return {d: amounts[d] for d in selected} if len(selected) == days else None


def _score(features, config):
    total, parts = 0.0, {}
    for key, group in config["scoring"]["groups"].items():
        if group["weight"] == 0:
            parts[key] = {"label": group["label"], "weight": 0, "normalized": None, "points": 0, "features": [], "disabled": True}
            continue
        value, detail = 0.0, []
        for item in group["features"]:
            raw = features.get(item["name"])
            if raw is None:
                return None, {}
            norm = min(1.0, max(0.0, (raw - item["low"]) / (item["high"] - item["low"])))
            norm = 1 - norm if item["inverse"] else norm
            value += norm * item["weight"]
            detail.append({"name": item["name"], "raw": raw, "normalized": round(norm, 8), "weight": item["weight"], "low": item["low"], "high": item["high"], "inverse": item["inverse"]})
        total += value * group["weight"]
        parts[key] = {"label": group["label"], "weight": group["weight"], "normalized": round(value, 8), "points": round(99 * value * group["weight"], 2), "features": detail}
    score = int(Decimal(str(1 + 99 * total)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return max(1, min(100, score)), parts


def _tag(tag_id, entity_type, entity_id, value, as_of, config, snapshot_id):
    return {"id": _id(tag_id, entity_id, as_of), "tag_id": tag_id, "definition_version": config["feature_version"], "entity_type": entity_type, "entity_id": entity_id, "kind": "computed", "value": value, "observed_at": as_of, "available_at": as_of, "valid_until": iso(timestamp(as_of) + timedelta(seconds=config["runtime"]["stale_after_seconds"])), "evidence_ids": [snapshot_id], "rule_version": config["id"], "status": "active"}


def evaluate(batch, config, prior_state=None):
    """Evaluate one completed slice and return a JSON-serializable result.

    Duplicate snapshot IDs are ignored. Late revisions are surfaced as a data
    correction and pause active signals instead of rewriting a published past.
    """
    config = validate_config(config)
    state = deepcopy(prior_state or {})
    signature = config_hash(config)
    if state.get("strategy_hash") not in {None, signature}:
        raise DataError("策略版本改变必须使用独立运行状态")
    for field in ("snapshot_id", "as_of", "source", "simulated", "calendar", "instruments", "sectors", "memberships", "quotes", "daily_bars", "minute_history", "benchmark", "units"):
        if field not in batch:
            raise DataError("批次缺少字段: " + field)
    if batch.get("schema_version") != 1:
        raise DataError("不支持的数据契约版本")
    if not isinstance(batch["simulated"], bool):
        raise DataError("simulated必须显式布尔值")
    if config["mode"] in {"shadow", "live_alert"} and batch["simulated"]:
        raise DataError("真实运行模式拒绝模拟数据")
    as_of, cutoff = batch["as_of"], timestamp(batch["as_of"])
    day = cutoff.astimezone(SHANGHAI).date().isoformat()
    snapshot_id = batch["snapshot_id"]
    if snapshot_id in state.get("processed", []):
        cached = deepcopy(state.get("last_result", {}))
        cached.update({"events": [], "evaluations": [], "tags": [], "state": state, "duplicate": True})
        return cached
    events, evaluations, tags = [], [], []
    state.setdefault("signals", {})
    state.setdefault("sectors", {})
    state.setdefault("episodes", {})
    state.setdefault("daily_alert_counts", {})
    state.setdefault("previous_prices", {})
    state.setdefault("processed", [])
    state["strategy_hash"] = signature
    global_reasons = []
    if batch["units"] != {"volume": "shares", "amount": "CNY", "amount_mode": "cumulative"}:
        global_reasons.append("UNIT_MISMATCH")
    late = bool(state.get("watermark") and cutoff <= timestamp(state["watermark"]))
    if late:
        global_reasons.append("LATE_CORRECTION")
    calendar = batch["calendar"]
    # All members and the benchmark must describe the same completed minute.
    # Use only already-visible, valid quotes to choose it; allow declared
    # upstream latency within the freshness bound without admitting the future.
    event_times = [timestamp(q["event_time"]) for q in batch["quotes"] if not _quote_error(q, cutoff, config)]
    slice_time = max(event_times) if event_times else cutoff.replace(second=0, microsecond=0)
    if _minute_number(slice_time, calendar) is None:
        global_reasons.append("OUTSIDE_SESSION")
    slice_index = _minute_number(slice_time, calendar)
    continuity_broken = state.get("last_slice_index") is not None and slice_index != state["last_slice_index"] + 1
    if continuity_broken:
        if "market" in state:
            state["market"].update(pending=None, count=0)
        for sector_state in state["sectors"].values():
            sector_state.update(candidate_count=0, confirm_count=0, fade_count=0, reset_count=0)
        for signal_state in state["signals"].values():
            signal_state["confirmation_count"] = 0
    instruments, excluded = {}, []
    daily = {}
    quote_map = {}
    for quote in batch["quotes"]:
        iid = quote.get("instrument_id")
        if iid not in quote_map or quote.get("revision", 1) > quote_map[iid].get("revision", 1):
            quote_map[iid] = quote
    for item in batch["instruments"]:
        iid = item.get("id")
        if (item.get("exchange"), item.get("board")) not in MARKET_PAIRS + (("BSE", "BSE"),):
            raise DataError("交易所与上市板块组合无效")
        reason = None
        if not _valid_at(item, cutoff):
            reason = "INSTRUMENT_NOT_VISIBLE"
        elif not isinstance(item.get("code"), str) or len(item["code"]) != 6 or not item["code"].isdigit():
            reason = "INSTRUMENT_CODE_INVALID"
        elif item.get("board") not in config["preferences"]["boards"] or item.get("exchange") not in {"SSE", "SZSE"}:
            reason = "BOARD_EXCLUDED"
        elif item.get("status") != "active":
            reason = "STATUS_" + str(item.get("status", "UNKNOWN")).upper()
        else:
            params = config["stock"][item["board"]]
            rows = _daily_rows(batch["daily_bars"], iid, day, cutoff, calendar)
            daily[iid] = rows
            try:
                listing_days = (datetime.fromisoformat(day) - datetime.fromisoformat(item["listed_on"])).days
            except (KeyError, ValueError):
                listing_days = -1
            if listing_days < params["min_listing_days"]:
                reason = "NEW_LISTING"
            elif len(rows) < max(params["lookback_days"], params["atr_days"]):
                reason = "HISTORY_INSUFFICIENT"
            elif median(float(decimal(r["amount_cny"])) for r in rows[-params["lookback_days"]:]) < params["min_daily_amount_cny"]:
                reason = "LOW_LIQUIDITY"
        if reason:
            excluded.append({"instrument_id": iid, "code": item.get("code"), "name": item.get("name"), "reason_codes": [reason], "as_of": as_of})
        else:
            instruments[iid] = item
    valid, invalid_quotes = {}, {}
    for iid in instruments:
        quote = quote_map.get(iid)
        reason = "QUOTE_MISSING" if quote is None else _quote_error(quote, cutoff, config)
        if not reason and timestamp(quote["event_time"]) != slice_time:
            reason = "SLICE_MISMATCH"
        if reason:
            invalid_quotes[iid] = reason
        else:
            valid[iid] = quote
    expected = len(instruments)
    coverage = len(valid) / expected if expected else None
    if coverage is None or coverage < config["runtime"]["universe_min_coverage"]:
        global_reasons.append("COVERAGE_LOW")
    if any(reason == "DATA_STALE" for reason in invalid_quotes.values()):
        global_reasons.append("DATA_STALE")
    quality = {"expected_count": expected, "valid_count": len(valid), "coverage": coverage, "missing_ids": sorted(invalid_quotes), "invalid_quotes": invalid_quotes, "excluded": excluded, "excluded_count": len(excluded), "status": "good" if not global_reasons else "paused", "reason_codes": sorted(set(global_reasons)), "as_of": as_of, "source": batch["source"], "simulated": batch["simulated"], "scope": "fixture_universe" if batch["simulated"] else "provider_declared_universe", "latency_seconds": max(0, (cutoff - slice_time).total_seconds()), "calendar_version": calendar["version"]}
    histories = _all_minutes(batch, state, cutoff, config)
    shapes, stock_features = {}, {}
    for iid, quote in valid.items():
        shape, reason = _shape(daily[iid], quote, config["stock"][instruments[iid]["board"]])
        if reason:
            stock_features[iid] = {"reason_codes": [reason]}
            continue
        shapes[iid] = shape
        returns = _window_returns(quote, histories[iid], calendar, config["sector"]["rs_window_minutes"])
        amounts = _same_minute_amounts(quote, histories[iid], config["sector"]["rvol_days"], day)
        rv = float(decimal(quote["amount_cny"])) / median(amounts.values()) if amounts else None
        rows = daily[iid]
        extension_days = config["sector"]["extension_days"]
        extension = None
        if len(rows) > extension_days:
            first, last = rows[-extension_days - 1], rows[-1]
            extension = float(decimal(last["close"]) * decimal(last["adjustment_factor"]) / (decimal(first["close"]) * decimal(first["adjustment_factor"])) - 1)
        stock_features[iid] = {"return": float(decimal(quote["close"]) / decimal(quote["prev_close"]) - 1), "window_return": returns[0] if returns else None, "previous_return": returns[1] if returns else None, "rvol": rv, "amount_history": amounts, "extension": extension, "breakout": decimal(quote["close"]) > shape["trigger"], "reason_codes": [] if returns and amounts else ["HISTORY_INSUFFICIENT"]}
    breadth = sum(decimal(q["close"]) > decimal(q["prev_close"]) for q in valid.values()) / len(valid) if valid else None
    bench = batch["benchmark"]
    bench_quote = bench.get("quote", {})
    bench_reason = _quote_error(bench_quote, cutoff, config) if bench_quote else "BENCHMARK_MISSING"
    if not bench_reason and timestamp(bench_quote["event_time"]) != slice_time:
        bench_reason = "SLICE_MISMATCH"
    bench_rows = _daily_rows(bench.get("daily_bars", []), bench.get("id"), day, cutoff, calendar)
    bench_returns = _window_returns(bench_quote, [r for r in bench.get("minute_history", []) if not _quote_error(r, cutoff, config, check_freshness=False) and _minute_number(timestamp(r["event_time"]), calendar) is not None], calendar, config["sector"]["rs_window_minutes"]) if not bench_reason else None
    market_cfg = config["market"]
    market_reasons = list(global_reasons)
    if bench.get("id") != market_cfg["benchmark"]:
        market_reasons.append("BENCHMARK_MISMATCH")
    if bench_reason:
        market_reasons.append(bench_reason)
    short_ma = long_ma = volatility = None
    raw_market = "UNKNOWN"
    if len(bench_rows) < max(market_cfg["long_window"], market_cfg["volatility_window"]) or bench_returns is None:
        market_reasons.append("HISTORY_INSUFFICIENT")
    elif not market_reasons and breadth is not None:
        closes = [float(decimal(r["close"]) * decimal(r["adjustment_factor"])) for r in bench_rows]
        short_ma = mean(closes[-market_cfg["short_window"]:])
        long_ma = mean(closes[-market_cfg["long_window"]:])
        volatility = pstdev(float(decimal(r["close"]) / decimal(r["prev_close"]) - 1) for r in bench_rows[-market_cfg["volatility_window"]:])
        raw_market = "HIGH_VOL" if volatility > market_cfg["high_volatility"] else "UP" if short_ma > long_ma and breadth >= market_cfg["up_breadth"] else "DOWN" if short_ma < long_ma and breadth <= market_cfg["down_breadth"] else "RANGE"
    previous_market = state.get("market", {"status": "UNKNOWN", "pending": None, "count": 0})
    market_state = deepcopy(previous_market)
    if raw_market == "UNKNOWN":
        market_state.update(status="UNKNOWN", pending=None, count=0)
    else:
        count = previous_market.get("count", 0) + 1 if previous_market.get("pending") == raw_market else 1
        market_state.update(pending=raw_market, count=count)
        if count >= market_cfg["state_slices"]:
            market_state["status"] = raw_market
    state["market"] = market_state
    market = {"status": market_state["status"], "raw_status": raw_market, "as_of": as_of, "breadth": breadth, "short_ma": short_ma, "long_ma": long_ma, "volatility": volatility, "benchmark": bench.get("id"), "reason_codes": sorted(set(market_reasons)), "simulated": batch["simulated"], "source": batch["source"]}
    tags.append(_tag("market." + market["status"].lower(), "market", bench.get("id"), True, as_of, config, snapshot_id))
    membership = defaultdict(set)
    invalid_membership = []
    for item in batch["memberships"]:
        if _valid_at(item, cutoff) and item.get("instrument_id") in instruments:
            membership[item["sector_id"]].add(item["instrument_id"])
        elif item.get("instrument_id") in instruments:
            invalid_membership.append(item["instrument_id"])
    sectors = []
    sector_cfg = config["sector"]
    for sector in sorted(batch["sectors"], key=lambda x: x["id"]):
        sid = sector["id"]
        members = sorted(membership[sid])
        present = [iid for iid in members if iid in valid]
        comparable = [iid for iid in present if not stock_features.get(iid, {}).get("reason_codes", ["MISSING"])]
        sector_coverage = len(present) / len(members) if members else None
        hist_coverage = len(comparable) / len(members) if members else None
        reasons = []
        if sector_coverage is None or sector_coverage < config["runtime"]["sector_min_coverage"]:
            reasons.append("COVERAGE_LOW")
        if hist_coverage is None or hist_coverage < config["runtime"]["historical_min_coverage"]:
            reasons.append("HISTORY_INSUFFICIENT")
        if len(comparable) < sector_cfg["min_members"]:
            reasons.append("SECTOR_SAMPLE_LOW")
        if bench_returns is None:
            reasons.append("BENCHMARK_MISSING")
        rs = delta_rs = sector_breadth = rvol = concentration = extension = sector_return = sector_median = None
        breakouts = 0
        if not reasons:
            sector_return = mean(stock_features[i]["window_return"] for i in comparable)
            sector_median = median(stock_features[i]["window_return"] for i in comparable)
            rs = sector_return - bench_returns[0]
            previous_rs = mean(stock_features[i]["previous_return"] for i in comparable) - bench_returns[1]
            delta_rs = rs - previous_rs
            sector_breadth = sum(stock_features[i]["window_return"] > 0 for i in comparable) / len(comparable)
            breakouts = sum(stock_features[i]["breakout"] for i in comparable)
            shared_days = set.intersection(*(set(stock_features[i]["amount_history"]) for i in comparable))
            current_amounts = [float(decimal(valid[i]["amount_cny"])) for i in comparable]
            if len(shared_days) < sector_cfg["rvol_days"] or sum(current_amounts) <= 0:
                reasons.append("HISTORY_INSUFFICIENT")
            else:
                hist_amounts = [sum(stock_features[i]["amount_history"][d] for i in comparable) for d in sorted(shared_days)[-sector_cfg["rvol_days"]:]]
                rvol = sum(current_amounts) / median(hist_amounts)
                concentration = sum(sorted(current_amounts, reverse=True)[:sector_cfg["concentration_top_k"]]) / sum(current_amounts)
            extensions = [stock_features[i]["extension"] for i in comparable]
            if None in extensions:
                reasons.append("HISTORY_INSUFFICIENT")
            else:
                extension = mean(extensions)
        data_ok = not reasons and not global_reasons
        candidate = bool(data_ok and rs >= sector_cfg["min_rs"] and delta_rs >= sector_cfg["min_delta_rs"] and sector_breadth >= sector_cfg["min_breadth"] and breakouts >= sector_cfg["min_breakouts"] and rvol >= sector_cfg["min_rvol"] and concentration <= sector_cfg["max_concentration"] and extension <= sector_cfg["max_extension"])
        confirmed = bool(candidate and rs >= sector_cfg["confirm_rs"] and sector_breadth >= sector_cfg["confirm_breadth"] and rvol >= sector_cfg["confirm_rvol"])
        unusual = bool(data_ok and (rs >= sector_cfg["unusual_rs"] or rvol >= sector_cfg["min_rvol"]))
        fade = bool(data_ok and (rs < sector_cfg["exit_rs"] or sector_breadth < sector_cfg["exit_breadth"]))
        old = state["sectors"].get(sid, {"status": "NORMAL", "candidate_count": 0, "confirm_count": 0, "fade_count": 0, "reset_count": 0, "candidate_at": None, "episode": 0})
        new = deepcopy(old)
        if not data_ok:
            new.update(candidate_count=0, confirm_count=0, fade_count=0, reset_count=0)
        else:
            new["candidate_count"] = old["candidate_count"] + 1 if candidate else 0
            new["confirm_count"] = old["confirm_count"] + 1 if confirmed else 0
            new["fade_count"] = old["fade_count"] + 1 if fade else 0
            if old["status"] == "FADING":
                new["reset_count"] = old["reset_count"] + 1
                if new["reset_count"] >= sector_cfg["reset_slices"]:
                    new.update(status="NORMAL", candidate_count=0, confirm_count=0, reset_count=0)
            elif old["status"] == "CONFIRMED":
                if new["fade_count"] >= sector_cfg["fade_slices"]:
                    new.update(status="FADING", reset_count=0)
            elif new["candidate_count"] >= sector_cfg["candidate_slices"]:
                if old["status"] not in {"CANDIDATE", "CONFIRMED"}:
                    new.update(candidate_at=as_of, episode=old["episode"] + 1)
                new["status"] = "CONFIRMED" if new["confirm_count"] >= sector_cfg["confirm_slices"] else "CANDIDATE"
            elif old["status"] == "CANDIDATE" and old.get("candidate_at") and (cutoff - timestamp(old["candidate_at"])).total_seconds() <= config["lifecycle"]["candidate_timeout_seconds"]:
                new["status"] = "CANDIDATE"
            else:
                new["status"] = "UNUSUAL" if unusual else "NORMAL"
        state["sectors"][sid] = new
        if data_ok and not candidate:
            gates = [(rs < sector_cfg["min_rs"], "SECTOR_RS_LOW"), (delta_rs < sector_cfg["min_delta_rs"], "SECTOR_MOMENTUM_LOW"), (sector_breadth < sector_cfg["min_breadth"], "SECTOR_BREADTH_LOW"), (breakouts < sector_cfg["min_breakouts"], "SECTOR_BREAKOUTS_LOW"), (rvol < sector_cfg["min_rvol"], "SECTOR_VOLUME_LOW"), (concentration > sector_cfg["max_concentration"], "SECTOR_CONCENTRATED"), (extension > sector_cfg["max_extension"], "SECTOR_EXTENDED")]
            reasons.extend(reason for failed, reason in gates if failed)
        result = {"id": sid, "name": sector["name"], "type": sector.get("type", "industry"), "status": new["status"], "quality": "good" if data_ok else "paused", "as_of": as_of, "rs": rs, "delta_rs": delta_rs, "breadth": sector_breadth, "rvol": rvol, "coverage": sector_coverage, "historical_coverage": hist_coverage, "member_count": len(members), "valid_count": len(present), "members": members, "active_members": [{"id": i, "code": instruments[i]["code"], "name": instruments[i]["name"], "return": stock_features.get(i, {}).get("return")} for i in present], "breakout_count": breakouts, "concentration": concentration, "extension": extension, "return": sector_return, "median_return": sector_median, "candidate_gate": candidate, "confirm_gate": confirmed, "episode": new["episode"], "reason_codes": sorted(set(reasons)), "simulated": batch["simulated"]}
        sectors.append(result)
        tags.append(_tag("sector." + new["status"].lower(), "sector", sid, True, as_of, config, snapshot_id))
    # Similarity metadata for display and notification grouping only; sector
    # metrics, scoring and individual signals remain distinct.
    _group_sectors(sectors, sector_cfg["jaccard_threshold"], config["feature_version"])
    sector_map = {s["id"]: s for s in sectors}

    def emit(signal, before, reasons):
        signal["revision"] = signal.get("revision", 0) + 1
        signal["reason_codes"] = sorted(set(reasons))
        signal["updated_at"] = as_of
        event = {"id": _id(signal["id"], signal["revision"]), "signal_id": signal["id"], "revision": signal["revision"], "from_status": before, "to_status": signal["status"], "reason_codes": signal["reason_codes"], "at": as_of, "snapshot_id": snapshot_id, "snapshot": deepcopy(signal)}
        events.append(event)

    # Update existing episodes even when new opportunities are disabled.
    for signal in state["signals"].values():
        if signal["status"] in {"INVALIDATED", "EXPIRED"}:
            continue
        iid = signal["instrument_id"]
        old_status, old_action = signal["status"], signal["actionability"]
        q = valid.get(iid)
        sector = sector_map.get(signal.get("primary_sector_id"))
        reasons = []
        if q and (not late or timestamp(q["event_time"]) >= timestamp(signal["latest_time"])):
            signal.update(latest_price=price(q["close"]), latest_time=q["event_time"])
        if cutoff >= timestamp(signal["expires_at"]):
            signal.update(status="EXPIRED", actionability="expired")
            reasons = ["ENTRY_TTL_EXPIRED"]
        elif global_reasons or not q or (sector and sector["quality"] != "good"):
            signal["actionability"] = "paused"
            signal["confirmation_count"] = 0
            reasons = global_reasons or [invalid_quotes.get(iid, "SECTOR_DATA_INCOMPLETE")]
        elif decimal(q["adjustment_factor"]) != decimal(signal["evidence"]["adjustment_factor"]):
            # Preserve the original episode's raw-price levels. Until a
            # versioned corporate-action conversion is explicitly reviewed,
            # a changed price basis cannot invalidate or reactivate it.
            signal["actionability"] = "paused"
            signal["confirmation_count"] = 0
            reasons = ["CORPORATE_ACTION_REVIEW"]
        elif decimal(q["close"]) < decimal(signal["invalidation_price"]) or (sector and sector["status"] == "FADING"):
            signal.update(status="INVALIDATED", actionability="expired")
            reasons = ["STRUCTURE_BROKEN" if decimal(q["close"]) < decimal(signal["invalidation_price"]) else "SECTOR_FADING"]
        elif market["status"] not in {"UP", "RANGE"}:
            signal["actionability"] = "paused"
            signal["confirmation_count"] = 0
            reasons = ["MARKET_GATE"]
        elif signal["status"] == "DETECTED":
            # Internal detections become actionable only in the complete
            # qualification pass below, including the frozen risk and score.
            signal["actionability"] = "paused"
        elif (stock_features.get(iid, {}).get("rvol") is None or
              stock_features[iid]["rvol"] < config["stock"][instruments[iid]["board"]]["min_rvol"] or
              decimal(q["amount_cny"]) < decimal(config["stock"][instruments[iid]["board"]]["min_amount_cny"])):
            signal["actionability"] = "paused"
            signal["confirmation_count"] = 0
            reasons = ["STOCK_VOLUME_LOW"]
        elif not decimal(signal["entry_low"]) < decimal(q["close"]) <= decimal(signal["entry_high"]):
            signal["actionability"] = "extended" if decimal(q["close"]) > decimal(signal["entry_high"]) else "paused"
            signal["confirmation_count"] = 0
            reasons = ["PRICE_EXTENDED" if signal["actionability"] == "extended" else "BELOW_ENTRY_RANGE"]
        else:
            signal["actionability"] = "eligible"
            signal["confirmation_count"] = signal.get("confirmation_count", 0) + 1
            sector_confirmed = (sector and sector["status"] == "CONFIRMED" and sector["confirm_gate"] and
                                state["sectors"][sector["id"]]["confirm_count"] >= config["sector"]["confirm_slices"])
            if signal["status"] == "PREALERT" and (not config["research"]["sector_filter"] or sector_confirmed) and signal["confirmation_count"] >= config["lifecycle"]["stock_confirm_slices"]:
                signal["status"] = "CONFIRMED"
                reasons = ["BREAKOUT_CONFIRMED"]
            elif old_action != "eligible":
                reasons = ["PARTICIPATION_RESTORED"]
        if old_status != signal["status"] or old_action != signal["actionability"]:
            emit(signal, old_status, reasons)
    # Evaluate every eligible instrument, including explicit rejection records.
    for iid, instrument in sorted(instruments.items()):
        q = valid.get(iid)
        params = config["stock"][instrument["board"]]
        associated = sorted([s for s in sectors if iid in s["members"]], key=lambda s: (-(s["rs"] if s["rs"] is not None else -999), s["id"]))
        reason_codes = list(global_reasons)
        if not q:
            reason_codes.append(invalid_quotes[iid])
        feature = stock_features.get(iid, {})
        shape = shapes.get(iid)
        if q and (not shape or feature.get("reason_codes")):
            reason_codes.extend(feature.get("reason_codes", ["HISTORY_INSUFFICIENT"]))
        current_signal = next((s for s in state["signals"].values() if s["instrument_id"] == iid and s["status"] not in {"INVALIDATED", "EXPIRED"}), None)
        episode = state["episodes"].setdefault(iid, {"number": 0, "reset_count": config["lifecycle"]["reset_slices"], "blocked": False})
        if q and shape and not global_reasons:
            if decimal(q["close"]) <= shape["high"]:
                episode["reset_count"] += 1
                if episode["reset_count"] >= config["lifecycle"]["reset_slices"]:
                    episode["blocked"] = False
            else:
                episode["reset_count"] = 0
        if q and shape and not current_signal and not global_reasons and not episode["blocked"]:
            previous = state["previous_prices"].get(iid)
            # First slice uses adjusted previous close. Across an adjustment,
            # compare prices on the current factor basis.
            previous_price = decimal(previous["price"]) * decimal(previous["factor"]) / decimal(q["adjustment_factor"]) if previous else decimal(q["prev_close"])
            if decimal(q["close"]) > shape["trigger"] and previous_price <= shape["trigger"]:
                episode["number"] += 1
                episode["blocked"] = True
                high, atr, stop = shape["high"], shape["atr"], shape["stop"]
                upper = min(high + decimal(params["max_distance_atr"]) * atr, stop / (1 - decimal(config["preferences"]["max_loss_fraction"])))
                signal_id = _id(config["id"], iid, day, episode["number"])
                current_signal = {"id": signal_id, "episode_id": str(episode["number"]), "instrument_id": iid, "code": instrument["code"], "name": instrument["name"], "board": instrument["board"], "primary_sector_id": None, "sector_name": None, "related_sectors": [{"id": s["id"], "name": s["name"]} for s in associated], "strategy_version": config["id"], "strategy_id": config["strategy_id"], "status": "DETECTED", "actionability": "paused", "score": None, "score_parts": {}, "trigger_price": price(q["close"]), "trigger_time": q["event_time"], "latest_price": price(q["close"]), "latest_time": q["event_time"], "breakout_price": price(high), "atr": price(atr), "invalidation_price": price(stop), "entry_low": price(shape["trigger"]), "entry_high": price(upper), "expires_at": iso(cutoff + timedelta(seconds=config["lifecycle"]["entry_ttl_seconds"])), "revision": 0, "reason_codes": ["BREAKOUT_DETECTED"], "evidence": {"as_of": as_of, "source": batch["source"], "simulated": batch["simulated"], "snapshot_id": snapshot_id, "config_hash": signature, "feature_version": config["feature_version"], "adjustment_factor": q["adjustment_factor"], "calendar_version": calendar["version"]}, "trading_date": day, "simulated": batch["simulated"], "confirmation_count": 0}
                state["signals"][signal_id] = current_signal
                emit(current_signal, None, ["BREAKOUT_DETECTED"])
        if q and not late:
            state["previous_prices"][iid] = {"price": q["close"], "factor": q["adjustment_factor"], "event_time": q["event_time"]}
        if not current_signal:
            reason_codes.append("NO_NEW_BREAKOUT")
        elif current_signal["status"] != "DETECTED":
            reason_codes.append("EXISTING_EPISODE")
        if market["status"] not in {"UP", "RANGE"}:
            reason_codes.append("MARKET_GATE")
        qualified = [s for s in associated if s["quality"] == "good" and s["status"] in {"CANDIDATE", "CONFIRMED"} and s["candidate_gate"]]
        selected = qualified[0] if qualified else associated[0] if associated else None
        if config["research"]["sector_filter"] and not qualified:
            reason_codes.append("SECTOR_GATE")
        if invalid_membership and iid in invalid_membership and not associated:
            reason_codes.append("MEMBERSHIP_NOT_VISIBLE")
        score = None
        score_parts = {}
        raw = {}
        if current_signal and q and shape:
            p = decimal(q["close"])
            high, atr, stop = (decimal(current_signal[k]) for k in ("breakout_price", "atr", "invalidation_price"))
            risk = float((p - stop) / p)
            distance = float((p - high) / atr)
            relative = feature.get("window_return") - selected["return"] if feature.get("window_return") is not None and selected and selected["return"] is not None else None
            if not config["research"]["sector_filter"] and relative is None:
                relative = feature.get("window_return")
            if not 0 < stop < p or risk > config["preferences"]["max_loss_fraction"]:
                reason_codes.append("RISK_DISTANCE_EXCEEDED")
            if decimal(current_signal["entry_high"]) < decimal(current_signal["entry_low"]):
                reason_codes.append("NO_ACTIONABLE_RANGE")
            if not decimal(current_signal["entry_low"]) < p <= decimal(current_signal["entry_high"]):
                reason_codes.append("PRICE_EXTENDED" if p > decimal(current_signal["entry_high"]) else "BELOW_ENTRY_RANGE")
            if feature.get("rvol") is None or feature["rvol"] < params["min_rvol"]:
                reason_codes.append("STOCK_VOLUME_LOW")
            if relative is None or relative < params["min_relative_strength"]:
                reason_codes.append("STOCK_RELATIVE_LOW")
            if decimal(q["amount_cny"]) < decimal(params["min_amount_cny"]):
                reason_codes.append("LOW_LIQUIDITY")
            if cutoff >= timestamp(current_signal["expires_at"]):
                reason_codes.append("ENTRY_TTL_EXPIRED")
            if config["research"]["alert_stage"] == "confirmed" and selected and selected["status"] != "CONFIRMED":
                reason_codes.append("WAITING_CONFIRMATION")
            raw = {"market_breadth": breadth, "sector_rs": selected["rs"] if selected else None, "sector_delta_rs": selected["delta_rs"] if selected else None, "sector_breadth": selected["breadth"] if selected else None, "sector_rvol": selected["rvol"] if selected else None, "stock_rvol": feature.get("rvol"), "stock_relative": relative, "entry_distance": distance, "risk_fraction": risk}
            # The stock-only baseline retains exactly the same measured scoring
            # features; it only removes the board qualification gate.
            if not reason_codes:
                score, score_parts = _score(raw, config)
                if score is None:
                    reason_codes.append("SCORE_INPUT_INCOMPLETE")
                elif score < config["scoring"]["alert_threshold"]:
                    reason_codes.append("SCORE_BELOW_THRESHOLD")
            count = state["daily_alert_counts"].get(day, 0)
            if config["lifecycle"]["daily_new_limit"] and count >= config["lifecycle"]["daily_new_limit"]:
                reason_codes.append("DAILY_NEW_LIMIT")
            if not reason_codes and current_signal["status"] == "DETECTED":
                current_signal.update(status="CONFIRMED" if config["research"]["alert_stage"] == "confirmed" else "PREALERT", actionability="eligible", primary_sector_id=selected["id"] if selected else None, sector_name=selected["name"] if selected else None, score=score, score_parts=score_parts, confirmation_count=1)
                current_signal["evidence"]["features"] = raw
                current_signal["evidence"]["prealert_snapshot_id"] = snapshot_id
                if selected:
                    # Freeze notification grouping at the first alert. Later
                    # membership changes must not rewrite trigger evidence.
                    group_members = sorted((s["id"], sorted(s["members"])) for s in sectors if s["group_id"] == selected["group_id"])
                    current_signal["evidence"]["notification_group"] = {
                        "id": selected["group_id"],
                        "version": _id(selected["group_version"], json.dumps(group_members, sort_keys=True))}
                current_signal["alert_time"] = as_of
                state["daily_alert_counts"][day] = count + 1
                emit(current_signal, "DETECTED", ["BREAKOUT_CONFIRMED" if current_signal["status"] == "CONFIRMED" else "HOTSPOT_BREAKOUT"])
        evaluations.append({"instrument_id": iid, "code": instrument["code"], "name": instrument["name"], "as_of": as_of, "snapshot_id": snapshot_id, "signal_id": current_signal["id"] if current_signal else None, "accepted": not reason_codes, "reason_codes": sorted(set(reason_codes)), "score": score, "score_parts": score_parts, "features": raw})
    for signal in state["signals"].values():
        if signal["status"] in {"PREALERT", "CONFIRMED"}:
            tags.append(_tag("stock.breakout", "instrument", signal["instrument_id"], True, as_of, config, snapshot_id))
            if signal["actionability"] == "extended":
                tags.append(_tag("stock.overextended", "instrument", signal["instrument_id"], True, as_of, config, snapshot_id))
        if signal["actionability"] == "paused":
            tags.append(_tag("data.incomplete", "instrument", signal["instrument_id"], True, as_of, config, snapshot_id))
    state["processed"].append(snapshot_id)
    if not late:
        state["watermark"] = as_of
        state["last_slice_index"] = slice_index
        # Only the current session cache is needed; historical daily curves
        # remain in each recorded input batch for independent replay.
        state["minute_cache"] = [deepcopy(q) for values in histories.values() for q in values if timestamp(q["event_time"]).astimezone(SHANGHAI).date().isoformat() == day]
    signals = sorted((deepcopy(s) for s in state["signals"].values()), key=lambda s: (-(s["score"] or 0), s["trigger_time"], s["instrument_id"]))
    result = {"market": market, "sectors": sectors, "signals": signals, "events": events, "evaluations": evaluations, "tags": tags, "quality": quality, "duplicate": False}
    state["last_result"] = deepcopy({k: v for k, v in result.items() if k not in {"events", "evaluations", "tags"}})
    result["state"] = state
    return result
