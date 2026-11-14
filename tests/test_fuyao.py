from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from stockradar.contracts import load_json
from stockradar.store import dumps
from stockradar.vendor_samples import collect_samples, compare_samples, prepare_samples, request_specs, validate_sample_plan


ROOT = Path(__file__).resolve().parent.parent


class Response(BytesIO):
    def __init__(self, body):
        super().__init__(body if isinstance(body, bytes) else json.dumps(body).encode())
        self.code, self.headers = 200, {}


def envelope(items, **data):
    return {"code": 0, "message": "success", "request_id": "synthetic-test", "data": {"item": items, **data}}


class FuyaoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.plan = load_json(ROOT / "configs/vendor-sample-fuyao-template.json")
        self.plan.update(symbols=[{"symbol": "600519.SH", "board": "MAIN"}], datasets=["daily_bars"],
                         start_date="2024-01-02", end_date="2024-01-03", max_requests=20,
                         authorization={"confirmed": True, "reference": "synthetic-only"})
        self.row = {"date_ms": 1704124800000, "open_price": "10.000000000000000001", "high_price": 11,
                    "low_price": 9, "close_price": "10.02", "volume": 123, "turnover": "1234.56"}

    def tearDown(self):
        self.temp.cleanup()

    def body(self, rows=None, symbol="600519.SH"):
        return envelope([{"thscode": symbol, "timestamp": 1704124800000, "item": [self.row] if rows is None else rows}],
                        interval="1d", adjust="none")

    def collect(self, bodies, plan=None, directory="sample", environ=None):
        opener = Mock()
        opener.open.side_effect = [Response(b) for b in bodies]
        result = collect_samples(plan or self.plan, self.root / directory, opener=opener,
                                 environ={"FUYAO_API_KEY": "synthetic-test-secret"} if environ is None else environ, sleep=lambda _: None)
        return result, opener

    def test_template_is_bounded_and_cannot_request_minute_or_custom_endpoints(self):
        plan = load_json(ROOT / "configs/vendor-sample-fuyao-template.json")
        specs = request_specs(validate_sample_plan(plan))
        self.assertEqual(len(specs), 12)
        self.assertFalse(plan["authorization"]["confirmed"])
        daily = next(s for s in specs if s["dataset"] == "daily_bars")
        self.assertEqual((daily["params"]["interval"], daily["params"]["adjust"]), ("1d", "none"))
        for change in ({"datasets": ["minute_history"]}, {"max_requests": 21}, {"endpoint": "https://example.invalid"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_sample_plan(dict(plan, **change))

    def test_dry_run_and_missing_key_perform_no_requests(self):
        with patch("stockradar.vendor_samples.request.build_opener") as network:
            prepared = prepare_samples(self.plan, environ={})
            self.assertEqual(prepared["sent_requests"], 0)
            self.assertIn("CREDENTIAL_MISSING", prepared["reason_codes"])
            network.assert_not_called()
        result, opener = self.collect([], environ={})
        self.assertEqual(result["sent_requests"], 0)
        opener.open.assert_not_called()
        plan = deepcopy(self.plan)
        plan["authorization"] = {"confirmed": False, "reference": None}
        result, opener = self.collect([], plan, directory="noauth")
        opener.open.assert_not_called()

    def test_daily_precision_documented_units_and_observed_availability(self):
        result, opener = self.collect([self.body()])
        bar = json.loads((self.root / "sample/bars.jsonl").read_text())
        self.assertEqual(bar["prices"]["open"], "10.000000000000000001")
        self.assertEqual((bar["volume_shares"], bar["amount_cny"]), ("123", "1234.56"))
        self.assertEqual(bar["label"], "2024-01-02")
        self.assertIsNone(bar["event_time"])
        self.assertIsNone(bar["is_complete"])
        self.assertIsNone(bar["source_available_at"])
        self.assertGreater(datetime.fromisoformat(bar["available_at"]), datetime(2024, 1, 2, tzinfo=timezone.utc))
        self.assertEqual(bar["unit_basis"], "fuyao_documented_not_independently_verified")
        req = opener.open.call_args[0][0]
        self.assertEqual(req.get_header("X-api-key"), "synthetic-test-secret")
        self.assertNotIn("synthetic-test-secret", req.full_url + dumps(result))
        self.assertFalse(result["strategy_input_ready"] or result["release_allowed"])

    def test_partial_batch_preserves_omitted_and_empty_targets(self):
        plan = deepcopy(self.plan)
        plan["symbols"] += [{"symbol": "300750.SZ", "board": "CHINEXT"}, {"symbol": "688981.SH", "board": "STAR"}]
        body = self.body()
        body["data"]["item"].append({"thscode": "300750.SZ", "timestamp": None, "item": []})
        result, _ = self.collect([body], plan)
        record = result["requests"][0]
        self.assertEqual(record["status"], "partial")
        self.assertEqual(record["missing_symbols"], ["688981.SH"])
        self.assertEqual(record["empty_symbols"], ["300750.SZ"])
        self.assertEqual(result["bar_count"], 1)

    def test_empty_success_is_not_a_captured_data_sample(self):
        result, _ = self.collect([self.body([])])
        self.assertEqual((result["requests"][0]["status"], result["captured_responses"]), ("empty", 0))

    def test_business_rate_limit_and_invalid_auth_stop_remaining_requests(self):
        for code in (4001, 2001):
            plan = dict(self.plan, datasets=["daily_bars", "quotes"])
            result, opener = self.collect([{"code": code, "message": "private-error", "data": None}], plan, str(code))
            self.assertEqual(opener.open.call_count, 1)
            self.assertEqual(result["requests"][1]["status"], "skipped")
            self.assertEqual(list((self.root / str(code) / "raw").iterdir()), [])
            self.assertNotIn("private-error", dumps(result))

    def test_capability_denial_does_not_hide_other_dataset(self):
        plan = dict(self.plan, datasets=["daily_bars", "quotes"])
        result, opener = self.collect([{"code": 2003, "message": "private-error", "data": None},
                                       envelope([{"thscode": "600519.SH", "last_price": 10}])], plan)
        self.assertEqual(opener.open.call_count, 2)
        self.assertEqual(result["requests"][0]["reason_code"], "VENDOR_PERMISSION_DENIED")
        self.assertEqual(result["requests"][1]["status"], "captured")

    def test_wrong_adjustment_duplicate_and_foreign_groups_keep_raw_not_bars(self):
        adjusted = self.body(); adjusted["data"]["adjust"] = "forward"
        duplicate = self.body(); duplicate["data"]["item"] *= 2
        for n, body in enumerate((adjusted, duplicate, self.body(symbol="000001.SZ"), self.body([self.row, self.row]))):
            result, _ = self.collect([body], directory=str(n))
            self.assertEqual(result["bar_count"], 0)
            self.assertIsNotNone(result["requests"][0]["raw_file"])
            self.assertEqual(result["status"], "incomplete")

    def test_current_memberships_never_establish_historical_eligibility(self):
        plan = dict(self.plan, datasets=["memberships"])
        result, _ = self.collect([envelope([{"thscode": "600519.SH", "index_list": []}])], plan)
        snapshot = json.loads((self.root / "sample/snapshots.jsonl").read_text())
        self.assertEqual(snapshot["rows"][0]["index_list"], [])
        self.assertFalse(snapshot["historical_eligibility_established"])
        self.assertIsNone(snapshot["source_effective_from"])
        self.assertEqual(result["requests"][0]["empty_symbols"], ["600519.SH"])

    def test_secret_echo_is_suppressed_before_raw_archive(self):
        body = self.body(); body["message"] = "synthetic-test-secret"
        result, _ = self.collect([body])
        self.assertIn("SENSITIVE_RESPONSE_SUPPRESSED", result["reason_codes"])
        self.assertEqual(list((self.root / "sample/raw").iterdir()), [])

    def test_future_daily_window_never_requests_data(self):
        plan = dict(self.plan, start_date="2099-01-01", end_date="2099-01-02")
        result, opener = self.collect([], plan)
        opener.open.assert_not_called()
        self.assertIn("HISTORY_WINDOW_NOT_CLOSED", result["reason_codes"])
