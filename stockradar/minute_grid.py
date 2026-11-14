"""Explicit, evidence-backed phase/availability grids for schema2 diagnostics.

No exchange calendar, security status or no-trade interval is inferred here.
An aggregate auction is a record spanning its full phase, not a one-minute bar.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
import re

from .contracts import fields, string, day
from .vendor_samples import SHANGHAI


PHASE_KINDS = {"continuous", "opening_auction", "closing_auction", "after_hours"}


def minute(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
        raise ValueError("交易阶段时间需要HH:MM")
    hour, part = map(int, value.split(":"))
    return hour * 60 + part


def choice(value, choices, name):
    if not isinstance(value, str) or value not in choices:
        raise ValueError(name + "无效")


def evidence(value, required, name):
    if value is not None:
        string(value, name)
    if required and value is None:
        raise ValueError(name + "必须显式提供")


def validate_grid(plan):
    phases = plan["calendar"]["phases"]
    if not isinstance(phases, list) or not 1 <= len(phases) <= 8:
        raise ValueError("schema2须提供1至8个显式交易阶段")
    ids, previous = set(), -1
    for phase in phases:
        fields(phase, ("id", "kind", "start", "end"), "交易阶段")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", string(phase["id"], "阶段ID")) or phase["id"] in ids:
            raise ValueError("交易阶段ID无效或重复")
        choice(phase["kind"], PHASE_KINDS, "交易阶段类型")
        start, end = minute(phase["start"]), minute(phase["end"])
        if not previous <= start < end:
            raise ValueError("交易阶段须有序、不重叠且不跨日")
        previous = end
        ids.add(phase["id"])
    for profile in plan["profiles"]:
        rules = profile["phase_rules"]
        if not isinstance(rules, list) or len(rules) != len(phases):
            raise ValueError("每个接口须完整声明所有交易阶段")
        seen = set()
        for rule in rules:
            fields(rule, ("phase_id", "mode", "label_at", "evidence"), "阶段口径")
            if not isinstance(rule["phase_id"], str) or rule["phase_id"] not in ids or rule["phase_id"] in seen:
                raise ValueError("阶段口径引用无效或重复")
            seen.add(rule["phase_id"])
            choice(rule["mode"], {"minutes", "aggregate", "excluded", "unknown"}, "阶段记录方式")
            if rule["mode"] == "aggregate":
                minute(rule["label_at"])
            elif rule["label_at"] is not None:
                raise ValueError("只有整阶段记录可显式指定标签时间")
            evidence(rule["evidence"], rule["mode"] != "unknown", "阶段口径依据")
        policy = profile["no_trade_policy"]
        fields(policy, ("mode", "evidence"), "无成交口径")
        choice(policy["mode"], {"emit", "omit", "unknown"}, "无成交记录方式")
        evidence(policy["evidence"], policy["mode"] != "unknown", "无成交口径依据")
    days = plan["security_days"]
    wanted = {(s["symbol"], d) for s in plan["symbols"] for d in plan["calendar"]["dates"]}
    if not isinstance(days, list) or len(days) != len(wanted):
        raise ValueError("证券日状态须覆盖每只证券及每个候选日期")
    seen = set()
    for record in days:
        fields(record, ("symbol", "date", "status", "evidence", "intervals"), "证券日状态")
        if not isinstance(record["symbol"], str) or not isinstance(record["date"], str):
            raise ValueError("证券日引用无效")
        key = record["symbol"], record["date"]
        if key not in wanted or key in seen:
            raise ValueError("证券日引用无效或重复")
        seen.add(key)
        choice(record["status"], {"trading", "suspended", "not_listed", "unknown"}, "证券日状态")
        evidence(record["evidence"], record["status"] != "unknown", "证券状态及完整区间清单依据")
        intervals = record["intervals"]
        if not isinstance(intervals, list) or len(intervals) > 1440:
            raise ValueError("证券日区间列表无效")
        if record["status"] != "trading" and intervals:
            raise ValueError("只有已确认交易日状态可以提供日内区间")
        previous = -1
        for interval in intervals:
            fields(interval, ("start", "end", "kind", "evidence"), "证券日内区间")
            start, end = minute(interval["start"]), minute(interval["end"])
            if not previous <= start < end:
                raise ValueError("证券日内区间须有序、不重叠且不跨日")
            if not any(start < minute(p["end"]) and end > minute(p["start"]) for p in phases):
                raise ValueError("证券日内区间须与计划交易阶段相交")
            previous = end
            choice(interval["kind"], {"halt", "no_trade"}, "证券日内区间类型")
            evidence(interval["evidence"], True, "证券日内区间依据")


def build_grids(plan):
    """Keys retain interface, security and date; absent series never shrink scope."""
    grids = {}
    for profile in plan["profiles"]:
        for record in plan["security_days"]:
            reasons, slots = set(), {}
            midnight = datetime.combine(day(record["date"]), datetime.min.time(), SHANGHAI)

            def stamp(number):
                return (midnight + timedelta(minutes=number)).astimezone(timezone.utc).isoformat()

            if plan["calendar"]["evidence"] is None:
                reasons.add("CALENDAR_UNVERIFIED")
            if record["status"] == "unknown":
                reasons.add("SECURITY_DAY_UNCONFIRMED")
            if record["status"] not in {"suspended", "not_listed"}:
                if profile["timestamp_label"] == "unknown" or profile["timestamp_timezone"] == "unknown":
                    reasons.add("GRID_TIME_SEMANTICS_UNCONFIRMED")
                if profile["no_trade_policy"]["mode"] == "unknown":
                    reasons.add("NO_TRADE_POLICY_UNCONFIRMED")
                rules = {r["phase_id"]: r for r in profile["phase_rules"]}
                for phase in plan["calendar"]["phases"]:
                    rule = rules[phase["id"]]
                    if rule["mode"] == "unknown":
                        reasons.add("PHASE_RULE_UNCONFIRMED")
                        continue
                    if rule["mode"] == "excluded":
                        continue
                    start, end = minute(phase["start"]), minute(phase["end"])
                    spans = [(start, end)] if rule["mode"] == "aggregate" else [(m, m + 1) for m in range(start, end)]
                    for begin, finish in spans:
                        label = minute(rule["label_at"]) if rule["mode"] == "aggregate" else (begin if profile["timestamp_label"] == "start" else finish)
                        excluded, zero = None, False
                        for interval in record["intervals"]:
                            a, b = minute(interval["start"]), minute(interval["end"])
                            if a < finish and b > begin:
                                if not a <= begin < finish <= b:
                                    reasons.add("PARTIAL_BAR_EXCEPTION")
                                elif interval["kind"] == "halt":
                                    excluded = "halt"
                                elif profile["no_trade_policy"]["mode"] == "omit":
                                    excluded = "no_trade"
                                elif profile["no_trade_policy"]["mode"] == "emit":
                                    zero = True
                        if stamp(label) in slots:
                            raise ValueError("接口阶段映射产生重复原始标签，不能猜测区间归属")
                        slots[stamp(label)] = {"interval_start": stamp(begin), "interval_end": stamp(finish),
                            "phase_id": phase["id"], "phase_kind": phase["kind"], "bar_mode": rule["mode"],
                            "interval_seconds": (finish - begin) * 60, "excluded": excluded, "zero_expected": zero}
            grids[(profile["provider"], profile["dataset"], record["symbol"], record["date"])] = {
                "known": not reasons, "reason_codes": sorted(reasons), "status": record["status"], "slots": slots,
                "expected": {s["interval_end"] for s in slots.values() if s["excluded"] is None},
                "minute_only": all(r["mode"] in {"minutes", "excluded"} for r in profile["phase_rules"])}
    return grids


def coverage_rows(plan, observations, grids):
    indexed = {}
    for row in observations:
        # source_time and mapped phases are confined to the explicit Shanghai day.
        date = datetime.fromisoformat(row["source_time"]).astimezone(SHANGHAI).date().isoformat()
        indexed.setdefault((row["provider"], row["dataset"], row["symbol"], date), []).append(row)
    result = []
    for key, grid in grids.items():
        rows = indexed.get(key, [])
        known, expected = grid["known"], grid["expected"]
        observed = {r["interval_end"] for r in rows if r["interval_end"] in expected}
        usable = {r["interval_end"] for r in rows if r["interval_end"] in expected and not r["reason_codes"] and r["is_complete"] is True}
        counts = Counter(s["excluded"] for s in grid["slots"].values() if s["excluded"])
        phase_rows = []
        for phase in plan["calendar"]["phases"]:
            ends = {s["interval_end"] for s in grid["slots"].values() if s["phase_id"] == phase["id"] and not s["excluded"]}
            phase_rows.append({"phase_id": phase["id"], "expected_records": len(ends) if known else None,
                               "observed_records": len(ends & observed) if known else None,
                               "usable_records": len(ends & usable) if known else None})
        result.append({"provider": key[0], "dataset": key[1], "symbol": key[2], "date": key[3],
            "security_status": grid["status"], "observations": len(rows), "denominator_known": known,
            "coverage_basis": "explicit_phase_records_after_evidenced_exclusions",
            "expected_records": len(expected) if known else None,
            "observed_unique_records": len(observed) if known else None, "usable_unique_records": len(usable) if known else None,
            "observed_coverage": len(observed) / len(expected) if known and expected else None,
            "coverage": len(usable) / len(expected) if known and expected else None,
            "missing_interval_ends": sorted(expected - observed) if known else None,
            "excluded_records": dict(counts) if known else None, "phases": phase_rows, "reason_codes": grid["reason_codes"],
            # Legacy UI minute totals are meaningful only for one-minute records.
            "expected_minutes": len(expected) if known and grid["minute_only"] and not counts else None,
            "observed_unique_minutes": len(observed) if known and grid["minute_only"] and not counts else None,
            "usable_unique_minutes": len(usable) if known and grid["minute_only"] and not counts else None})
    return result
