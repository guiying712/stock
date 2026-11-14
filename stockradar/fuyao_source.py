"""Fuyao's public, daily/current-data contracts for bounded research samples."""
from datetime import datetime, time, timedelta

from .contracts import day


BASE_URL = "https://fuyao.aicubes.cn"
DATASETS = {"instruments", "daily_bars", "quotes", "calendar", "adjustment_factors",
            "sector_catalog", "memberships"}


def request_specs(plan, shanghai):
    symbols = [item["symbol"] for item in plan["symbols"]]
    start, end = day(plan["start_date"]), day(plan["end_date"])
    start_ms = int(datetime.combine(start, time(), shanghai).timestamp() * 1000)
    end_ms = int(datetime.combine(end + timedelta(days=1), time(), shanghai).timestamp() * 1000) - 1
    result = []

    def add(dataset, operation, params, symbol=None, limit=None):
        result.append({"dataset": dataset, "operation": operation, "params": params,
                       "symbol": symbol, "fields": "", "row_limit": limit})

    for dataset in plan["datasets"]:
        if dataset == "instruments":
            for symbol in symbols:
                add(dataset, "/api/meta/tickers/search", {"q": symbol, "asset_type": "a-share", "limit": 10}, symbol, 10)
        elif dataset == "daily_bars":
            add(dataset, "/api/a-share/prices/historical-batch",
                {"thscodes": ",".join(symbols), "interval": "1d", "adjust": "none", "start": start_ms, "end": end_ms})
        elif dataset == "quotes":
            add(dataset, "/api/a-share/prices/snapshot", {"thscodes": ",".join(symbols)})
        elif dataset == "calendar":
            add(dataset, "/api/a-share/calendar/trading-days",
                {"start_date": start.strftime("%Y%m%d"), "end_date": end.strftime("%Y%m%d")})
        elif dataset == "adjustment_factors":
            for symbol in symbols:
                add(dataset, "/api/a-share/corporate-actions/adjustment-factors",
                    {"thscode": symbol, "from": plan["start_date"], "to": plan["end_date"]}, symbol)
        elif dataset == "sector_catalog":
            for tag in ("cn_concept", "industry"):
                add(dataset, "/api/a-share-index/catalog/ths-index-list", {"tag": tag})
        elif dataset == "memberships":
            add(dataset, "/api/a-share-index/constituents/ths-index-list-by-stock", {"thscode": ",".join(symbols)})
    if len(result) > plan["max_requests"]:
        raise ValueError("完整样本计划超出max_requests；未执行网络请求")
    return result


def response_data(body):
    if (not isinstance(body, dict) or type(body.get("code")) is not int
            or not isinstance(body.get("message"), str) or not isinstance(body.get("request_id"), str)):
        raise ValueError("FUYAO_ENVELOPE_INVALID")
    if body["code"] != 0:
        raise ValueError("FUYAO_API_ERROR")
    data = body.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("item"), list) or any(not isinstance(r, dict) for r in data["item"]):
        raise ValueError("FUYAO_DATA_INVALID")
    return data


def rows(body, spec):
    data = response_data(body)
    if spec["dataset"] == "daily_bars":
        if data.get("interval") != "1d" or data.get("adjust") != "none":
            raise ValueError("FUYAO_ADJUSTMENT_MISMATCH")
        expected = set(spec["params"]["thscodes"].split(","))
        seen, result = set(), []
        for group in data["item"]:
            symbol = group.get("thscode")
            if not isinstance(symbol, str) or symbol not in expected or symbol in seen:
                raise ValueError("UNEXPECTED_SYMBOL")
            seen.add(symbol)
            if not isinstance(group.get("item"), list) or any(not isinstance(r, dict) for r in group["item"]):
                raise ValueError("FUYAO_DATA_INVALID")
            for row in group["item"]:
                if "thscode" in row and row["thscode"] != symbol:
                    raise ValueError("UNEXPECTED_SYMBOL")
                result.append(dict(row, thscode=symbol))
        return result
    if spec["dataset"] == "adjustment_factors" and data.get("thscode") != spec["symbol"]:
        raise ValueError("UNEXPECTED_SYMBOL")
    if spec["dataset"] == "memberships":
        expected = set(spec["params"]["thscode"].split(","))
        observed = [r.get("thscode") for r in data["item"]]
        if any(not isinstance(s, str) or s not in expected for s in observed) or len(set(observed)) != len(observed):
            raise ValueError("UNEXPECTED_SYMBOL")
        for row in data["item"]:
            if not isinstance(row.get("index_list"), list) or any(not isinstance(r, dict) for r in row["index_list"]):
                raise ValueError("FUYAO_DATA_INVALID")
    return data["item"]


def coverage(body, spec):
    """Distinguish omitted targets, legal empty groups and unknown stock existence."""
    if spec["dataset"] not in {"daily_bars", "memberships"}:
        return None
    groups = response_data(body)["item"]
    key = "thscodes" if spec["dataset"] == "daily_bars" else "thscode"
    expected = set(spec["params"][key].split(","))
    observed = {g["thscode"] for g in groups}
    array = "item" if spec["dataset"] == "daily_bars" else "index_list"
    return {"missing_symbols": sorted(expected - observed),
            "empty_symbols": sorted(g["thscode"] for g in groups if not g[array]),
            "historical_eligibility_established": False}
