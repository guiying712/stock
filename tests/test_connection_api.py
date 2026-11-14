import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock

from stockradar.connection_settings import ConnectionSettings
from stockradar.server import handler_for
from stockradar.service import Application


class ConnectionAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = Application(str(self.root / "test.sqlite3"), seed=False)
        self.app.connections = ConnectionSettings(self.root / ".connections", environ={})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.app, "synthetic-local-token"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.temp.cleanup()

    def request(self, path="connections", method="GET", body=None, auth=True, origin=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        headers = {"Authorization": "Bearer synthetic-local-token"} if auth else {}
        if body is not None: headers["Content-Type"] = "application/json"
        if origin: headers["Origin"] = origin
        connection.request(method, "/api/v1/" + path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        result = json.loads(response.read())
        connection.close()
        return response.status, result

    def payload(self):
        return {"schema_version": 1, "revision": "new", "key_action": "replace", "api_key": "synthetic-test-secret",
                "authorization": {"confirmed": False, "reference": None}}

    def test_connections_require_auth_and_same_origin(self):
        self.assertEqual(self.request(auth=False)[0], 401)
        self.assertEqual(self.request("connections/market/fuyao", "POST", self.payload(), auth=False)[0], 401)
        self.assertEqual(self.request("connections/market/fuyao", "POST", self.payload(), origin="https://evil.invalid")[0], 403)
        self.assertFalse((self.root / ".connections").exists())

    def test_save_is_separate_from_strategy_export_diagnostics_and_database(self):
        status, result = self.request("connections/market/fuyao", "POST", self.payload())
        self.assertEqual(status, 200)
        self.assertTrue(result["credential"]["configured"])
        for path in ("connections", "config/export", "diagnostics", "health"):
            status, result = self.request(path)
            self.assertEqual(status, 200)
            self.assertNotIn("synthetic-test-secret", json.dumps(result))
        with self.app.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM scans").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM outbox").fetchone()[0], 0)
        self.assertNotIn(b"synthetic-test-secret", (self.root / "test.sqlite3").read_bytes())

    def test_unconfirmed_testing_sends_zero_and_rejects_inline_credentials(self):
        self.request("connections/market/fuyao", "POST", self.payload())
        status, result = self.request("connections/market/fuyao/test", "POST", {})
        self.assertEqual(status, 200)
        self.assertEqual(result["sent_requests"], 0)
        self.assertEqual(self.request("connections/market/fuyao/test", "POST", {"api_key": "synthetic-test-secret"})[0], 400)

    def test_model_requires_explicit_config_and_does_not_generate(self):
        value = {"schema_version": 1, "revision": "new", "key_action": "keep", "api_key": "", "base_url": "http://127.0.0.1:11434/v1",
                 "model": "synthetic-model", "timeout_seconds": 5}
        self.assertEqual(self.request("connections/model", "POST", value)[0], 200)
        self.app.connections.test = Mock(return_value={"status": "blocked", "sent_requests": 0})
        self.assertEqual(self.request("connections/model/test", "POST", {})[0], 200)
        self.app.connections.test.assert_called_once_with("model")
        self.assertEqual(self.request("connections/model", "POST", dict(value, extra=True))[0], 400)

    def test_connection_module_is_served_as_script_and_private_files_are_not(self):
        c = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        c.request("GET", "/connection-view.js")
        response = c.getresponse(); body = response.read()
        self.assertEqual(response.status, 200)
        self.assertIn(b"connectionPage", body)
        c.request("GET", "/.connections/fuyao.json")
        response = c.getresponse(); response.read()
        self.assertEqual(response.status, 404)
        c.close()

    def test_duplicate_json_keys_are_rejected_before_credentials_are_saved(self):
        c = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        raw = '{"api_key":"synthetic-one","api_key":"synthetic-two"}'
        c.request("POST", "/api/v1/connections/market/fuyao", raw,
                  {"Authorization": "Bearer synthetic-local-token", "Content-Type": "application/json"})
        response = c.getresponse(); result = json.loads(response.read()); c.close()
        self.assertEqual(response.status, 400)
        self.assertNotIn("synthetic-", json.dumps(result))
        self.assertFalse((self.root / ".connections").exists())
