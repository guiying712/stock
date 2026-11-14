from copy import deepcopy
from io import BytesIO
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from stockradar.connection_settings import ConnectionSettings, MARKETS
from stockradar.store import dumps
from stockradar.vendor_samples import prepare_samples
from stockradar.contracts import load_json


class Response(BytesIO):
    def __init__(self, body):
        super().__init__(body if isinstance(body, bytes) else json.dumps(body).encode())
        self.code, self.headers = 200, {}


class ConnectionSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "connections"
        self.manager = ConnectionSettings(self.root, environ={})

    def tearDown(self):
        self.temp.cleanup()

    def payload(self, identifier="fuyao", **changes):
        profile = self.manager._describe(identifier)
        value = {"schema_version": 1, "revision": profile["revision"], "key_action": "replace", "api_key": "synthetic-secret-only"}
        value.update({"base_url": "https://model.example.invalid/v1", "model": "test-model", "timeout_seconds": 15} if identifier == "model" else
                     {"authorization": {"confirmed": True, "reference": "synthetic-permission-only"}})
        value.update(changes)
        return value

    def opener(self, body):
        opener = Mock(); opener.open.return_value = Response(body)
        return opener

    def test_status_read_is_side_effect_free_and_never_contains_secrets(self):
        result = self.manager.describe()
        self.assertEqual(len(result["market"]), 3)
        self.assertFalse(self.root.exists())
        self.assertFalse(result["model"]["credential"]["configured"])
        self.assertFalse(result["release_allowed"])

    def test_private_token_file_and_redacted_metadata_survive_restart(self):
        self.manager.save("fuyao", self.payload())
        result = ConnectionSettings(self.root, environ={}).describe()
        self.assertTrue(result["market"][0]["credential"]["configured"])
        self.assertNotIn("synthetic-secret-only", dumps(result))
        self.assertNotIn("synthetic-secret-only", (self.root / "fuyao.json").read_text())
        tokens = list(self.root.glob("*.token"))
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].read_text(), "synthetic-secret-only")
        self.assertEqual(stat.S_IMODE(tokens[0].stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)

    def test_keep_replace_clear_and_stale_revision(self):
        old = self.payload(); self.manager.save("fuyao", old)
        with self.assertRaises(ValueError): self.manager.save("fuyao", old)
        self.manager.save("fuyao", self.payload(key_action="keep", api_key=""))
        self.assertEqual(self.manager.market_credential("fuyao"), "synthetic-secret-only")
        self.manager.save("fuyao", self.payload(api_key="replacement-only"))
        self.assertEqual(len(list(self.root.glob("*.token"))), 1)
        self.assertEqual(self.manager.market_credential("fuyao"), "replacement-only")
        self.manager.save("fuyao", self.payload(key_action="clear", api_key=""))
        self.assertEqual(self.manager.market_credential("fuyao"), "")
        self.assertFalse(list(self.root.glob("*.token")))

    def test_environment_precedes_local_without_being_changed_by_save(self):
        env = {"FUYAO_API_KEY": "environment-test-key"}
        self.manager.environ = env
        self.manager.save("fuyao", self.payload())
        self.assertEqual(self.manager.market_credential("fuyao"), "environment-test-key")
        self.manager.save("fuyao", self.payload(key_action="clear", api_key=""))
        self.assertTrue(self.manager.describe()["market"][0]["credential"]["configured"])
        self.assertEqual(env["FUYAO_API_KEY"], "environment-test-key")
        self.assertNotIn("environment-test-key", dumps(self.manager.describe()))

    def test_strict_fields_key_validation_and_secret_in_metadata(self):
        values = [self.payload(extra=True), self.payload(api_key="bad\nkey"), self.payload(schema_version=True),
                  self.payload(authorization={"confirmed": True, "reference": None}),
                  self.payload(authorization={"confirmed": True, "reference": "synthetic-secret-only"})]
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError): self.manager.save("fuyao", value)
        self.assertFalse(self.root.exists())

    def test_remote_http_credentials_urls_queries_and_fragments_rejected(self):
        for url in ("http://remote.invalid/v1", "https://user:pass@service.invalid/v1", "https://host.invalid/v1?key=x", "https://host.invalid/v1#key", "file:///tmp/key", "https://host.invalid/%2e%2e", "https://host.invalid:99999"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.manager.save("model", self.payload("model", base_url=url))
        self.assertFalse(self.root.exists())

    def test_model_directory_check_sends_no_generation_and_uses_header(self):
        self.manager.save("model", self.payload("model"))
        opener = self.opener({"data": [{"id": "test-model"}]})
        result = self.manager.test("model", opener)
        req = opener.open.call_args[0][0]
        self.assertEqual(req.full_url, "https://model.example.invalid/v1/models")
        self.assertIsNone(req.data)
        self.assertEqual(req.get_header("Authorization"), "Bearer synthetic-secret-only")
        self.assertEqual(result["status"], "reachable")
        self.assertFalse(result["inference_tested"] or result["strategy_input_ready"])
        self.assertNotIn("synthetic-secret-only", dumps(self.manager.describe()))

    def test_model_not_listed_and_bad_response_do_not_pass_inference(self):
        self.manager.save("model", self.payload("model"))
        for body, status in (({"data": [{"id": "other"}]}, "model_not_listed"), ({"data": "invalid"}, "failed"), ({"data": []}, "model_not_listed")):
            result = self.manager.test("model", self.opener(body))
            self.assertEqual(result["status"], status)
            self.assertFalse(result["inference_tested"])

    def test_loopback_compatible_service_can_have_no_key(self):
        self.manager.save("model", self.payload("model", base_url="http://127.0.0.1:11434/v1/", key_action="keep", api_key=""))
        opener = self.opener({"data": [{"id": "test-model"}]})
        self.assertEqual(self.manager.test("model", opener)["status"], "reachable")
        self.assertIsNone(opener.open.call_args[0][0].get_header("Authorization"))

    def test_unconfigured_or_unconfirmed_connections_never_open_network(self):
        opener = Mock()
        self.assertEqual(self.manager.test("fuyao", opener)["sent_requests"], 0)
        self.assertEqual(self.manager.test("model", opener)["sent_requests"], 0)
        self.manager.save("fuyao", self.payload(authorization={"confirmed": False, "reference": None}))
        self.assertEqual(self.manager.test("fuyao", opener)["sent_requests"], 0)
        opener.open.assert_not_called()

    def test_business_errors_http_redirect_and_transport_are_redacted_no_retry(self):
        self.manager.save("fuyao", self.payload())
        result = self.manager.test("fuyao", self.opener({"code": 2003, "message": "synthetic-secret-only", "data": None}))
        self.assertEqual(result["status"], "failed")
        for failure in (HTTPError("https://synthetic-secret-only", 302, "synthetic-secret-only", {}, BytesIO(b"synthetic-secret-only")), URLError("synthetic-secret-only")):
            opener = Mock(); opener.open.side_effect = failure
            result = self.manager.test("fuyao", opener)
            self.assertEqual(opener.open.call_count, 1)
            self.assertEqual(result["status"], "failed")
            self.assertNotIn("synthetic-secret-only", dumps(result))

    def test_environment_rotation_and_config_save_invalidate_check(self):
        self.manager.save("model", self.payload("model"))
        self.manager.test("model", self.opener({"data": [{"id": "test-model"}]}))
        self.assertIsNotNone(self.manager.describe()["model"]["last_test"])
        self.manager.environ["STOCKRADAR_LLM_API_KEY"] = "rotated-key-only"
        self.assertIsNone(self.manager.describe()["model"]["last_test"])
        self.manager.save("model", self.payload("model", key_action="keep", api_key=""))
        self.assertIsNone(self.manager.describe()["model"]["last_test"])

    def test_token_symlink_and_permissive_permissions_are_rejected(self):
        self.manager.save("fuyao", self.payload())
        token = next(self.root.glob("*.token"))
        token.chmod(0o644)
        with self.assertRaises(ValueError): self.manager.market_credential("fuyao")
        token.chmod(0o600); token.unlink()
        outside = Path(self.temp.name) / "outside"; outside.write_text("private")
        token.symlink_to(outside)
        with self.assertRaises(ValueError): self.manager.market_credential("fuyao")

    def test_failed_metadata_publish_preserves_old_key_and_removes_new_token(self):
        self.manager.save("fuyao", self.payload())
        original = self.manager._write
        def fail_metadata(name, raw):
            if name == "fuyao.json": raise OSError("synthetic failure")
            return original(name, raw)
        with patch.object(self.manager, "_write", side_effect=fail_metadata), self.assertRaises(OSError):
            self.manager.save("fuyao", self.payload(api_key="replacement-only"))
        self.assertEqual(self.manager.market_credential("fuyao"), "synthetic-secret-only")
        self.assertEqual(len(list(self.root.glob("*.token"))), 1)

    def test_missing_local_key_can_be_replaced_without_loading_old_secret(self):
        self.manager.save("fuyao", self.payload())
        next(self.root.glob("*.token")).unlink()
        self.assertFalse(self.manager.describe()["market"][0]["credential"]["configured"])
        self.manager.save("fuyao", self.payload(api_key="new-test-key-only"))
        self.assertEqual(self.manager.market_credential("fuyao"), "new-test-key-only")

    def test_saved_metadata_is_revalidated_before_use(self):
        self.manager.save("model", self.payload("model"))
        path = self.root / "model.json"
        saved = json.loads(path.read_text())
        for change in ({"timeout_seconds": True}, {"base_url": "http://remote.invalid/v1"}, {"updated_at": "no-timezone"}):
            path.write_text(json.dumps(dict(saved, **change)))
            with self.subTest(change=change), self.assertRaises(ValueError): self.manager.describe()

    def test_vendor_dry_run_can_read_saved_key_without_exposing_it(self):
        self.manager.save("fuyao", self.payload())
        plan = load_json(Path(__file__).resolve().parent.parent / "configs/vendor-sample-fuyao-template.json")
        result = prepare_samples(plan, environ={}, credentials_dir=self.root)
        self.assertTrue(result["credential_present"])
        self.assertEqual(result["sent_requests"], 0)
        self.assertIn("ACCESS_AUTHORIZATION_NOT_CONFIRMED", result["reason_codes"])
        self.assertNotIn("synthetic-secret-only", dumps(result))
