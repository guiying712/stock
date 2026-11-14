"""Isolated, deterministic replay using the very same strategy entry point."""
from copy import deepcopy
from datetime import datetime, timedelta, time
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
from statistics import mean, median
from zoneinfo import ZoneInfo

from . import __version__
from .config import config_hash, validate_config
from .store import digest


def parse_time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("回放时间必须包含时区")
    return parsed


def source_hash():
    """Fingerprint the actual strategy/runtime sources, not a version label alone."""
    sha = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        sha.update(path.name.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return sha.hexdigest()


def run_replay(batches, config):
    from .engine import evaluate
    # Preserve recorded arrival order, including late corrections. Sorting by
    # event time here would run a different history from the live state machine.
    batches = list(batches)
    if not batches:
        raise ValueError("数据集为空")
    if any(type(b.get("simulated")) is not bool for b in batches):
        raise ValueError("每个批次必须明确标记 simulated")
    if len({b["simulated"] for b in batches}) != 1:
        raise ValueError("模拟数据与真实数据不得混入同一次回放")
    input_count = len(batches)
    seen = {}
    unique = []
    for batch in batches:
        key = batch["snapshot_id"]
        if key in seen:
            if seen[key] != digest(batch):
                raise ValueError("同一快照键存在冲突修订，须显式版本化")
            continue
        seen[key] = digest(batch)
        unique.append(batch)
    batches = unique
    profiles = [("stock_only", "个股突破单独", False, "early"),
                ("sector_filter", "板块过滤＋个股突破", True, "early"),
                ("early", "早期预警", True, "early"),
                ("confirmed", "确认后提醒", True, "confirmed")]
    reports = []
    for profile, label, sector_filter, stage in profiles:
        cfg = deepcopy(config)
        cfg.update(id=config["id"] + "-" + profile, mode="replay", purpose="experimental")
        if "research" in cfg:
            cfg["research"] = {"sector_filter": sector_filter, "alert_stage": stage}
        elif profile in {"stock_only", "confirmed"}:
            reports.append({"id": profile, "name": label, "status": "unsupported", "reason": "当前参数版本未提供该研究分支"})
            continue
        validate_config(cfg)
        state = None
        events, coverage, rejected = [], [], {}
        last = None
        for batch in batches:
            last = evaluate(batch, cfg, state)
            state = last["state"]
            events.extend(last["events"])
            coverage.append(last["quality"].get("coverage", 0))
            for item in last.get("evaluations", []):
                for code in item.get("reason_codes", []):
                    rejected[code] = rejected.get(code, 0) + 1
        signals = last["signals"]
        first_alert = {}
        for event in events:
            if event.get("to_status") in {"PREALERT", "CONFIRMED"}:
                first_alert.setdefault(event["signal_id"], event)
        alerted = [s for s in signals if s["id"] in first_alert]
        evaluation = evaluate_observations(alerted, first_alert, batches)
        reports.append({"id": profile, "name": label, "status": "completed", "config_hash": config_hash(cfg),
                        "config": cfg, "signal_count": len(alerted), "detected_count": len(signals),
                        "event_count": len(events), "invalidated_count": sum(s["status"] == "INVALIDATED" for s in alerted),
                        "min_coverage": min((value for value in coverage if value is not None), default=None), "rejections": rejected, "evaluation": evaluation,
                        "output_hash": digest({"signals": signals, "events": events}),
                        "signals": alerted, "events": events})
    return {"status": "completed", "kind": "functional_replay", "simulated": batches[0]["simulated"],
            "strategy_version": config["id"], "config_hash": config_hash(config), "code_version": __version__,
            "code_hash": source_hash(), "dataset_hash": digest(batches),
            "start": min(batches, key=lambda b: parse_time(b["as_of"]))["as_of"],
            "end": max(batches, key=lambda b: parse_time(b["as_of"]))["as_of"],
            "batch_count": len(batches), "duplicate_batches_removed": input_count - len(batches), "baselines": reports,
            "selected_baseline_id": config.get("research", {}).get("alert_stage", "early"),
            "assumptions": ["严格复用 evaluate 并保持录制到达顺序；可见时间由数据记录约束，历史网络延迟未复现",
                            "sector_filter 与 early 共享相同基线，作为组装和提醒时点的参照",
                            "仅评价信号和可观察价格，不模拟真实成交、组合净值或盈利胜率"],
            "limitations": ["合成数据仅用于功能验收；不能证明全市场覆盖、策略收益或真实通知时延",
                            "5/10/20交易日窗口缺少成熟数据时为 pending；停牌、涨跌停、复权等输入须由数据供应商完整提供",
                            "本功能回放不做成交/成本仿真，成本后收益为 null；显式模型研究使用study命令",
                            "本报告不提供时间分割、聚类置信区间或连续影子证据；真实数据与发布门槛须独立验收"]}


def _positive(value):
    try:
        if value is None or isinstance(value, bool):
            return None
        number = Decimal(str(value))
        return number if number.is_finite() and number > 0 else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def _prices_valid(quote):
    values = {key: _positive(quote.get(key)) for key in ("close", "high", "low", "adjustment_factor")}
    return all(value is not None for value in values.values()) and values["low"] <= values["close"] <= values["high"]


def _visible_rows(batches):
    rows, daily, rejected = [], [], {}
    quote_keys, daily_keys = set(), set()
    for batch in batches:
        cutoff = parse_time(batch["as_of"])
        for quote in batch.get("quotes", []):
            reason = None
            try:
                event, available = parse_time(quote["event_time"]), parse_time(quote["available_at"])
                if quote.get("is_complete") is not True or quote.get("interval") != 60 or quote.get("quality") != "good" or not _prices_valid(quote):
                    reason = "INVALID_OR_MISSING_QUOTE"
                elif event > cutoff or available > cutoff or available < event:
                    reason = "QUOTE_NOT_VISIBLE"
                elif event != cutoff.replace(second=0, microsecond=0):
                    reason = "QUOTE_SLICE_MISMATCH"
            except (KeyError, ValueError, TypeError):
                reason = "INVALID_QUOTE_TIME"
            if reason:
                rejected[reason] = rejected.get(reason, 0) + 1
                continue
            key = (quote["instrument_id"], event, quote.get("revision", 1))
            if key in quote_keys:
                continue
            quote_keys.add(key)
            rows.append({"cutoff": cutoff, "event": event, "available": available, "quote": quote})
        for bar in batch.get("daily_bars", []):
            try:
                available = parse_time(bar["available_at"])
                day = datetime.strptime(bar["date"], "%Y-%m-%d").date()
                if available > cutoff or not _prices_valid(bar):
                    continue
                key = (bar["instrument_id"], day, available, str(bar["close"]), str(bar["adjustment_factor"]))
                if key in daily_keys:
                    continue
                daily_keys.add(key)
                daily.append({"cutoff": cutoff, "available": available, "day": day, "quote": bar})
            except (KeyError, ValueError, TypeError):
                rejected["INVALID_DAILY_BAR"] = rejected.get("INVALID_DAILY_BAR", 0) + 1
    rows.sort(key=lambda row: (row["cutoff"], row["available"], row["event"], row["quote"].get("revision", 1)))
    daily.sort(key=lambda row: (row["cutoff"], row["available"]))
    return rows, daily, rejected


def _calendar_at(batches, start):
    earlier = [batch for batch in batches if parse_time(batch["as_of"]) <= start]
    if not earlier:
        return None
    calendar = max(earlier, key=lambda batch: parse_time(batch["as_of"])) .get("calendar")
    if not isinstance(calendar, dict) or not calendar.get("version"):
        return None
    return calendar


def evaluate_observations(signals, first_alert, batches):
    """Describe observations without inferring executable fills or trading P&L."""
    rows, daily, gaps = _visible_rows(batches)
    opportunities = []
    for delay in (0, 1, 3, 5):
        available, pending = 0, 0
        for signal in signals:
            received = parse_time(first_alert[signal["id"]]["at"]) + timedelta(minutes=delay)
            # A later delivery of the same old bar must not count as a new price.
            future = [row for row in rows if row["quote"]["instrument_id"] == signal["instrument_id"]
                      and row["event"] > received and row["available"] > received and row["cutoff"] > received]
            low, high = _positive(signal.get("entry_low")), _positive(signal.get("entry_high"))
            if not future or low is None or high is None:
                pending += 1
                continue
            row = future[0]
            price = _positive(row["quote"]["close"])
            if row["cutoff"] < parse_time(signal["expires_at"]) and low < price <= high:
                available += 1
        opportunities.append({"extra_delay_minutes": delay, "sample_count": len(signals), "observable_in_range": available,
                              "pending": pending, "observed_unavailable": len(signals) - available - pending,
                              "observable_fraction": available / len(signals) if signals else None,
                              "observed_sample_count": len(signals) - pending,
                              "note": "全部提醒为分母的前向价格区间观测；pending保留，非成交率，未核验可交易性"})
    windows = []
    shanghai = ZoneInfo("Asia/Shanghai")
    for days in (5, 10, 20):
        returns, favorable, adverse, pending_reasons = [], [], [], {}
        samples = []
        for signal in signals:
            start = parse_time(first_alert[signal["id"]]["at"])
            calendar = _calendar_at(batches, start)
            reason = None
            target, close_at = None, None
            try:
                if not calendar or not calendar.get("close_time"):
                    reason = "CALENDAR_CLOSE_UNSPECIFIED"
                else:
                    close_time = datetime.strptime(calendar["close_time"], "%H:%M").time()
                    trade_days = sorted({datetime.strptime(day, "%Y-%m-%d").date() for day in calendar["trading_dates"]
                                         if datetime.strptime(day, "%Y-%m-%d").date() > start.astimezone(shanghai).date()})
                    if len(trade_days) < days:
                        reason = "CALENDAR_WINDOW_INCOMPLETE"
                    else:
                        target = trade_days[days - 1]
                        close_at = datetime.combine(target, close_time, tzinfo=shanghai)
            except (KeyError, ValueError, TypeError):
                reason = "CALENDAR_INVALID"
            endpoint = None
            if not reason:
                closing = [row for row in rows if row["quote"]["instrument_id"] == signal["instrument_id"] and row["event"] == close_at]
                day_end = [row for row in daily if row["quote"]["instrument_id"] == signal["instrument_id"] and
                           row["day"] == target and row["available"] >= close_at and row["cutoff"] >= close_at]
                if closing:
                    endpoint = closing[-1]["quote"]
                elif day_end:
                    endpoint = day_end[-1]["quote"]
                else:
                    reason = "TARGET_CLOSE_MISSING"
            evidence = signal.get("evidence") or {}
            trigger_factor = _positive(evidence.get("adjustment_factor"))
            trigger_price = _positive(signal.get("trigger_price"))
            if not reason and (trigger_factor is None or trigger_price is None):
                reason = "TRIGGER_ADJUSTMENT_MISSING"
            if reason:
                pending_reasons[reason] = pending_reasons.get(reason, 0) + 1
                samples.append({"signal_id": signal["id"], "status": "pending", "reason_code": reason,
                                "target_date": target.isoformat() if target else None})
                continue
            base = trigger_price * trigger_factor
            value = float(_positive(endpoint["close"]) * _positive(endpoint["adjustment_factor"]) / base - 1)
            returns.append(value)
            observed = [row["quote"] for row in rows if row["quote"]["instrument_id"] == signal["instrument_id"] and start < row["event"] <= close_at]
            observed.append(endpoint)
            favorable.append(float(max(_positive(q["high"]) * _positive(q["adjustment_factor"]) for q in observed) / base - 1))
            adverse.append(float(min(_positive(q["low"]) * _positive(q["adjustment_factor"]) for q in observed) / base - 1))
            samples.append({"signal_id": signal["id"], "status": "observed", "target_date": target.isoformat(),
                            "calendar_version": calendar["version"], "gross_trigger_return": value})
        windows.append({"trading_days": days, "status": "observed" if returns else "pending", "sample_count": len(returns),
                        "pending": len(signals) - len(returns), "pending_reasons": pending_reasons, "samples": samples,
                        "gross_trigger_return_mean": mean(returns) if returns else None,
                        "gross_trigger_return_median": median(returns) if returns else None,
                        "max_favorable": None, "max_adverse": None,
                        "observed_max_favorable": max(favorable) if favorable else None,
                        "observed_max_adverse": min(adverse) if adverse else None,
                        "cost_adjusted_return": None, "benchmark_excess": None,
                        "note": "按触发时可见的版本化交易日历和目标日收盘计算复权可比的触发价观察；仅有观测极值，完整窗口极值未验收，非交易收益"})
    return {"delay_scenarios": opportunities, "windows": windows, "cost_adjusted_status": "not_configured", "observation_gaps": gaps}
