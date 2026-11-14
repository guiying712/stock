"""Offline minute-sample diagnostics. No network, database or strategy input output."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from itertools import combinations
from pathlib import Path
import re

from . import __version__
from .contracts import day, fields, integer, numeric, string, utc
from .replay import source_hash
from .store import digest, now
from .vendor_samples import DATASETS, SHANGHAI, _bar, _decode_response, _read_probe, _rows, validate_sample_plan
from .minute_grid import build_grids, coverage_rows, validate_grid


MINUTE_DATASETS = {"minute_history", "minute_quotes", "intraday"}
PROFILE_FIELDS = ("provider", "dataset", "timestamp_label", "timestamp_timezone", "completion", "volume_unit", "amount_unit",
                  "turnover_mode", "adjustment", "max_observation_delay_seconds", "evidence")
EVIDENCE_FIELDS = ("timestamp", "completion", "units", "turnover", "adjustment")
PRICE_FIELDS = ("open", "high", "low", "close")


def validate_quality_plan(value):
    version = value.get("schema_version") if isinstance(value, dict) else None
    if type(version) is not int or version not in {1, 2}:
        raise ValueError("分钟诊断只支持显式schema1或schema2")
    fields(value, ("schema_version", "id", "purpose", "symbols", "calendar", "profiles") +
           (("security_days",) if version == 2 else ()), "分钟诊断计划")
    if value["purpose"] != "experimental":
        raise ValueError("分钟诊断只支持experimental用途")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", string(value["id"], "诊断计划ID")):
        raise ValueError("分钟诊断计划ID无效")
    # Reuse the sample contract's code, leading-zero and board checks.
    validate_sample_plan({"schema_version": 1, "id": value["id"], "purpose": "experimental", "provider": "tickflow",
        "authorization": {"confirmed": False, "reference": None}, "symbols": value["symbols"], "datasets": ["minute_history"],
        "start_date": "2000-01-01", "end_date": "2000-01-01", "request_interval_seconds": "6.1",
        "request_timeout_seconds": 15, "max_requests": 5})
    calendar = value["calendar"]
    fields(calendar, ("version", "evidence", "dates", "sessions" if version == 1 else "phases"), "诊断交易日历")
    if (calendar["version"] is None) != (calendar["evidence"] is None):
        raise ValueError("交易日历版本与依据须同时提供或同时保持null")
    for key in ("version", "evidence"):
        if calendar[key] is not None:
            string(calendar[key], "日历" + key)
    dates = calendar["dates"]
    if not isinstance(dates, list) or not 1 <= len(dates) <= 7 or any(not isinstance(d, str) for d in dates):
        raise ValueError("诊断须显式选择1至7个候选日期")
    parsed = [day(d) for d in dates]
    if parsed != sorted(set(parsed)) or (parsed[-1] - parsed[0]).days > 6:
        raise ValueError("候选日期须唯一有序且在7个自然日内")
    sessions = calendar.get("sessions", [])
    if version == 1 and (not isinstance(sessions, list) or not 1 <= len(sessions) <= 4):
        raise ValueError("诊断须显式提供同日连续竞价时段")
    previous = -1
    for session in sessions:
        if not isinstance(session, list) or len(session) != 2 or any(not isinstance(t, str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", t) for t in session):
            raise ValueError("时段需要HH:MM起止时间")
        start, end = [_minute_number(t) for t in session]
        if not previous <= start < end:
            raise ValueError("连续竞价时段须有序、不重叠且不跨日")
        previous = end
    profiles = value["profiles"]
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= 4:
        raise ValueError("分钟诊断需要1至4个显式接口口径")
    seen = set()
    choices = {"timestamp_label": {"unknown", "start", "end"}, "timestamp_timezone": {"unknown", "UTC", "Asia/Shanghai"},
               "completion": {"unknown", "provider_closed"},
               "volume_unit": {"unknown", "shares", "lots_100"}, "amount_unit": {"unknown", "CNY", "thousand_CNY"},
               "turnover_mode": {"unknown", "interval", "cumulative"}, "adjustment": {"unknown", "none"}}
    for profile in profiles:
        fields(profile, PROFILE_FIELDS + (("phase_rules", "no_trade_policy") if version == 2 else ()), "接口口径")
        provider, dataset = profile["provider"], profile["dataset"]
        if not isinstance(provider, str) or provider not in {"tickflow", "tushare", "sina_public", "eastmoney_public"} or not isinstance(dataset, str) or dataset not in (DATASETS[provider] & MINUTE_DATASETS):
            raise ValueError("分钟接口须选择受支持的供应商及对应数据集")
        if (provider, dataset) in seen:
            raise ValueError("分钟接口口径不得重复")
        seen.add((provider, dataset))
        for key, allowed in choices.items():
            if not isinstance(profile[key], str) or profile[key] not in allowed:
                raise ValueError("接口口径" + key + "无效")
        if profile["timestamp_timezone"] not in {"unknown", "UTC" if provider == "tickflow" else "Asia/Shanghai"}:
            raise ValueError("时间标签时区与原始端点格式不一致")
        evidence = profile["evidence"]
        fields(evidence, EVIDENCE_FIELDS, "接口口径依据")
        for key in EVIDENCE_FIELDS:
            if evidence[key] is not None:
                string(evidence[key], "接口依据" + key)
        required = {"timestamp": profile["timestamp_label"] != "unknown" or profile["timestamp_timezone"] != "unknown", "completion": profile["completion"] != "unknown",
                    "units": profile["volume_unit"] != "unknown" or profile["amount_unit"] != "unknown",
                    "turnover": profile["turnover_mode"] != "unknown", "adjustment": profile["adjustment"] != "unknown"}
        if any(needed and evidence[key] is None for key, needed in required.items()):
            raise ValueError("已确认的接口口径必须提供相应依据；不得从字段名称或时间经过推断")
        if profile["max_observation_delay_seconds"] is not None:
            integer(profile["max_observation_delay_seconds"], 0, 86400, "观测延迟预算")
    if version == 2:
        validate_grid(value)
        build_grids(value)  # Reject colliding source labels before reading samples.
    return value


def _minute_number(value):
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def _expected_ends(calendar):
    result = {}
    for date in calendar["dates"]:
        midnight = datetime.combine(day(date), datetime.min.time(), SHANGHAI)
        result[date] = { (midnight + timedelta(minutes=m)).astimezone(timezone.utc).isoformat()
            for start, end in calendar["sessions"] for m in range(_minute_number(start) + 1, _minute_number(end) + 1) }
    return result


def _profile_reasons(profile):
    checks = (("timestamp_label", "TIME_LABEL_SEMANTICS_UNCONFIRMED"), ("timestamp_timezone", "TIMEZONE_UNCONFIRMED"),
              ("completion", "MINUTE_COMPLETION_UNCONFIRMED"),
              ("volume_unit", "VOLUME_UNIT_UNCONFIRMED"), ("amount_unit", "AMOUNT_UNIT_UNCONFIRMED"),
              ("turnover_mode", "TURNOVER_MODE_UNCONFIRMED"), ("adjustment", "ADJUSTMENT_UNCONFIRMED"))
    return [reason for key, reason in checks if profile[key] == "unknown"]


def _observation(bar, profile, reference, expected, grids=None):
    reasons = set(_profile_reasons(profile))
    reasons.update(r for r in bar["reason_codes"] if r in {"OHLC_UNKNOWN_OR_NONPOSITIVE", "OHLC_INCONSISTENT", "TURNOVER_UNKNOWN"})
    source = utc(bar["source_time"])
    if source.second or source.microsecond:
        reasons.add("TIME_LABEL_NOT_MINUTE_ALIGNED")
    end = None if profile["timestamp_label"] == "unknown" or profile["timestamp_timezone"] == "unknown" else source + timedelta(minutes=profile["timestamp_label"] == "start")
    date = (end or source).astimezone(SHANGHAI).date().isoformat()
    if date not in expected:
        reasons.add("DATE_OUTSIDE_DIAGNOSTIC_WINDOW")
    end_text = end.isoformat() if end else None
    slot = None
    if grids is not None:
        reasons.discard("DATE_OUTSIDE_DIAGNOSTIC_WINDOW")
        date = source.astimezone(SHANGHAI).date().isoformat()
        grid = grids.get((bar["provider"], bar["dataset"], bar["symbol"], date))
        end = end_text = None
        if grid is None:
            reasons.add("DATE_OUTSIDE_DIAGNOSTIC_WINDOW")
        else:
            reasons.update(grid["reason_codes"])
            if profile["timestamp_label"] != "unknown" and profile["timestamp_timezone"] != "unknown":
                slot = grid["slots"].get(source.isoformat())
                if slot:
                    end_text = slot["interval_end"]
                    end = utc(end_text)
                    if slot["excluded"]:
                        reasons.add("OBSERVATION_IN_EXCLUDED_INTERVAL")
                else:
                    reasons.add("OBSERVATION_OUTSIDE_REVIEWED_GRID")
    elif end and date in expected and end_text not in expected[date]:
        reasons.add("OUTSIDE_CONTINUOUS_SESSION")
    received = utc(bar["available_at"])
    if source > received:
        reasons.add("SOURCE_LABEL_AFTER_OBSERVATION")
    complete = None
    if end and profile["completion"] == "provider_closed":
        complete = received >= end
        if not complete:
            reasons.add("MINUTE_NOT_CLOSED_AT_OBSERVATION")
    delay = (received - end) / timedelta(seconds=1) if end else None
    budget = profile["max_observation_delay_seconds"]
    if delay is not None and budget is not None and delay > budget:
        reasons.add("OBSERVED_AFTER_DELAY_BUDGET")
    raw_volume = numeric(bar["volume_raw"], "原始量", nullable=True)
    raw_amount = numeric(bar["amount_raw"], "原始额", nullable=True)
    volume_scale = {"shares": Decimal(1), "lots_100": Decimal(100)}.get(profile["volume_unit"])
    amount_scale = {"CNY": Decimal(1), "thousand_CNY": Decimal(1000)}.get(profile["amount_unit"])
    # The ambient Decimal context must not round high precision source values.
    with localcontext() as context:
        values = [raw_volume, raw_amount] + [None if bar["prices"][k] is None else Decimal(bar["prices"][k]) for k in PRICE_FIELDS]
        context.prec = max(50, sum(len(v.as_tuple().digits) for v in values if v is not None) + 12)
        volume = raw_volume * volume_scale if raw_volume is not None and volume_scale is not None else None
        amount = raw_amount * amount_scale if raw_amount is not None and amount_scale is not None else None
        if slot and slot["zero_expected"]:
            if profile["turnover_mode"] != "interval":
                reasons.add("NO_TRADE_INCREMENT_UNVERIFIED")
            elif raw_volume is not None and raw_amount is not None and (raw_volume != 0 or raw_amount != 0):
                reasons.add("NO_TRADE_EVIDENCE_CONFLICT")
        if volume is not None and amount is not None and profile["turnover_mode"] == "interval":
            if (volume == 0) != (amount == 0):
                reasons.add("ZERO_VOLUME_AMOUNT_CONFLICT")
            if volume and amount and all(bar["prices"][k] is not None for k in ("low", "high")):
                # Multiplication avoids rounding a VWAP division at a price boundary.
                if not Decimal(bar["prices"]["low"]) * volume <= amount <= Decimal(bar["prices"]["high"]) * volume:
                    reasons.add("INTERVAL_TURNOVER_OUTSIDE_PRICE_RANGE")
    result = dict(reference, provider=bar["provider"], dataset=bar["dataset"], symbol=bar["symbol"], source_time=bar["source_time"],
                interval_end=end_text, observed_at=bar["available_at"], source_available_at=None,
                availability_basis="first_observed_not_historical_publication", is_complete=complete,
                observed_delay_seconds=delay, prices=bar["prices"], volume_raw=bar["volume_raw"], amount_raw=bar["amount_raw"],
                volume_shares=None if volume is None else str(volume), amount_cny=None if amount is None else str(amount),
                diagnostic_volume_scales_assuming_amount_cny=bar["diagnostic_volume_scales_assuming_amount_cny"],
                reason_codes=sorted(reasons))
    if grids is not None:
        result.update({key: slot[key] if slot else None for key in
                       ("interval_start", "phase_id", "phase_kind", "bar_mode", "interval_seconds")})
    return result


def _fingerprint(row):
    return tuple(None if v is None else Decimal(v) for v in [*(row["prices"][k] for k in PRICE_FIELDS), row["volume_raw"], row["amount_raw"]])


def _repeats(observations):
    groups = defaultdict(list)
    for index, row in enumerate(observations):
        groups[(row["provider"], row["dataset"], row["symbol"], row["source_time"])].append(index)
    repeated, conflicts, duplicates = [], [], []
    for key, indices in sorted(groups.items()):
        if len(indices) < 2:
            continue
        item = {"provider": key[0], "dataset": key[1], "symbol": key[2], "source_time": key[3], "observation_indices": indices}
        same_response = len({(observations[i]["sample_hash"], observations[i]["raw_file"]) for i in indices}) < len(indices)
        conflict = len({_fingerprint(observations[i]) for i in indices}) > 1
        if same_response:
            duplicates.append(item)
        if conflict:
            conflicts.append(item)
        if not same_response and not conflict:
            repeated.append(item)
        for i in indices:
            observations[i]["reason_codes"] = sorted(set(observations[i]["reason_codes"]) |
                ({"DUPLICATE_MINUTE_LABEL"} if same_response else set()) | ({"REVISION_CONFLICT"} if conflict else set()))
    return repeated, conflicts, duplicates


def _coverage(plan, observations, expected):
    result = []
    verified = plan["calendar"]["evidence"] is not None
    for profile in plan["profiles"]:
        for symbol in plan["symbols"]:
            for date in plan["calendar"]["dates"]:
                # Compare by Shanghai day, never the UTC date prefix at a day boundary.
                rows = [r for r in observations if (r["provider"], r["dataset"], r["symbol"]) ==
                        (profile["provider"], profile["dataset"], symbol["symbol"]) and
                        utc(r["interval_end"] or r["source_time"]).astimezone(SHANGHAI).date().isoformat() == date]
                known = verified and profile["timestamp_label"] != "unknown" and profile["timestamp_timezone"] != "unknown"
                observed = {r["interval_end"] for r in rows if r["interval_end"] in expected[date]}
                usable = {r["interval_end"] for r in rows if r["interval_end"] in expected[date] and not r["reason_codes"] and r["is_complete"] is True}
                result.append({"provider": profile["provider"], "dataset": profile["dataset"], "symbol": symbol["symbol"], "date": date,
                    "observations": len(rows), "expected_minutes": len(expected[date]) if known else None,
                    "observed_unique_minutes": len(observed) if known else None, "usable_unique_minutes": len(usable) if known else None,
                    "coverage": len(usable) / len(expected[date]) if known else None,
                    "missing_interval_ends": sorted(expected[date] - observed) if known else None})
    return result


def _comparisons(profiles, observations):
    result = []
    blockers = {"TIME_LABEL_SEMANTICS_UNCONFIRMED", "TIMEZONE_UNCONFIRMED", "MINUTE_COMPLETION_UNCONFIRMED", "ADJUSTMENT_UNCONFIRMED",
                "TIME_LABEL_NOT_MINUTE_ALIGNED", "DATE_OUTSIDE_DIAGNOSTIC_WINDOW", "OUTSIDE_CONTINUOUS_SESSION",
                "MINUTE_NOT_CLOSED_AT_OBSERVATION", "SOURCE_LABEL_AFTER_OBSERVATION", "OHLC_UNKNOWN_OR_NONPOSITIVE", "OHLC_INCONSISTENT",
                "REVISION_CONFLICT", "DUPLICATE_MINUTE_LABEL"}
    blockers.update({"CALENDAR_UNVERIFIED", "GRID_TIME_SEMANTICS_UNCONFIRMED", "SECURITY_DAY_UNCONFIRMED",
                     "NO_TRADE_POLICY_UNCONFIRMED", "PHASE_RULE_UNCONFIRMED", "PARTIAL_BAR_EXCEPTION",
                     "OBSERVATION_IN_EXCLUDED_INTERVAL", "OBSERVATION_OUTSIDE_REVIEWED_GRID", "NO_TRADE_EVIDENCE_CONFLICT",
                     "NO_TRADE_INCREMENT_UNVERIFIED"})
    for left, right in combinations(profiles, 2):
        def indexed(profile):
            rows = sorted((r for r in observations if (r["provider"], r["dataset"]) == (profile["provider"], profile["dataset"])),
                          key=lambda r: (r["observed_at"], r["sample_hash"], r["row_index"]))
            index = {}
            for row in rows:
                if row["interval_end"] and row["is_complete"] is True and not set(row["reason_codes"]) & blockers:
                    start = row.get("interval_start") or (utc(row["interval_end"]) - timedelta(minutes=1)).isoformat()
                    index.setdefault((row["symbol"], start, row["interval_end"], row.get("phase_kind", "continuous")), row)
            return index
        a, b = indexed(left), indexed(right)
        common = sorted(a.keys() & b.keys())
        comparisons = []
        for key in common:
            x, y = a[key], b[key]
            differences, unknown = [], []
            for field in (*PRICE_FIELDS, "volume_shares", "amount_cny"):
                xv = x["prices"][field] if field in PRICE_FIELDS else x[field]
                yv = y["prices"][field] if field in PRICE_FIELDS else y[field]
                if xv is None or yv is None or (field not in PRICE_FIELDS and (left["turnover_mode"] == "unknown" or left["turnover_mode"] != right["turnover_mode"])):
                    unknown.append(field)
                elif Decimal(xv) != Decimal(yv):
                    differences.append({"field": field, "left": xv, "right": yv})
            item = {"symbol": key[0], "interval_end": key[2], "differences": differences, "unknown_fields": unknown}
            if "interval_start" in x or "interval_start" in y:
                item.update(interval_start=key[1], phase_kind=key[3])
            comparisons.append(item)
        semantics_known = all(p["timestamp_label"] != "unknown" and p["timestamp_timezone"] != "unknown" and p["completion"] != "unknown" and p["adjustment"] != "unknown" for p in (left, right))
        result.append({"left": [left["provider"], left["dataset"]], "right": [right["provider"], right["dataset"]],
                       "type": "same_provider_endpoints" if left["provider"] == right["provider"] else "cross_provider",
                       "status": "compared" if common else "no_overlap" if semantics_known else "blocked_semantics",
                       "common_minutes": len(common), "comparisons": comparisons,
                       "turnover_basis_comparable": left["turnover_mode"] != "unknown" and left["turnover_mode"] == right["turnover_mode"],
                       "underlying_source_independence": "unverified"})
        if "phase_rules" in left:
            result[-1].update(common_records=len(common),
                common_minutes=sum(utc(key[2]) - utc(key[1]) == timedelta(minutes=1) for key in common))
    return result


def minute_quality_report(value, sample_dirs=()):
    """Re-read hashed raw responses; keep duplicate/revised rows that projection rejected."""
    plan = validate_quality_plan(value)
    sample_dirs = list(sample_dirs)
    if len(sample_dirs) > 8:
        raise ValueError("每次分钟诊断最多读取8份采样目录")
    code_hash = source_hash()
    profiles = {(p["provider"], p["dataset"]): p for p in plan["profiles"]}
    symbols = {s["symbol"] for s in plan["symbols"]}
    grids = build_grids(plan) if plan["schema_version"] == 2 else None
    expected = _expected_ends(plan["calendar"]) if grids is None else {}
    observations, capture_issues, samples, ignored = [], [], [], 0
    seen = set()
    for directory in sample_dirs:
        sample, _ = _read_probe(directory)
        if sample["output_hash"] in seen:
            raise ValueError("同一份样本报告不得重复计入诊断")
        seen.add(sample["output_hash"])
        samples.append({"hash": sample["output_hash"], "provider": sample["provider"], "code_hash": sample["code_hash"],
                        "started_at": sample["started_at"], "completed_at": sample["completed_at"], "status": sample["status"]})
        for request_index, record in enumerate(sample["requests"]):
            key = sample["provider"], record["dataset"]
            if record["dataset"] not in MINUTE_DATASETS:
                ignored += 1
                continue
            if key not in profiles:
                raise ValueError("分钟样本接口缺少显式口径；请补充诊断计划")
            if not record["raw_file"]:
                capture_issues.append({"sample_hash": sample["output_hash"], "request_index": request_index,
                                       "reason_code": "MINUTE_RESPONSE_NOT_CAPTURED"})
                continue
            if record["reason_code"] == "POSSIBLE_RESPONSE_TRUNCATION":
                capture_issues.append({"sample_hash": sample["output_hash"], "request_index": request_index,
                                       "reason_code": "POSSIBLE_RESPONSE_TRUNCATION"})
            raw = (Path(directory) / record["raw_file"]).read_bytes()
            try:
                rows = _rows(_decode_response(raw, sample["provider"]), sample["provider"], record)
            except (ValueError, TypeError, KeyError):
                capture_issues.append({"sample_hash": sample["output_hash"], "request_index": request_index,
                                       "reason_code": "RAW_MINUTE_RESPONSE_INVALID"})
                continue
            if len(observations) + len(rows) > 100000:
                raise ValueError("分钟诊断超过100000行上限；请缩小样本，不截断后继续")
            if not rows:
                capture_issues.append({"sample_hash": sample["output_hash"], "request_index": request_index, "reason_code": "NO_MINUTE_ROWS"})
            for row_index, row in enumerate(rows):
                reference = {"sample_hash": sample["output_hash"], "raw_file": record["raw_file"],
                             "raw_sha256": record["raw_sha256"], "row_index": row_index}
                try:
                    bar = _bar(row, sample["provider"], record, record["received_at"], record["raw_file"], None)
                    if bar["symbol"] not in symbols or (record["symbol"] and bar["symbol"] != record["symbol"]):
                        raise ValueError("UNEXPECTED_SYMBOL")
                    if record["dataset"] == "minute_history" and not sample["plan"]["start_date"] <= bar["label"][:10] <= sample["plan"]["end_date"]:
                        raise ValueError("PERIOD_OUTSIDE_REQUESTED_WINDOW")
                    observation = _observation(bar, profiles[key], reference, expected, grids)
                    observations.append(observation)
                except (ValueError, TypeError, KeyError, ArithmeticError):
                    capture_issues.append(dict(reference, reason_code="RAW_MINUTE_ROW_INVALID"))
    repeated, conflicts, duplicates = _repeats(observations)
    # A cumulative day series cannot reset at lunch. Do not compare it to minute OHLC/VWAP.
    cumulative = defaultdict(list)
    for row in observations:
        if profiles[(row["provider"], row["dataset"])]["turnover_mode"] == "cumulative" and row["interval_end"]:
            cumulative[(row["provider"], row["dataset"], row["symbol"], utc(row["interval_end"]).astimezone(SHANGHAI).date())].append(row)
    for rows in cumulative.values():
        previous = None
        for row in sorted(rows, key=lambda r: (r["interval_end"], r["observed_at"])):
            values = [numeric(row[k], k, nullable=True) for k in ("volume_shares", "amount_cny")]
            if previous and any(v is not None and p is not None and v < p for v, p in zip(values, previous)):
                row["reason_codes"] = sorted(set(row["reason_codes"]) | {"CUMULATIVE_TURNOVER_DECREASE"})
            previous = values
    coverage = _coverage(plan, observations, expected) if grids is None else coverage_rows(plan, observations, grids)
    comparisons = _comparisons(plan["profiles"], observations)
    reasons = {reason for profile in plan["profiles"] for reason in _profile_reasons(profile)}
    reasons.update(reason for row in observations for reason in row["reason_codes"])
    reasons.update(issue["reason_code"] for issue in capture_issues)
    reasons.update(reason for row in coverage for reason in row.get("reason_codes", []))
    if plan["calendar"]["evidence"] is None:
        reasons.add("CALENDAR_UNVERIFIED")
    if not observations:
        reasons.add("NO_MINUTE_SAMPLES")
    if any(c["observations"] == 0 and c.get("expected_records", c["expected_minutes"]) != 0 for c in coverage):
        reasons.add("REQUESTED_MINUTE_SERIES_MISSING")
    if any(c["missing_interval_ends"] for c in coverage):
        reasons.add("MINUTE_GAPS")
    if any(item["differences"] for pair in comparisons for item in pair["comparisons"]):
        reasons.add("ALIGNED_MINUTE_VALUES_DIFFER")
    if any(pair.get("common_records", pair["common_minutes"]) and not pair["turnover_basis_comparable"] for pair in comparisons):
        reasons.add("TURNOVER_BASES_NOT_COMPARABLE")
    if source_hash() != code_hash:
        reasons.add("CODE_CHANGED_DURING_DIAGNOSTIC")
    report = {"schema_version": plan["schema_version"], "kind": "vendor_minute_quality", "software_version": __version__, "code_hash": code_hash,
              "created_at": now(), "plan": plan, "plan_hash": digest(plan), "samples": samples,
              "scope": "explicit_small_sample", "status": "no_minute_samples" if not observations else "issues_found" if reasons else "checks_passed",
              "minute_checks_passed": not reasons, "contract_basis": "explicit_review_references_not_automatic_vendor_verification",
              "calendar_basis": "explicit_version_and_reference_required", "delay_basis": "first_observed_delay_not_historical_or_platform_latency",
              "observation_count": len(observations), "observations": observations, "ignored_nonminute_requests": ignored,
              "capture_issues": capture_issues, "coverage": coverage, "identical_reobservations": repeated,
              "duplicate_minutes": duplicates, "revision_conflicts": conflicts, "comparisons": comparisons,
              "reason_codes": sorted(reasons), "cross_source_verified": False, "strategy_input_ready": False, "full_market_verified": False, "release_allowed": False,
              "remaining_strategy_inputs": ["historical_publication_times", "security_risk_status", "historical_memberships",
                                            "adjustment_factors", "benchmark", "complete_standard_batch", "market_data_rights"]}
    report["output_hash"] = digest(report)
    return report
