"""Bounded vendor probes. Raw samples never become strategy input implicitly."""
from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import ssl
import time as clock
from urllib import error, parse, request
from zoneinfo import ZoneInfo

from . import __version__
from .contracts import day, fields, integer, numeric, string, utc, write_new_json
from .providers import _NoRedirect
from .public_sources import (PUBLIC_DATASETS, PUBLIC_ENDPOINTS, decode_public, public_bar_inputs,
                             public_page_info, public_request_specs, public_rows)
from . import fuyao_source
from .replay import source_hash
from .store import digest, dumps, now


SHANGHAI = ZoneInfo("Asia/Shanghai")
ENDPOINTS = {"tickflow_free": "https://free-api.tickflow.org",
             "tickflow": "https://api.tickflow.org", "tushare": "https://api.tushare.pro",
             "fuyao": fuyao_source.BASE_URL, **PUBLIC_ENDPOINTS}
KEY_ENV = {"tickflow": "TICKFLOW_API_KEY", "tushare": "TUSHARE_TOKEN", "fuyao": "FUYAO_API_KEY"}
DATASETS = {
    "tickflow_free": {"instruments", "daily_bars"},
    "tickflow": {"instruments", "daily_bars", "minute_history", "intraday", "quotes", "adjustment_factors"},
    "tushare": {"instruments", "daily_bars", "minute_history", "minute_quotes", "intraday", "calendar", "adjustment_factors", "memberships"},
    "fuyao": fuyao_source.DATASETS,
    **PUBLIC_DATASETS,
}
BAR_DATASETS = {"daily_bars", "minute_history", "minute_quotes", "intraday"}
MAX_BYTES = 2 * 1024 * 1024
SENSITIVE_KEYS = {"token", "apikey", "xapikey", "accesstoken", "refreshtoken", "authorization", "secret", "clientsecret", "password", "cookie", "setcookie"}


def validate_sample_plan(value):
    fields(value, ("schema_version", "id", "purpose", "provider", "authorization", "symbols", "datasets",
                   "start_date", "end_date", "request_interval_seconds", "request_timeout_seconds", "max_requests"), "供应商样本计划")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1 or value["purpose"] != "experimental":
        raise ValueError("供应商样本只支持schema1和experimental用途")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", string(value["id"], "计划ID")):
        raise ValueError("计划ID需要安全的字母数字标识")
    if not isinstance(value["provider"], str) or value["provider"] not in ENDPOINTS:
        raise ValueError("供应商须显式选择受支持的固定接口")
    auth = value["authorization"]
    fields(auth, ("confirmed", "reference"), "访问授权")
    if type(auth["confirmed"]) is not bool or (auth["confirmed"] and not auth["reference"]):
        raise ValueError("访问授权需要明确布尔值；确认后须提供非密钥的授权依据")
    if auth["reference"] is not None:
        string(auth["reference"], "访问授权依据")
    if not isinstance(value["symbols"], list) or not 1 <= len(value["symbols"]) <= 5:
        raise ValueError("每次样本须显式选择1至5只证券，不代表全市场")
    seen = set()
    for item in value["symbols"]:
        fields(item, ("symbol", "board"), "样本证券")
        symbol = item["symbol"]
        if not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}\.(SH|SZ)", symbol) or symbol in seen:
            raise ValueError("样本代码须唯一且保留六位数字及SH/SZ后缀")
        code, exchange = symbol.split(".")
        expected = ("STAR" if exchange == "SH" and code.startswith(("688", "689")) else
                    "CHINEXT" if exchange == "SZ" and code.startswith(("300", "301")) else
                    "MAIN" if ((exchange == "SH" and code.startswith(("600", "601", "603", "605"))) or
                               (exchange == "SZ" and code.startswith(("000", "001", "002", "003")))) else None)
        if expected is None or item["board"] != expected:
            raise ValueError("样本的上市板块分组与代码不一致；该分组不构成实时资格证明")
        seen.add(symbol)
    datasets = value["datasets"]
    if (not isinstance(datasets, list) or not datasets or any(not isinstance(x, str) for x in datasets)
            or len(set(datasets)) != len(datasets) or not set(datasets) <= DATASETS[value["provider"]]):
        raise ValueError("datasets须显式列出所选供应商支持的唯一数据集")
    start, end = day(value["start_date"]), day(value["end_date"])
    if not 0 <= (end - start).days <= 6:
        raise ValueError("小样本日期窗口须有序且最多7个自然日，不推测交易日历")
    numeric(value["request_interval_seconds"], "请求间隔", Decimal("6.1"), Decimal(60))
    numeric(value["request_timeout_seconds"], "请求超时", Decimal(1), Decimal(30))
    integer(value["max_requests"], 1, 60, "请求预算")
    if value["provider"] == "fuyao" and value["max_requests"] > 20:
        raise ValueError("Fuyao首轮小样本请求预算最多20次")
    return deepcopy(value)


def request_specs(plan):
    """Public request descriptions only. Authentication is added at send time."""
    if plan["provider"] in PUBLIC_ENDPOINTS:
        return public_request_specs(plan)
    if plan["provider"] == "fuyao":
        return fuyao_source.request_specs(plan, SHANGHAI)
    symbols = [s["symbol"] for s in plan["symbols"]]
    start, end = plan["start_date"], plan["end_date"]
    start_ms = int(datetime.combine(day(start), time(), SHANGHAI).timestamp() * 1000)
    end_ms = int(datetime.combine(day(end) + timedelta(days=1), time(), SHANGHAI).timestamp() * 1000) - 1
    specs = []
    def add(dataset, operation, params, symbol=None, wanted="", limit=None):
        specs.append({"dataset": dataset, "operation": operation, "params": params,
                      "symbol": symbol, "fields": wanted, "row_limit": limit})
    for dataset in plan["datasets"]:
        if plan["provider"] != "tushare":
            if dataset in {"instruments", "quotes", "adjustment_factors"}:
                operation = {"instruments": "/v1/instruments", "quotes": "/v1/quotes", "adjustment_factors": "/v1/klines/ex-factors"}[dataset]
                add(dataset, operation, {"symbols": ",".join(symbols)})
            else:
                for symbol in symbols:
                    if dataset == "intraday":
                        add(dataset, "/v1/klines/intraday", {"symbol": symbol, "period": "1m", "count": 1000}, symbol, limit=1000)
                    else:
                        limit = 10 if dataset == "daily_bars" else 10000
                        add(dataset, "/v1/klines", {"symbol": symbol, "period": "1d" if dataset == "daily_bars" else "1m",
                            "count": limit, "adjust": "none", "start_time": start_ms, "end_time": end_ms}, symbol, limit=limit)
        elif dataset == "calendar":
            for exchange in ("SSE", "SZSE"):
                add(dataset, "trade_cal", {"exchange": exchange, "start_date": start.replace("-", ""),
                    "end_date": end.replace("-", "")}, wanted="exchange,cal_date,is_open,pretrade_date")
        elif dataset == "minute_quotes":
            add(dataset, "rt_min", {"ts_code": ",".join(symbols), "freq": "1MIN"},
                wanted="ts_code,time,open,high,low,close,vol,amount", limit=1000)
        else:
            for symbol in symbols:
                params = {"ts_code": symbol}
                if dataset == "instruments":
                    add(dataset, "stock_basic", params, symbol, "ts_code,symbol,name,exchange,market,list_status,list_date,delist_date", 6000)
                elif dataset == "memberships":
                    add(dataset, "ths_member", {"con_code": symbol}, symbol,
                        "ts_code,con_code,con_name,in_date,out_date,is_new")
                elif dataset == "minute_history":
                    params.update(freq="1min", start_date=start + " 09:00:00", end_date=end + " 15:30:00")
                    add(dataset, "stk_mins", params, symbol, "ts_code,trade_time,open,high,low,close,vol,amount", 8000)
                elif dataset == "intraday":
                    params.update(freq="1MIN")
                    add(dataset, "rt_min_daily", params, symbol, "ts_code,freq,time,open,high,low,close,vol,amount", 1000)
                else:
                    params.update(start_date=start.replace("-", ""), end_date=end.replace("-", ""))
                    add(dataset, "daily" if dataset == "daily_bars" else "adj_factor", params, symbol,
                        "ts_code,trade_date,open,high,low,close,pre_close,vol,amount" if dataset == "daily_bars" else "ts_code,trade_date,adj_factor", 6000)
    if len(specs) > plan["max_requests"]:
        raise ValueError("完整样本计划超出max_requests；未执行网络请求")
    return specs


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    def bad_constant(_):
        raise ValueError("NONFINITE_JSON_NUMBER")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_float=Decimal, parse_constant=bad_constant)


def _decode_response(raw, provider):
    return decode_public(raw, provider, _json) if provider in PUBLIC_ENDPOINTS else _json(raw)


def _sensitive(value, credential, check_keys=True):
    if isinstance(value, dict):
        return any((check_keys and re.sub(r"[^a-z]", "", k.lower()) in SENSITIVE_KEYS) or _sensitive(k, credential, check_keys)
                   or _sensitive(v, credential, check_keys) for k, v in value.items())
    if isinstance(value, list):
        return any(_sensitive(v, credential, check_keys) for v in value)
    return isinstance(value, str) and bool(credential and any(credential in text for text in
                                                            (value, parse.unquote(value), parse.unquote_plus(value))))


def _plain(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _rows(body, provider, spec):
    if provider == "fuyao":
        return fuyao_source.rows(body, spec)
    if provider in PUBLIC_ENDPOINTS:
        return public_rows(body, provider, spec)
    if not isinstance(body, dict) or "data" not in body:
        raise ValueError("RESPONSE_SCHEMA_INVALID")
    data = body["data"]
    if provider == "tushare":
        if not isinstance(data, dict) or not isinstance(data.get("fields"), list) or not isinstance(data.get("items"), list):
            raise ValueError("TABLE_SCHEMA_INVALID")
        names = data["fields"]
        if any(not isinstance(k, str) for k in names) or len(set(names)) != len(names) or not set(spec["fields"].split(",")) <= set(names):
            raise ValueError("TABLE_FIELDS_INVALID")
        if any(not isinstance(row, list) or len(row) != len(names) for row in data["items"]):
            raise ValueError("TABLE_WIDTH_INVALID")
        return [dict(zip(names, row)) for row in data["items"]]
    if spec["dataset"] in BAR_DATASETS:
        names = ("timestamp", "open", "high", "low", "close", "volume", "amount")
        if not isinstance(data, dict) or any(not isinstance(data.get(k), list) for k in names):
            raise ValueError("KLINE_COLUMNS_INVALID")
        if any(len(data[k]) != len(data["timestamp"]) for k in names):
            raise ValueError("COLUMN_LENGTH_MISMATCH")
        return [dict(zip(names, values)) for values in zip(*(data[k] for k in names))]
    if isinstance(data, list) and all(isinstance(v, dict) for v in data):
        return data
    if spec["dataset"] == "adjustment_factors" and isinstance(data, dict):
        return [{"symbol": key, "factors": value} for key, value in data.items()]
    raise ValueError("RESPONSE_SCHEMA_INVALID")


def _decimal(value):
    if value is None:
        return None
    return numeric(value, "原始数值")


def _bar(row, provider, spec, received_at, filename, ingested_at):
    daily = spec["dataset"] == "daily_bars"
    if provider in PUBLIC_ENDPOINTS:
        symbol, label, source_time, volume, amount, raw_prices = public_bar_inputs(row, provider, spec, SHANGHAI)
        volume, amount = _decimal(volume), _decimal(amount)
        volume_scale = amount_scale = None
    elif provider == "fuyao":
        symbol, stamp = row.get("thscode"), row.get("date_ms")
        if type(stamp) is not int or stamp < 0:
            raise ValueError("TIME_LABEL_INVALID")
        parsed = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=stamp)
        source_time, label = parsed.isoformat(), parsed.astimezone(SHANGHAI).date().isoformat()
        volume, amount = _decimal(row.get("volume")), _decimal(row.get("turnover"))
        if any(v is not None and v < 0 for v in (volume, amount)):
            raise ValueError("FUYAO_DATA_INVALID")
        volume_scale = amount_scale = Decimal(1)
        row = dict(row, **{k: row.get(k + "_price") for k in ("open", "high", "low", "close")})
    elif provider == "tushare":
        symbol = row.get("ts_code")
        if not isinstance(symbol, str):
            raise ValueError("SYMBOL_INVALID")
        if spec["dataset"] == "intraday" and row.get("freq") != "1MIN":
            raise ValueError("MINUTE_INTERVAL_MISMATCH")
        raw_time = row.get("trade_date" if daily else "trade_time" if spec["dataset"] == "minute_history" else "time")
        if not isinstance(raw_time, str):
            raise ValueError("TIME_LABEL_INVALID")
        if daily:
            label = datetime.strptime(raw_time, "%Y%m%d").date().isoformat()
            source_time = None
        else:
            parsed = datetime.strptime(raw_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=SHANGHAI)
            label, source_time = parsed.isoformat(), parsed.astimezone(timezone.utc).isoformat()
        volume, amount = _decimal(row["vol"]), _decimal(row["amount"])
        volume_scale, amount_scale = (Decimal(100), Decimal(1000)) if daily else (Decimal(1), Decimal(1))
    else:
        symbol = spec["symbol"]
        stamp = row["timestamp"]
        if type(stamp) is not int or stamp < 0:
            raise ValueError("TIME_LABEL_INVALID")
        parsed = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=stamp)
        source_time = parsed.isoformat()
        label = parsed.astimezone(SHANGHAI).date().isoformat() if daily else parsed.astimezone(SHANGHAI).isoformat()
        volume, amount = _decimal(row["volume"]), _decimal(row["amount"])
        # The published OpenAPI says volume/amount but does not establish units.
        # A 100x plausibility finding must never silently become a conversion.
        volume_scale = amount_scale = None
    prices = {k: _decimal(raw_prices[k] if provider in PUBLIC_ENDPOINTS else row[k]) for k in ("open", "high", "low", "close")}
    reasons = []
    if any(v is None or v <= 0 for v in prices.values()):
        reasons.append("OHLC_UNKNOWN_OR_NONPOSITIVE")
    elif not (prices["low"] <= min(prices["open"], prices["close"]) <= max(prices["open"], prices["close"]) <= prices["high"]):
        reasons.append("OHLC_INCONSISTENT")
    if volume is None or amount is None:
        reasons.append("TURNOVER_UNKNOWN")
    candidates = []
    if volume_scale is None:
        reasons.append("VOLUME_AMOUNT_UNIT_UNCONFIRMED")
        if volume and amount and prices["low"] and prices["high"]:
            candidates = [str(scale) for scale in (Decimal(1), Decimal(100))
                          if prices["low"] <= amount / (volume * scale) <= prices["high"]]
            if candidates == ["100"]:
                reasons.append("UNIT_SCALE_100_CANDIDATE")
    result = {"provider": provider, "dataset": spec["dataset"], "symbol": symbol,
            "period": "1d" if daily else "1m", "label": label, "source_time": source_time,
            "time_semantics": "provider_label_not_verified_bar_end", "event_time": None,
            "source_available_at": None, "available_at": received_at, "ingested_at": ingested_at,
            "availability_basis": "first_observed_now_not_historical_publication", "is_complete": None,
            "adjustment": "none" if daily or (provider != "tushare" and spec["dataset"] != "intraday") else "unknown",
            "prices": {k: None if v is None else str(v) for k, v in prices.items()},
            "volume_raw": None if volume is None else str(volume), "amount_raw": None if amount is None else str(amount),
            "volume_shares": None if volume is None or volume_scale is None else str(volume * volume_scale),
            "amount_cny": None if amount is None or amount_scale is None else str(amount * amount_scale),
            "unit_basis": "tushare_documented_not_independently_verified" if provider == "tushare" else "not_established",
            "diagnostic_volume_scales_assuming_amount_cny": candidates, "reason_codes": reasons, "raw_file": filename}
    if provider in PUBLIC_ENDPOINTS:
        result.update(raw_price_values={k: _plain(row.get(k)) for k in ("open", "high", "low", "close")},
                      symbol_basis="request_parameter_not_response_identity" if provider == "sina_public" else "response_identity_and_request",
                      adjustment="none", unit_basis="public_raw_units_not_independently_verified")
        if provider == "eastmoney_public" and any(result["prices"][k] is None and row.get(k) in (0, "0", "0.00") for k in result["prices"]):
            result["reason_codes"].append("SOURCE_ZERO_PRICE_AS_UNKNOWN")
    if provider == "fuyao":
        result["unit_basis"] = "fuyao_documented_not_independently_verified"
        result["time_semantics"] = "daily_date_not_historical_publication"
    return result


def _private_write(path, raw):
    with path.open("xb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(raw)


def _safe_retry_after(headers):
    try:
        return max(0, min(3600, int(headers.get("Retry-After", "60"))))
    except (ValueError, TypeError, AttributeError):
        return 60


def prepare_samples(value, environ=None, credentials_dir=None):
    """Inspect a bounded plan without opening a connection or verifying account rights."""
    plan = validate_sample_plan(value)
    specs = request_specs(plan)
    environment = os.environ if environ is None else environ
    provider = plan["provider"]
    credential = _credential(provider, environment, credentials_dir)
    if credential and (not isinstance(credential, str) or not re.fullmatch(r"[!-~]{1,4096}", credential)):
        raise ValueError("供应商凭据格式无效；未执行网络请求")
    if _sensitive(plan, credential, check_keys=False):
        raise ValueError("计划不得包含凭据；未写出计划或执行请求")
    missing = []
    if not plan["authorization"]["confirmed"]:
        missing.append("ACCESS_AUTHORIZATION_NOT_CONFIRMED")
    if provider in KEY_ENV and not credential:
        missing.append("CREDENTIAL_MISSING")
    if provider == "fuyao" and "daily_bars" in plan["datasets"] and day(plan["end_date"]) >= datetime.now(SHANGHAI).date():
        missing.append("HISTORY_WINDOW_NOT_CLOSED")
    report = {"schema_version": 1, "kind": "vendor_sample_preparation", "software_version": __version__,
              "created_at": now(), "plan": plan, "plan_hash": digest(plan), "provider": provider,
              "endpoint": ENDPOINTS[provider], "requests": specs, "planned_requests": len(specs),
              "sent_requests": 0, "credential_present": bool(credential),
              "status": "blocked_configuration" if missing else "prepared_not_permission_verified",
              "reason_codes": missing, "account_permissions": "not_tested", "network_access": "not_tested",
              "strategy_input_ready": False, "full_market_verified": False, "release_allowed": False}
    report["output_hash"] = digest(report)
    return report


def _credential(provider, environ, credentials_dir):
    if provider not in KEY_ENV:
        return ""
    if credentials_dir is not None:
        from .connection_settings import ConnectionSettings
        return ConnectionSettings(credentials_dir, environ=environ).market_credential(provider)
    return environ.get(KEY_ENV[provider], "")


def collect_samples(value, output_dir, opener=None, environ=None, sleep=clock.sleep, credentials_dir=None):
    """Explicit single run, no retries/fallback, no database or notification access."""
    plan = validate_sample_plan(value)
    specs = request_specs(plan)
    provider = plan["provider"]
    environment = os.environ if environ is None else environ
    credential = _credential(provider, environment, credentials_dir)
    if credential and (not isinstance(credential, str) or not re.fullmatch(r"[!-~]{1,4096}", credential)):
        raise ValueError("供应商凭据格式无效；未执行网络请求")
    if _sensitive(plan, credential, check_keys=False):
        raise ValueError("计划不得包含凭据或敏感字段；未写出计划或执行请求")
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    (root / "raw").mkdir(mode=0o700)
    started, code_hash = now(), source_hash()
    reasons = ["RAW_SAMPLE_ONLY", "MARKET_DATA_RIGHTS_NOT_VERIFIED", "FULL_MARKET_NOT_VERIFIED",
               "HISTORICAL_PUBLICATION_TIMES_UNKNOWN", "SECURITY_RISK_STATUS_NOT_VERIFIED", "HISTORICAL_MEMBERSHIPS_NOT_VERIFIED"]
    if provider in PUBLIC_ENDPOINTS and "intraday" in plan["datasets"]:
        reasons.append("RECENT_WINDOW_NOT_DATE_RANGE")
    if provider == "tushare" and {"intraday", "minute_quotes"} & set(plan["datasets"]):
        reasons.append("CURRENT_SESSION_NOT_DATE_RANGE")
    blocked = None
    if not plan["authorization"]["confirmed"]:
        reasons.append("ACCESS_AUTHORIZATION_NOT_CONFIRMED")
        blocked = "ACCESS_AUTHORIZATION_NOT_CONFIRMED"
    if provider in KEY_ENV and not credential:
        reasons.append("CREDENTIAL_MISSING")
        blocked = blocked or "CREDENTIAL_MISSING"
    if provider == "fuyao" and "daily_bars" in plan["datasets"] and day(plan["end_date"]) >= datetime.now(SHANGHAI).date():
        reasons.append("HISTORY_WINDOW_NOT_CLOSED")
        blocked = blocked or "HISTORY_WINDOW_NOT_CLOSED"
    http = opener or request.build_opener(_NoRedirect())
    records, bars, snapshots, artifacts = [], [], [], []
    blocked_datasets = set()
    sent = 0
    for index, spec in enumerate(specs):
        record = dict(spec, started_at=None, received_at=None, http_status=None, api_code=None,
                      status="skipped", reason_code=blocked, raw_file=None, raw_sha256=None, row_count=None)
        records.append(record)
        if blocked or spec["dataset"] in blocked_datasets:
            record["reason_code"] = blocked or "DATASET_PERMISSION_BLOCKED"
            continue
        if sent:
            sleep(float(Decimal(str(plan["request_interval_seconds"]))))
        headers = {"Accept": "application/json", "User-Agent": "StockRadar-vendor-sample/" + __version__}
        if provider in PUBLIC_ENDPOINTS:
            url, body = spec["operation"] + "?" + parse.urlencode(spec["params"]), None
        elif provider == "tushare":
            url = ENDPOINTS[provider]
            body = dumps({"api_name": spec["operation"], "token": credential, "params": spec["params"], "fields": spec["fields"]}).encode()
            headers["Content-Type"] = "application/json"
        else:
            url, body = ENDPOINTS[provider] + spec["operation"] + "?" + parse.urlencode(spec["params"]), None
            if credential:
                headers["x-api-key"] = credential
        sent += 1
        record.update(started_at=now(), status="failed", reason_code=None)
        network_finished = False
        try:
            try:
                response = http.open(request.Request(url, data=body, headers=headers), timeout=float(plan["request_timeout_seconds"]))
            except error.HTTPError as exc:
                response = exc
            with response:
                record.update(http_status=response.code, received_at=now())
                if response.code != 200:
                    code = "RATE_LIMITED" if response.code == 429 else "AUTHENTICATION_FAILED" if response.code == 401 else "PERMISSION_DENIED" if response.code == 403 else "HTTP_ERROR"
                    record["reason_code"] = code
                    if response.code == 429:
                        record["retry_after_seconds"] = _safe_retry_after(response.headers)
                    if response.code in (401, 429) or 300 <= response.code < 400:
                        blocked = code
                    if response.code == 403:
                        blocked_datasets.add(spec["dataset"])
                    continue
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError("RESPONSE_TOO_LARGE")
            record["received_at"] = now()
            network_finished = True
            body = _decode_response(raw, provider)
            if _sensitive(body, credential):
                blocked = "SENSITIVE_RESPONSE_SUPPRESSED"
                raise ValueError("SENSITIVE_RESPONSE_SUPPRESSED")
            if provider == "fuyao":
                if not isinstance(body, dict) or type(body.get("code")) is not int:
                    raise ValueError("FUYAO_ENVELOPE_INVALID")
                record["api_code"] = body["code"]
                if body["code"] != 0:
                    code = {2001: "AUTHENTICATION_FAILED", 2003: "VENDOR_PERMISSION_DENIED", 4001: "RATE_LIMITED",
                            3002: "VENDOR_DATA_NOT_READY"}.get(body["code"], "VENDOR_API_ERROR")
                    record["reason_code"] = code
                    if body["code"] in (2001, 4001):
                        blocked = code
                    if body["code"] == 2003:
                        blocked_datasets.add(spec["dataset"])
                    continue
            if provider == "tushare" and (not isinstance(body, dict) or type(body.get("code")) is not int or body["code"] != 0):
                record["api_code"] = body.get("code") if isinstance(body, dict) and type(body.get("code")) is int else None
                record["reason_code"] = "VENDOR_PERMISSION_DENIED" if record["api_code"] == 2002 else "VENDOR_API_ERROR"
                blocked_datasets.add(spec["dataset"])
                continue  # Error messages/request echoes are deliberately not archived.
            filename = "raw/%02d-%s.json" % (index + 1, spec["dataset"])
            _private_write(root / filename, raw)
            sha = hashlib.sha256(raw).hexdigest()
            artifacts.append({"file": filename, "sha256": sha, "bytes": len(raw)})
            record.update(raw_file=filename, raw_sha256=sha)
            rows = _rows(body, provider, spec)
            record["row_count"] = len(rows)
            page_info = public_page_info(body, spec["dataset"], len(rows)) if provider == "eastmoney_public" else None
            if page_info is not None:
                record["page_info"] = page_info
            partial_page = page_info is not None and page_info["has_more"] is True
            missing_symbols = []
            empty_symbols = []
            if provider == "fuyao":
                coverage = fuyao_source.coverage(body, spec)
                if coverage is not None:
                    missing_symbols, empty_symbols = coverage["missing_symbols"], coverage["empty_symbols"]
                    record.update(coverage)
            if spec["dataset"] in {"instruments", "quotes"}:
                key = "ts_code" if provider == "tushare" else "thscode" if provider == "fuyao" else "symbol"
                expected = {spec["symbol"]} if spec["symbol"] else {s["symbol"] for s in plan["symbols"]}
                observed = {row.get(key) for row in rows}
                if not observed <= expected:
                    raise ValueError("UNEXPECTED_SYMBOL")
                missing_symbols = sorted(expected - observed)
                record["missing_symbols"] = missing_symbols
            if spec["row_limit"] and len(rows) >= spec["row_limit"]:
                raise ValueError("POSSIBLE_RESPONSE_TRUNCATION")
            if spec["dataset"] in BAR_DATASETS:
                projected = [_bar(row, provider, spec, record["received_at"], filename, now()) for row in rows]
                expected = {s["symbol"] for s in plan["symbols"]}
                keys = [(b["symbol"], b["label"]) for b in projected]
                if len(set(keys)) != len(keys):
                    raise ValueError("DUPLICATE_PERIOD_LABEL")
                if any(b["symbol"] not in expected or (spec["symbol"] and b["symbol"] != spec["symbol"]) for b in projected):
                    raise ValueError("UNEXPECTED_SYMBOL")
                if spec["dataset"] in {"daily_bars", "minute_history"} and any(not plan["start_date"] <= b["label"][:10] <= plan["end_date"] for b in projected):
                    raise ValueError("PERIOD_OUTSIDE_REQUESTED_WINDOW")
                bars.extend(projected)
            else:
                snapshots.append({"provider": provider, "dataset": spec["dataset"], "query": spec["params"],
                    "scope": "sample_instruments_not_complete_sector_universe", "observed_at": record["received_at"],
                    "available_at": record["received_at"], "source_effective_from": None, "source_effective_to": None,
                    "historical_eligibility_established": False, "raw_file": filename, "raw_sha256": sha,
                    "content_hash": digest(_plain(rows)), "rows": _plain(rows)})
                if provider == "fuyao":
                    snapshots[-1].update(source_timestamp_ms=body["data"].get("timestamp"),
                                         timestamp_semantics="latest_upstream_time_not_per_instrument" if spec["dataset"] == "quotes" else "provider_metadata_not_historical_publication")
            record.update(status="partial" if partial_page or (rows and (missing_symbols or empty_symbols)) else "captured" if rows else "empty",
                          reason_code="PARTIAL_PUBLIC_SNAPSHOT" if partial_page else "REQUESTED_SYMBOLS_MISSING" if rows and missing_symbols else "EMPTY_SYMBOL_GROUPS" if rows and empty_symbols else None if rows else "NO_ROWS")
        except (error.URLError, socket.timeout, TimeoutError, OSError) as exc:
            if network_finished:
                raise
            # Never serialize exceptions: URLs, request bodies or proxy credentials may appear in them.
            record["reason_code"] = "TRANSPORT_ERROR"
            cause = exc.reason if isinstance(exc, error.URLError) else exc
            record["transport_error_kind"] = ("dns" if isinstance(cause, socket.gaierror) else
                "tls" if isinstance(cause, ssl.SSLError) else "timeout" if isinstance(cause, TimeoutError) else
                "os_permission" if isinstance(cause, PermissionError) else "connection")
            blocked = "TRANSPORT_ERROR"
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            # Use only fixed diagnostics below, not arbitrary vendor values.
            known = {"RESPONSE_TOO_LARGE", "SENSITIVE_RESPONSE_SUPPRESSED", "DUPLICATE_JSON_KEY", "NONFINITE_JSON_NUMBER",
                     "RESPONSE_SCHEMA_INVALID", "TABLE_SCHEMA_INVALID", "TABLE_FIELDS_INVALID", "TABLE_WIDTH_INVALID",
                     "KLINE_COLUMNS_INVALID", "COLUMN_LENGTH_MISMATCH", "POSSIBLE_RESPONSE_TRUNCATION", "UNEXPECTED_SYMBOL",
                     "DUPLICATE_PERIOD_LABEL", "PERIOD_OUTSIDE_REQUESTED_WINDOW", "SYMBOL_INVALID", "TIME_LABEL_INVALID",
                     "PUBLIC_JSONP_ENVELOPE_INVALID", "PUBLIC_WINDOW_LIMIT_EXCEEDED", "PUBLIC_API_ERROR", "UNADJUSTED_SERIES_MISSING",
                     "PUBLIC_BAR_WIDTH_INVALID", "PUBLIC_PAGE_TOTAL_INVALID", "MINUTE_INTERVAL_MISMATCH"}
            known.update({"FUYAO_ENVELOPE_INVALID", "FUYAO_API_ERROR", "FUYAO_DATA_INVALID", "FUYAO_ADJUSTMENT_MISMATCH"})
            record["reason_code"] = str(exc) if str(exc) in known else "RESPONSE_DATA_INVALID"
    for filename, rows in (("bars.jsonl", bars), ("snapshots.jsonl", snapshots)):
        raw = ("".join(dumps(row) + "\n" for row in rows)).encode()
        _private_write(root / filename, raw)
        artifacts.append({"file": filename, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    reasons.extend(sorted({r["reason_code"] for r in records if r["reason_code"]}))
    reasons.extend(sorted({code for b in bars for code in b["reason_codes"]}))
    code_changed = source_hash() != code_hash
    if code_changed:
        reasons.append("CODE_CHANGED_DURING_PROBE")
    report = {"schema_version": 1, "kind": "vendor_raw_sample", "software_version": __version__, "code_hash": code_hash,
              "provider": provider, "endpoint": ENDPOINTS[provider], "plan": plan, "plan_hash": digest(plan),
              "started_at": started, "completed_at": now(), "status": "sample_captured" if not code_changed and records and all(r["status"] == "captured" for r in records) else "incomplete",
              "scope": "explicit_small_sample", "simulated": False, "credential_present": bool(credential),
              "planned_requests": len(specs), "sent_requests": sent, "captured_responses": sum(r["status"] == "captured" for r in records),
              "bar_count": len(bars), "snapshot_count": len(snapshots), "requests": records, "artifacts": artifacts,
              "reason_codes": sorted(set(reasons)), "strategy_input_ready": False, "cross_source_verified": False,
              "full_market_verified": False, "release_allowed": False}
    report["output_hash"] = digest(report)
    write_new_json(root / "report.json", report)
    os.chmod(root / "report.json", 0o600)
    return report


def _read_probe_report(root):
    """Validate the captured request ledger without reopening its payload files."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("样本目录须为实际目录")
    from .contracts import load_json
    if (root / "report.json").is_symlink() or (root / "report.json").stat().st_size > 2 * 1024 * 1024:
        raise ValueError("样本报告过大或为符号链接")
    report = load_json(root / "report.json")
    if report.get("schema_version") != 1 or report.get("kind") != "vendor_raw_sample" or report.get("output_hash") != digest({k: v for k, v in report.items() if k != "output_hash"}):
        raise ValueError("样本报告哈希或类型无效")
    plan = validate_sample_plan(report["plan"])
    if report["plan_hash"] != digest(plan) or report["provider"] != plan["provider"]:
        raise ValueError("样本计划哈希或供应商不一致")
    files = {}
    for artifact in report["artifacts"]:
        filename = artifact["file"]
        if not isinstance(filename, str) or not re.fullmatch(r"(?:raw/[0-9]{2}-[a-z_]+\.json|bars\.jsonl|snapshots\.jsonl)", filename) or filename in files:
            raise ValueError("样本报告包含非法文件路径")
        files[filename] = artifact["sha256"]
    if not {"bars.jsonl", "snapshots.jsonl"} <= files.keys():
        raise ValueError("样本缺少已校验的派生文件")
    specs = request_specs(plan)
    if len(report["requests"]) != len(specs):
        raise ValueError("样本请求记录与计划不一致")
    for record, spec in zip(report["requests"], specs):
        if any(record.get(k) != v for k, v in spec.items()):
            raise ValueError("样本请求记录与计划不一致")
        if record["raw_file"] is not None and (record["raw_file"] not in files or not record["raw_file"].startswith("raw/")
                or record["raw_sha256"] != files[record["raw_file"]]):
            raise ValueError("原始响应未被文件清单验证")
    return report


def _read_probe(root):
    root = Path(root)
    report = _read_probe_report(root)
    for artifact in report["artifacts"]:
        path = root / artifact["file"]
        if any(p.is_symlink() for p in (root / "raw", path)) or not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("样本文件缺失、过大或包含符号链接")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != artifact["sha256"] or len(raw) != artifact["bytes"]:
            raise ValueError("样本文件哈希不一致；未执行比较")
    bars = [json.loads(line) for line in (root / "bars.jsonl").read_text().splitlines() if line]
    return report, bars


def compare_samples(left_dir, right_dir):
    """Exact, unadjusted DAILY comparison. Minute labels/closure need separate validation."""
    left, left_bars = _read_probe(left_dir)
    right, right_bars = _read_probe(right_dir)
    if left["provider"] == right["provider"] or {left["provider"], right["provider"]} <= {"tickflow", "tickflow_free"}:
        raise ValueError("同供应商/同TickFlow服务不能作为交叉来源验证")
    def indexed(bars):
        result = {}
        for bar in bars:
            if bar["dataset"] != "daily_bars" or bar["adjustment"] != "none":
                continue
            key = (bar["symbol"], bar["label"])
            if key in result:
                raise ValueError("样本中同一日线有重复或修订；须先明确修订版本")
            result[key] = bar
        return result
    a, b = indexed(left_bars), indexed(right_bars)
    common = sorted(a.keys() & b.keys())
    comparisons = []
    for key in common:
        x, y = a[key], b[key]
        differences, unknown = [], []
        for field in ("open", "high", "low", "close", "volume_shares", "amount_cny"):
            xv = x["prices"][field] if field in x["prices"] else x[field]
            yv = y["prices"][field] if field in y["prices"] else y[field]
            if xv is None or yv is None or (field in x["prices"] and (Decimal(xv) <= 0 or Decimal(yv) <= 0)):
                unknown.append(field)
            elif Decimal(xv) != Decimal(yv):
                differences.append({"field": field, "left": xv, "right": yv})
        comparisons.append({"symbol": key[0], "date": key[1], "differences": differences, "unknown_fields": unknown})
    report = {"schema_version": 1, "kind": "vendor_daily_comparison", "created_at": now(),
              "left_report_hash": left["output_hash"], "right_report_hash": right["output_hash"],
              "providers": [left["provider"], right["provider"]], "comparison_basis": "unadjusted_daily_exact_decimal",
              "common_bars": len(common), "left_only": [list(k) for k in sorted(a.keys() - b.keys())],
              "right_only": [list(k) for k in sorted(b.keys() - a.keys())], "comparisons": comparisons,
              "status": "compared" if common else "no_overlap", "underlying_source_independence": "unverified",
              "minute_comparison": "not_performed", "strategy_input_ready": False, "full_market_verified": False, "release_allowed": False}
    report["output_hash"] = digest(report)
    return report
