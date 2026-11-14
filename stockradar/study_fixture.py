"""Small-session synthetic study tape; not an exchange calendar or real rules."""
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
from zoneinfo import ZoneInfo

from .config import load_config
from .fixtures import fixture_batches


def make_study_fixture(days=90):
    if type(days) is not int or not 9 <= days <= 150:
        raise ValueError("合成研究交易日数须为9至150")
    dates, cursor = [], date(2026, 4, 1)
    while len(dates) < days + 15:
        if cursor.weekday() < 5:
            dates.append(cursor)
        cursor += timedelta(days=1)
    shanghai = ZoneInfo("Asia/Shanghai")
    def at(d, minute):
        return datetime.combine(d, time(9, minute), shanghai).astimezone(timezone.utc).isoformat()
    def price(value):
        return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    def turnover(index, multiplier):
        with localcontext() as context:
            context.prec = 60
            return (Decimal(2000000) * multiplier * Decimal("1.35") ** index).quantize(Decimal("0.01"))
    template = fixture_batches()[0]
    instruments = deepcopy(template["instruments"])
    quoted_ids = {q["instrument_id"] for q in template["quotes"]}
    tradable = [i for i in instruments if i["id"] in quoted_ids]
    width = len(tradable)
    memberships = deepcopy(template["memberships"])
    for item in memberships:
        item.update(provider="synthetic-study-v2-star", snapshot_id="synthetic-study-members-v2-star")
    calendar = {"version": "synthetic-short-session-v1", "simulated": True,
                "trading_dates": [d.isoformat() for d in dates], "sessions": [["09:30", "09:37"]], "close_time": "09:37"}
    rule_ids = {("SSE", "MAIN"): "synthetic-sse-main-v1", ("SZSE", "MAIN"): "synthetic-szse-main-v1",
                ("SZSE", "CHINEXT"): "synthetic-szse-chinext-v1"}
    rules = [{"id": rule_id, "exchange": exchange, "board": board, "valid_from": "2020-01-01", "valid_to": None,
              "available_at": "2020-01-01T00:00:00Z", "source_urls": ["synthetic-only:not-market-rules"], "verified": False,
              "buy_lot": 100, "max_order_shares": 1000000, "tick_size": "0.01", "sell_delay_sessions": 1,
              "valuation_sessions": [["09:30", "09:37"]],
              "fees": {"commission_fraction": "0.0003", "minimum_commission": "5", "buy_transfer_fraction": "0.00001",
                       "sell_transfer_fraction": "0.00001", "sell_tax_fraction": "0.0005"},
              "slippage_buy_fraction": "0.0005", "slippage_sell_fraction": "0.0005"}
             for (exchange, board), rule_id in sorted(rule_ids.items())]
    rule_ids[("SSE", "STAR")] = "synthetic-sse-star-v2"
    star_rule = deepcopy(rules[0])
    star_rule.pop("buy_lot")
    star_rule.update(schema_version=2, id=rule_ids[("SSE", "STAR")], exchange="SSE", board="STAR", order_type="limit",
                     buy_min_shares=200, buy_step_shares=1, sell_min_shares=200, sell_step_shares=1,
                     sell_odd_lot_full_exit=True, max_order_shares=100000)
    rules.append(star_rule)
    daily, minutes, benchmark_daily, benchmark_minutes, batches = [], [], [], [], []
    values = ["0.995", "0.996", "0.997", "0.998", "1.020", "1.021", "1.022"]
    for index, current_day in enumerate(dates):
        base = Decimal(10) * Decimal("1.01") ** index
        benchmark_base = Decimal(100) * Decimal("1.003") ** index
        for offset, value in enumerate(values, 31):
            quotes = []
            for position, instrument in enumerate(tradable):
                scale = Decimal(1) + Decimal(position % 4) / 5
                close = base * scale * Decimal(value)
                ts = at(current_day, offset)
                amount = turnover(index, offset - 30)
                quotes.append({"instrument_id": instrument["id"], "open": price(close), "close": price(close),
                               "high": price(close + Decimal("0.01")), "low": price(close - Decimal("0.01")),
                               "prev_close": price(base / Decimal("1.01") * scale * Decimal("1.022")),
                               "volume_shares": int(amount / close), "amount_cny": str(amount.quantize(Decimal("0.01"))),
                               "adjustment_factor": "1", "interval": 60, "is_complete": True, "quality": "good",
                               "event_time": ts, "available_at": ts, "ingested_at": ts, "revision": 1, "source": "synthetic-study-v2-star",
                               "execution": {"status": "trading", "can_buy": True, "can_sell": True,
                                             "available_volume_shares": 1000000, "limit_state": "bounded",
                                             "limit_up": price(base * scale * Decimal("1.5")),
                                             "limit_down": price(base * scale * Decimal("0.5")),
                                             "rule_version": rule_ids[(instrument["exchange"], instrument["board"])], "available_at": ts}})
            benchmark = deepcopy(quotes[0])
            benchmark.update(instrument_id="FIXTURE.BENCHMARK", close=price(benchmark_base * (1 + Decimal(offset - 30) / 10000)),
                             open=price(benchmark_base), high=price(benchmark_base * Decimal("1.001")),
                             low=price(benchmark_base * Decimal("0.999")), prev_close=price(benchmark_base / Decimal("1.003")))
            benchmark.pop("execution")
            if index >= 15:
                batch = {"schema_version": 1, "snapshot_id": "study-%s-%d" % (current_day.isoformat(), offset),
                         "source": "synthetic-study-v2-star", "simulated": True, "as_of": ts,
                         "units": deepcopy(template["units"]), "calendar": deepcopy(calendar),
                         "instruments": deepcopy(instruments), "sectors": deepcopy(template["sectors"]),
                         "memberships": deepcopy(memberships), "quotes": deepcopy(quotes),
                         "daily_bars": deepcopy(daily[-15 * width:]), "minute_history": deepcopy(minutes[-(3 * 7 + 6) * width:]),
                         "benchmark": {"id": "FIXTURE.BENCHMARK", "quote": deepcopy(benchmark),
                                       "daily_bars": deepcopy(benchmark_daily[-15:]), "minute_history": deepcopy(benchmark_minutes[-(3 * 7 + 6):])},
                         "corporate_actions": []}
                batches.append(batch)
            minutes.extend(quotes)
            benchmark_minutes.append(benchmark)
        for position, instrument in enumerate(tradable):
            scale = Decimal(1) + Decimal(position % 4) / 5
            daily.append({"instrument_id": instrument["id"], "date": current_day.isoformat(),
                          "high": price(base * scale * Decimal("1.023")), "low": price(base * scale * Decimal("0.970")),
                          "close": price(base * scale * Decimal("1.022")), "prev_close": price(base / Decimal("1.01") * scale * Decimal("1.022")),
                          "amount_cny": str(turnover(index, 10)),
                          "adjustment_factor": "1", "available_at": at(current_day, 38)})
        benchmark_daily.append({"instrument_id": "FIXTURE.BENCHMARK", "date": current_day.isoformat(),
                                "high": price(benchmark_base * Decimal("1.003")), "low": price(benchmark_base * Decimal("0.995")),
                                "close": price(benchmark_base), "prev_close": price(benchmark_base / Decimal("1.003")),
                                "amount_cny": "1000000000", "adjustment_factor": "1", "available_at": at(current_day, 38)})
    profiles = []
    for name in ("stock_only", "sector_filter", "early", "confirmed"):
        cfg = load_config()
        cfg.update(id="synthetic-study-v2-star-" + name, mode="replay", purpose="experimental")
        cfg["research"].update(sector_filter=name != "stock_only", alert_stage="confirmed" if name == "confirmed" else "early")
        cfg["scoring"]["alert_threshold"] = 40
        if name in {"stock_only", "sector_filter"}:
            cfg["scoring"]["groups"]["sector"]["weight"] = 0
            cfg["scoring"]["groups"]["stock"]["weight"] = 0.6
        profiles.append({"id": name, "config": cfg})
    split_dates = [dates[15], dates[15 + days // 3], dates[15 + 2 * (days // 3)], dates[-1] + timedelta(days=1)]
    plan = {"schema_version": 1, "id": "synthetic-study-v2-star", "purpose": "fixture", "capital_per_signal": "10000",
            "delivery_delay_seconds": 0, "reaction_delays_minutes": [0, 1, 3, 5], "holding_windows_days": [5, 10, 20],
            "exit_modes": ["fixed", "risk"], "price_model": "next_completed_close",
            "dividend_accounting": "net_receivable_on_ex_date", "max_loss_fraction": "0.10", "benchmark_id": "FIXTURE.BENCHMARK",
            "rules": rules, "profiles": profiles,
            "splits": [{"name": name, "start": datetime.combine(a, time(), shanghai).astimezone(timezone.utc).isoformat(),
                        "end": datetime.combine(b, time(), shanghai).astimezone(timezone.utc).isoformat()}
                       for name, a, b in zip(("train", "validation", "test"), split_dates, split_dates[1:])],
            "bootstrap_samples": 200, "min_clusters": 5, "seed": 20261029}
    return batches, plan
