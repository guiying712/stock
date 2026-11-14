"""Read-only history of local capture requests and reviewed minute coverage."""
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from .contracts import load_json, utc
from .minute_quality import validate_quality_plan
from .store import digest
from .vendor_samples import _read_probe_report


CAPTURES_PER_DIRECTORY = 24
QUALITY_REPORTS = 8
SHANGHAI = ZoneInfo("Asia/Shanghai")
REQUEST_OUTCOMES = {"captured", "partial", "empty", "failed"}
DISPLAY_REASONS = {
    "RATE_LIMITED", "TRANSPORT_ERROR", "AUTHENTICATION_FAILED", "PERMISSION_DENIED",
    "HTTP_ERROR", "VENDOR_PERMISSION_DENIED", "VENDOR_API_ERROR", "FUYAO_API_ERROR",
    "NO_ROWS", "REQUESTED_SYMBOLS_MISSING", "EMPTY_SYMBOL_GROUPS", "PARTIAL_PUBLIC_SNAPSHOT",
    "POSSIBLE_RESPONSE_TRUNCATION", "RESPONSE_TOO_LARGE", "RESPONSE_DATA_INVALID",
    "SENSITIVE_RESPONSE_SUPPRESSED",
}


def _recent(root, limit, *, captures):
    if root.is_symlink() or not root.is_dir():
        return [], 0
    candidates = []
    for path in root.iterdir():
        if path.is_symlink():
            continue
        report = path / "report.json" if captures else path
        if (not captures and report.suffix != ".json") or report.is_symlink() or not report.is_file():
            continue
        try:
            candidates.append((report.stat().st_mtime_ns, path))
        except FileNotFoundError:
            continue
    candidates.sort(reverse=True)
    return [path for _, path in candidates[:limit]], max(0, len(candidates) - limit)


def _request_rows(report):
    rows = []
    for record in report["requests"]:
        if record.get("started_at") is None:
            continue
        started = utc(record["started_at"])
        received = utc(record["received_at"]) if record.get("received_at") is not None else None
        outcome = record["status"]
        if outcome not in REQUEST_OUTCOMES or (received is not None and received < started):
            raise ValueError("请求结果或时点无效")
        if outcome == "captured" and received is None:
            raise ValueError("成功请求缺接收时间")
        reason = record.get("reason_code")
        reason = reason if reason in DISPLAY_REASONS else "OTHER_CAPTURE_ISSUE" if reason else None
        op = record["operation"]
        rows.append({
            "dataset": record["dataset"], "operation": urlsplit(op).path if op.startswith("https://") else op,
            "started_at": started, "received_at": received, "status": outcome, "reason_code": reason,
            "limited": reason == "RATE_LIMITED" or record.get("http_status") == 429,
            "report_hash": report["output_hash"],
        })
    if type(report["simulated"]) is not bool or report["sent_requests"] != len(rows):
        raise ValueError("采样请求分母或模式无效")
    return rows


def _quality_projection(report, captures):
    if (type(report.get("schema_version")) is not int or report["schema_version"] not in {1, 2} or report.get("kind") != "vendor_minute_quality"
            or report.get("output_hash") != digest({k: v for k, v in report.items() if k != "output_hash"})):
        raise ValueError("分钟诊断报告无效")
    plan = validate_quality_plan(report["plan"])
    if plan["schema_version"] != report["schema_version"]:
        raise ValueError("分钟诊断计划与报告版本不一致")
    if report["plan_hash"] != digest(plan):
        raise ValueError("分钟诊断计划哈希不一致")
    created = utc(report["created_at"])
    samples = [item["hash"] for item in report["samples"]]
    if not samples or len(samples) != len(set(samples)) or any(sha not in captures for sha in samples):
        return {}
    modes = {captures[sha][0] for sha in samples}
    if len(modes) != 1:
        return {}
    simulated = modes.pop()
    linked = {key for sha in samples for key in captures[sha][1]}
    profiles = {(p["provider"], p["dataset"]): p for p in plan["profiles"]}
    by_dataset = defaultdict(list)
    for row in report["coverage"]:
        key = row["provider"], row["dataset"]
        if key in profiles and key in linked:
            by_dataset[key].append(row)
    # Latest quote observations have a meaningful first-observed delay. A
    # later history or full-session download is never a real-time delay sample.
    first = defaultdict(dict)
    for row in report["observations"]:
        key = row["provider"], row["dataset"]
        if (key not in by_dataset or key[1] != "minute_quotes" or row["sample_hash"] not in samples
                or key not in captures[row["sample_hash"]][1]
                or row["is_complete"] is not True or not row["interval_end"]
                or set(row["reason_codes"]) - {"OBSERVED_AFTER_DELAY_BUDGET"}):
            continue
        end, observed = utc(row["interval_end"]), utc(row["observed_at"])
        if observed >= end and observed.astimezone(SHANGHAI).date() == end.astimezone(SHANGHAI).date():
            ident = row["symbol"], end
            first[key][ident] = min(observed, first[key].get(ident, observed))
    result = {}
    for key, rows in by_dataset.items():
        known = all(type(r["expected_minutes"]) is int and type(r["usable_unique_minutes"]) is int
                    and 0 <= r["usable_unique_minutes"] <= r["expected_minutes"] <= 1440 for r in rows)
        expected = sum(r["expected_minutes"] for r in rows) if known else None
        usable = sum(r["usable_unique_minutes"] for r in rows) if known else None
        delays = [(seen - end).total_seconds() for (_, end), seen in first[key].items()]
        budget = profiles[key]["max_observation_delay_seconds"]
        result[(*key, simulated)] = {
            "at": created.isoformat(), "report_hash": report["output_hash"],
            "expected_minutes": expected, "usable_minutes": usable,
            "coverage": usable / expected if expected else None,
            "delay_observations": len(delays), "max_observed_delay_seconds": max(delays, default=None),
            "delay_budget_seconds": budget,
            "late_count": sum(d > budget for d in delays) if budget is not None and delays else None,
        }
        if report["schema_version"] == 2:
            record_known = all(type(r["expected_records"]) is int and type(r["usable_unique_records"]) is int
                               and 0 <= r["usable_unique_records"] <= r["expected_records"] <= 1440 for r in rows)
            record_count = sum(r["expected_records"] for r in rows) if record_known else None
            usable_records = sum(r["usable_unique_records"] for r in rows) if record_known else None
            result[(*key, simulated)].update(diagnostic_schema_version=2, expected_records=record_count,
                usable_records=usable_records, record_coverage=usable_records / record_count if record_count else None,
                coverage_basis="explicit_phase_records_after_evidenced_exclusions")
    return result


def source_health(directory):
    """Group attempted requests by provider, operation, dataset and sample mode."""
    directory = Path(directory)
    groups = defaultdict(list)
    captures = {}
    ignored = omitted = 0
    for name in ("minute-data", "source-samples"):
        paths, older = _recent(directory / name, CAPTURES_PER_DIRECTORY, captures=True)
        omitted += older
        for path in paths:
            try:
                report = _read_probe_report(path)
                sha = report["output_hash"]
                if sha in captures:
                    continue
                rows = _request_rows(report)
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                ignored += 1
                continue
            provider, simulated = report["provider"], report["simulated"]
            captures[sha] = simulated, {(provider, row["dataset"]) for row in rows}
            for row in rows:
                groups[(provider, row["dataset"], row["operation"], simulated)].append(row)
    quality = {}
    paths, older = _recent(directory / "source-quality", QUALITY_REPORTS, captures=False)
    for path in paths:
        try:
            if path.stat().st_size > 16 * 1024 * 1024:
                raise ValueError("分钟诊断过大")
            for key, result in _quality_projection(load_json(path), captures).items():
                if key not in quality or utc(result["at"]) > utc(quality[key]["at"]):
                    quality[key] = result
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            ignored += 1
    items = []
    for (provider, dataset, operation, simulated), rows in sorted(groups.items()):
        ordered = sorted(rows, key=lambda row: (row["started_at"], row["report_hash"]), reverse=True)
        counts = Counter(row["status"] for row in rows)
        successes = [row["received_at"] for row in rows if row["status"] == "captured"]
        last_success = max(successes, default=None)
        recent = [{**row, "started_at": row["started_at"].isoformat(),
                   "received_at": row["received_at"].isoformat() if row["received_at"] else None} for row in ordered[:5]]
        items.append({
            "provider": provider, "dataset": dataset, "operation": operation, "simulated": simulated,
            "attempt_count": len(rows), "status_counts": dict(counts), "limited_count": sum(row["limited"] for row in rows),
            "last_success_at": last_success.isoformat() if last_success else None,
            "latest_status": ordered[0]["status"], "recent": recent,
            "minute_quality": quality.get((provider, dataset, simulated)),
        })
    return {"items": items, "capture_count": len(captures), "ignored_count": ignored,
            "older_capture_count": omitted, "older_quality_count": older}
