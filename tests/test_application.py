"""Recovery, transactional integrity, auth and independent replay acceptance checks."""
from copy import deepcopy
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer

from stockradar.config import load_config
from stockradar.fixtures import fixture_batches
from stockradar.replay import run_replay
from stockradar.server import handler_for
from stockradar.service import Application
from stockradar.store import Store, StoreError


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "test.sqlite3")
        self.config = load_config()
        self.app = Application(self.path, self.config, seed=False)
        self.batches = fixture_batches()

    def tearDown(self):
        self.temp.cleanup()

    def populate(self):
        for batch in self.batches:
            self.app.scan(batch)
        return self.app.store.signals()

    def test_empty_database_coverage_is_unknown_until_first_scan(self):
        health = self.app.health()
        self.assertIsNone(health["coverage"])
        self.assertIsNone(health["quality"]["coverage"])
        self.assertEqual(health["market_status"], "UNKNOWN")
        self.assertTrue(health["updates_paused"])
        self.assertIn("NO_DATA", health["warnings"])
        self.assertIsNone(health["as_of"])
        self.assertEqual((health["expected_count"], health["valid_count"]), (0, 0))
        self.app.scan(self.batches[0])
        scanned = self.app.health()
        self.assertEqual(scanned["coverage"], 1)
        self.assertFalse(scanned["updates_paused"])
        self.assertNotIn("NO_DATA", scanned["warnings"])

    def test_restart_and_duplicate_are_idempotent(self):
        self.populate()
        before_signals = self.app.store.signals()
        before_notifications = self.app.store.notifications()
        restarted = Application(self.path, self.config, seed=False)
        result = restarted.scan(self.batches[-1])
        self.assertTrue(result["duplicate"])
        self.assertEqual(before_signals, restarted.store.signals())
        self.assertEqual(before_notifications, restarted.store.notifications())

    def test_signal_and_outbox_are_one_transaction(self):
        with self.app.store.connect() as db:
            db.execute("CREATE TRIGGER fail_event BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT, 'injected crash'); END")
        committed = 0
        for batch in self.batches:
            try:
                self.app.scan(batch)
                committed += 1
            except sqlite3.IntegrityError:
                break
        else:
            self.fail("fixture must generate signal events")
        with self.app.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM scans").fetchone()[0], committed)
            self.assertEqual(db.execute("SELECT count(*) FROM events").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM outbox").fetchone()[0], 0)
            db.execute("DROP TRIGGER fail_event")
        for batch in self.batches:
            self.app.scan(batch)
        self.assertTrue(self.app.store.notifications())

    def test_feedback_idempotent_and_not_a_trade(self):
        signal = self.populate()[0]
        first = self.app.store.feedback(signal["id"], "bought", "test-key-123456")
        second = self.app.store.feedback(signal["id"], "bought", "test-key-123456")
        self.assertEqual(first, second)
        self.assertEqual(len(self.app.store.detail(signal["id"])["feedback"]), 1)
        with self.assertRaises(StoreError):
            self.app.store.feedback(signal["id"], "ignore", "test-key-123456")
        with self.app.store.connect() as db:
            self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='trades'").fetchone())

    def test_config_immutable_and_corrected_snapshot_preserves_original(self):
        changed = deepcopy(self.config)
        changed["scoring"]["alert_threshold"] += 1
        with self.assertRaises(StoreError):
            self.app.store.register_version(changed)
        self.app.scan(self.batches[0])
        changed_batch = deepcopy(self.batches[0])
        changed_batch["quotes"][0]["close"] = "999"
        with self.assertRaises(StoreError):
            self.app.scan(changed_batch)
        with self.app.store.connect() as db:
            self.assertEqual(json.loads(db.execute("SELECT input FROM scans").fetchone()[0]), self.batches[0])

    def test_backup_restore_preserves_watermark_and_events(self):
        self.populate()
        backup = Path(self.temp.name) / "backup.sqlite3"
        self.app.store.backup(backup)
        recovered = Store(backup)
        self.assertEqual(self.app.store.signals(), recovered.signals())
        self.assertEqual(self.app.store.latest(), recovered.latest())
        self.assertEqual(self.app.store.notifications(), recovered.notifications())
        with self.assertRaises(StoreError):
            self.app.store.backup(backup)

    def test_replay_same_hash_and_no_notifications(self):
        before = self.app.store.notifications()
        first = run_replay(self.batches, self.config)
        second = run_replay(self.batches, self.config)
        self.assertEqual(first, second)
        self.assertEqual(len(first["baselines"]), 4)
        self.assertEqual(before, self.app.store.notifications())
        for baseline in first["baselines"]:
            if baseline["status"] == "completed":
                for window in baseline["evaluation"]["windows"]:
                    self.assertIsNone(window["cost_adjusted_return"])

    def test_modes_and_release_gate(self):
        cfg = deepcopy(self.config)
        cfg.update(id="real-v1", mode="live_alert", purpose="experimental")
        with self.assertRaises(StoreError):
            Application(self.path, cfg, seed=False)
        batch = deepcopy(self.batches[0])
        batch["simulated"] = False
        with self.assertRaises(StoreError):
            self.app.scan(batch)

    def test_one_inbox_message_per_alert_revision_with_original_snapshot(self):
        self.app.scan(self.batches[0])
        self.app.scan(self.batches[1])
        messages = self.app.store.notifications()
        self.assertEqual(len(messages), 7)
        self.assertTrue(all(n["payload"]["event"]["to_status"] == "PREALERT" for n in messages))
        for message in messages:
            self.assertEqual(message["revision"], message["payload"]["signal"]["revision"])
            self.assertEqual(message["payload"]["signal"], message["payload"]["event"]["snapshot"])
        frozen = deepcopy(messages)
        self.app.scan(self.batches[2])
        self.assertEqual(frozen, [n for n in self.app.store.notifications() if n["revision"] == 2])

    def test_outbox_diagnostics_do_not_drop_old_unknown_rows(self):
        from stockradar.store import dumps, now
        stamp = now()
        with self.app.store.connect() as db:
            db.execute("INSERT INTO outbox(id,channel,status,created_at,updated_at,payload) VALUES('unknown-old','dingtalk','unknown',?,?,?)", (stamp, stamp, dumps({})))
            db.execute("INSERT INTO outbox(id,channel,status,created_at,updated_at,payload) VALUES('accepted-test','dingtalk_test','accepted',?,?,?)", (stamp, stamp, dumps({})))
            for index in range(201):
                db.execute("INSERT INTO outbox(id,channel,status,created_at,updated_at,payload) VALUES(?,'inbox','accepted',?,?,?)", (str(index), stamp, stamp, dumps({})))
        self.assertEqual(self.app.health()["outbox"]["unknown"], 1)
        # An old acceptance without the current target fingerprint is evidence
        # of that historical test only, not validation of today's configuration.
        self.assertFalse(self.app._tested_channel())

    def test_abandoned_test_delivery_and_replay_become_visible_failures(self):
        from stockradar.store import dumps
        old = "2020-01-01T00:00:00+00:00"
        with self.app.store.connect() as db:
            db.execute("INSERT INTO outbox(id,channel,status,created_at,updated_at,payload) VALUES('abandoned','dingtalk_test','sending',?,?,?)", (old, old, dumps({})))
            db.execute("INSERT INTO jobs VALUES('abandoned','running',?,?,?,NULL,NULL)", (old, old, dumps({"dataset_id": "fixture"})))
        self.app.health()
        self.assertEqual(self.app.store.notifications()[0]["status"], "unknown")
        self.assertEqual(self.app.store.job("abandoned")["status"], "failed")

    def test_concurrent_version_registration_cannot_silently_accept_conflict(self):
        first = deepcopy(self.config)
        first["id"] = "concurrent-version"
        second = deepcopy(first)
        second["scoring"]["alert_threshold"] += 1
        results = []
        def register(cfg):
            try:
                self.app.store.register_version(cfg)
                results.append("saved")
            except StoreError:
                results.append("conflict")
        threads = [threading.Thread(target=register, args=(cfg,)) for cfg in (first, second)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertCountEqual(results, ["saved", "conflict"])

    def test_provider_fault_pauses_immediately_and_fresh_scan_recovers(self):
        self.app.scan(self.batches[0])
        self.app.scan(self.batches[1])
        before = self.app.store.signals()
        self.app.store.pause(self.config["id"], "PROVIDER_UNAVAILABLE")
        health = self.app.health()
        self.assertTrue(health["updates_paused"])
        self.assertEqual(health["market_status"], "UNKNOWN")
        self.assertIn("PROVIDER_UNAVAILABLE", health["warnings"])
        # Failure reporting does not rewrite historical strategy evidence.
        self.assertEqual(before, self.app.store.signals())
        self.app.scan(self.batches[2])
        self.assertFalse(self.app.health()["updates_paused"])


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.app = Application(str(Path(cls.temp.name) / "api.sqlite3"))
        cls.token = "test-token-with-at-least-32-characters"
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(cls.app, cls.token))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        for process in cls.app.processes:
            process.wait(timeout=30)
        cls.temp.cleanup()

    def request(self, method, path, data=None, auth=True, extra_headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        headers = {"Authorization": "Bearer " + self.token} if auth else {}
        if data is not None:
            headers["Content-Type"] = "application/json"
        headers.update(extra_headers or {})
        conn.request(method, path, body=json.dumps(data) if data is not None else None, headers=headers)
        response = conn.getresponse()
        body = response.read()
        result = json.loads(body) if response.getheader("Content-Type", "").startswith("application/json") else body
        status = response.status
        conn.close()
        return status, result

    def test_authenticated_endpoints(self):
        self.assertEqual(self.request("GET", "/api/v1/health", auth=False)[0], 401)
        for path in ("health", "market", "sectors", "signals", "notifications", "strategy-versions", "diagnostics", "config/export", "replays"):
            status, body = self.request("GET", "/api/v1/" + path)
            self.assertEqual(status, 200, (path, body))
        self.assertEqual(self.request("GET", "/")[0], 200)
        self.assertEqual(self.request("GET", "/setup-view.js", auth=False)[0], 200)
        self.assertEqual(self.request("GET", "/../../.env")[0], 404)

    def test_history_routes_share_auth_and_return_saved_hotspot_evidence(self):
        paths = ("source-health", "sector-timeline?sector_id=chips", "study-cards", "studies/missing/cases?profile=early")
        for path in paths:
            self.assertEqual(self.request("GET", "/api/v1/" + path, auth=False)[0], 401)
        for path in paths[:3]:
            self.assertEqual(self.request("GET", "/api/v1/" + path)[0], 200)
        timeline = self.request("GET", "/api/v1/" + paths[1])[1]
        self.assertTrue(timeline["events"])
        self.assertTrue(timeline["events"][0]["simulated"])
        self.assertEqual(self.request("GET", "/api/v1/" + paths[-1])[0], 404)
        self.assertEqual(self.request("GET", "/history-view.js", auth=False)[0], 200)

    def test_csrf_rebinding_and_input_validation(self):
        self.assertEqual(self.request("POST", "/api/v1/demo/advance", {}, extra_headers={"Origin": "https://attacker.example"})[0], 403)
        self.assertEqual(self.request("GET", "/api/v1/health", extra_headers={"Host": "attacker.example"})[0], 403)
        self.assertEqual(self.request("POST", "/api/v1/demo/advance", {"unexpected": True})[0], 400)
        self.assertEqual(self.request("POST", "/api/v1/replays", {"dataset_id": "../secrets"})[0], 400)

    def test_async_replay_completes(self):
        status, body = self.request("POST", "/api/v1/replays", {"dataset_id": "fixture"})
        self.assertEqual(status, 202, body)
        run_id = body["run_id"]
        for _ in range(100):
            _, job = self.request("GET", "/api/v1/replays/" + run_id)
            if job["status"] in {"completed", "failed"}:
                break
            time.sleep(0.1)
        self.assertEqual(job["status"], "completed", job)
        self.assertTrue(job["result"]["simulated"])

    def test_preferences_version_replays_with_selected_timing_and_preserves_running_version(self):
        from copy import deepcopy
        original = self.app.config
        config = deepcopy(original)
        config.update(id="test-preferences", mode="replay", purpose="experimental", status="draft")
        config["research"]["alert_stage"] = "confirmed"
        config["lifecycle"]["daily_new_limit"] = 0
        config["preferences"]["max_loss_fraction"] = 0.075
        for _ in range(2):
            self.assertEqual(self.request("POST", "/api/v1/strategy-versions", {"config": config})[0], 201)
        self.assertEqual(self.request("GET", "/api/v1/config/export")[1], original)
        self.assertEqual(self.request("GET", "/api/v1/health")[1]["strategy_version"], original["id"])
        from stockradar.fixtures import fixture_batches
        result = run_replay(fixture_batches(config.get("schema_version", 1)), self.app.store.version(config["id"]))
        self.assertEqual(result["selected_baseline_id"], "confirmed")
        baseline = next(b for b in result["baselines"] if b["id"] == "confirmed")
        self.assertEqual(baseline["config"]["lifecycle"]["daily_new_limit"], 0)
        self.assertEqual(baseline["config"]["preferences"]["max_loss_fraction"], 0.075)

    def test_study_endpoints_keep_authentication_and_strict_requests(self):
        self.assertEqual(self.request("GET", "/api/v1/studies", auth=False)[0], 401)
        self.assertEqual(self.request("GET", "/api/v1/study-sources")[1], {"datasets": ["fixture"], "plans": ["fixture"]})
        self.assertEqual(self.request("POST", "/api/v1/studies", {})[0], 400)
        self.assertEqual(self.request("POST", "/api/v1/studies", {"dataset_id": "../secret", "plan_id": "sample"})[0], 400)
        for path in ("/evidence-chart.js", "/study-view.js"):
            self.assertEqual(self.request("GET", path)[0], 200)
        identifier = self.app.store.signals()[0]["id"]
        detail = self.request("GET", "/api/v1/signals/" + identifier)[1]
        self.assertIn("trigger", detail["chart"])

    def test_study_export_preserves_report_hash_and_float_types(self):
        from stockradar.store import digest
        identifier = "study-export-test"
        self.app.store.save_job(identifier, {"kind": "study", "dataset_id": "fixture", "plan_id": "fixture"})
        path = "/api/v1/studies/" + identifier + "/report"
        self.assertEqual(self.request("GET", path, auth=False)[0], 401)
        self.assertEqual(self.request("GET", path)[0], 409)
        report = {"simulated": True, "profiles": [], "float_zero": 0.0, "integer_zero": 0, "fraction": 0.01, "missing": None}
        report["output_hash"] = digest(report)
        self.app.store.update_job(identifier, "completed", result=report)
        status, exported = self.request("GET", path)
        self.assertEqual(status, 200)
        self.assertIsInstance(exported["float_zero"], float)
        self.assertIsInstance(exported["integer_zero"], int)
        self.assertEqual(exported["output_hash"], digest({key: value for key, value in exported.items() if key != "output_hash"}))


if __name__ == "__main__":
    unittest.main()
