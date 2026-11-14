"""Minute capture never bypasses account access, provenance or strategy gates."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from stockradar.connection_settings import ConnectionSettings
from stockradar.minute_feed import MinuteFeed
from stockradar.store import StoreError
from stockradar.vendor_samples import request_specs, _read_probe


class Response(BytesIO):
    def __init__(self, value):
        super().__init__(json.dumps(value).encode())
        self.code, self.headers = 200, {}


class Opener:
    def __init__(self, values, callback=None):
        self.values, self.calls, self.callback = list(values), [], callback

    def open(self, request, timeout):
        self.calls.append(request)
        if self.callback:
            self.callback()
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return Response(value)


class MinuteFeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.connections = ConnectionSettings(self.root / ".connections", environ={})
        self.timestamp = datetime(2026, 11, 8, 8, tzinfo=timezone.utc)
        self.feed = MinuteFeed(self.root / "minutes", self.connections, clock=lambda: self.timestamp)
        self.value = {"schema_version": 1, "mode": "session", "symbols": ["600519.SH"],
                      "start_date": None, "end_date": None, "access_confirmed": True}

    def tearDown(self):
        self.temp.cleanup()

    def configure(self, confirmed=True):
        return self.connections.save("tushare", {"schema_version": 1, "revision": "new", "key_action": "replace",
            "api_key": "synthetic-minute-secret", "authorization": {"confirmed": confirmed, "reference": "synthetic-minute-access"}})

    def table(self, symbols=None, mode=None, freq="1MIN", stamp="2026-11-06 14:59:00"):
        value = dict(self.value, mode=mode or self.value["mode"])
        if value["mode"] == "history":
            value.update(start_date="2026-11-06", end_date="2026-11-06")
        names = request_specs(self.feed.plan(value))[0]["fields"].split(",")
        rows = []
        for symbol in symbols or self.value["symbols"]:
            row = {"ts_code": symbol, "freq": freq, "time": stamp, "trade_time": stamp,
                   "open": "10.000000000000000001", "high": "11", "low": "9", "close": "10.5", "vol": 100, "amount": "1010.25"}
            rows.append([row.get(name) for name in names])
        return {"code": 0, "msg": None, "data": {"fields": names, "items": rows}}

    def test_missing_key_and_confirmation_are_zero_request_and_no_output(self):
        with patch("stockradar.vendor_samples.request.build_opener") as network:
            prepared = self.feed.prepare(self.value)
            self.assertEqual(prepared["sent_requests"], 0)
            self.assertEqual(set(prepared["reason_codes"]), {"CREDENTIAL_MISSING", "ACCESS_AUTHORIZATION_NOT_CONFIRMED"})
            with self.assertRaises(StoreError):
                self.feed.fetch(self.value)
            self.assertEqual(self.feed.describe()["groups"], [])
            network.assert_not_called()
        self.assertFalse(self.feed.directory.exists())

    def test_saved_key_is_not_enough_without_each_access_confirmation(self):
        self.configure(confirmed=False)
        self.assertIn("ACCESS_AUTHORIZATION_NOT_CONFIRMED", self.feed.prepare(self.value)["reason_codes"])
        profile = self.connections.market_status("tushare")
        self.connections.save("tushare", {"schema_version":1,"revision":profile["revision"],"key_action":"keep","api_key":"",
            "authorization":{"confirmed":True,"reference":"synthetic-access"}})
        with self.assertRaises(StoreError):
            self.feed.fetch(dict(self.value, access_confirmed=False))
        self.assertEqual(self.feed.prepare(self.value)["status"], "prepared_not_permission_verified")
        self.assertFalse(self.feed.directory.exists())

    def test_unknown_fields_codes_dates_and_budget_fail_before_network(self):
        bad_values = [dict(self.value, api_key="synthetic-secret"), dict(self.value, mode="unknown"),
            dict(self.value, schema_version=True), dict(self.value, access_confirmed=1),
            dict(self.value, symbols=["600519.SH"]*4), dict(self.value, symbols=["600519.SH"]*2),
            dict(self.value, symbols=["000001.SH"]), dict(self.value, symbols=["000001"]),
            dict(self.value, start_date="2026-11-06"),
            dict(self.value, mode="history", start_date="2026-11-08", end_date="2026-11-08"),
            dict(self.value, mode="history", start_date="2026-10-01", end_date="2026-11-06")]
        with patch("stockradar.vendor_samples.request.build_opener") as network:
            for value in bad_values:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    self.feed.prepare(value)
            network.assert_not_called()
        self.assertFalse(self.feed.directory.exists())

    def test_session_uses_day_endpoint_and_keeps_unknown_times_and_decimal(self):
        self.configure()
        opener = Opener([self.table()])
        result = self.feed.fetch(self.value, opener=opener, sleep=lambda _: None)
        body = json.loads(opener.calls[0].data)
        self.assertEqual(body["api_name"], "rt_min_daily")
        self.assertEqual(body["params"], {"ts_code":"600519.SH","freq":"1MIN"})
        row = result["groups"][0]["bars"][0]
        self.assertEqual(row["prices"]["open"], "10.000000000000000001")
        self.assertEqual(row["volume_shares"], "100")
        self.assertEqual(row["source_time"], "2026-11-06T06:59:00+00:00")
        self.assertIsNone(row["event_time"])
        self.assertIsNone(row["is_complete"])
        self.assertFalse(result["strategy_input_ready"])
        self.assertFalse(result["automatic_collection"])
        self.assertGreater(result["groups"][0]["label_age_seconds"], 86400)
        for path in self.feed.directory.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"synthetic-minute-secret", path.read_bytes())
        self.assertNotIn("synthetic-minute-secret", json.dumps(result))
        self.assertEqual(os.stat(self.feed.directory / "latest.json").st_mode & 0o777, 0o600)

    def test_latest_batches_symbols_once_and_historical_request_uses_explicit_dates(self):
        self.configure()
        self.value.update(mode="latest", symbols=["600519.SH", "300750.SZ", "688981.SH"])
        self.assertEqual(self.feed.prepare(self.value)["planned_requests"], 1)
        opener = Opener([self.table()])
        result = self.feed.fetch(self.value, opener=opener)
        self.assertEqual(json.loads(opener.calls[0].data)["api_name"], "rt_min")
        self.assertEqual(result["capture"]["bar_count"], 3)
        self.timestamp += timedelta(seconds=61)
        historical = dict(self.value, mode="history", symbols=["600519.SH"], start_date="2026-11-06", end_date="2026-11-06")
        opener = Opener([self.table(symbols=["600519.SH"], mode="history")])
        result = self.feed.fetch(historical, opener=opener)
        request = json.loads(opener.calls[0].data)
        self.assertEqual(request["api_name"], "stk_mins")
        self.assertEqual(request["params"]["start_date"], "2026-11-06 09:00:00")
        self.assertEqual(request["params"]["end_date"], "2026-11-06 15:30:00")
        self.assertEqual(result["capture"]["bar_count"], 1)

    def test_wrong_frequency_and_duplicate_minutes_keep_raw_but_no_false_projection(self):
        self.configure()
        opener = Opener([self.table(freq="5MIN")])
        result = self.feed.fetch(self.value, opener=opener)
        self.assertEqual(result["capture"]["bar_count"], 0)
        self.assertIn("MINUTE_INTERVAL_MISMATCH", result["capture"]["reason_codes"])
        raw = self.feed.directory / result["capture"]["id"] / "raw/01-intraday.json"
        self.assertTrue(raw.exists())
        self.timestamp += timedelta(seconds=61)
        body = self.table();body["data"]["items"] *= 2
        result = self.feed.fetch(self.value, opener=Opener([body]))
        self.assertIn("DUPLICATE_PERIOD_LABEL", result["capture"]["reason_codes"])
        self.assertEqual(result["capture"]["bar_count"], 0)

    def test_permission_denied_stops_same_dataset_and_suppresses_error_echo(self):
        self.configure()
        self.value["symbols"] = ["600519.SH", "300750.SZ", "688981.SH"]
        opener = Opener([{"code":2002,"msg":"private permission message","data":None}])
        result = self.feed.fetch(self.value, opener=opener)
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(result["capture"]["sent_requests"], 1)
        self.assertIn("VENDOR_PERMISSION_DENIED", result["capture"]["reason_codes"])
        self.assertEqual(list((self.feed.directory / result["capture"]["id"] / "raw").iterdir()), [])
        self.assertNotIn("synthetic-minute-secret", json.dumps(result))

    def test_sensitive_response_stops_all_requests_without_echo_or_archive(self):
        self.configure()
        self.value["symbols"] = ["600519.SH", "300750.SZ", "688981.SH"]
        opener = Opener([{"code":2002,"msg":"echo synthetic-minute-secret","data":None}])
        result = self.feed.fetch(self.value, opener=opener)
        self.assertEqual(len(opener.calls), 1)
        self.assertIn("SENSITIVE_RESPONSE_SUPPRESSED", result["capture"]["reason_codes"])
        self.assertNotIn("synthetic-minute-secret", json.dumps(result))
        self.assertEqual(list((self.feed.directory / result["capture"]["id"] / "raw").iterdir()), [])

    def test_rate_limit_or_transport_error_never_retries(self):
        self.configure()
        self.value["symbols"] = ["600519.SH", "300750.SZ"]
        errors = [HTTPError("https://api.tushare.pro",429,"limit",{},BytesIO()), URLError("synthetic proxy credential")]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                opener = Opener([error])
                result = self.feed.fetch(self.value, opener=opener)
                self.assertEqual(len(opener.calls), 1)
                self.assertEqual(result["capture"]["bar_count"], 0)
                self.assertNotIn("synthetic proxy credential", json.dumps(result))
                self.timestamp += timedelta(seconds=61)

    def test_concurrent_services_and_restart_cooldown_do_not_double_request(self):
        self.configure()
        other = MinuteFeed(self.feed.directory, self.connections, clock=lambda:self.timestamp)
        errors = []
        def concurrent():
            try:
                other.fetch(self.value, opener=Opener([]))
            except StoreError as exc:
                errors.append(exc.code)
        opener = Opener([self.table()], callback=concurrent)
        self.feed.fetch(self.value, opener=opener)
        self.assertEqual(errors, ["MINUTE_BUSY"])
        with self.assertRaises(StoreError) as raised:
            other.fetch(self.value, opener=Opener([]))
        self.assertEqual(raised.exception.code, "MINUTE_COOLDOWN")
        self.assertEqual(len(opener.calls), 1)

    def test_failed_refresh_does_not_merge_old_data_and_retains_original(self):
        self.configure()
        first = self.feed.fetch(self.value, opener=Opener([self.table()]))
        self.timestamp += timedelta(seconds=61)
        second = self.feed.fetch(self.value, opener=Opener([{"code":2002,"data":None}]))
        self.assertEqual(second["capture"]["bar_count"], 0)
        self.assertEqual(second["groups"][0]["bars"], [])
        self.assertNotEqual(first["capture"]["id"], second["capture"]["id"])
        self.assertEqual(len(_read_probe(self.feed.directory / first["capture"]["id"])[1]), 1)

    def test_read_only_view_validates_hashes_and_rejects_paths_and_symlinks(self):
        self.configure()
        result = self.feed.fetch(self.value, opener=Opener([self.table()]))
        sample = self.feed.directory / result["capture"]["id"]
        (sample / "bars.jsonl").write_text("{}\n")
        with self.assertRaises(ValueError):
            self.feed.describe()
        self.feed._write("latest.json", {"schema_version":1,"id":"../secret"})
        with self.assertRaises(ValueError):
            self.feed.describe()
        (self.feed.directory / "latest.json").unlink()
        (self.feed.directory / "latest.json").symlink_to(self.root / "unrelated")
        with self.assertRaises(ValueError):
            self.feed.describe()

    def test_unfinished_capture_is_explicit_and_never_auto_resumed(self):
        self.feed._write("attempt.json", {"schema_version":1,"id":"a"*32,"mode":"session","started_at":self.timestamp.isoformat(),"status":"running"})
        with patch("stockradar.vendor_samples.request.build_opener") as network:
            result = self.feed.describe()
            self.assertEqual(result["attempt"]["status"], "unfinished")
            self.assertIsNone(result["capture"])
            network.assert_not_called()
