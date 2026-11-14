"""Fixed, anonymous HTTPS requests for bounded public-data research samples."""
from datetime import datetime, timezone
from decimal import Decimal
import json
import re


PUBLIC_ENDPOINTS = {
    "sina_public": "https://quotes.sina.cn",
    "eastmoney_public": "https://push2.eastmoney.com",
    "tencent_public": "https://web.ifzq.gtimg.cn",
}
PUBLIC_DATASETS = {
    "sina_public": {"intraday"},
    "eastmoney_public": {"quotes", "intraday", "memberships", "risk_status", "suspensions"},
    "tencent_public": {"daily_bars"},
}


def public_request_specs(plan):
    specs = []
    def add(dataset, url, params, symbol=None):
        specs.append({"dataset": dataset, "operation": url, "params": params,
                      "symbol": symbol, "fields": "", "row_limit": None})
    symbols = [s["symbol"] for s in plan["symbols"]]
    def secid(symbol):
        code, exchange = symbol.split(".")
        return ("1." if exchange == "SH" else "0.") + code
    for dataset in plan["datasets"]:
        if plan["provider"] == "sina_public":
            for symbol in symbols:
                code, exchange = symbol.split(".")
                add(dataset, PUBLIC_ENDPOINTS["sina_public"] + "/cn/api/jsonp_v2.php/=/CN_MarketDataService.getKLineData",
                    {"symbol": exchange.lower() + code, "scale": "1", "ma": "no", "datalen": "240"}, symbol)
        elif plan["provider"] == "tencent_public":
            for symbol in symbols:
                code, exchange = symbol.split(".")
                add(dataset, PUBLIC_ENDPOINTS["tencent_public"] + "/appstock/app/fqkline/get",
                    {"param": "%s%s,day,%s,%s,10," % (exchange.lower(), code, plan["start_date"], plan["end_date"])}, symbol)
        elif dataset == "quotes":
            add(dataset, PUBLIC_ENDPOINTS["eastmoney_public"] + "/api/qt/ulist.np/get",
                {"secids": ",".join(secid(s) for s in symbols), "fltt": "2", "invt": "2",
                 "fields": "f12,f13,f14,f2,f3,f4,f5,f6,f15,f16,f17,f18,f86"})
        elif dataset == "intraday":
            for symbol in symbols:
                add(dataset, "https://push2his.eastmoney.com/api/qt/stock/trends2/get",
                    {"secid": secid(symbol), "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
                     "fields2": "f51,f52,f53,f54,f55,f56,f57,f58", "ndays": "5", "iscr": "0", "iscca": "0"}, symbol)
        elif dataset == "memberships":
            for symbol in symbols:
                add(dataset, PUBLIC_ENDPOINTS["eastmoney_public"] + "/api/qt/slist/get",
                    {"forcect": "1", "spt": "3", "fields": "f1,f12,f152,f3,f14,f128,f136", "pi": "0",
                     "pz": "1000", "po": "1", "fid": "f3", "fid0": "f4003", "invt": "2", "secid": secid(symbol)}, symbol)
        elif dataset == "risk_status":
            add(dataset, "https://40.push2.eastmoney.com/api/qt/clist/get",
                {"pn": "1", "pz": "100", "po": "1", "np": "1", "fltt": "2", "invt": "2",
                 "fid": "f12", "fs": "m:0 f:4,m:1 f:4", "fields": "f12,f13,f14,f2,f86"})
        elif dataset == "suspensions":
            add(dataset, "https://datacenter-web.eastmoney.com/api/data/v1/get",
                {"sortColumns": "SUSPEND_START_DATE", "sortTypes": "-1", "pageSize": "500", "pageNumber": "1",
                 "reportName": "RPT_CUSTOM_SUSPEND_DATA_INTERFACE", "columns": "ALL", "source": "WEB", "client": "WEB",
                 "filter": '(MARKET="全部")(DATETIME=\'%s\')' % plan["end_date"]})
    if len(specs) > plan["max_requests"]:
        raise ValueError("完整样本计划超出max_requests；未执行网络请求")
    return specs


def decode_public(raw, provider, parse_json):
    if provider != "sina_public" or raw.lstrip().startswith((b"[", b"{")):
        return parse_json(raw)
    # Only extract a literal argument from the known JSONP envelope. Never eval JS.
    match = re.fullmatch(rb"\s*(?:/\*.*?\*/\s*)?=\((.*)\);?\s*", raw, re.S)
    if not match:
        raise ValueError("PUBLIC_JSONP_ENVELOPE_INVALID")
    try:
        return parse_json(match.group(1))
    except json.JSONDecodeError:
        raise ValueError("PUBLIC_JSONP_ENVELOPE_INVALID") from None


def _diff(data):
    if not isinstance(data, dict):
        raise ValueError("RESPONSE_SCHEMA_INVALID")
    values = data.get("diff")
    if isinstance(values, dict) and all(isinstance(k, str) and k.isdigit() for k in values):
        values = [values[k] for k in sorted(values, key=int)]
    if not isinstance(values, list) or any(not isinstance(row, dict) for row in values):
        raise ValueError("RESPONSE_SCHEMA_INVALID")
    return values


def _symbol(row):
    code, exchange = row.get("f12"), row.get("f13")
    if not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code) or type(exchange) is not int or exchange not in (0, 1):
        raise ValueError("SYMBOL_INVALID")
    return code + (".SH" if exchange == 1 else ".SZ")


def public_rows(body, provider, spec):
    dataset = spec["dataset"]
    if provider == "sina_public":
        if not isinstance(body, list) or any(not isinstance(row, dict) or not {"day", "open", "high", "low", "close", "volume"} <= set(row) for row in body):
            raise ValueError("RESPONSE_SCHEMA_INVALID")
        if len(body) > int(spec["params"]["datalen"]):
            raise ValueError("PUBLIC_WINDOW_LIMIT_EXCEEDED")
        return body
    if not isinstance(body, dict):
        raise ValueError("RESPONSE_SCHEMA_INVALID")
    if provider == "tencent_public":
        if type(body.get("code")) is not int or body["code"] != 0 or not isinstance(body.get("data"), dict):
            raise ValueError("PUBLIC_API_ERROR")
        code, exchange = spec["symbol"].split(".")
        data = body["data"].get(exchange.lower() + code)
        if not isinstance(data, dict) or not isinstance(data.get("day"), list):
            # Never substitute qfqday/hfqday or a current quote for the requested day.
            raise ValueError("UNADJUSTED_SERIES_MISSING")
        rows = data["day"]
        if any(not isinstance(row, list) or len(row) < 6 for row in rows) or len(rows) >= 10:
            raise ValueError("POSSIBLE_RESPONSE_TRUNCATION")
        return [{"day": row[0], "open": row[1], "close": row[2], "high": row[3], "low": row[4], "volume": row[5]} for row in rows]
    if dataset == "suspensions":
        if body.get("success") is not True or not isinstance(body.get("result"), dict):
            raise ValueError("PUBLIC_API_ERROR")
        rows = body["result"].get("data")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("RESPONSE_SCHEMA_INVALID")
        return rows
    if type(body.get("rc")) is not int or body["rc"] != 0:
        raise ValueError("PUBLIC_API_ERROR")
    data = body.get("data")
    if dataset == "intraday":
        if not isinstance(data, dict) or data.get("code") != spec["symbol"][:6] or not isinstance(data.get("trends"), list):
            raise ValueError("RESPONSE_SCHEMA_INVALID")
        rows = []
        if len(data["trends"]) > 1300:
            raise ValueError("PUBLIC_WINDOW_LIMIT_EXCEEDED")
        for value in data["trends"]:
            if not isinstance(value, str) or len(value.split(",")) != 8:
                raise ValueError("PUBLIC_BAR_WIDTH_INVALID")
            parts = value.split(",")
            rows.append(dict(zip(("day", "open", "close", "high", "low", "volume", "amount", "average"), parts)))
        return rows
    rows = _diff(data)
    if len(rows) > (1000 if dataset == "memberships" else 100 if dataset == "risk_status" else 5):
        raise ValueError("PUBLIC_WINDOW_LIMIT_EXCEEDED")
    if dataset in {"quotes", "risk_status"}:
        return [dict(row, symbol=_symbol(row)) for row in rows]
    return rows


def public_page_info(body, dataset, row_count):
    if dataset not in {"memberships", "risk_status", "suspensions"}:
        return None
    data = body.get("result" if dataset == "suspensions" else "data")
    total = data.get("count" if dataset == "suspensions" else "total") if isinstance(data, dict) else None
    pages = data.get("pages") if dataset == "suspensions" and isinstance(data, dict) else None
    if total is not None and (type(total) is not int or total < row_count):
        raise ValueError("PUBLIC_PAGE_TOTAL_INVALID")
    if pages is not None and (type(pages) is not int or pages < 0):
        raise ValueError("PUBLIC_PAGE_TOTAL_INVALID")
    more = total > row_count if total is not None else pages > 1 if pages is not None else None
    return {"observed_rows": row_count, "reported_total": total, "reported_pages": pages, "has_more": more,
            "all_pages_verified": more is False}


def public_bar_inputs(row, provider, spec, shanghai):
    daily = spec["dataset"] == "daily_bars"
    raw_time = row.get("day")
    if not isinstance(raw_time, str):
        raise ValueError("TIME_LABEL_INVALID")
    if daily:
        label = datetime.strptime(raw_time, "%Y-%m-%d").date().isoformat()
        source_time = None
    else:
        pattern = "%Y-%m-%d %H:%M" if provider == "eastmoney_public" else "%Y-%m-%d %H:%M:%S"
        local = datetime.strptime(raw_time, pattern).replace(tzinfo=shanghai)
        label, source_time = local.isoformat(), local.astimezone(timezone.utc).isoformat()
    def unknown(value):
        return None if value is None or value in ("", "-", "--") else value
    prices = {k: unknown(row.get(k)) for k in ("open", "high", "low", "close")}
    if provider == "eastmoney_public":
        prices = {k: None if v is not None and Decimal(str(v)) == 0 else v for k, v in prices.items()}
    return spec["symbol"], label, source_time, unknown(row.get("volume")), unknown(row.get("amount")), prices
