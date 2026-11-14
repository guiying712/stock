"""Bounded, explicit data/channel PoCs; reports never authorize live alerts."""
from datetime import datetime, timezone
from decimal import Decimal
import os
from time import monotonic
from zoneinfo import ZoneInfo

from .config import validate_config
from .contracts import fields, integer, numeric, string, utc
from .engine import evaluate
from .providers import validate_batch
from .store import digest


CAPABILITIES = ("instruments", "calendar", "memberships", "daily_bars",
                "minute_history", "adjustment_factors", "minute_quotes")
PLAN_KEYS = ("schema_version", "id", "purpose", "provider_name", "authorization",
             "declared_capabilities", "expected_boards", "expected_instrument_count",
             "minimum_coverage", "minimum_sector_coverage", "minimum_trading_dates",
             "max_batches", "sample_times")


def validate_provider_plan(plan):
    fields(plan, PLAN_KEYS, "数据PoC计划")
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1 or plan["purpose"] not in ("fixture", "experimental"):
        raise ValueError("数据PoC版本或用途无效")
    for key in ("id", "provider_name"):
        string(plan[key], key)
    fields(plan["authorization"], ("confirmed", "reference"), "授权声明")
    if type(plan["authorization"]["confirmed"]) is not bool:
        raise ValueError("授权确认必须为布尔值")
    reference = plan["authorization"]["reference"]
    if reference is not None:
        string(reference, "授权证据编号")
    if plan["authorization"]["confirmed"] and reference is None:
        raise ValueError("确认授权须提供本地证据编号，不填写凭据")
    fields(plan["declared_capabilities"], CAPABILITIES, "数据能力声明")
    if any(value not in ("available", "unavailable", "unknown") for value in plan["declared_capabilities"].values()):
        raise ValueError("能力须显式声明available/unavailable/unknown")
    boards = plan["expected_boards"]
    if not isinstance(boards, list) or not boards or any(b not in ("MAIN", "CHINEXT", "STAR") for b in boards) or len(set(boards)) != len(boards):
        raise ValueError("PoC股票板块无效或重复")
    if plan["expected_instrument_count"] is not None:
        integer(plan["expected_instrument_count"], 1, 100000, "外部股票池分母")
    for key in ("minimum_coverage", "minimum_sector_coverage"):
        numeric(plan[key], key, low=Decimal("0.000001"), high=Decimal(1))
    integer(plan["minimum_trading_dates"], 1, 10000, "最少样本交易日")
    integer(plan["max_batches"], 1, 10000, "最多样本切片")
    if not isinstance(plan["sample_times"], list) or len(plan["sample_times"]) > plan["max_batches"]:
        raise ValueError("网关样本时点须为有界数组")
    times = [utc(value) for value in plan["sample_times"]]
    if times != sorted(set(times)):
        raise ValueError("网关样本时点须递增且无重复")
    return plan


def provider_report(batches, config, plan, transport="jsonl"):
    """Check the supplied sample, never extrapolate it to an entire market."""
    validate_provider_plan(plan)
    validate_config(config)
    if transport not in ("jsonl", "https"):
        raise ValueError("不支持的数据PoC传输")
    if set(config["preferences"]["boards"]) != set(plan["expected_boards"]):
        raise ValueError("PoC板块须与显式策略配置一致")
    simulated = plan["purpose"] == "fixture"
    if not simulated and (config["purpose"] != "experimental" or config["mode"] != "shadow"):
        raise ValueError("真实PoC须使用独立experimental shadow配置")
    if simulated and config["mode"] != "fixture":
        raise ValueError("合成PoC须使用fixture配置")
    seen, samples, dates, state = {}, [], set(), None
    duplicates, correction_count, truncated = 0, 0, False
    witnessed = {key: True for key in CAPABILITIES}
    issues = set()
    last = None
    for index, batch in enumerate(batches):
        if index >= plan["max_batches"]:
            truncated = True
            break
        validate_batch(batch)
        if batch["simulated"] != simulated:
            raise ValueError("PoC用途与数据模拟标记不一致，禁止改写标记")
        fingerprint = digest(batch)
        if batch["snapshot_id"] in seen:
            if seen[batch["snapshot_id"]] != fingerprint:
                correction_count += 1
                issues.add("SNAPSHOT_CONTENT_CONFLICT")
            else:
                duplicates += 1
            continue
        seen[batch["snapshot_id"]] = fingerprint
        instant = utc(batch["as_of"])
        if last is not None and instant <= last:
            issues.add("NON_INCREASING_SAMPLE_TIMES")
        last = instant
        result = evaluate(batch, config, state)
        state = result["state"]
        dates.add(instant.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat())
        present = {"instruments": bool(batch["instruments"]), "calendar": bool(batch["calendar"]["trading_dates"]),
                   "memberships": bool(batch["memberships"]), "daily_bars": bool(batch["daily_bars"]),
                   "minute_history": bool(batch["minute_history"]), "minute_quotes": bool(batch["quotes"]),
                   "adjustment_factors": bool(batch["quotes"]) and all(q["adjustment_factor"] is not None for q in batch["quotes"])}
        for key in CAPABILITIES:
            witnessed[key] = witnessed[key] and present[key]
        quality = result["quality"]
        if quality["status"] != "good":
            issues.add("SAMPLE_QUALITY_PAUSED")
        if quality.get("coverage") is None or Decimal(str(quality["coverage"])) < Decimal(str(plan["minimum_coverage"])):
            issues.add("SAMPLE_COVERAGE_BELOW_TARGET")
        denominator = plan["expected_instrument_count"]
        if denominator is not None and quality["expected_count"] != denominator:
            issues.add("EXTERNAL_UNIVERSE_DENOMINATOR_MISMATCH")
        coverages = [sector.get("coverage") for sector in result["sectors"]]
        if not coverages or any(c is None or Decimal(str(c)) < Decimal(str(plan["minimum_sector_coverage"])) for c in coverages):
            issues.add("SECTOR_COVERAGE_BELOW_TARGET")
        samples.append({"snapshot_id": batch["snapshot_id"], "input_hash": fingerprint,
                        "as_of": batch["as_of"], "quality": quality,
                        "minimum_sector_coverage": min((c for c in coverages if c is not None), default=None)})
    if not samples:
        issues.add("NO_SAMPLES")
        witnessed = {key: False for key in CAPABILITIES}
    if len(dates) < plan["minimum_trading_dates"]:
        issues.add("INSUFFICIENT_TRADING_DATES")
    if plan["expected_instrument_count"] is None:
        issues.add("EXTERNAL_UNIVERSE_DENOMINATOR_UNKNOWN")
    if not plan["authorization"]["confirmed"]:
        issues.add("AUTHORIZATION_NOT_CONFIRMED")
    for key in CAPABILITIES:
        if not witnessed[key] or plan["declared_capabilities"][key] != "available":
            issues.add("CAPABILITY_NOT_ESTABLISHED:" + key)
    from .replay import source_hash
    report = {"schema_version": 1, "kind": "provider_sample_poc", "checked_at": datetime.now(timezone.utc).isoformat(), "code_hash": source_hash(),
              "plan": plan, "plan_hash": digest(plan), "config_hash": digest(config), "transport": transport,
              "simulated": simulated, "status": "sample_checked" if not issues else "incomplete",
              "sample_count": len(samples), "duplicate_count": duplicates, "correction_count": correction_count,
              "sample_limit_reached": truncated, "trading_dates": sorted(dates), "samples": samples,
              "capabilities": {key: {"declared": plan["declared_capabilities"][key], "present_in_every_sample": witnessed[key]} for key in CAPABILITIES},
              "reason_codes": sorted(issues), "full_market_verified": False, "release_allowed": False,
              "limitations": ["字段存在不代表历史深度、历史成分或数据授权已独立核验",
                              "样本覆盖分母另需外部股票池核对，不外推全市场长期可用性",
                              "本报告不证明限流、长期时延、策略效果或连续真实影子验收通过"]}
    report["output_hash"] = digest(report)
    return report


def channel_fingerprint():
    url = os.environ.get("DINGTALK_WEBHOOK")
    return digest([url, os.environ.get("DINGTALK_SECRET")]) if url else None


def channel_report(app, send_test=False):
    """Exactly one explicit connection test, without automatic retry."""
    if type(send_test) is not bool:
        raise ValueError("测试发送开关须为布尔值")
    report = {"schema_version": 1, "kind": "dingtalk_connection_poc", "checked_at": datetime.now(timezone.utc).isoformat(),
              "explicit_test_requested": send_test, "network_requests": 0, "result": None,
              "status": "not_sent", "elapsed_seconds": None, "release_allowed": False,
              "rendering_confirmed": False, "opportunity_path_verified": False,
              "limitations": ["仅显式测试消息，不投递真实机会，不解除live_alert锁定",
                              "受理不表示已读；消息呈现、聚合拆分、真实恢复及平台P95须另行验收",
                              "unknown禁止自动重试，需人工核对群消息"]}
    if send_test:
        if not channel_fingerprint():
            report["status"] = "blocked_missing_configuration"
        else:
            start = monotonic()
            result = app.test_channel()
            report.update(status=result["status"], network_requests=1, result=result, elapsed_seconds=monotonic() - start)
    report["output_hash"] = digest(report)
    return report
