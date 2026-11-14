"""Conservative independent-signal simulations, never orders or actual fills."""
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from statistics import mean, median
from zoneinfo import ZoneInfo

from .contracts import day, fields, integer, numeric, string, utc
from .config import MARKET_PAIRS
from .store import digest
from .temporal import effective_interval

SHANGHAI = ZoneInfo("Asia/Shanghai")
FEE_KEYS = ("commission_fraction", "minimum_commission", "buy_transfer_fraction", "sell_transfer_fraction", "sell_tax_fraction")
EXECUTION_KEYS = ("status", "can_buy", "can_sell", "available_volume_shares", "limit_state", "limit_up", "limit_down", "rule_version", "available_at")
RULE_KEYS = ("id", "exchange", "board", "valid_from", "valid_to", "available_at", "source_urls", "verified", "buy_lot", "max_order_shares", "tick_size", "sell_delay_sessions", "valuation_sessions", "fees", "slippage_buy_fraction", "slippage_sell_fraction")
RULE_V2_KEYS = tuple(k for k in RULE_KEYS if k != "buy_lot") + ("schema_version", "order_type", "buy_min_shares", "buy_step_shares", "sell_min_shares", "sell_step_shares", "sell_odd_lot_full_exit")


def validate_execution(value):
    fields(value, EXECUTION_KEYS, "execution")
    if value["status"] not in ("trading", "suspended", "delisted", "unknown"):
        raise ValueError("execution.status无效")
    for key in ("can_buy", "can_sell"):
        if value[key] is not None and type(value[key]) is not bool:
            raise ValueError("execution买卖资格须为布尔值或null")
    if value["available_volume_shares"] is not None:
        integer(value["available_volume_shares"], 0, 10**12, "可成交量")
    if value["limit_state"] not in ("bounded", "unbounded", "unknown"):
        raise ValueError("涨跌停状态无效")
    limits = [numeric(value[k], k, low=Decimal("0.000001"), nullable=True) for k in ("limit_down", "limit_up")]
    if value["limit_state"] == "bounded" and (None in limits or limits[0] >= limits[1]):
        raise ValueError("有涨跌停限制时须提供有效上下限")
    if value["limit_state"] != "bounded" and any(v is not None for v in limits):
        raise ValueError("未知或无限制时不得伪造涨跌停价")
    string(value["rule_version"], "execution.rule_version")
    utc(value["available_at"])


def validate_rules(rules):
    if not isinstance(rules, list) or not rules:
        raise ValueError("须显式提供版本化执行规则")
    ids = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("执行规则须为对象")
        schema = rule.get("schema_version", 1)
        if type(schema) is not int or schema not in (1, 2) or (schema == 1 and "schema_version" in rule):
            raise ValueError("执行规则schema须为2；历史v1格式不含schema_version")
        fields(rule, RULE_V2_KEYS if schema == 2 else RULE_KEYS, "执行规则")
        string(rule["id"], "规则ID")
        if rule["id"] in ids:
            raise ValueError("规则ID不得重复")
        ids.add(rule["id"])
        if (rule["exchange"], rule["board"]) not in MARKET_PAIRS:
            raise ValueError("执行规则交易所与板块组合无效")
        if rule["board"] == "STAR" and schema != 2:
            raise ValueError("科创板执行规则须使用schema_version=2，明确最小数量和递增单位")
        start = day(rule["valid_from"])
        end = day(rule["valid_to"]) if rule["valid_to"] is not None else None
        if end is not None and start >= end:
            raise ValueError("执行规则有效区间无效")
        utc(rule["available_at"])
        if type(rule["verified"]) is not bool or not isinstance(rule["source_urls"], list) or not rule["source_urls"]:
            raise ValueError("执行规则须声明核验状态和来源")
        for source in rule["source_urls"]:
            string(source, "规则来源")
        if schema == 1:
            integer(rule["buy_lot"], 1, 10**6, "买入单位")
            minimum = rule["buy_lot"]
        else:
            for key in ("buy_min_shares", "buy_step_shares", "sell_min_shares", "sell_step_shares"):
                integer(rule[key], 1, 10**6, key)
            if rule["order_type"] not in ("limit", "market") or type(rule["sell_odd_lot_full_exit"]) is not bool:
                raise ValueError("申报类型或零股全额卖出声明无效")
            minimum = rule["buy_min_shares"]
        integer(rule["max_order_shares"], minimum, 10**9, "最大申报量")
        if rule["board"] == "STAR":
            if (rule["buy_min_shares"], rule["buy_step_shares"], rule["sell_min_shares"], rule["sell_step_shares"], rule["sell_odd_lot_full_exit"]) != (200, 1, 200, 1, True):
                raise ValueError("科创板须区分200股最低申报量、1股递增及不足200股全额卖出")
            if rule["max_order_shares"] > (100000 if rule["order_type"] == "limit" else 50000) or numeric(rule["tick_size"], "价格单位") != Decimal("0.01"):
                raise ValueError("科创板申报上限或价格单位无效")
        integer(rule["sell_delay_sessions"], 1, 100, "可卖交易日间隔")
        numeric(rule["tick_size"], "价格单位", low=Decimal("0.000001"))
        sessions = rule["valuation_sessions"]
        if not isinstance(sessions, list) or not sessions:
            raise ValueError("须声明完整估值分钟时段")
        previous = -1
        for session in sessions:
            if not isinstance(session, list) or len(session) != 2:
                raise ValueError("估值时段格式无效")
            if any(not isinstance(x, str) for x in session):
                raise ValueError("估值时段格式无效")
            a, b = [datetime.strptime(x, "%H:%M").time() for x in session]
            left, right = a.hour * 60 + a.minute, b.hour * 60 + b.minute
            if not previous <= left < right:
                raise ValueError("估值时段须有序且不重叠")
            previous = right
        fields(rule["fees"], FEE_KEYS, "费用")
        for key in FEE_KEYS:
            numeric(rule["fees"][key], key, high=None if key == "minimum_commission" else Decimal(1), nullable=True)
        for key in ("slippage_buy_fraction", "slippage_sell_fraction"):
            numeric(rule[key], key, high=Decimal("0.5"), nullable=True)
    for index, left in enumerate(rules):
        for right in rules[index + 1:]:
            if (left["exchange"], left["board"]) == (right["exchange"], right["board"]):
                a, b = day(left["valid_from"]), day(right["valid_from"])
                x = day(left["valid_to"]) if left["valid_to"] else datetime.max.date()
                y = day(right["valid_to"]) if right["valid_to"] else datetime.max.date()
                if max(a, b) < min(x, y):
                    raise ValueError("同一市场/板块执行规则有效区间重叠")


def money(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _fee(notional, rule, side):
    fee = rule["fees"]
    commission = max(numeric(fee["minimum_commission"], "最低佣金"), notional * numeric(fee["commission_fraction"], "佣金"))
    transfer = notional * numeric(fee[side + "_transfer_fraction"], "过户费用")
    tax = notional * numeric(fee["sell_tax_fraction"], "卖出税费") if side == "sell" else Decimal(0)
    return money(commission) + money(transfer) + money(tax)


def _fill_price(quote, rule, side):
    tick = numeric(rule["tick_size"], "价格单位")
    slip = numeric(rule["slippage_" + side + "_fraction"], "滑点")
    value = numeric(quote["close"], "价格", low=tick) * (1 + slip if side == "buy" else 1 - slip)
    return (value / tick).to_integral_value(rounding=ROUND_CEILING if side == "buy" else ROUND_FLOOR) * tick


class Tape:
    """Index only newly completed, visible quotes in recorded arrival order."""
    def __init__(self, batches):
        self.rows, self.benchmarks, self.actions = {}, {}, {}
        self.calendars = [(utc(b["as_of"]), b["calendar"]) for b in batches]
        self.gaps = Counter()
        seen, last, actions_seen = {}, {}, {}
        self.last_cutoff = max(utc(b["as_of"]) for b in batches)
        for batch in batches:
            cutoff = utc(batch["as_of"])
            instruments = {i["id"]: i for i in batch.get("instruments", [])}
            for quote in list(batch.get("quotes", [])) + ([batch["benchmark"]["quote"]] if batch.get("benchmark", {}).get("quote") else []):
                try:
                    event, available, ingested = [utc(quote[k]) for k in ("event_time", "available_at", "ingested_at")]
                    prices = [numeric(quote[k], k, low=Decimal("0.000001")) for k in ("close", "high", "low", "adjustment_factor")]
                    if not (prices[2] <= prices[0] <= prices[1]) or quote["is_complete"] is not True or quote["interval"] != 60 or quote["quality"] != "good":
                        raise ValueError()
                    if not event <= available <= ingested <= cutoff or event != cutoff.replace(second=0, microsecond=0):
                        raise ValueError()
                    key = (quote["instrument_id"], event, quote["revision"])
                    sha = digest(quote)
                    if key in seen:
                        if seen[key] != sha:
                            raise ValueError("QUOTE_REVISION_CONFLICT")
                        continue
                    seen[key] = sha
                    if event <= last.get(quote["instrument_id"], datetime.min.replace(tzinfo=event.tzinfo)):
                        self.gaps["LATE_REVISION_NOT_A_NEW_FILL"] += 1
                        continue
                    last[quote["instrument_id"]] = event
                    instrument = instruments.get(quote["instrument_id"])
                    row = {"q": quote, "event": event, "cutoff": cutoff, "instrument": instrument,
                           "calendar": batch["calendar"], "snapshot_id": batch["snapshot_id"]}
                    if quote["instrument_id"] == batch.get("benchmark", {}).get("id"):
                        self.benchmarks.setdefault(quote["instrument_id"], []).append(row)
                    else:
                        self.rows.setdefault(quote["instrument_id"], []).append(row)
                except (KeyError, TypeError, ValueError) as exc:
                    if str(exc) == "QUOTE_REVISION_CONFLICT":
                        raise
                    self.gaps["INVALID_OR_NOT_VISIBLE_QUOTE"] += 1
            for action in batch.get("corporate_actions", []):
                validate_action(action)
                sha = digest(action)
                if action["id"] in actions_seen and actions_seen[action["id"]] != sha:
                    raise ValueError("公司行为ID载荷冲突，须使用新修订ID")
                if action["id"] not in actions_seen and utc(action["available_at"]) <= cutoff:
                    self.actions.setdefault(action["instrument_id"], []).append({**action, "received_at": cutoff})
                    actions_seen[action["id"]] = sha


def validate_action(action):
    fields(action, ("id", "instrument_id", "type", "effective_at", "available_at", "share_multiplier", "cash_net_per_old_share", "factor_from", "factor_to", "source"), "corporate_action")
    for key in ("id", "instrument_id", "source"):
        string(action[key], key)
    if action["type"] not in ("split_dividend", "unsupported"):
        raise ValueError("公司行为类型无效")
    utc(action["effective_at"])
    utc(action["available_at"])
    numeric(action["share_multiplier"], "股份倍率", low=Decimal("0.000001"), nullable=True)
    numeric(action["cash_net_per_old_share"], "每旧股净现金", nullable=True)
    for key in ("factor_from", "factor_to"):
        numeric(action[key], key, low=Decimal("0.000001"), nullable=True)


def _rule(row, rules):
    instrument = row["instrument"]
    if not instrument:
        return None
    start, end = effective_interval(instrument)
    if utc(instrument["available_at"]) > row["cutoff"] or (start and start > row["cutoff"]) or (end and end <= row["cutoff"]):
        return None
    today = row["event"].astimezone(SHANGHAI).date()
    return next((r for r in rules if r["exchange"] == instrument["exchange"] and r["board"] == instrument["board"]
                 and day(r["valid_from"]) <= today and (r["valid_to"] is None or today < day(r["valid_to"]))
                 and utc(r["available_at"]) <= row["cutoff"]), None)


def _executable(row, rule, side, quantity=None, purpose="fixture"):
    if rule is None:
        return "RULE_OR_INSTRUMENT_NOT_VISIBLE"
    if purpose != "fixture" and rule["verified"] is not True:
        return "RULES_AND_COSTS_NOT_VERIFIED"
    if any(value is None for value in rule["fees"].values()) or rule["slippage_" + side + "_fraction"] is None:
        return "COST_MODEL_INCOMPLETE"
    execution = row["q"].get("execution")
    if execution is None:
        return "EXECUTION_UNSPECIFIED"
    validate_execution(execution)
    if utc(execution["available_at"]) > row["cutoff"] or execution["rule_version"] != rule["id"]:
        return "EXECUTION_NOT_VISIBLE_OR_RULE_MISMATCH"
    if execution["status"] == "unknown":
        return "EXECUTION_UNKNOWN"
    status = row["instrument"]["status"]
    if execution["status"] != "trading" or status in ("suspended", "delisted") or (side == "buy" and status != "active") or execution["can_" + side] is False:
        return side.upper() + "_BLOCKED"
    if execution["can_" + side] is None or execution["available_volume_shares"] is None or execution["limit_state"] == "unknown":
        return "EXECUTION_UNKNOWN"
    if quantity is not None and (quantity > execution["available_volume_shares"] or quantity > rule["max_order_shares"]):
        return "INSUFFICIENT_EXECUTABLE_VOLUME"
    if quantity is not None and rule.get("schema_version") == 2:
        minimum, step = rule[side + "_min_shares"], rule[side + "_step_shares"]
        # This study always closes the entire independent sample; an odd-lot
        # allowance never fabricates a partial sale or a portfolio balance.
        odd_exit = side == "sell" and rule["sell_odd_lot_full_exit"] and 0 < quantity < minimum
        if not odd_exit and (quantity < minimum or (quantity - minimum) % step):
            return "ORDER_QUANTITY_INVALID"
    fill = _fill_price(row["q"], rule, side)
    if execution["limit_state"] == "bounded":
        low, high = numeric(execution["limit_down"], "跌停价"), numeric(execution["limit_up"], "涨停价")
        if not low <= fill <= high or (side == "buy" and fill >= high) or (side == "sell" and fill <= low):
            return "LIMIT_OR_SLIPPAGE_BLOCKED"
    return None


def _target(calendar, entry, days):
    dates = sorted(day(d) for d in calendar["trading_dates"])
    today = entry.astimezone(SHANGHAI).date()
    future = [d for d in dates if d > today]
    if len(future) < days or not calendar.get("close_time"):
        return None
    return datetime.combine(future[days - 1], datetime.strptime(calendar["close_time"], "%H:%M").time(), SHANGHAI)


def _complete_window(rows, calendar, rule, start, end):
    observed = {r["event"] for r in rows if start < r["event"] <= end}
    for value in calendar["trading_dates"]:
        today = day(value)
        if not start.astimezone(SHANGHAI).date() <= today <= end.astimezone(SHANGHAI).date():
            continue
        for a, b in rule["valuation_sessions"]:
            instant = datetime.combine(today, datetime.strptime(a, "%H:%M").time(), SHANGHAI) + timedelta(minutes=1)
            finish = datetime.combine(today, datetime.strptime(b, "%H:%M").time(), SHANGHAI)
            while instant <= finish:
                if start < instant <= end and instant not in observed:
                    return False
                instant += timedelta(minutes=1)
    return True


def simulate(signal, alert, events, tape, plan, delay, horizon, exit_mode, split):
    result = {"signal_id": signal["id"], "delay_minutes": delay, "holding_days": horizon, "exit_mode": exit_mode,
              "split": split["name"], "status": "pending", "reason_code": None, "entry": None, "exit": None,
              "net_return": None, "gross_return": None, "net_pnl_cny": None, "benchmark_excess": None,
              "max_favorable": None, "max_adverse": None, "structure_failure": None, "revenue_failure": None,
              "cluster": [signal["trading_date"], signal.get("evidence", {}).get("notification_group", {}).get("id") or signal.get("primary_sector_id") or signal["instrument_id"]]}
    rows = tape.rows.get(signal["instrument_id"], [])
    ready = utc(alert["at"]) + timedelta(seconds=plan["delivery_delay_seconds"], minutes=delay)
    expires = utc(signal["expires_at"])
    if ready >= utc(split["end"]) or expires >= utc(split["end"]):
        result.update(status="purged", reason_code="ENTRY_WINDOW_CROSSES_SPLIT_BOUNDARY")
        return result
    if ready >= expires:
        result.update(status="not_filled", reason_code="EXPIRED_BEFORE_REACTION")
        return result
    candidates = [r for r in rows if r["event"] > ready and r["cutoff"] > ready and r["event"] < expires]
    missing, rejected = [], []
    entry_row, buy_rule = None, None
    for row in candidates:
        latest = next((e for e in reversed(events) if utc(e["at"]) <= row["cutoff"]), None)
        snapshot = latest.get("snapshot", {}) if latest else signal
        if latest and latest.get("to_status") in ("INVALIDATED", "EXPIRED"):
            rejected.append("SIGNAL_NO_LONGER_ACTIVE")
            break
        if snapshot.get("actionability", "eligible") != "eligible":
            (missing if snapshot["actionability"] == "paused" else rejected).append("SIGNAL_NOT_ACTIONABLE")
            continue
        rule = _rule(row, plan["rules"])
        reason = _executable(row, rule, "buy", purpose=plan["purpose"])
        if reason:
            (missing if reason not in {"BUY_BLOCKED", "LIMIT_OR_SLIPPAGE_BLOCKED", "INSUFFICIENT_EXECUTABLE_VOLUME"} else rejected).append(reason)
            continue
        fill = _fill_price(row["q"], rule, "buy")
        if not numeric(signal["entry_low"], "入场下限") < fill <= numeric(signal["entry_high"], "入场上限"):
            rejected.append("OUTSIDE_ENTRY_RANGE")
            continue
        capital = numeric(plan["capital_per_signal"], "独立样本预算")
        minimum = rule["buy_min_shares"] if rule.get("schema_version") == 2 else rule["buy_lot"]
        step = rule["buy_step_shares"] if rule.get("schema_version") == 2 else rule["buy_lot"]
        upper = min(int(capital / fill), rule["max_order_shares"])
        quantity = minimum + (upper - minimum) // step * step if upper >= minimum else 0
        while quantity > 0 and fill * quantity + _fee(fill * quantity, rule, "buy") > capital:
            quantity -= step
            if quantity < minimum:
                quantity = 0
        reason = "BUDGET_BELOW_LOT" if not quantity else _executable(row, rule, "buy", quantity, plan["purpose"])
        if reason:
            rejected.append(reason)
            continue
        entry_row, buy_rule, buy_price, shares = row, rule, fill, Decimal(quantity)
        break
    if entry_row is None:
        earlier_calendars = [(t, c) for t, c in tape.calendars if t <= ready]
        calendar = max(earlier_calendars, key=lambda item: item[0])[1] if earlier_calendars else None
        known_rule = next((_rule(r, plan["rules"]) for r in candidates if _rule(r, plan["rules"]) is not None), None)
        if known_rule is None:
            known_rule = next((_rule(r, plan["rules"]) for r in reversed(rows) if r["cutoff"] <= ready and _rule(r, plan["rules"]) is not None), None)
        complete = bool(calendar and known_rule and _complete_window(candidates, calendar, known_rule, ready, expires - timedelta(microseconds=1)))
        if not candidates and complete:
            result.update(status="not_filled", reason_code="NO_TRADING_MINUTE_BEFORE_TTL")
            return result
        result.update(status="pending" if missing or not complete or tape.last_cutoff < expires else "not_filled",
                      reason_code=missing[0] if missing else (rejected[0] if rejected else "NO_EXECUTABLE_QUOTE_BEFORE_TTL"))
        return result
    if numeric(entry_row["q"]["adjustment_factor"], "入场因子") != numeric(signal["evidence"]["adjustment_factor"], "触发因子"):
        result["reason_code"] = "CORPORATE_ACTION_BEFORE_ENTRY"
        return result
    close_at = _target(entry_row["calendar"], entry_row["event"], horizon)
    if close_at is None:
        result["reason_code"] = "CALENDAR_WINDOW_INCOMPLETE"
        return result
    if close_at >= utc(split["end"]):
        result.update(status="purged", reason_code="LABEL_CROSSES_SPLIT_BOUNDARY")
        return result
    buy_notional = buy_price * shares
    buy_fee = _fee(buy_notional, buy_rule, "buy")
    invested = buy_notional + buy_fee
    result["entry"] = {"at": entry_row["q"]["event_time"], "known_at": entry_row["q"]["available_at"],
                       "price": str(buy_price), "quantity": str(shares), "fee_cny": str(buy_fee),
                       "rule_version": buy_rule["id"], "snapshot_id": entry_row["snapshot_id"]}
    factor = numeric(entry_row["q"]["adjustment_factor"], "复权因子")
    stop = numeric(signal["invalidation_price"], "冻结结构位")
    cash, structure, request, request_reason = Decimal(0), False, None, None
    applied, values, post_rows = set(), [], []
    failure_events = [utc(e["at"]) for e in events if e.get("to_status") == "INVALIDATED"]
    dates = sorted(day(d) for d in entry_row["calendar"]["trading_dates"])
    entry_day = entry_row["event"].astimezone(SHANGHAI).date()
    sell_days = [d for d in dates if d > entry_day]
    if len(sell_days) < buy_rule["sell_delay_sessions"]:
        result["reason_code"] = "SETTLEMENT_CALENDAR_INCOMPLETE"
        return result
    first_sell_day = sell_days[buy_rule["sell_delay_sessions"] - 1]
    for row in rows:
        if row["event"] <= entry_row["event"]:
            continue
        if row["event"] >= utc(split["end"]):
            break
        if exit_mode == "fixed" and row["event"] > close_at:
            result["reason_code"] = result["reason_code"] or "TARGET_CLOSE_MISSING"
            break
        for action in tape.actions.get(signal["instrument_id"], []):
            effective = utc(action["effective_at"])
            if action["id"] in applied or not entry_row["event"] < effective <= row["event"]:
                continue
            if (utc(action["available_at"]) > effective or action["received_at"] > row["cutoff"] or
                    action["type"] != "split_dividend" or any(action[k] is None for k in ("share_multiplier", "cash_net_per_old_share", "factor_from", "factor_to"))):
                result["reason_code"] = "CORPORATE_ACTION_UNRESOLVED"
                return result
            if numeric(action["factor_from"], "旧因子") != factor:
                result["reason_code"] = "CORPORATE_ACTION_FACTOR_MISMATCH"
                return result
            multiplier = numeric(action["share_multiplier"], "股份倍率")
            dividend = numeric(action["cash_net_per_old_share"], "每股净现金")
            cash += shares * dividend
            shares *= multiplier
            stop = (stop - dividend) / multiplier
            factor = numeric(action["factor_to"], "新因子")
            if shares != shares.to_integral_value() or stop <= 0:
                result["reason_code"] = "CORPORATE_ACTION_FRACTIONAL_OR_INVALID"
                return result
            applied.add(action["id"])
        if numeric(row["q"]["adjustment_factor"], "最新因子") != factor:
            result["reason_code"] = "CORPORATE_ACTION_UNRESOLVED"
            return result
        post_rows.append(row)
        high = numeric(row["q"]["high"], "最高价") * shares + cash
        low = numeric(row["q"]["low"], "最低价") * shares + cash
        values.append((high / buy_notional - 1, low / buy_notional - 1))
        if numeric(row["q"]["low"], "最低价") <= stop or any(t <= row["cutoff"] for t in failure_events):
            structure = True
        if request is None:
            if exit_mode == "risk" and (structure or low <= invested * (1 - numeric(plan["max_loss_fraction"], "风险边界"))):
                request, request_reason = row["cutoff"], "STRUCTURE_OR_COST_RISK"
            elif row["event"] >= close_at:
                request, request_reason = close_at, "HOLDING_WINDOW_END"
        # An intrabar stop is observable at completion. Never fabricate a fill
        # at the frozen stop, and never sell the new purchase on its buy day.
        eligible_time = request is not None and (row["event"] > request or (request_reason == "HOLDING_WINDOW_END" and row["event"] == request))
        if not eligible_time or row["event"].astimezone(SHANGHAI).date() < first_sell_day:
            continue
        rule = _rule(row, plan["rules"])
        reason = _executable(row, rule, "sell", int(shares), plan["purpose"])
        if reason:
            result["reason_code"] = reason
            if exit_mode == "fixed":
                break
            continue
        sell_price = _fill_price(row["q"], rule, "sell")
        proceeds = sell_price * shares
        sell_fee = _fee(proceeds, rule, "sell")
        pnl = money(proceeds + cash - sell_fee - invested)
        complete = _complete_window(post_rows, entry_row["calendar"], buy_rule, entry_row["event"], row["event"])
        result.update(status="closed", reason_code=None, exit={"at": row["q"]["event_time"], "price": str(sell_price),
                      "quantity": str(shares), "fee_cny": str(sell_fee), "cash_net_receivable_cny": str(money(cash)),
                      "rule_version": rule["id"], "reason": request_reason, "snapshot_id": row["snapshot_id"]},
                      net_return=float(pnl / invested), gross_return=float((proceeds + cash) / buy_notional - 1),
                      net_pnl_cny=str(pnl), structure_failure=True if structure else False if complete else None,
                      revenue_failure=pnl < 0, max_favorable=float(max(v[0] for v in values)) if complete else None,
                      max_adverse=float(min(v[1] for v in values)) if complete else None,
                      window_coverage="complete" if complete else "gapped", corporate_action_ids=sorted(applied))
        benchmark = tape.benchmarks.get(plan["benchmark_id"], [])
        start_price = next((r["q"] for r in benchmark if r["event"] == entry_row["event"]), None)
        end_price = next((r["q"] for r in benchmark if r["event"] == row["event"]), None)
        if start_price and end_price:
            benchmark_return = numeric(end_price["close"], "基准价格") * numeric(end_price["adjustment_factor"], "基准因子") / (numeric(start_price["close"], "基准价格") * numeric(start_price["adjustment_factor"], "基准因子")) - 1
            result["benchmark_excess"] = float(pnl / invested - benchmark_return)
        return result
    result.update(reason_code=result["reason_code"] or "EXIT_NOT_YET_EXECUTABLE_OR_WINDOW_INCOMPLETE", structure_failure=True if structure else None)
    return result


def summarize(samples):
    counts = Counter(s["status"] for s in samples)
    closed = [s for s in samples if s["status"] == "closed"]
    values = [s["net_return"] for s in closed]
    structural = [s for s in samples if s["structure_failure"] is not None]
    eligible = len(samples) - counts["purged"]
    filled = sum(s["entry"] is not None for s in samples)
    entry_decisions = filled + counts["not_filled"]
    def metric(name):
        known = [s[name] for s in closed if s[name] is not None]
        return {"mean": mean(known) if known else None, "denominator": len(known)}
    return {"total": len(samples), "eligible_denominator": eligible, "status_counts": dict(counts),
            "reason_counts": dict(Counter(s["reason_code"] for s in samples if s["reason_code"])),
            "not_filled_count": counts["not_filled"], "not_filled_fraction": counts["not_filled"] / eligible if eligible else None,
            "filled_count": filled, "entry_decision_denominator": entry_decisions,
            "participation_fraction": filled / entry_decisions if entry_decisions else None,
            "entry_pending_count": sum(s["status"] == "pending" and s["entry"] is None for s in samples),
            "closed_count": len(closed), "net_return_mean": mean(values) if values else None,
            "net_return_median": median(values) if values else None,
            "benchmark_excess": metric("benchmark_excess"), "max_favorable": metric("max_favorable"), "max_adverse": metric("max_adverse"),
            "revenue_failures": sum(s["revenue_failure"] for s in closed), "revenue_failure_denominator": len(closed),
            "structure_failures": sum(s["structure_failure"] for s in structural), "structure_failure_denominator": len(structural)}
