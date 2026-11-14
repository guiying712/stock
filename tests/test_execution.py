from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest

from stockradar.execution import Tape, simulate, summarize, validate_execution, validate_rules
from stockradar.research import _cluster_interval, run_study, validate_study_plan
from stockradar.study_fixture import make_study_fixture


def at(day, minute):
    return "2026-10-%02dT02:%02d:00+00:00" % (day, minute)


class ExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture, cls.fixture_plan = make_study_fixture(9)

    def setUp(self):
        self.plan = deepcopy(self.fixture_plan)
        self.plan["holding_windows_days"] = [1]
        self.plan["reaction_delays_minutes"] = [0]
        self.rule = next(r for r in self.plan["rules"] if r["exchange"] == "SZSE" and r["board"] == "MAIN")
        for rule in self.plan["rules"]:
            rule["valuation_sessions"] = [["10:00", "10:03"]]
            rule["slippage_buy_fraction"] = rule["slippage_sell_fraction"] = "0"
        self.signal = {"id": "s1", "instrument_id": "SZSE.000001", "trading_date": "2026-10-19",
                       "entry_low": "10", "entry_high": "10.50", "expires_at": at(19, 3),
                       "invalidation_price": "9.70", "primary_sector_id": "chips", "evidence": {"adjustment_factor": "1"}}
        self.alert = {"at": at(19, 0)}
        self.split = {"name": "train", "start": "2026-10-18T00:00:00Z", "end": "2026-10-22T00:00:00Z"}
        self.calendar = {"version": "test", "close_time": "10:03", "trading_dates": ["2026-10-19", "2026-10-20", "2026-10-21"],
                         "sessions": [["10:00", "10:03"]]}
        self.instrument = {"id": "SZSE.000001", "exchange": "SZSE", "board": "MAIN", "status": "active",
                           "valid_from": "2000-01-01", "valid_to": None, "available_at": "2000-01-01T00:00:00Z"}
        self.batches = [self.batch(19, 0, None)] + [self.batch(d, m, "10.10" if d == 19 else "11") for d in (19, 20, 21) for m in (1, 2, 3)]

    def batch(self, day, minute, price):
        quote = {"instrument_id": "SZSE.000001", "event_time": at(day, minute), "available_at": at(day, minute), "ingested_at": at(day, minute),
                 "close": price, "high": price, "low": price, "adjustment_factor": "1", "interval": 60, "is_complete": True,
                 "quality": "good", "revision": 1,
                 "execution": {"status": "trading", "can_buy": True, "can_sell": True, "available_volume_shares": 1000000,
                               "limit_state": "bounded", "limit_up": "15", "limit_down": "5", "rule_version": self.rule["id"], "available_at": at(day, minute)}}
        benchmark = {**quote, "instrument_id": "BENCH", "close": "100" if day == 19 else "101", "high": "101", "low": "99"}
        return {"as_of": at(day, minute), "snapshot_id": "b-%d-%d" % (day, minute), "calendar": deepcopy(self.calendar),
                "instruments": [deepcopy(self.instrument)], "quotes": [quote] if price is not None else [],
                "benchmark": {"id": "BENCH", "quote": benchmark if price is not None else None}, "corporate_actions": []}

    def simulate(self, mode="fixed", delay=0, batches=None, events=()):
        self.plan["benchmark_id"] = "BENCH"
        return simulate(self.signal, self.alert, events, Tape(batches or self.batches), self.plan, delay, 1, mode, self.split)

    def use_star(self):
        self.rule = next(r for r in self.plan["rules"] if r["board"] == "STAR")
        self.signal["instrument_id"] = "SSE.688101"
        for batch in self.batches:
            batch["instruments"][0].update(id="SSE.688101", exchange="SSE", board="STAR")
            for quote in batch["quotes"]:
                quote["instrument_id"] = "SSE.688101"
                quote["execution"]["rule_version"] = self.rule["id"]

    def test_star_minimum_is_200_but_increment_is_one_with_buy_fees(self):
        self.use_star()
        for budget, expected in (("2020", None), ("2025.02", "200"), ("2035.12", "201")):
            self.plan["capital_per_signal"] = budget
            result = self.simulate()
            with self.subTest(budget=budget):
                if expected is None:
                    self.assertEqual((result["status"], result["reason_code"]), ("not_filled", "BUDGET_BELOW_LOT"))
                else:
                    self.assertEqual(result["status"], "closed")
                    self.assertEqual(result["entry"]["quantity"], expected)
                    self.assertEqual(result["exit"]["quantity"], expected)
                    self.assertNotEqual(result["entry"]["at"][:10], result["exit"]["at"][:10])

    def test_star_rule_schema_order_caps_tick_and_legacy_rejection(self):
        self.use_star(); validate_rules([self.rule])
        for values in ({"schema_version": 3}, {"buy_min_shares": 100}, {"buy_step_shares": 200},
                       {"sell_odd_lot_full_exit": False}, {"max_order_shares": 100001},
                       {"order_type": "market", "max_order_shares": 50001}, {"exchange": "SZSE"}, {"tick_size": "0.05"}):
            with self.subTest(values=values), self.assertRaises(ValueError): validate_rules([{**self.rule, **values}])
        legacy = deepcopy(next(r for r in self.plan["rules"] if r["board"] == "MAIN"))
        legacy.update(exchange="SSE", board="STAR")
        with self.assertRaisesRegex(ValueError, "schema_version=2"): validate_rules([legacy])
        market = dict(self.rule, order_type="market", max_order_shares=50000)
        validate_rules([market])
        self.plan["capital_per_signal"] = "2000000"
        self.assertEqual(self.simulate()["entry"]["quantity"], "100000")
        self.rule.update(order_type="market", max_order_shares=50000)
        self.assertEqual(self.simulate()["entry"]["quantity"], "50000")

    def test_star_integer_odd_lot_after_explicit_reverse_split_exits_in_full(self):
        self.use_star(); self.plan["capital_per_signal"] = "2025.02"
        action = {"id": "reverse", "instrument_id": "SSE.688101", "type": "split_dividend",
                  "effective_at": at(20, 0), "available_at": at(19, 3), "share_multiplier": "0.5",
                  "cash_net_per_old_share": "0", "factor_from": "1", "factor_to": "0.5", "source": "synthetic-only"}
        for batch in self.batches:
            batch["corporate_actions"] = [deepcopy(action)]
            if utc_day(batch["as_of"]) >= 20:
                for quote in batch["quotes"]:
                    quote.update(close="22", high="22", low="22", adjustment_factor="0.5")
                    quote["execution"].update(limit_up="30", limit_down="10")
        result = self.simulate()
        self.assertEqual(result["status"], "closed")
        self.assertEqual(result["entry"]["quantity"], "200")
        self.assertEqual(result["exit"]["quantity"], "100.0")
        self.assertEqual(result["corporate_action_ids"], ["reverse"])

    def test_star_unknown_and_unbounded_price_limits_remain_explicit(self):
        self.use_star()
        for batch in self.batches:
            for quote in batch["quotes"]:
                quote["execution"].update(limit_state="unknown", limit_up=None, limit_down=None)
        self.assertEqual(self.simulate()["reason_code"], "EXECUTION_UNKNOWN")
        for batch in self.batches:
            for quote in batch["quotes"]: quote["execution"]["limit_state"] = "unbounded"
        self.assertEqual(self.simulate()["status"], "closed")

    def test_costs_quantity_and_excess_use_actual_simulated_entry_not_trigger(self):
        result = self.simulate()
        self.assertEqual(result["status"], "closed")
        self.assertEqual(result["entry"]["price"], "10.10")
        self.assertEqual(result["entry"]["quantity"], "900")
        self.assertEqual(result["entry"]["fee_cny"], "5.09")
        self.assertEqual(result["exit"]["fee_cny"], "10.05")
        self.assertEqual(result["net_pnl_cny"], "794.86")
        self.assertAlmostEqual(result["net_return"], float(Decimal("794.86") / Decimal("9095.09")))
        self.assertAlmostEqual(result["benchmark_excess"], result["net_return"] - .01)
        self.assertEqual(result["window_coverage"], "complete")
        self.assertFalse(result["revenue_failure"])

    def test_entry_is_strictly_later_than_delay_and_slippage_is_adverse(self):
        self.rule["slippage_buy_fraction"] = "0.001"
        self.rule["slippage_sell_fraction"] = "0.001"
        result = self.simulate(delay=1)
        self.assertEqual(result["entry"]["at"], at(19, 2))
        self.assertEqual(result["entry"]["price"], "10.12")
        self.assertEqual(result["exit"]["price"], "10.98")
        self.assertEqual(self.simulate(delay=5)["reason_code"], "EXPIRED_BEFORE_REACTION")

    def test_unknown_execution_cost_and_future_execution_do_not_fill(self):
        for change, expected in (("missing", "EXECUTION_UNSPECIFIED"), ("future", "EXECUTION_NOT_VISIBLE_OR_RULE_MISMATCH"),
                                 ("volume", "EXECUTION_UNKNOWN"), ("cost", "COST_MODEL_INCOMPLETE")):
            batches = deepcopy(self.batches)
            for batch in batches:
                for quote in batch["quotes"]:
                    if change == "missing":
                        quote.pop("execution")
                    elif change == "future":
                        quote["execution"]["available_at"] = at(21, 3)
                    elif change == "volume":
                        quote["execution"]["available_volume_shares"] = None
            original = self.rule["fees"]["commission_fraction"]
            if change == "cost":
                self.rule["fees"]["commission_fraction"] = None
            with self.subTest(change=change):
                result = self.simulate(batches=batches)
                self.assertEqual((result["status"], result["reason_code"]), ("pending", expected))
                self.assertIsNone(result["net_return"])
            self.rule["fees"]["commission_fraction"] = original

    def test_suspension_limits_and_budget_are_explicit_unfilled_denominators(self):
        for change, expected in (("suspended", "BUY_BLOCKED"), ("limit", "LIMIT_OR_SLIPPAGE_BLOCKED"), ("budget", "BUDGET_BELOW_LOT")):
            batches = deepcopy(self.batches)
            for batch in batches:
                for quote in batch["quotes"]:
                    if change == "suspended":
                        quote["execution"]["can_buy"] = False
                    elif change == "limit":
                        quote["execution"]["limit_up"] = quote["close"]
            self.plan["capital_per_signal"] = "1010" if change == "budget" else "10000"
            with self.subTest(change=change):
                result = self.simulate(batches=batches)
                self.assertEqual((result["status"], result["reason_code"]), ("not_filled", expected))
                self.assertIsNone(result["revenue_failure"])

    def test_missing_entry_bars_are_pending_not_unfilled(self):
        for batch in self.batches:
            for quote in batch["quotes"]:
                quote["execution"]["can_buy"] = False
        self.batches = [b for b in self.batches if b["as_of"] != at(19, 2)]
        self.assertEqual(self.simulate()["status"], "pending")

    def test_unverified_rules_only_allow_hypothetical_fixture_results(self):
        self.plan["purpose"] = "experimental"
        result = self.simulate()
        self.assertEqual((result["status"], result["reason_code"]), ("pending", "RULES_AND_COSTS_NOT_VERIFIED"))
        self.assertIsNone(result["net_return"])
        self.assertIsNone(result["entry"])
        self.rule["verified"] = True
        self.assertEqual(self.simulate()["status"], "closed")

    def test_unknown_execution_and_suspended_registry_cannot_fill(self):
        for batch in self.batches:
            for quote in batch["quotes"]:
                quote["execution"]["status"] = "unknown"
        self.assertEqual(self.simulate()["status"], "pending")
        for batch in self.batches:
            batch["instruments"][0]["status"] = "suspended"
            for quote in batch["quotes"]:
                quote["execution"]["status"] = "trading"
        result = self.simulate()
        self.assertEqual((result["status"], result["reason_code"]), ("not_filled", "BUY_BLOCKED"))

    def test_delayed_entry_respects_latest_signal_participation_and_terminal_events(self):
        paused = {"at": at(19, 1), "to_status": "PREALERT", "snapshot": {"actionability": "paused"}}
        result = self.simulate(events=[paused])
        self.assertEqual((result["status"], result["reason_code"]), ("pending", "SIGNAL_NOT_ACTIONABLE"))
        self.assertIsNone(result["entry"])
        recovered = {"at": at(19, 2), "to_status": "PREALERT", "snapshot": {"actionability": "eligible"}}
        self.assertEqual(self.simulate(events=[paused, recovered])["entry"]["at"], at(19, 2))
        terminal = {"at": at(19, 1), "to_status": "INVALIDATED", "snapshot": {"actionability": "expired"}}
        result = self.simulate(events=[terminal])
        self.assertEqual((result["status"], result["reason_code"]), ("not_filled", "SIGNAL_NO_LONGER_ACTIVE"))
        self.assertIsNone(result["entry"])

    def test_t_plus_one_risk_exit_uses_next_executable_gap_price_not_stop(self):
        self.batches[2]["quotes"][0].update(close="9.50", high="9.60", low="9.40")
        self.batches[3]["quotes"][0].update(close="9.20", high="9.30", low="9.10")
        self.batches[4]["quotes"][0].update(close="9.00", high="9.10", low="8.90")
        result = self.simulate(mode="risk")
        self.assertEqual(result["status"], "closed")
        self.assertEqual(result["exit"]["at"], at(20, 1))
        self.assertEqual(result["exit"]["price"], "9.00")
        self.assertTrue(result["structure_failure"])
        self.assertTrue(result["revenue_failure"])
        self.assertLess(result["net_return"], -.10)

    def test_blocked_sell_waits_but_fixed_window_never_uses_later_close(self):
        self.batches = [b for b in self.batches if b["as_of"] != at(20, 3)]
        result = self.simulate()
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["reason_code"], "TARGET_CLOSE_MISSING")
        self.assertIsNone(result["net_return"])
        # A blocked exact close is also not replaced by next day's close.
        blocked = self.batch(20, 3, "11")
        blocked["quotes"][0]["execution"]["can_sell"] = False
        self.batches.insert(6, blocked)
        self.assertEqual(self.simulate()["reason_code"], "SELL_BLOCKED")

    def test_gapped_window_extrema_and_unknown_failure_remain_null(self):
        self.batches = [b for b in self.batches if b["as_of"] != at(20, 2)]
        result = self.simulate()
        self.assertEqual(result["status"], "closed")
        self.assertEqual(result["window_coverage"], "gapped")
        self.assertIsNone(result["max_favorable"])
        self.assertIsNone(result["max_adverse"])
        self.assertIsNone(result["structure_failure"])

    def test_cross_boundary_samples_purged_even_when_risk_exits_earlier(self):
        self.split["end"] = at(20, 3)
        self.assertEqual(self.simulate()["status"], "purged")
        self.assertEqual(self.simulate(mode="risk")["status"], "purged")

    def test_split_dividend_converts_shares_and_stop_without_fake_loss(self):
        action = {"id": "split", "instrument_id": self.signal["instrument_id"], "type": "split_dividend",
                  "effective_at": at(20, 0), "available_at": at(19, 3), "share_multiplier": "2",
                  "cash_net_per_old_share": "0.20", "factor_from": "1", "factor_to": "2", "source": "synthetic-only"}
        for batch in self.batches:
            batch["corporate_actions"] = [deepcopy(action)]
            if utc_day(batch["as_of"]) >= 20:
                for quote in batch["quotes"]:
                    quote.update(close="5.40", high="5.40", low="5.40", adjustment_factor="2")
        result = self.simulate()
        self.assertEqual(result["status"], "closed")
        self.assertEqual(result["exit"]["quantity"], "1800")
        self.assertEqual(result["exit"]["cash_net_receivable_cny"], "180.00")
        self.assertEqual(result["corporate_action_ids"], ["split"])
        self.assertGreater(result["net_return"], 0)
        self.assertFalse(result["structure_failure"])

    def test_unknown_or_late_corporate_action_pauses_instead_of_inventing_pnl(self):
        self.batches[4]["quotes"][0].update(close="5", high="5", low="5", adjustment_factor="2")
        result = self.simulate()
        self.assertEqual(result["reason_code"], "CORPORATE_ACTION_UNRESOLVED")
        self.assertIsNone(result["net_return"])

    def test_rule_dates_visibility_and_unknown_contract_keys_are_rejected(self):
        self.rule["available_at"] = at(21, 3)
        self.assertEqual(self.simulate()["reason_code"], "RULE_OR_INSTRUMENT_NOT_VISIBLE")
        for invalid in (dict(self.rule, typo=1), dict(self.rule, sell_delay_sessions=0)):
            with self.assertRaises(ValueError):
                validate_rules([invalid])
        execution = deepcopy(self.batches[1]["quotes"][0]["execution"])
        execution["can_buy"] = "yes"
        with self.assertRaises(ValueError):
            validate_execution(execution)

    def test_price_revision_conflict_fails_and_late_revision_is_not_new_fill(self):
        batches = deepcopy(self.batches)
        duplicate = deepcopy(batches[1])
        duplicate["quotes"][0]["close"] = duplicate["quotes"][0]["high"] = "10.20"
        with self.assertRaisesRegex(ValueError, "CONFLICT"):
            Tape([batches[1], duplicate])
        later = deepcopy(batches[1])
        later["as_of"] = at(19, 2)
        tape = Tape([batches[1], later])
        self.assertEqual(len(tape.rows[self.signal["instrument_id"]]), 1)

    def test_failure_statistics_keep_not_filled_pending_and_purged_separate(self):
        closed = self.simulate()
        values = [closed] + [{**closed, "status": status, "entry": None, "structure_failure": None, "revenue_failure": None,
                             "net_return": None, "reason_code": status} for status in ("not_filled", "pending", "purged")]
        report = summarize(values)
        self.assertEqual(report["total"], 4)
        self.assertEqual(report["eligible_denominator"], 3)
        self.assertEqual(report["revenue_failure_denominator"], 1)
        self.assertEqual(report["not_filled_fraction"], 1 / 3)
        self.assertEqual(report["entry_decision_denominator"], 2)
        self.assertEqual(report["participation_fraction"], .5)
        self.assertEqual(report["entry_pending_count"], 1)
        self.assertEqual(report["max_favorable"]["denominator"], 1)

    def test_four_profiles_are_explicit_and_study_is_repeatable(self):
        plan = deepcopy(self.fixture_plan)
        plan.update(holding_windows_days=[1], reaction_delays_minutes=[0], bootstrap_samples=0)
        a, b = run_study(self.fixture, plan), run_study(self.fixture, plan)
        self.assertEqual(a, b)
        self.assertEqual([p["id"] for p in a["profiles"]], ["stock_only", "sector_filter", "early", "confirmed"])
        self.assertTrue(any(s["status"] == "closed" for p in a["profiles"] for s in p["samples"]))
        self.assertFalse(a["parameter_freeze"]["eligible"])
        invalid = deepcopy(plan)
        invalid["profiles"][1]["config"]["scoring"]["groups"]["sector"]["weight"] = .3
        invalid["profiles"][1]["config"]["scoring"]["groups"]["stock"]["weight"] = .3
        with self.assertRaises(ValueError):
            validate_study_plan(invalid)
        mismatched = deepcopy(plan)
        for profile in mismatched["profiles"][:2]:
            profile["config"]["scoring"]["alert_threshold"] += 1
        with self.assertRaisesRegex(ValueError, "其余参数一致"):
            validate_study_plan(mismatched)

    def test_malformed_container_types_fail_as_contract_errors(self):
        for key, value in (("purpose", []), ("reaction_delays_minutes", [[]]), ("holding_windows_days", [True]),
                           ("exit_modes", None), ("exit_modes", [{}, []]), ("splits", [None]), ("profiles", [None])):
            plan = deepcopy(self.fixture_plan)
            plan[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_study_plan(plan)
        rule = deepcopy(self.rule)
        rule["valuation_sessions"] = [[None, "10:03"]]
        with self.assertRaises(ValueError):
            validate_rules([rule])
        with self.assertRaises(ValueError):
            run_study([None], self.fixture_plan)

    def test_cluster_intervals_use_hotspot_day_not_stock_count(self):
        samples = [{"status": "closed", "cluster": ["d1", "hotspot"], "net_return": .2}] * 10
        self.plan.update(bootstrap_samples=200, min_clusters=2)
        self.assertIsNone(_cluster_interval(samples, self.plan)["interval_95"])
        samples += [{"status": "closed", "cluster": ["d2", "hotspot"], "net_return": -.1}]
        report = _cluster_interval(samples, self.plan)
        self.assertEqual(report["cluster_count"], 2)
        self.assertAlmostEqual(report["cluster_weighted_mean"], .05)
        self.assertEqual(report, _cluster_interval(samples, self.plan))


def utc_day(value):
    return datetime.fromisoformat(value).day
