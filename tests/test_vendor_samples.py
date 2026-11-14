"""Vendor schema/units/provenance and credential boundaries, without live network."""
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from stockradar.contracts import load_json
from stockradar.store import digest, dumps
from stockradar.vendor_samples import collect_samples, compare_samples, request_specs, validate_sample_plan


class Response(BytesIO):
    def __init__(self, body, status=200):
        super().__init__(body if isinstance(body, bytes) else json.dumps(body).encode())
        self.code, self.headers = status, {}


class Opener:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def open(self, req, timeout):
        self.calls.append(req)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return Response(item)


class VendorSampleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.plan = load_json(Path(__file__).resolve().parent.parent / "configs/vendor-sample-tickflow-free.json")
        self.plan.update(symbols=[{"symbol": "000001.SZ", "board": "MAIN"}], datasets=["daily_bars"],
                         start_date="2024-01-02", end_date="2024-01-03", max_requests=1)
        self.tick_bar = {"data": {"timestamp": [1704153600000], "open": [10], "high": [11], "low": [9],
                                  "close": [10], "volume": [10], "amount": [10000]}}

    def tearDown(self):
        self.temp.cleanup()

    def collect(self, body, plan=None, name="sample", environ=None):
        opener = Opener([body])
        result = collect_samples(plan or self.plan, self.root / name, opener=opener,
                                 environ={} if environ is None else environ, sleep=lambda _: None)
        return result, opener

    def tushare_plan(self, datasets=None):
        plan = deepcopy(self.plan)
        plan.update(provider="tushare", datasets=datasets or ["daily_bars"], max_requests=60,
                    authorization={"confirmed": True, "reference": "local-test-access"})
        return plan

    def table(self, plan, rows):
        names = request_specs(plan)[0]["fields"].split(",")
        return {"code": 0, "msg": None, "data": {"fields": names, "items": [[r.get(k) for k in names] for r in rows]}}

    def bars(self, name="sample"):
        return [json.loads(line) for line in (self.root / name / "bars.jsonl").read_text().splitlines()]

    def test_strict_plan_window_board_and_budget_before_network(self):
        mutations = [lambda p: p.pop("max_requests"), lambda p: p.update(extra=True),
                     lambda p: p.update(request_timeout_seconds=True), lambda p: p.update(provider=[]),
                     lambda p: p.update(start_date="2024-01-01", end_date="2024-02-01"),
                     lambda p: p["symbols"][0].update(symbol="000001.SH"),
                     lambda p: p["symbols"][0].update(board="STAR"),
                     lambda p: p.update(datasets=["minute_history"])]
        for mutation in mutations:
            plan = deepcopy(self.plan)
            mutation(plan)
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                validate_sample_plan(plan)
        plan = deepcopy(self.plan)
        plan.update(datasets=["instruments", "daily_bars"], max_requests=1)
        with self.assertRaises(ValueError):
            collect_samples(plan, self.root / "unused", opener=Opener([]), environ={})
        self.assertFalse((self.root / "unused").exists())

    def test_tickflow_unknown_units_never_silently_convert_100x(self):
        result, opener = self.collect(self.tick_bar)
        bar = self.bars()[0]
        self.assertEqual((result["bar_count"], bar["symbol"], bar["label"]), (1, "000001.SZ", "2024-01-02"))
        self.assertIsNone(bar["volume_shares"])
        self.assertIsNone(bar["amount_cny"])
        self.assertEqual(bar["diagnostic_volume_scales_assuming_amount_cny"], ["100"])
        self.assertIn("UNIT_SCALE_100_CANDIDATE", result["reason_codes"])
        self.assertEqual(bar["volume_raw"], "10")
        self.assertIsNone(bar["event_time"])
        self.assertIsNone(bar["is_complete"])
        self.assertGreater(datetime.fromisoformat(bar["available_at"]), datetime(2024, 1, 2, tzinfo=timezone.utc))
        self.assertFalse(result["strategy_input_ready"])
        self.assertFalse(result["release_allowed"])
        self.assertTrue(opener.calls[0].full_url.startswith("https://free-api.tickflow.org/"))
        self.assertEqual(result["output_hash"], digest({k: v for k, v in result.items() if k != "output_hash"}))

    def test_decimal_prices_survive_response_and_projection_exactly(self):
        raw = b'{"data":{"timestamp":[1704153600000],"open":[10.000000000000000001],"high":[11],"low":[9],"close":[10.000000000000000001],"volume":[10],"amount":[10000]}}'
        result, _ = self.collect(raw)
        self.assertEqual(self.bars()[0]["prices"]["close"], "10.000000000000000001")
        self.assertEqual((self.root / "sample" / result["requests"][0]["raw_file"]).read_bytes(), raw)

    def test_empty_200_does_not_count_as_captured_sample(self):
        empty = deepcopy(self.tick_bar)
        empty["data"] = {k: [] for k in empty["data"]}
        result, _ = self.collect(empty)
        self.assertEqual((result["status"], result["captured_responses"], result["bar_count"]), ("incomplete", 0, 0))
        self.assertIn("NO_ROWS", result["reason_codes"])

    def test_conflicting_columns_and_duplicate_labels_are_preserved_as_failures(self):
        bad = deepcopy(self.tick_bar)
        bad["data"]["close"].append(11)
        result, _ = self.collect(bad)
        self.assertIn("COLUMN_LENGTH_MISMATCH", result["reason_codes"])
        self.assertTrue((self.root / "sample" / result["requests"][0]["raw_file"]).is_file())
        self.assertEqual(result["bar_count"], 0)
        duplicate = deepcopy(self.tick_bar)
        duplicate["data"] = {k: v + v for k, v in duplicate["data"].items()}
        result, _ = self.collect(duplicate, name="duplicate")
        self.assertIn("DUPLICATE_PERIOD_LABEL", result["reason_codes"])

    def test_json_duplicate_nonfinite_and_null_price_have_explicit_outcomes(self):
        for i, body in enumerate((b'{"data":{},"data":{}}', b'{"data":NaN}')):
            result, _ = self.collect(body, name="invalid%d" % i)
            self.assertEqual((result["status"], result["bar_count"]), ("incomplete", 0))
        bad = deepcopy(self.tick_bar)
        bad["data"]["open"][0] = None
        result, _ = self.collect(bad)
        self.assertIsNone(self.bars()[0]["prices"]["open"])
        self.assertIn("OHLC_UNKNOWN_OR_NONPOSITIVE", result["reason_codes"])

    def test_rate_limit_stops_without_retry_or_old_data_fallback(self):
        plan = deepcopy(self.plan)
        plan.update(datasets=["instruments", "daily_bars"], max_requests=2)
        opener = Opener([HTTPError("https://free-api.tickflow.org", 429, "private-message", {"Retry-After": "99999"}, BytesIO(b"private"))])
        result = collect_samples(plan, self.root / "sample", opener=opener, environ={})
        self.assertEqual((len(opener.calls), result["sent_requests"], result["requests"][1]["status"]), (1, 1, "skipped"))
        self.assertEqual(result["requests"][0]["retry_after_seconds"], 3600)
        self.assertNotIn("private-message", dumps(result))

    def test_redirect_and_transport_errors_do_not_expose_urls_or_follow(self):
        for i, failure in enumerate((HTTPError("https://private-url", 302, "private-message", {"Location": "https://evil.invalid"}, BytesIO()),
                                     URLError("private-proxy-credential"))):
            opener = Opener([failure])
            result = collect_samples(self.plan, self.root / str(i), opener=opener, environ={})
            self.assertEqual(len(opener.calls), 1)
            self.assertNotIn("private-", dumps(result))
            self.assertEqual(result["captured_responses"], 0)

    def test_missing_credential_or_authorization_performs_zero_requests(self):
        plan = self.tushare_plan()
        opener = Opener([])
        result = collect_samples(plan, self.root / "missing", opener=opener, environ={})
        self.assertEqual(result["sent_requests"], 0)
        self.assertIn("CREDENTIAL_MISSING", result["reason_codes"])
        plan["authorization"] = {"confirmed": False, "reference": None}
        result = collect_samples(plan, self.root / "unauthorized", opener=opener, environ={"TUSHARE_TOKEN": "test-only-secret"})
        self.assertEqual(result["sent_requests"], 0)
        self.assertIn("ACCESS_AUTHORIZATION_NOT_CONFIRMED", result["reason_codes"])
        self.assertEqual(opener.calls, [])

    def test_tushare_credentials_only_in_https_body_and_daily_units_are_explicit(self):
        plan = self.tushare_plan()
        row = dict(ts_code="000001.SZ", trade_date="20240102", open="10.01", high="11", low="9", close="10.02",
                   pre_close="10", vol="12.34", amount="12.3456789")
        result, opener = self.collect(self.table(plan, [row]), plan, environ={"TUSHARE_TOKEN": "test-only-secret"})
        req = opener.calls[0]
        self.assertEqual(req.full_url, "https://api.tushare.pro")
        self.assertEqual(json.loads(req.data)["token"], "test-only-secret")
        self.assertNotIn("test-only-secret", dumps(result))
        self.assertNotIn("test-only-secret", (self.root / "sample" / "snapshots.jsonl").read_text())
        self.assertEqual((self.bars()[0]["volume_shares"], self.bars()[0]["amount_cny"]), ("1234.00", "12345.6789000"))

    def test_tickflow_key_only_in_header_not_report_url_or_body(self):
        plan = deepcopy(self.plan)
        plan["provider"] = "tickflow"
        result, opener = self.collect(self.tick_bar, plan, environ={"TICKFLOW_API_KEY": "test-only-secret"})
        req = opener.calls[0]
        self.assertEqual(req.get_header("X-api-key"), "test-only-secret")
        self.assertIsNone(req.data)
        self.assertNotIn("test-only-secret", req.full_url)
        self.assertNotIn("test-only-secret", dumps(result))

    def test_sensitive_response_and_key_reflection_are_not_archived(self):
        plan = self.tushare_plan()
        for i, body in enumerate(({"code": 0, "data": {"api_key": "other-private-key"}},
                                  {"code": 0, "msg": "echo test-only-secret", "data": {}})):
            result, _ = self.collect(body, plan, name=str(i), environ={"TUSHARE_TOKEN": "test-only-secret"})
            self.assertIn("SENSITIVE_RESPONSE_SUPPRESSED", result["reason_codes"])
            self.assertEqual(list((self.root / str(i) / "raw").iterdir()), [])
            self.assertNotIn("other-private-key", dumps(result))
        result, _ = self.collect({"code": 0, "msg": "echo test%2Bonly%2Fsecret", "data": {}}, plan,
                                 name="encoded", environ={"TUSHARE_TOKEN": "test+only/secret"})
        self.assertIn("SENSITIVE_RESPONSE_SUPPRESSED", result["reason_codes"])
        self.assertEqual(list((self.root / "encoded" / "raw").iterdir()), [])

    def test_response_size_and_row_limit_never_silently_truncate(self):
        from stockradar.vendor_samples import MAX_BYTES
        result, _ = self.collect(b" " * (MAX_BYTES + 1))
        self.assertIn("RESPONSE_TOO_LARGE", result["reason_codes"])
        self.assertEqual(result["bar_count"], 0)
        many = deepcopy(self.tick_bar)
        many["data"] = {k: v * 10 for k, v in many["data"].items()}
        result, _ = self.collect(many, name="rowlimit")
        self.assertIn("POSSIBLE_RESPONSE_TRUNCATION", result["reason_codes"])
        self.assertEqual(result["bar_count"], 0)

    def test_table_width_and_bar_scope_errors_keep_no_partial_projection(self):
        plan = self.tushare_plan()
        malformed = self.table(plan, [dict(ts_code="000001.SZ")])
        malformed["data"]["items"][0].append("unexpected")
        result, _ = self.collect(malformed, plan, environ={"TUSHARE_TOKEN": "test-only-secret"})
        self.assertIn("TABLE_WIDTH_INVALID", result["reason_codes"])
        outside = deepcopy(self.tick_bar)
        outside["data"]["timestamp"] = [1704067200000]
        result, _ = self.collect(outside, name="outside")
        self.assertIn("PERIOD_OUTSIDE_REQUESTED_WINDOW", result["reason_codes"])
        self.assertEqual(result["bar_count"], 0)

    def test_error_body_never_archived_and_permission_block_only_current_dataset(self):
        plan = self.tushare_plan(["daily_bars", "memberships"])
        plan["symbols"].append({"symbol": "600000.SH", "board": "MAIN"})
        member_names = request_specs(plan)[2]["fields"].split(",")
        opener = Opener([{"code": 2002, "msg": "private-error", "data": None},
                         {"code": 0, "data": {"fields": member_names, "items": []}},
                         {"code": 0, "data": {"fields": member_names, "items": []}}])
        result = collect_samples(plan, self.root / "sample", opener=opener,
                                 environ={"TUSHARE_TOKEN": "test-only-secret"}, sleep=lambda _: None)
        self.assertEqual((len(opener.calls), result["requests"][1]["status"]), (3, "skipped"))
        self.assertEqual(result["requests"][0]["api_code"], 2002)
        self.assertNotIn("private-error", dumps(result))

    def test_tushare_minute_frequencies_units_and_unknown_closure(self):
        for dataset, frequency, time_field in (("minute_history", "1min", "trade_time"), ("minute_quotes", "1MIN", "time")):
            plan = self.tushare_plan([dataset])
            row = dict(ts_code="000001.SZ", open="10", high="11", low="9", close="10", vol="1234", amount="12340")
            row[time_field] = "2024-01-02 09:31:00"
            result, opener = self.collect(self.table(plan, [row]), plan, name=dataset, environ={"TUSHARE_TOKEN": "test-only-secret"})
            bar = self.bars(dataset)[0]
            self.assertEqual(json.loads(opener.calls[0].data)["params"]["freq"], frequency)
            self.assertEqual((bar["volume_shares"], bar["amount_cny"]), ("1234", "12340"))
            self.assertEqual(bar["source_time"], "2024-01-02T01:31:00+00:00")
            self.assertIsNone(bar["event_time"])
            self.assertIsNone(bar["is_complete"])
            self.assertFalse(result["strategy_input_ready"])

    def test_current_membership_snapshot_does_not_backfill_historical_eligibility(self):
        plan = self.tushare_plan(["memberships"])
        row = dict(ts_code="885800.TI", con_code="000001.SZ", con_name="test", in_date=None, out_date=None, is_new="Y")
        result, _ = self.collect(self.table(plan, [row]), plan, environ={"TUSHARE_TOKEN": "test-only-secret"})
        snapshot = json.loads((self.root / "sample" / "snapshots.jsonl").read_text())
        self.assertEqual(snapshot["rows"][0]["con_code"], "000001.SZ")
        self.assertIsNone(snapshot["source_effective_from"])
        self.assertFalse(snapshot["historical_eligibility_established"])
        self.assertIn("HISTORICAL_MEMBERSHIPS_NOT_VERIFIED", result["reason_codes"])

    def test_metadata_partial_or_unexpected_symbols_are_visible(self):
        plan = deepcopy(self.plan)
        plan["datasets"] = ["instruments"]
        plan["symbols"].append({"symbol": "600000.SH", "board": "MAIN"})
        result, _ = self.collect({"data": [{"symbol": "000001.SZ"}]}, plan)
        self.assertEqual(result["requests"][0]["status"], "partial")
        self.assertEqual(result["requests"][0]["missing_symbols"], ["600000.SH"])
        result, _ = self.collect({"data": [{"symbol": "999999.SH"}]}, plan, name="unexpected")
        self.assertIn("UNEXPECTED_SYMBOL", result["reason_codes"])

    def test_no_overwrite_and_bad_credential_fail_before_network(self):
        self.collect(self.tick_bar)
        opener = Opener([])
        with self.assertRaises(FileExistsError):
            collect_samples(self.plan, self.root / "sample", opener=opener, environ={})
        with self.assertRaises(ValueError):
            collect_samples(self.tushare_plan(), self.root / "invalid", opener=opener, environ={"TUSHARE_TOKEN": "bad\nkey"})
        self.assertFalse((self.root / "invalid").exists())
        self.assertEqual(opener.calls, [])

    def test_source_change_during_probe_marks_incomplete(self):
        with patch("stockradar.vendor_samples.source_hash", side_effect=["before", "after"]):
            result, _ = self.collect(self.tick_bar)
        self.assertEqual(result["status"], "incomplete")
        self.assertIn("CODE_CHANGED_DURING_PROBE", result["reason_codes"])

    def test_compare_daily_exact_decimals_missing_dates_and_unknown_units(self):
        self.collect(self.tick_bar, name="left")
        plan = self.tushare_plan()
        rows = [dict(ts_code="000001.SZ", trade_date="20240102", open="10", high="11", low="9", close="10.01", vol="10", amount="10"),
                dict(ts_code="000001.SZ", trade_date="20240103", open="10", high="11", low="9", close="10", vol="10", amount="10")]
        self.collect(self.table(plan, rows), plan, name="right", environ={"TUSHARE_TOKEN": "test-only-secret"})
        report = compare_samples(self.root / "left", self.root / "right")
        self.assertEqual(report["common_bars"], 1)
        self.assertEqual(report["right_only"], [["000001.SZ", "2024-01-03"]])
        self.assertEqual(report["comparisons"][0]["differences"], [{"field": "close", "left": "10", "right": "10.01"}])
        self.assertEqual(report["comparisons"][0]["unknown_fields"], ["volume_shares", "amount_cny"])
        self.assertFalse(report["strategy_input_ready"])

    def test_compare_rejects_same_provider_tampering_and_symlinks(self):
        left, _ = self.collect(self.tick_bar, name="left")
        self.collect(self.tick_bar, name="same")
        with self.assertRaises(ValueError):
            compare_samples(self.root / "left", self.root / "same")
        plan = self.tushare_plan()
        self.collect(self.table(plan, []), plan, name="right", environ={"TUSHARE_TOKEN": "test-only-secret"})
        raw = self.root / "left" / left["requests"][0]["raw_file"]
        raw.write_bytes(raw.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            compare_samples(self.root / "left", self.root / "right")
        (self.root / "link").symlink_to(self.root / "right", target_is_directory=True)
        with self.assertRaises(ValueError):
            compare_samples(self.root / "link", self.root / "right")

    def test_no_overlap_comparison_is_not_successful_validation(self):
        self.collect(self.tick_bar, name="left")
        plan = self.tushare_plan()
        self.collect(self.table(plan, []), plan, name="right", environ={"TUSHARE_TOKEN": "test-only-secret"})
        report = compare_samples(self.root / "left", self.root / "right")
        self.assertEqual((report["status"], report["common_bars"]), ("no_overlap", 0))
        self.assertEqual(report["minute_comparison"], "not_performed")
