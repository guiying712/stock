"""Compile a bounded Tushare acceptance campaign without credentials or HTTP."""
from copy import deepcopy
from pathlib import Path
import re

from . import __version__
from .contracts import day, fields, integer, string, utc, write_new_json
from .store import digest, now
from .vendor_samples import SHANGHAI, request_specs, validate_sample_plan


STAGES = (("latest", "minute_quotes", "A股分钟RT"), ("session", "intraday", "A股分钟RT"),
          ("history", "minute_history", "A股历史分钟"), ("daily", "daily_bars", "日线接口权限"))


def acceptance_plan(value):
    fields(value, ("schema_version", "id", "purpose", "symbols", "trade_date", "calendar", "capture_times",
                   "request_interval_seconds", "request_timeout_seconds", "max_requests"), "分钟验收准备计划")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1 or value["purpose"] != "experimental":
        raise ValueError("分钟验收准备只支持schema1及experimental用途")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", string(value["id"], "验收准备ID")):
        raise ValueError("验收准备ID无效")
    date = day(value["trade_date"])
    calendar = value["calendar"]
    fields(calendar, ("version", "evidence", "is_trading_day"), "验收交易日依据")
    if (calendar["version"] is None) != (calendar["evidence"] is None):
        raise ValueError("交易日历版本与依据须同时提供或同时保持null")
    for key in ("version", "evidence"):
        if calendar[key] is not None:
            string(calendar[key], "交易日历依据")
    if calendar["is_trading_day"] is not None and type(calendar["is_trading_day"]) is not bool:
        raise ValueError("交易日确认只支持布尔值或null")
    if calendar["is_trading_day"] is not None and calendar["evidence"] is None:
        raise ValueError("交易日确认必须有依据")
    if calendar["is_trading_day"] is False:
        raise ValueError("不能为已知非交易日生成分钟实采计划")
    fields(value["capture_times"], [name for name, _, _ in STAGES], "四阶段采集时间")
    integer(value["max_requests"], 1, 60, "验收总请求预算")
    missing, stages = [], []
    if calendar["is_trading_day"] is not True:
        missing.append("TRADING_DATE_UNCONFIRMED")
    latest_time = session_time = None
    for name, dataset, permission in STAGES:
        scheduled = value["capture_times"][name]
        if scheduled is None:
            missing.append("CAPTURE_TIME_MISSING_" + name.upper())
        else:
            parsed = utc(scheduled)
            local_date = parsed.astimezone(SHANGHAI).date()
            if name in {"latest", "session"} and local_date != date:
                raise ValueError("最新及当日分钟必须在所选交易日采集，不能回放历史日期")
            if name in {"history", "daily"} and local_date <= date:
                raise ValueError("本验收方案的历史及日线回查须安排在数据交易日之后")
            if name == "latest":
                latest_time = parsed
            if name == "session":
                session_time = parsed
        plan = {"schema_version": 1, "id": value["id"] + "-" + name, "purpose": "experimental", "provider": "tushare",
                "authorization": {"confirmed": False, "reference": None}, "symbols": deepcopy(value["symbols"]),
                "datasets": [dataset], "start_date": value["trade_date"], "end_date": value["trade_date"],
                "request_interval_seconds": value["request_interval_seconds"], "request_timeout_seconds": value["request_timeout_seconds"],
                "max_requests": 1 if name == "latest" else len(value["symbols"]) if isinstance(value["symbols"], list) else 0}
        validate_sample_plan(plan)
        if len(plan["symbols"]) > 3:
            raise ValueError("首轮验收仅支持1至3只显式证券")
        specs = request_specs(plan)
        stages.append({"id": name, "scheduled_at": scheduled, "data_date": value["trade_date"],
                       "required_permission": permission, "planned_requests": len(specs),
                       "operation": specs[0]["operation"], "file": name + ".json", "sample_plan": plan,
                       "date_parameter_applies": name in {"history", "daily"}})
    if latest_time and session_time and session_time <= latest_time:
        raise ValueError("当日序列采集须安排在最新分钟观察之后")
    total = sum(stage["planned_requests"] for stage in stages)
    if total > value["max_requests"]:
        raise ValueError("四阶段合计超出总请求预算；未生成计划或执行请求")
    report = {"schema_version": 1, "kind": "minute_acceptance_preparation", "software_version": __version__, "created_at": now(),
              "plan": deepcopy(value), "plan_hash": digest(value), "stages": stages, "planned_requests": total, "sent_requests": 0,
              "status": "needs_schedule_or_calendar" if missing else "planned_not_permission_verified", "reason_codes": sorted(missing),
              "credentials_accessed": False, "account_permissions": "not_tested", "access_authorization": "not_confirmed",
              "schedule_enforced": False, "automatic_execution": False, "strategy_input_ready": False, "release_allowed": False}
    report["output_hash"] = digest(report)
    return report


def write_acceptance_plan(value, directory):
    report = acceptance_plan(value)
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    for stage in report["stages"]:
        write_new_json(root / stage["file"], stage["sample_plan"])
        (root / stage["file"]).chmod(0o600)
    write_new_json(root / "report.json", report)
    (root / "report.json").chmod(0o600)
    return report
