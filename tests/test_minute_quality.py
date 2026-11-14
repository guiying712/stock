from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from datetime import datetime
from io import BytesIO, StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from stockradar.__main__ import main
from stockradar.contracts import load_json
from stockradar.minute_quality import minute_quality_report, validate_quality_plan
from stockradar.store import digest, dumps
from stockradar.vendor_samples import collect_samples, prepare_samples, request_specs


ROOT = Path(__file__).resolve().parent.parent


class Response(BytesIO):
    def __init__(self, body):
        super().__init__(json.dumps(body).encode())
        self.code, self.headers = 200, {}


class MinuteQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.plan = load_json(ROOT / "configs/minute-quality-template.json")
        self.plan.update(id="synthetic-minute-test", symbols=[{"symbol": "600000.SH", "board": "MAIN"}])
        self.plan["calendar"] = {"version": "synthetic-calendar-v1", "evidence": "synthetic-test-only",
                                 "dates": ["2024-01-02"], "sessions": [["09:30", "09:32"]]}
        self.plan["profiles"] = [self.profile()]

    def tearDown(self):
        self.temp.cleanup()

    def profile(self, provider="tickflow", dataset="minute_history", **changes):
        result = {"provider": provider, "dataset": dataset, "timestamp_label": "end",
                  "timestamp_timezone": "UTC" if provider == "tickflow" else "Asia/Shanghai", "completion": "provider_closed",
                  "volume_unit": "shares", "amount_unit": "CNY", "turnover_mode": "interval", "adjustment": "none",
                  "max_observation_delay_seconds": None,
                  "evidence": dict.fromkeys(("timestamp", "completion", "units", "turnover", "adjustment"), "synthetic-test-only")}
        result.update(changes)
        return result

    def sample(self, name, provider="tickflow", dataset="minute_history", labels=("09:31:00", "09:32:00"),
               prices=None, volumes=None, amounts=None, received="2024-01-02T01:40:00+00:00", body=None):
        sample_plan = load_json(ROOT / "configs/vendor-minute-tickflow-template.json")
        sample_plan.update(id=name, provider=provider, symbols=self.plan["symbols"], datasets=[dataset],
                           start_date="2024-01-02", end_date="2024-01-02", max_requests=1,
                           authorization={"confirmed": True, "reference": "synthetic-test-only"})
        count = len(labels)
        prices = prices or ["10"] * count
        volumes = volumes or ["100"] * count
        amounts = amounts or ["1000"] * count
        if body is None and provider == "tickflow":
            stamps = [int(datetime.fromisoformat("2024-01-02T" + label + "+08:00").timestamp() * 1000) for label in labels]
            body = {"data": {"timestamp": stamps, "open": prices, "high": prices, "low": prices, "close": prices,
                             "volume": volumes, "amount": amounts}}
        elif body is None:
            names = request_specs(sample_plan)[0]["fields"].split(",")
            rows = [dict(ts_code="600000.SH", freq="1MIN", trade_time="2024-01-02 " + label, time="2024-01-02 " + label,
                         open=price, high=price, low=price, close=price, vol=volume, amount=amount)
                    for label, price, volume, amount in zip(labels, prices, volumes, amounts)]
            body = {"code": 0, "data": {"fields": names, "items": [[r.get(k) for k in names] for r in rows]}}
        opener = Mock()
        opener.open.return_value = Response(body)
        with patch("stockradar.vendor_samples.now", return_value=received):
            result = collect_samples(sample_plan, self.root / name, opener=opener,
                                     environ={"TICKFLOW_API_KEY": "fake-test-key", "TUSHARE_TOKEN": "fake-test-token"})
        self.assertEqual(opener.open.call_count, 1)
        return result

    def report(self, *names):
        return minute_quality_report(self.plan, [self.root / name for name in names])

    def phase_plan(self):
        self.plan["schema_version"] = 2
        self.plan["calendar"].pop("sessions")
        self.plan["calendar"]["phases"] = [dict(id="morning", kind="continuous", start="09:30", end="09:32")]
        self.plan["security_days"] = [dict(symbol=s["symbol"], date="2024-01-02", status="trading",
                                          evidence="synthetic-complete-status-and-interval-list", intervals=[]) for s in self.plan["symbols"]]
        for profile in self.plan["profiles"]:
            profile.update(phase_rules=[dict(phase_id="morning", mode="minutes", label_at=None, evidence="synthetic-only")],
                           no_trade_policy=dict(mode="emit", evidence="synthetic-only"))
        return self.plan

    def test_phase_grid_preserves_unknowns_and_old_templates(self):
        template = load_json(ROOT / "configs/minute-quality-phases-template.json")
        before = deepcopy(template)
        result = minute_quality_report(template)
        self.assertEqual(result["schema_version"], 2)
        self.assertEqual(template, before)
        self.assertTrue(all(r["expected_records"] is None and r["coverage"] is None for r in result["coverage"]))
        self.assertTrue({"PHASE_RULE_UNCONFIRMED", "SECURITY_DAY_UNCONFIRMED", "NO_TRADE_POLICY_UNCONFIRMED"} <= set(result["reason_codes"]))
        self.assertFalse(result["strategy_input_ready"] or result["release_allowed"])

    def test_auction_is_one_record_with_full_interval_not_three_minutes(self):
        self.phase_plan()
        self.plan["calendar"]["phases"].append(dict(id="closing", kind="closing_auction", start="14:57", end="15:00"))
        self.plan["profiles"][0]["phase_rules"].append(dict(phase_id="closing", mode="aggregate", label_at="15:00", evidence="synthetic-only"))
        self.sample("auction", labels=("09:31:00", "09:32:00", "15:00:00"), received="2024-01-02T07:00:01+00:00")
        result = self.report("auction")
        row = result["observations"][-1]
        self.assertEqual((row["interval_start"], row["interval_end"], row["interval_seconds"]),
                         ("2024-01-02T06:57:00+00:00", "2024-01-02T07:00:00+00:00", 180))
        coverage = result["coverage"][0]
        self.assertEqual((coverage["expected_records"], coverage["coverage"]), (3, 1))
        self.assertIsNone(coverage["expected_minutes"])
        self.assertEqual(result["status"], "checks_passed")

    def test_same_end_different_intervals_are_not_cross_compared(self):
        self.plan["profiles"] = [self.profile(), self.profile("tushare")]
        self.phase_plan()
        self.plan["calendar"]["phases"] = [dict(id="morning", kind="closing_auction", start="14:57", end="15:00")]
        self.plan["profiles"][0]["phase_rules"][0].update(mode="aggregate", label_at="15:00")
        self.sample("aggregate", labels=("15:00:00",), received="2024-01-02T07:01:00+00:00")
        self.sample("minutes", provider="tushare", labels=("14:58:00", "14:59:00", "15:00:00"), received="2024-01-02T07:01:00+00:00")
        result = self.report("aggregate", "minutes")
        self.assertEqual(result["comparisons"][0]["common_minutes"], 0)
        self.assertEqual([c["expected_records"] for c in result["coverage"]], [1, 3])

    def test_aggregate_label_has_explicit_mapping_and_cannot_collide(self):
        self.phase_plan()
        self.plan["calendar"]["phases"].insert(0, dict(id="opening", kind="opening_auction", start="09:15", end="09:25"))
        self.plan["profiles"][0]["phase_rules"].insert(0, dict(phase_id="opening", mode="aggregate", label_at="09:30", evidence="synthetic-only"))
        self.sample("open", labels=("09:30:00", "09:31:00", "09:32:00"))
        row = self.report("open")["observations"][0]
        self.assertEqual(row["interval_end"], "2024-01-02T01:25:00+00:00")
        self.assertEqual(row["interval_seconds"], 600)
        self.plan["profiles"][0]["timestamp_label"] = "start"
        with self.assertRaisesRegex(ValueError, "重复原始标签"):
            validate_quality_plan(self.plan)

    def test_halt_changes_only_its_evidenced_security_day(self):
        self.plan["symbols"].append(dict(symbol="300750.SZ", board="CHINEXT"))
        self.phase_plan()
        self.plan["security_days"][0]["intervals"] = [dict(start="09:31", end="09:32", kind="halt", evidence="synthetic-only")]
        result = self.report()
        self.assertEqual([c["expected_records"] for c in result["coverage"]], [1, 2])
        self.assertEqual(result["coverage"][0]["excluded_records"], {"halt": 1})
        self.assertIn("REQUESTED_MINUTE_SERIES_MISSING", result["reason_codes"])

    def test_full_suspension_is_zero_denominator_not_full_coverage(self):
        self.phase_plan()
        self.plan["security_days"][0]["status"] = "suspended"
        coverage = self.report()["coverage"][0]
        self.assertEqual(coverage["expected_records"], 0)
        self.assertIsNone(coverage["coverage"])
        self.sample("unexpected")
        result = self.report("unexpected")
        self.assertIn("OBSERVATION_OUTSIDE_REVIEWED_GRID", result["reason_codes"])
        self.assertEqual(result["coverage"][0]["usable_unique_records"], 0)

    def test_no_trade_omission_needs_explicit_rule_and_interval_evidence(self):
        self.phase_plan()
        self.plan["profiles"][0]["no_trade_policy"]["mode"] = "omit"
        self.plan["security_days"][0]["intervals"] = [dict(start="09:31", end="09:32", kind="no_trade", evidence="synthetic-only")]
        self.sample("omitted-zero", labels=("09:31:00",))
        result = self.report("omitted-zero")
        coverage = result["coverage"][0]
        self.assertEqual((coverage["expected_records"], coverage["coverage"], coverage["excluded_records"]), (1, 1, {"no_trade": 1}))
        self.assertIsNone(coverage["expected_minutes"])
        self.assertFalse(result["strategy_input_ready"])
        self.plan["profiles"][0]["no_trade_policy"]["mode"] = "emit"
        result = self.report("omitted-zero")
        self.assertEqual(result["coverage"][0]["coverage"], 0.5)
        self.assertIn("MINUTE_GAPS", result["reason_codes"])

    def test_no_trade_emission_does_not_treat_positive_or_cumulative_as_zero(self):
        self.phase_plan()
        self.plan["security_days"][0]["intervals"] = [dict(start="09:31", end="09:32", kind="no_trade", evidence="synthetic-only")]
        self.sample("contradiction")
        self.assertIn("NO_TRADE_EVIDENCE_CONFLICT", self.report("contradiction")["reason_codes"])
        self.sample("zero-bars", volumes=["100", "0"], amounts=["1000", "0"])
        self.assertEqual(self.report("zero-bars")["status"], "checks_passed")
        self.plan["profiles"][0]["turnover_mode"] = "cumulative"
        self.assertIn("NO_TRADE_INCREMENT_UNVERIFIED", self.report("contradiction")["reason_codes"])

    def test_partial_halt_of_aggregate_does_not_shrink_denominator(self):
        self.phase_plan()
        self.plan["profiles"][0]["phase_rules"][0].update(mode="aggregate", label_at="09:32")
        self.plan["security_days"][0]["intervals"] = [dict(start="09:31", end="09:32", kind="halt", evidence="synthetic-only")]
        result = self.report()
        self.assertIn("PARTIAL_BAR_EXCEPTION", result["reason_codes"])
        self.assertIsNone(result["coverage"][0]["expected_records"])

    def test_schema2_strict_scope_and_unknown_rules_cannot_pass(self):
        self.phase_plan()
        mutations = [lambda p: p["security_days"].clear(),
                     lambda p: p["security_days"][0].update(evidence=None),
                     lambda p: p["profiles"][0]["phase_rules"].clear(),
                     lambda p: p["profiles"][0]["phase_rules"][0].update(mode="guess"),
                     lambda p: p["profiles"][0]["phase_rules"][0].update(evidence=None),
                     lambda p: p["profiles"][0]["phase_rules"][0].update(label_at="09:31"),
                     lambda p: p["calendar"]["phases"][0].update(end="09:29"),
                     lambda p: p["calendar"]["phases"][0].update(unexpected=True),
                     lambda p: p["profiles"][0]["no_trade_policy"].update(evidence=None)]
        for mutation in mutations:
            plan = deepcopy(self.plan)
            mutation(plan)
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                validate_quality_plan(plan)
        self.sample("unreviewed")
        self.plan["profiles"][0]["no_trade_policy"].update(mode="unknown", evidence=None)
        result = self.report("unreviewed")
        self.assertIsNone(result["coverage"][0]["expected_records"])
        self.assertFalse(result["minute_checks_passed"])

    def test_schema2_reobservations_and_revisions_preserve_unique_counts(self):
        self.phase_plan()
        self.sample("first-phase")
        self.sample("repeat-phase", received="2024-01-02T01:41:00+00:00")
        result = self.report("first-phase", "repeat-phase")
        self.assertEqual(result["coverage"][0]["usable_unique_records"], 2)
        self.sample("revision-phase", prices=["11", "10"], amounts=["1100", "1000"])
        result = self.report("first-phase", "revision-phase")
        self.assertEqual(result["coverage"][0]["usable_unique_records"], 1)
        self.assertEqual(result["coverage"][0]["observed_coverage"], 1)

    def test_schema2_tushare_session_uses_real_parser_with_mock_response(self):
        self.plan["profiles"] = [self.profile("tushare", "intraday")]
        self.phase_plan()
        self.sample("session", provider="tushare", dataset="intraday")
        result = self.report("session")
        self.assertEqual(result["status"], "checks_passed")
        self.assertEqual(result["coverage"][0]["expected_records"], 2)

    def test_schema2_same_aggregate_compares_as_record_not_minute(self):
        self.plan["profiles"] = [self.profile(), self.profile("tushare")]
        self.phase_plan()
        for profile in self.plan["profiles"]:
            profile["phase_rules"][0].update(mode="aggregate", label_at="09:32")
        self.sample("aggregate-left", labels=("09:32:00",))
        self.sample("aggregate-right", provider="tushare", labels=("09:32:00",))
        result = self.report("aggregate-left", "aggregate-right")
        self.assertEqual((result["comparisons"][0]["common_records"], result["comparisons"][0]["common_minutes"]), (1, 0))

    def test_schema2_unknown_calendar_status_or_time_blocks_coverage_and_comparison(self):
        self.plan["profiles"] = [self.profile(), self.profile("tushare")]
        self.phase_plan()
        self.sample("v2-left")
        self.sample("v2-right", provider="tushare")
        original = deepcopy(self.plan)
        for mutation in [lambda p: p["calendar"].update(version=None, evidence=None),
                         lambda p: p["security_days"][0].update(status="unknown", evidence=None),
                         lambda p: p["profiles"][0].update(timestamp_label="unknown")]:
            self.plan = deepcopy(original)
            mutation(self.plan)
            result = self.report("v2-left", "v2-right")
            self.assertIsNone(result["coverage"][0]["expected_records"])
            self.assertEqual(result["comparisons"][0]["common_records"], 0)

    def test_schema2_halted_observation_and_source_label_after_receipt_remain_invalid(self):
        self.phase_plan()
        self.plan["security_days"][0]["intervals"] = [dict(start="09:31", end="09:32", kind="halt", evidence="synthetic-only")]
        self.sample("halted", received="2024-01-02T01:31:01+00:00")
        result = self.report("halted")
        self.assertIn("OBSERVATION_IN_EXCLUDED_INTERVAL", result["reason_codes"])
        self.assertIn("MINUTE_NOT_CLOSED_AT_OBSERVATION", result["reason_codes"])
        self.assertIn("SOURCE_LABEL_AFTER_OBSERVATION", result["reason_codes"])
        self.assertEqual(result["coverage"][0]["usable_unique_records"], 1)

    def rewrite_report(self, name, change):
        path = self.root / name / "report.json"
        report = load_json(path)
        change(report)
        report.pop("output_hash")
        report["output_hash"] = digest(report)
        path.write_text(dumps(report))

    def test_strict_plan_requires_explicit_semantics_evidence_and_calendar(self):
        mutations = [lambda p: p.update(extra=True), lambda p: p.pop("calendar"),
                     lambda p: p["profiles"][0]["evidence"].update(timestamp=None),
                     lambda p: p["profiles"][0].update(max_observation_delay_seconds=True),
                     lambda p: p["profiles"][0].update(provider="tickflow_free"),
                     lambda p: p["profiles"][0].update(turnover_mode="auto"),
                     lambda p: p["calendar"].update(version=None),
                     lambda p: p["calendar"].update(dates=["2024-01-02", "2024-01-02"]),
                     lambda p: p["calendar"].update(sessions=[["11:30", "09:30"]]),
                     lambda p: p["symbols"][0].update(symbol="000001.SH"),
                     lambda p: p["profiles"].append(deepcopy(p["profiles"][0]))]
        for mutation in mutations:
            value = deepcopy(self.plan)
            mutation(value)
            with self.subTest(plan=value), self.assertRaises(ValueError):
                validate_quality_plan(value)

    def test_no_account_preparation_is_zero_network_and_does_not_claim_permissions(self):
        plan = load_json(ROOT / "configs/vendor-minute-tushare-template.json")
        with patch("urllib.request.build_opener", side_effect=AssertionError("must remain offline")):
            result = prepare_samples(plan, environ={})
        self.assertEqual((result["sent_requests"], result["planned_requests"]), (0, 7))
        self.assertEqual(result["account_permissions"], "not_tested")
        self.assertEqual(set(result["reason_codes"]), {"CREDENTIAL_MISSING", "ACCESS_AUTHORIZATION_NOT_CONFIRMED"})
        plan["authorization"] = {"confirmed": True, "reference": "synthetic-test-access"}
        result = prepare_samples(plan, environ={"TUSHARE_TOKEN": "fake-test-token"})
        self.assertEqual(result["status"], "prepared_not_permission_verified")
        self.assertNotIn("fake-test-token", dumps(result))
        self.assertFalse(result["strategy_input_ready"])

    def test_dry_run_cli_creates_only_preparation_and_never_constructs_application(self):
        path = self.root / "prepared"
        with patch.dict("os.environ", {}, clear=True), patch("urllib.request.build_opener", side_effect=AssertionError("network")), redirect_stdout(StringIO()):
            main(["vendor-sample", "--dry-run", "--plan", str(ROOT / "configs/vendor-minute-tickflow-template.json"), "--output-dir", str(path)])
        self.assertEqual({p.name for p in path.iterdir()}, {"report.json"})
        self.assertEqual(load_json(path / "report.json")["kind"], "vendor_sample_preparation")
        self.assertEqual((path / "report.json").stat().st_mode & 0o777, 0o600)
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            main(["vendor-sample", "--dry-run", "--plan", str(ROOT / "configs/vendor-minute-tickflow-template.json"), "--output-dir", str(path)])

    def test_preparation_rejects_bad_budget_and_credential_echo_before_output(self):
        plan = load_json(ROOT / "configs/vendor-minute-tickflow-template.json")
        plan["max_requests"] = 1
        with self.assertRaises(ValueError):
            prepare_samples(plan, environ={})
        plan["max_requests"] = 9
        plan["authorization"]["reference"] = "fake-test-key"
        with self.assertRaises(ValueError):
            prepare_samples(plan, environ={"TICKFLOW_API_KEY": "fake-test-key"})

    def test_unknown_template_and_missing_samples_remain_unknown_not_zero(self):
        result = minute_quality_report(load_json(ROOT / "configs/minute-quality-template.json"))
        self.assertEqual((result["status"], result["observation_count"]), ("no_minute_samples", 0))
        self.assertIn("CALENDAR_UNVERIFIED", result["reason_codes"])
        self.assertTrue(all(row["coverage"] is None and row["expected_minutes"] is None for row in result["coverage"]))
        self.assertFalse(result["minute_checks_passed"])

    def test_complete_reviewed_sample_passes_local_checks_without_strategy_release(self):
        self.sample("good")
        before = {p.name: p.read_bytes() for p in (self.root / "good").iterdir() if p.is_file()}
        result = self.report("good")
        self.assertEqual((result["status"], result["coverage"][0]["coverage"]), ("checks_passed", 1))
        self.assertEqual(result["observations"][0]["interval_end"], "2024-01-02T01:31:00+00:00")
        self.assertEqual(result["observations"][0]["observed_delay_seconds"], 540)
        self.assertTrue(result["observations"][0]["is_complete"])
        self.assertIsNone(result["observations"][0]["source_available_at"])
        self.assertFalse(result["strategy_input_ready"] or result["release_allowed"])
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.root / "good").iterdir() if p.is_file()})
        self.assertEqual(result["output_hash"], digest({k: v for k, v in result.items() if k != "output_hash"}))

    def test_calendar_unknown_never_claims_coverage_even_with_known_labels(self):
        self.sample("good")
        self.plan["calendar"].update(version=None, evidence=None)
        result = self.report("good")
        self.assertIsNone(result["coverage"][0]["coverage"])
        self.assertIn("CALENDAR_UNVERIFIED", result["reason_codes"])

    def test_start_and_end_labels_align_by_interval_end_and_not_raw_string(self):
        self.plan["profiles"] = [self.profile(timestamp_label="start"), self.profile("tushare")]
        self.sample("start", labels=("09:30:00", "09:31:00"))
        self.sample("end", provider="tushare")
        result = self.report("start", "end")
        self.assertEqual(result["comparisons"][0]["common_minutes"], 2)
        self.assertTrue(all(not row["differences"] for row in result["comparisons"][0]["comparisons"]))
        self.assertEqual(result["status"], "checks_passed")

    def test_same_labels_are_not_compared_when_timestamp_semantics_unknown(self):
        self.plan["profiles"] = [self.profile(timestamp_label="unknown"), self.profile("tushare")]
        self.sample("left")
        self.sample("right", provider="tushare")
        result = self.report("left", "right")
        self.assertEqual((result["comparisons"][0]["status"], result["comparisons"][0]["common_minutes"]), ("blocked_semantics", 0))
        self.assertIsNone(result["observations"][0]["interval_end"])
        self.assertIsNone(result["coverage"][0]["coverage"])

    def test_unconfirmed_timezone_cannot_align_or_claim_complete_minutes(self):
        self.plan["profiles"][0]["timestamp_timezone"] = "unknown"
        self.sample("timezone")
        result = self.report("timezone")
        self.assertIn("TIMEZONE_UNCONFIRMED", result["reason_codes"])
        self.assertIsNone(result["observations"][0]["interval_end"])
        self.assertIsNone(result["observations"][0]["is_complete"])
        self.assertIsNone(result["coverage"][0]["coverage"])

    def test_same_provider_history_and_intraday_comparison_is_not_independent_source(self):
        self.plan["profiles"] = [self.profile(), self.profile(dataset="intraday")]
        self.sample("history")
        self.sample("intraday", dataset="intraday")
        result = self.report("history", "intraday")
        self.assertEqual(result["comparisons"][0]["type"], "same_provider_endpoints")
        self.assertEqual(result["comparisons"][0]["common_minutes"], 2)
        self.assertFalse(result["cross_source_verified"])

    def test_documented_unit_scaling_retains_long_decimal_precision(self):
        self.plan["profiles"][0].update(volume_unit="lots_100", amount_unit="thousand_CNY")
        value = "0." + "1234567890" * 7
        from decimal import Decimal, localcontext
        with localcontext() as context:
            context.prec = 120
            amount = str(Decimal(value))
            expected_volume = str(Decimal(value) * 100)
            expected_amount = str(Decimal(amount) * 1000)
        self.sample("precision", volumes=[value] * 2, amounts=[amount] * 2)
        row = self.report("precision")["observations"][0]
        self.assertEqual(row["volume_shares"], expected_volume)
        self.assertEqual(row["amount_cny"], expected_amount)

    def test_interval_and_cumulative_turnover_are_not_compared_as_equal_units(self):
        self.plan["profiles"] = [self.profile(), self.profile("tushare", turnover_mode="cumulative")]
        self.sample("left")
        self.sample("right", provider="tushare", volumes=["100", "200"], amounts=["1000", "2000"])
        result = self.report("left", "right")
        self.assertEqual(result["comparisons"][0]["common_minutes"], 2)
        self.assertEqual(result["comparisons"][0]["comparisons"][1]["unknown_fields"], ["volume_shares", "amount_cny"])
        self.assertEqual(result["comparisons"][0]["comparisons"][1]["differences"], [])

    def test_exact_decimal_difference_is_visible_and_never_tolerated_away(self):
        self.plan["profiles"] = [self.profile(), self.profile("tushare")]
        self.sample("left", prices=["10.000000000000000001"] * 2, amounts=["1000.000000000000000100"] * 2)
        self.sample("right", provider="tushare")
        result = self.report("left", "right")
        self.assertIn("ALIGNED_MINUTE_VALUES_DIFFER", result["reason_codes"])
        self.assertEqual(result["comparisons"][0]["comparisons"][0]["differences"][0]["left"], "10.000000000000000001")

    def test_unknown_units_preserve_raw_and_never_apply_100_candidate(self):
        self.plan["profiles"] = [self.profile(volume_unit="unknown", amount_unit="unknown")]
        self.sample("unit", volumes=["1", "1"], amounts=["1000", "1000"])
        result = self.report("unit")
        row = result["observations"][0]
        self.assertEqual((row["volume_raw"], row["diagnostic_volume_scales_assuming_amount_cny"]), ("1", ["100"]))
        self.assertIsNone(row["volume_shares"])
        self.assertIsNone(row["amount_cny"])
        self.assertIn("VOLUME_UNIT_UNCONFIRMED", result["reason_codes"])

    def test_missing_minutes_are_reported_without_filling_and_lunch_is_excluded(self):
        self.plan["calendar"]["sessions"] = [["09:30", "09:32"], ["13:00", "13:01"]]
        self.sample("gaps", labels=("09:31:00", "13:01:00"), received="2024-01-02T06:00:00+00:00")
        result = self.report("gaps")
        self.assertEqual(result["coverage"][0]["expected_minutes"], 3)
        self.assertEqual(result["coverage"][0]["missing_interval_ends"], ["2024-01-02T01:32:00+00:00"])
        self.assertEqual(len(result["observations"]), 2)

    def test_duplicate_rejected_projection_is_recovered_from_hashed_raw(self):
        sample = self.sample("duplicates", labels=("09:31:00", "09:31:00"))
        self.assertEqual(sample["bar_count"], 0)
        result = self.report("duplicates")
        self.assertEqual((len(result["observations"]), len(result["duplicate_minutes"])), (2, 1))
        self.assertIn("DUPLICATE_MINUTE_LABEL", result["reason_codes"])
        self.assertEqual(result["coverage"][0]["usable_unique_minutes"], 0)

    def test_identical_reobservations_do_not_inflate_coverage_or_become_revisions(self):
        self.sample("first")
        self.sample("second", prices=["10.0", "10.0"], received="2024-01-02T01:41:00+00:00")
        result = self.report("first", "second")
        self.assertEqual(result["coverage"][0]["observed_unique_minutes"], 2)
        self.assertEqual(len(result["identical_reobservations"]), 2)
        self.assertEqual(result["revision_conflicts"], [])
        self.assertEqual(result["status"], "checks_passed")

    def test_revision_conflict_keeps_both_observations_without_choosing_latest(self):
        self.sample("before")
        self.sample("after", prices=["11", "10"], amounts=["1100", "1000"], received="2024-01-02T01:41:00+00:00")
        result = self.report("before", "after")
        self.assertEqual(len(result["revision_conflicts"]), 1)
        self.assertEqual(len(result["observations"]), 4)
        self.assertEqual(result["coverage"][0]["usable_unique_minutes"], 1)
        self.assertIn("REVISION_CONFLICT", result["reason_codes"])

    def test_future_unclosed_unaligned_and_auction_labels_are_explicit(self):
        self.sample("future", received="2024-01-02T01:30:30+00:00")
        result = self.report("future")
        self.assertFalse(result["observations"][0]["is_complete"])
        self.assertIn("MINUTE_NOT_CLOSED_AT_OBSERVATION", result["reason_codes"])
        self.sample("unaligned", labels=("09:30:30", "09:30:00"))
        result = self.report("unaligned")
        self.assertIn("TIME_LABEL_NOT_MINUTE_ALIGNED", result["reason_codes"])
        self.assertIn("OUTSIDE_CONTINUOUS_SESSION", result["reason_codes"])

    def test_delay_budget_is_explicit_and_does_not_claim_platform_latency(self):
        self.sample("delayed")
        result = self.report("delayed")
        self.assertNotIn("OBSERVED_AFTER_DELAY_BUDGET", result["reason_codes"])
        self.plan["profiles"][0]["max_observation_delay_seconds"] = 60
        result = self.report("delayed")
        self.assertIn("OBSERVED_AFTER_DELAY_BUDGET", result["reason_codes"])
        self.assertEqual(result["delay_basis"], "first_observed_delay_not_historical_or_platform_latency")

    def test_cumulative_decrease_including_lunch_is_not_ignored(self):
        self.plan["calendar"]["sessions"] = [["09:30", "09:31"], ["13:00", "13:01"]]
        self.plan["profiles"][0]["turnover_mode"] = "cumulative"
        self.sample("reset", labels=("09:31:00", "13:01:00"), volumes=["200", "100"], amounts=["2000", "1000"], received="2024-01-02T06:00:00+00:00")
        result = self.report("reset")
        self.assertIn("CUMULATIVE_TURNOVER_DECREASE", result["reason_codes"])
        self.assertNotIn("INTERVAL_TURNOVER_OUTSIDE_PRICE_RANGE", result["reason_codes"])

    def test_interval_turnover_consistency_and_zero_unknown_cases(self):
        self.sample("bad", amounts=["2000", "1000"])
        self.assertIn("INTERVAL_TURNOVER_OUTSIDE_PRICE_RANGE", self.report("bad")["reason_codes"])
        self.sample("zero", volumes=["0", "0"], amounts=["0", "0"])
        self.assertEqual(self.report("zero")["status"], "checks_passed")
        self.sample("conflict", volumes=["0", "100"], amounts=["1", "1000"])
        self.assertIn("ZERO_VOLUME_AMOUNT_CONFLICT", self.report("conflict")["reason_codes"])
        self.sample("unknown", amounts=[None, "1000"])
        self.assertIn("TURNOVER_UNKNOWN", self.report("unknown")["reason_codes"])

    def test_empty_and_invalid_raw_rows_do_not_become_valid_coverage(self):
        self.sample("empty", labels=())
        result = self.report("empty")
        self.assertEqual(result["status"], "no_minute_samples")
        self.assertEqual(result["capture_issues"][0]["reason_code"], "NO_MINUTE_ROWS")
        self.sample("negative", volumes=["-1", "100"])
        result = self.report("negative")
        self.assertEqual(len(result["observations"]), 1)
        self.assertEqual(result["capture_issues"][0]["reason_code"], "RAW_MINUTE_ROW_INVALID")

    def test_unplanned_dataset_and_duplicate_input_report_are_rejected(self):
        self.sample("good")
        with self.assertRaises(ValueError):
            self.report("good", "good")
        self.plan["profiles"] = [self.profile("tushare")]
        with self.assertRaises(ValueError):
            self.report("good")

    def test_hashed_artifacts_cannot_be_omitted_tampered_or_symlinked(self):
        sample = self.sample("good")
        self.rewrite_report("good", lambda r: r.update(artifacts=[a for a in r["artifacts"] if a["file"] != "bars.jsonl"]))
        with self.assertRaises(ValueError):
            self.report("good")
        sample = self.sample("tamper")
        raw = self.root / "tamper" / sample["requests"][0]["raw_file"]
        raw.write_bytes(raw.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            self.report("tamper")
        self.sample("rawlink")
        raw = self.root / "rawlink" / "raw"
        raw.rename(self.root / "rawtarget")
        raw.symlink_to(self.root / "rawtarget", target_is_directory=True)
        with self.assertRaises(ValueError):
            self.report("rawlink")

    def test_unlisted_raw_reference_and_changed_request_contract_are_rejected(self):
        self.sample("omitted")
        self.rewrite_report("omitted", lambda r: r.update(artifacts=[a for a in r["artifacts"] if not a["file"].startswith("raw/")]))
        with self.assertRaises(ValueError):
            self.report("omitted")
        self.sample("changed")
        self.rewrite_report("changed", lambda r: r["requests"][0].update(dataset="intraday"))
        with self.assertRaises(ValueError):
            self.report("changed")

    def test_code_changes_during_diagnostic_are_reported_not_passed(self):
        self.sample("good")
        with patch("stockradar.minute_quality.source_hash", side_effect=["before", "after"]):
            result = self.report("good")
        self.assertIn("CODE_CHANGED_DURING_DIAGNOSTIC", result["reason_codes"])
        self.assertFalse(result["minute_checks_passed"])

    def test_cli_no_samples_and_no_overwrite(self):
        output = self.root / "quality.json"
        with redirect_stdout(StringIO()):
            main(["minute-quality", "--plan", str(ROOT / "configs/minute-quality-template.json"), "--output", str(output)])
        raw = output.read_bytes()
        self.assertEqual(load_json(output)["status"], "no_minute_samples")
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            main(["minute-quality", "--plan", str(ROOT / "configs/minute-quality-template.json"), "--output", str(output)])
        self.assertEqual(output.read_bytes(), raw)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_all_preparation_templates_are_consistent_and_leave_access_unconfirmed(self):
        profile_keys = {(p["provider"], p["dataset"]) for p in load_json(ROOT / "configs/minute-quality-template.json")["profiles"]}
        for provider, count in (("tickflow", 9), ("tushare", 7)):
            plan = load_json(ROOT / ("configs/vendor-minute-" + provider + "-template.json"))
            self.assertEqual(len(request_specs(plan)), count)
            self.assertFalse(plan["authorization"]["confirmed"])
            self.assertTrue({(provider, d) for d in plan["datasets"] if d != "daily_bars"} <= profile_keys)

