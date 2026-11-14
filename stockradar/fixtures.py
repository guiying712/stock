"""Reproducible synthetic market tape. No real prices, constituents or calendar."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal


SOURCE = "synthetic-fixture-v1"
DAY = date(2026, 10, 28)


def _time(day, minute):
    # Fixture inputs are UTC; minute is an Asia/Shanghai wall-clock minute.
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(minutes=minute - 480)


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def _p(value):
    return str(Decimal(str(value)).quantize(Decimal("0.0001")))


def _quote(iid, day, minute, close, prev_close, factor="1", activity="1"):
    close, prev = Decimal(str(close)), Decimal(str(prev_close))
    amount = (Decimal(2000000) + Decimal(minute - 570) * 100000) * Decimal(activity)
    ts = _iso(_time(day, minute))
    return {"instrument_id": iid, "open": _p(close - Decimal("0.01")), "high": _p(close + Decimal("0.02")),
            "low": _p(close - Decimal("0.02")), "close": _p(close), "prev_close": _p(prev),
            "volume_shares": int(amount / close), "amount_cny": _p(amount), "interval": 60,
            "is_complete": True, "event_time": ts, "available_at": ts, "ingested_at": ts,
            "adjustment_factor": factor, "source": SOURCE, "quality": "good", "revision": 1}


def _fixture_v1_batches():
    """Return fresh independent values for eleven explicit acceptance scenarios."""
    past = []
    cursor = DAY - timedelta(days=1)
    while len(past) < 15:
        if cursor.weekday() < 5:
            past.append(cursor)
        cursor -= timedelta(days=1)
    past.sort()
    calendar = {"version": "fixture-calendar-v1", "simulated": True, "close_time": "15:00",
                "trading_dates": [d.isoformat() for d in past] + [DAY.isoformat()],
                "sessions": [["09:30", "11:30"], ["13:00", "14:57"]]}
    instruments, memberships, daily = [], [], []
    sectors = [{"id": "chips", "name": "半导体（模拟）", "type": "industry"},
               {"id": "ai", "name": "算力硬件（模拟）", "type": "theme"},
               {"id": "robotics", "name": "机器人（模拟）", "type": "theme"},
               {"id": "finance", "name": "金融（模拟）", "type": "industry"}]
    bases = {}
    for index in range(12):
        code = ("300" if index % 4 >= 2 else "000") + ("%03d" % (101 + index))
        iid = "SZSE." + code
        scale = Decimal(1) + Decimal(index % 4) / 5
        bases[iid] = scale
        family = "芯材" if index < 4 else "智造" if index < 8 else "金融"
        instrument = {"id": iid, "code": code, "name": "模拟%s%d" % (family, index % 4 + 1),
                      "exchange": "SZSE", "board": "CHINEXT" if code.startswith("300") else "MAIN",
                      "listed_on": "2020-01-01", "status": "active", "valid_from": "2020-01-01", "valid_to": None,
                      "available_at": "2020-01-01T00:00:00Z"}
        instruments.append(instrument)
        for sid in (["chips", "ai"] if index < 4 else ["robotics"] if index < 8 else ["finance"]):
            memberships.append({"instrument_id": iid, "sector_id": sid, "valid_from": "2020-01-01", "valid_to": None,
                                "available_at": "2020-01-01T00:00:00Z", "provider": SOURCE, "snapshot_id": "fixture-members-v1"})
        for day in past:
            daily.append({"instrument_id": iid, "date": day.isoformat(), "high": _p(10 * scale), "low": _p(Decimal("9.5") * scale),
                          "close": _p(Decimal("9.8") * scale), "prev_close": _p(Decimal("9.8") * scale),
                          "amount_cny": "50000000", "adjustment_factor": "1", "available_at": _iso(_time(day, 15 * 60 + 1))})
    # Explicitly excluded records make the denominator and scope inspectable.
    for code, board, status, name in [("688001", "STAR", "active", "模拟科创排除"), ("000999", "MAIN", "st", "模拟ST排除"),
                                      ("000998", "MAIN", "suspended", "模拟停牌排除")]:
        instruments.append({"id": "SSE." + code if board == "STAR" else "SZSE." + code, "code": code, "name": name,
                            "exchange": "SSE" if board == "STAR" else "SZSE", "board": board, "status": status,
                            "listed_on": "2020-01-01", "valid_from": "2020-01-01", "valid_to": None,
                            "available_at": "2020-01-01T00:00:00Z"})
    benchmark_id = "FIXTURE.BENCHMARK"
    benchmark_daily = [{"instrument_id": benchmark_id, "date": day.isoformat(), "high": _p(98 + index * 0.1 + 0.5),
                        "low": _p(98 + index * 0.1 - 0.5), "close": _p(98 + index * 0.1),
                        "prev_close": _p(97.9 + index * 0.1), "amount_cny": "1000000000", "adjustment_factor": "1",
                        "available_at": _iso(_time(day, 15 * 60 + 1))} for index, day in enumerate(past)]
    stages = [(600, "9.95", "盘中观察：未突破整理上沿"), (601, "10.12", "板块启动与个股突破：预警"),
              (602, "10.30", "持续共振：增强确认"), (603, "10.90", "价格偏离：暂停可参与提醒"),
              (604, "10.38", "价格回归：更新原机会"), (605, "10.40", "断源注入：缺一只行情，暂停新机会"),
              (606, "10.42", "数据恢复：重新积累确认"), (607, "9.60", "跌破冻结结构位：失效"),
              (608, "9.65", "退出后重置观察"), (609, "10.15", "新一轮突破：独立episode"),
              (631, "10.20", "参与窗口到期：过期更新")]
    history = []
    # Same-minute curves from the same comparable members on three prior days.
    for instrument in instruments[:12]:
        iid, scale = instrument["id"], bases[instrument["id"]]
        for day in past[-3:]:
            for minute in range(596, 632):
                history.append(_quote(iid, day, minute, Decimal("9.8") * scale, Decimal("9.8") * scale))
        for minute in range(596, 600):
            value = Decimal("9.83") + Decimal(minute - 596) * Decimal("0.03")
            history.append(_quote(iid, DAY, minute, value * scale, Decimal("9.8") * scale, activity="1.9"))
    batches = []
    for index, (minute, semiprice, description) in enumerate(stages):
        quotes = []
        for pos, instrument in enumerate(instruments[:12]):
            iid, scale = instrument["id"], bases[instrument["id"]]
            value = Decimal(semiprice) if pos < 4 else Decimal("9.84") + Decimal(index) * Decimal("0.001") if pos < 8 else Decimal("9.75")
            q = _quote(iid, DAY, minute, value * scale, Decimal("9.8") * scale, activity="1.9" if pos < 4 else "1")
            quotes.append(q)
        benchmark_minutes = [_quote(benchmark_id, DAY, m, Decimal("100") + Decimal(m - 596) * Decimal("0.001"), "99.4") for m in range(596, minute + 1)]
        current_history = deepcopy(history)
        if minute == 631:
            # The late TTL observation has its own complete window references.
            for instrument in instruments[:12]:
                for m in range(610, 631):
                    current_history.append(_quote(instrument["id"], DAY, m, Decimal("10.2") * bases[instrument["id"]], Decimal("9.8") * bases[instrument["id"]], activity="1.9"))
        batch = {"schema_version": 1, "snapshot_id": "fixture-%02d" % index, "source": SOURCE, "simulated": True,
                 "as_of": _iso(_time(DAY, minute)), "description": description, "calendar": deepcopy(calendar),
                 "units": {"volume": "shares", "amount": "CNY", "amount_mode": "cumulative"},
                 "instruments": deepcopy(instruments), "sectors": deepcopy(sectors), "memberships": deepcopy(memberships),
                 "quotes": deepcopy(quotes if index != 5 else quotes[1:]), "daily_bars": deepcopy(daily),
                 "minute_history": current_history,
                 "benchmark": {"id": benchmark_id, "quote": benchmark_minutes[-1], "daily_bars": deepcopy(benchmark_daily), "minute_history": benchmark_minutes}}
        history.extend(quotes)
        batches.append(batch)
    return batches


def fixture_batches(version=2):
    """Version 1 is byte-for-value compatible; version 2 adds STAR examples."""
    if type(version) is not int or version not in (1, 2):
        raise ValueError("合成样例版本须为1或2")
    batches = _fixture_v1_batches()
    if version == 1:
        return batches
    for batch in batches:
        batch.update(snapshot_id=batch["snapshot_id"].replace("fixture-", "fixture-v2-"), source="synthetic-fixture-v2-star")
        # Three new stocks share historical inputs only inside this explicitly
        # synthetic tape. The original v1 records are never rewritten on disk.
        for number in range(3):
            original = batch["instruments"][number]
            code = "68810%d" % (number + 1)
            instrument = deepcopy(original)
            instrument.update(id="SSE." + code, code=code, name="模拟科创%d" % (number + 1), exchange="SSE", board="STAR")
            batch["instruments"].append(instrument)
            for collection in ("quotes", "daily_bars", "minute_history", "memberships"):
                copied = [deepcopy(row) for row in batch[collection] if row["instrument_id"] == original["id"]]
                for row in copied:
                    row["instrument_id"] = instrument["id"]
                batch[collection].extend(copied)
        # Complete legacy quotes are available in neighbouring snapshots;
        # the fault slice specifically removes a STAR quote from its denominator.
        if "断源注入" in batch.get("description", ""):
            original_quote = _quote("SZSE.000101", DAY, 605, "10.40", "9.8", activity="1.9")
            batch["quotes"].insert(0, original_quote)
            batch["quotes"] = [q for q in batch["quotes"] if q["instrument_id"] != "SSE.688101"]
            batch["description"] = "断源注入：缺一只科创板行情，暂停新机会"
        excluded = deepcopy(batch["instruments"][0])
        for code, exchange, board, status, name in (("688998", "SSE", "STAR", "st", "模拟科创ST排除"),
                                                    ("688997", "SSE", "STAR", "suspended", "模拟科创停牌排除"),
                                                    ("920001", "BSE", "BSE", "active", "模拟北交所范围外")):
            item = deepcopy(excluded)
            item.update(id=exchange + "." + code, code=code, exchange=exchange, board=board, status=status, name=name)
            batch["instruments"].append(item)
        next(i for i in batch["instruments"] if i["id"] == "SSE.688001")["name"] = "模拟科创历史不足"
        for collection in ("quotes", "daily_bars", "minute_history", "memberships"):
            for row in batch[collection]:
                if "source" in row:
                    row["source"] = batch["source"]
                if "provider" in row:
                    row.update(provider=batch["source"], snapshot_id="fixture-members-v2-star")
    return batches
