import base64
import copy
import hashlib
import hmac
import io
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib import error, parse

from stockradar.notifier import DingTalkNotifier, NotificationConfigError, build_group_message, build_message
from stockradar.providers import (HTTPJSONProvider, JSONLProvider, ProviderError,
                                  record_batches, validate_batch)


def valid_batch():
    at = "2026-10-28T02:01:00Z"
    quote = {"instrument_id": "SZSE.000001", "open": "10", "high": "10.2", "low": "10",
             "close": "10.1", "prev_close": "10", "volume_shares": "100000",
             "amount_cny": "1000000", "interval": 60, "is_complete": True,
             "event_time": at, "available_at": at, "ingested_at": at,
             "adjustment_factor": "1", "source": "synthetic", "quality": "good", "revision": 1}
    daily = {"instrument_id": quote["instrument_id"], "date": "2026-10-27", "high": "10.1",
             "low": "9.9", "close": "10", "prev_close": "10", "amount_cny": "2000000",
             "adjustment_factor": "1", "available_at": "2026-10-27T08:00:00Z"}
    return {"schema_version": 1, "snapshot_id": "sample-1", "source": "synthetic", "simulated": True,
            "as_of": at, "units": {"volume": "shares", "amount": "CNY", "amount_mode": "cumulative"},
            "calendar": {"version": "fixture-1", "trading_dates": ["2026-10-28"],
                         "sessions": [["09:30", "11:30"], ["13:00", "14:57"]]},
            "instruments": [{"id": quote["instrument_id"], "code": "000001", "name": "测试证券",
                             "exchange": "SZSE", "board": "MAIN", "listed_on": "2000-01-01",
                             "status": "active", "valid_from": "2000-01-01", "valid_to": None,
                             "available_at": "2000-01-01T00:00:00Z"}],
            "sectors": [{"id": "sector-1", "name": "测试行业", "type": "industry"}],
            "memberships": [{"instrument_id": quote["instrument_id"], "sector_id": "sector-1",
                             "valid_from": "2020-01-01", "valid_to": None,
                             "available_at": "2020-01-01T00:00:00Z", "provider": "synthetic", "snapshot_id": "m-1"}],
            "quotes": [quote], "daily_bars": [daily], "minute_history": [],
            "benchmark": {"id": "INDEX", "quote": dict(quote, instrument_id="INDEX"),
                          "daily_bars": [dict(daily, instrument_id="INDEX")], "minute_history": []}}


class FakeResponse:
    def __init__(self, data, status=200):
        self.data = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.data[:limit]


class ProviderTests(unittest.TestCase):
    def test_effective_interval_contract_and_mixed_boundaries(self):
        for collection in ("instruments", "memberships"):
            for start, end in (("2026-10-28", "2026-10-28T02:01:00Z"),
                               ("2026-10-28T02:01:00+00:00", "2026-10-29"),
                               (None, None)):
                with self.subTest(collection=collection, start=start, end=end):
                    batch = valid_batch()
                    batch[collection][0].update(valid_from=start, valid_to=end)
                    original = copy.deepcopy(batch)
                    self.assertEqual(validate_batch(batch), original)

    def test_invalid_effective_boundaries_rejected(self):
        for collection in ("instruments", "memberships"):
            for start, end in (("2026-10-29", "2026-10-28"),
                               ("2026-10-28", "2026-10-27T16:00:00Z"),
                               ("2026-10-28T02:01:00Z", "2026-10-28T02:01:00Z"),
                               ("2026-10-28T10:01:00+08:00", None),
                               ("2026-10-28T02:01:00", None),
                               ("2026-02-30", None), (False, None), ("", None)):
                with self.subTest(collection=collection, start=start, end=end):
                    batch = valid_batch()
                    batch[collection][0].update(valid_from=start, valid_to=end)
                    with self.assertRaises(ProviderError) as caught:
                        validate_batch(batch)
                    self.assertEqual(caught.exception.code, "DATA_INVALID")

    def test_lossless_roundtrip_preserves_leading_zero_and_null(self):
        batch = valid_batch()
        batch["quotes"][0]["close"] = None
        original = copy.deepcopy(batch)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.jsonl"
            self.assertEqual(record_batches(path, [batch]), 1)
            restored = list(JSONLProvider(path).iter_batches())
        self.assertEqual(restored, [original])
        self.assertEqual(batch, original)
        self.assertEqual(restored[0]["instruments"][0]["code"], "000001")

    def test_bad_units_are_rejected_not_converted(self):
        batch = valid_batch()
        batch["units"]["volume"] = "lots"
        with self.assertRaises(ProviderError) as caught:
            validate_batch(batch)
        self.assertEqual(caught.exception.code, "UNIT_MISMATCH")

    def test_non_utc_and_numeric_code_rejected(self):
        for path, value in [("as_of", "2026-10-28T10:01:00"), ("code", 1)]:
            batch = valid_batch()
            if path == "as_of":
                batch[path] = value
            else:
                batch["instruments"][0][path] = value
            with self.assertRaises(ProviderError):
                validate_batch(batch)

    def test_nan_duplicate_keys_and_large_lines_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.jsonl"
            for raw in ('{"x": NaN}', '{"x": 1, "x": 2}'):
                path.write_text(raw, encoding="utf-8")
                with self.assertRaises(ProviderError) as caught:
                    list(JSONLProvider(path).iter_batches())
                self.assertIn("第 1 行", str(caught.exception))
            path.write_text("x" * 32, encoding="utf-8")
            with self.assertRaises(ProviderError) as caught:
                list(JSONLProvider(path, max_line_bytes=16).iter_batches())
            self.assertEqual(caught.exception.code, "DATA_TOO_LARGE")

    def test_failed_export_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recording.jsonl"
            path.write_text("previous", encoding="utf-8")
            with self.assertRaises(ProviderError):
                record_batches(path, [valid_batch(), {"broken": True}])
            self.assertEqual(path.read_text(), "previous")
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_http_success_and_auth_header(self):
        opener = Mock()
        opener.open.return_value = FakeResponse(valid_batch())
        provider = HTTPJSONProvider("https://data.example.test/v1/slice", "private-key", opener=opener)
        batch = provider.get_slice("2026-10-28T02:01:00Z")
        req = opener.open.call_args.args[0]
        self.assertEqual(req.get_header("Authorization"), "Bearer private-key")
        self.assertNotIn("private-key", req.full_url)
        self.assertEqual(batch["snapshot_id"], "sample-1")
        self.assertFalse(provider.capabilities()["full_market_verified"])

    def test_gateway_url_must_be_https_and_no_embedded_secrets(self):
        for url in ("http://data.test", "https://user:password@data.test", "https://data.test/?token=secret"):
            with self.assertRaises(ProviderError):
                HTTPJSONProvider(url)

    def test_http_limit_and_network_error_are_visible_and_redacted(self):
        opener = Mock()
        opener.open.side_effect = error.HTTPError("https://example.test/secret", 429, "secret", {"Retry-After": "45"}, io.BytesIO())
        provider = HTTPJSONProvider("https://example.test/", opener=opener)
        with self.assertRaises(ProviderError) as caught:
            provider.fetch()
        self.assertEqual(caught.exception.code, "PROVIDER_LIMITED")
        self.assertEqual(caught.exception.retry_after, 45)
        self.assertNotIn("secret", str(caught.exception))
        opener.open.side_effect = error.URLError("https://example.test/?token=secret")
        with self.assertRaises(ProviderError) as caught:
            provider.fetch()
        self.assertEqual(caught.exception.code, "PROVIDER_UNAVAILABLE")
        self.assertNotIn("secret", str(caught.exception))


class NotificationTests(unittest.TestCase):
    webhook = "https://oapi.dingtalk.com/robot/send?access_token=private-token"

    def send(self, response):
        opener = Mock()
        if isinstance(response, Exception):
            opener.open.side_effect = response
        else:
            opener.open.return_value = FakeResponse(response)
        notifier = DingTalkNotifier(self.webhook, "SEC-test", opener=opener)
        return notifier.send(build_message({}, {}, test=True), "test-1"), opener

    def test_signature_uses_milliseconds_newline_hmac_and_urlencoding(self):
        with patch("stockradar.notifier.time.time", return_value=1700000000.125):
            result, opener = self.send({"errcode": 0, "errmsg": "ok"})
        req = opener.open.call_args.args[0]
        params = parse.parse_qs(parse.urlsplit(req.full_url).query)
        self.assertEqual(params["timestamp"], ["1700000000125"])
        expected = base64.b64encode(hmac.new(b"SEC-test", b"1700000000125\nSEC-test", hashlib.sha256).digest()).decode()
        self.assertEqual(params["sign"], [expected])
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(result["status"], "accepted")
        self.assertNotIn("private-token", json.dumps(result))

    def test_timeout_is_unknown_and_not_retryable(self):
        result, _ = self.send(socket.timeout("secret"))
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["retryable"])
        self.assertNotIn("secret", json.dumps(result))

    def test_explicit_platform_failure_is_not_success(self):
        result, _ = self.send({"errcode": 310000, "errmsg": "wrong SEC-test private-token"})
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["receipt"], {"errcode": 310000})
        self.assertFalse(result["retryable"])
        self.assertNotIn("SEC-test", json.dumps(result))

    def test_ambiguous_responses_are_unknown(self):
        for response in (b"not JSON", {}, {"errcode": False}, {"errcode": "0"}, []):
            result, _ = self.send(response)
            self.assertEqual(result["status"], "unknown")
            self.assertFalse(result["retryable"])

    def test_bad_webhook_urls_rejected_without_network(self):
        invalid = ["http://oapi.dingtalk.com/robot/send?access_token=token",
                   "https://oapi.dingtalk.com.evil.test/robot/send?access_token=token",
                   "https://oapi.dingtalk.com@evil.test/robot/send?access_token=token",
                   "https://oapi.dingtalk.com/evil?access_token=token",
                   "https://oapi.dingtalk.com/robot/send?access_token=a&access_token=b",
                   "https://oapi.dingtalk.com/robot/send?access_token=a&redirect=evil"]
        for url in invalid:
            with self.assertRaises(NotificationConfigError):
                DingTalkNotifier(url)

    def test_message_has_separate_prices_simulation_and_no_credential_link(self):
        signal = {"id": "s-1", "code": "000001", "name": "测试", "status": "PREALERT",
                  "score": 82, "trigger_price": "10.10", "latest_price": "10.30",
                  "trigger_time": "2026-10-28T02:00:00Z", "latest_time": "2026-10-28T02:01:00Z",
                  "evidence": {"simulated": True, "source": "fixture"}}
        payload = build_message(signal, {}, base_url="https://radar.example.test")
        content = payload["markdown"]["text"]
        self.assertIn("模拟数据", payload["markdown"]["title"])
        self.assertIn("非胜率", content)
        self.assertIn("10:00:00", content)
        self.assertIn("10:01:00", content)
        self.assertIn("https://radar.example.test/#signals/s-1", content)
        with self.assertRaises(NotificationConfigError):
            build_message(signal, {}, base_url="https://radar.example.test/?token=secret")

    def test_group_message_preserves_escaping_times_and_simulation_warning(self):
        signals = [{"id": "s-%d" % i, "code": "%06d" % i, "name": "[伪链接](https://invalid.test)",
                    "status": "PREALERT", "actionability": "eligible", "trigger_price": "10.10",
                    "latest_price": "10.30", "trigger_time": "2026-10-28T02:00:00Z",
                    "latest_time": "2026-10-28T02:01:00Z", "evidence": {"simulated": bool(i)}}
                   for i in range(2)]
        payload = build_group_message([build_message(s, {}) for s in signals])
        self.assertIn("模拟数据", payload["markdown"]["title"])
        self.assertNotIn("[伪链接]", payload["markdown"]["text"])
        for signal in signals:
            self.assertIn(signal["id"], payload["markdown"]["text"])
            self.assertIn(signal["code"], payload["markdown"]["text"])
        self.assertEqual(payload["markdown"]["text"].count("10:00:00"), 2)
        self.assertEqual(payload["markdown"]["text"].count("10:01:00"), 2)
        self.assertFalse(payload["at"]["isAtAll"])


if __name__ == "__main__":
    unittest.main()
