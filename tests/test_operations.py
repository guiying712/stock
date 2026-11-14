from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock

from stockradar.config import load_config
from stockradar.contracts import load_json, write_new_json
from stockradar.fixtures import fixture_batches
from stockradar.maintenance import archive_scans, read_archive
from stockradar.operations import WorkerRuntime, initialize, operations_report, validate_operations_plan
from stockradar.replay import source_hash
from stockradar.service import Application
from stockradar.store import Store, StoreError, digest, dumps
from stockradar.worker import run_worker, supervise_worker


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = Application(str(self.root / "ops.sqlite3"), seed=False)
        self.plan = load_json(Path(__file__).resolve().parents[1] / "configs" / "operations-fixture.json")
        self.batches = fixture_batches()

    def test_worker_lock_heartbeat_and_clean_stop(self):
        with WorkerRuntime(self.app.store, self.app.config, "jsonl") as runtime:
            runtime.scan(self.app, self.batches[0])
            with self.assertRaises(StoreError) as caught:
                with WorkerRuntime(self.app.store, self.app.config, "jsonl"):
                    pass
            self.assertEqual(caught.exception.code, "WORKER_BUSY")
            report = operations_report(self.app.store, self.plan)
            self.assertTrue(report["current_worker"]["healthy"])
            self.assertEqual(report["observed_slices"], 1)
        self.assertEqual(operations_report(self.app.store, self.plan)["current_worker"]["state"], "stopped")

    def test_provider_fault_is_idempotent_and_old_snapshot_does_not_fake_recovery(self):
        with WorkerRuntime(self.app.store, self.app.config, "fake") as runtime:
            runtime.scan(self.app, self.batches[0])
            runtime.fault("PROVIDER_LIMITED")
            runtime.fault("PROVIDER_LIMITED")
            self.assertEqual(len(self.app.store.notifications()), 1)
            runtime.scan(self.app, self.batches[0])
            self.assertEqual(self.app.store.pause_code(self.app.config["id"]), "PROVIDER_LIMITED")
            self.assertEqual(operations_report(self.app.store, self.plan)["incidents"][0]["state"], "open")
            runtime.scan(self.app, self.batches[1])
            self.assertIsNone(self.app.store.pause_code(self.app.config["id"]))
            self.assertEqual(operations_report(self.app.store, self.plan)["incidents"][0]["state"], "recovered")
        self.assertEqual(operations_report(self.app.store, self.plan)["observed_slices"], 2)

    def test_wait_preserves_pause_and_heartbeats_during_retry_after(self):
        with WorkerRuntime(self.app.store, self.app.config, "fake") as runtime:
            runtime.fault("PROVIDER_LIMITED")
            pause = Mock()
            runtime.wait(31, pause)
            self.assertEqual([c.args[0] for c in pause.call_args_list], [10, 10, 10, 1])
            self.assertEqual(runtime.state, "paused")
            self.assertEqual(self.app.store.pause_code(self.app.config["id"]), "PROVIDER_LIMITED")

    def test_report_without_runtime_is_read_only_and_unknown_latency_is_null(self):
        report = operations_report(self.app.store, self.plan)
        self.assertEqual(report["observed_slices"], 0)
        self.assertFalse(report["release_allowed"])
        self.assertIsNone(next(g for g in report["gates"] if g["id"] == "platform_acceptance_p95")["observed_seconds"])
        with self.app.store.connect() as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='ops_meta'").fetchone())

    def test_fixture_old_code_and_historical_replay_never_count_as_shadow_days(self):
        with WorkerRuntime(self.app.store, self.app.config, "fixture", {"full_market_verified": True}) as runtime:
            runtime.scan(self.app, self.batches[0])
        report = operations_report(self.app.store, self.plan)
        self.assertEqual(next(g for g in report["gates"] if g["id"] == "shadow_trading_days")["observed"], 0)
        with self.app.store.connect() as db:
            row = db.execute("SELECT data FROM ops_observations").fetchone()
            value = json.loads(row[0]); value["code_hash"] = "older-code"
            db.execute("UPDATE ops_observations SET data=?", (dumps(value),))
        self.assertEqual(operations_report(self.app.store, self.plan)["excluded_or_older_code_slices"], 1)

    def shadow_facts(self, day_count=21, sparse=False, omit_day=None, replay=False):
        cfg = load_config()
        cfg.update(id="shadow-test", mode="shadow", purpose="experimental")
        self.app.store.register_version(cfg)
        initialize(self.app.store)
        self.plan.update(purpose="experimental", strategy_version=cfg["id"], calendar_version="calendar-fake", target_universe_count=12)
        dates, current = [], datetime(2026, 8, 3, tzinfo=timezone.utc)
        while len(dates) < day_count:
            if current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)
        with self.app.store.connect() as db:
            for index, date in enumerate(dates):
                if index == omit_day:
                    continue
                for minute in ([1] if sparse else [1, 2, 3]):
                    stamp = date.replace(hour=2, minute=minute)
                    value = {"mode": "shadow", "simulated": False, "config_hash": digest(cfg), "code_hash": source_hash(),
                             "as_of": stamp.isoformat(), "slice_end": stamp.isoformat(), "observed_at": (stamp + timedelta(days=40) if replay else stamp).isoformat(),
                             "calendar_version": "calendar-fake", "trading_date": date.date().isoformat(),
                             "calendar_trading_dates": [d.date().isoformat() for d in dates], "session_end": "10:03",
                             "trading_minute": index * 3 + minute, "expected_minutes": 3, "quality": "good",
                             "expected_count": 12, "valid_count": 12, "coverage": 1, "minimum_sector_coverage": 1,
                             "data_age_seconds": 40 * 86400 if replay else 0, "scan_commit_seconds": .1, "full_market_verified": True}
                    db.execute("INSERT INTO ops_observations VALUES(?,?,?,?)", (cfg["id"], "fake-%d-%d" % (index, minute), value["observed_at"], dumps(value)))
        return (dates[-1].replace(hour=8) + timedelta(days=40) if replay else dates[-1].replace(hour=8)).isoformat()

    def test_one_slice_per_day_is_not_a_complete_twenty_day_observation(self):
        report = operations_report(self.app.store, self.plan, self.shadow_facts(sparse=True))
        gate = next(g for g in report["gates"] if g["id"] == "shadow_trading_days")
        self.assertEqual(gate["observed"], 0)
        self.assertEqual(gate["status"], "pending")

    def test_twenty_nonconsecutive_days_do_not_pass_continuous_observation(self):
        cutoff = self.shadow_facts(21, omit_day=10)
        report = operations_report(self.app.store, self.plan, cutoff)
        gate = next(g for g in report["gates"] if g["id"] == "shadow_trading_days")
        self.assertEqual(gate["total_qualified_days"], 20)
        self.assertEqual(gate["observed"], 10)
        self.assertEqual(gate["status"], "pending")

    def test_synthetic_unit_evidence_can_exercise_day_count_but_never_unlocks_live(self):
        cutoff = self.shadow_facts(20)
        report = operations_report(self.app.store, self.plan, cutoff)
        self.assertEqual(next(g for g in report["gates"] if g["id"] == "shadow_trading_days")["observed"], 20)
        self.assertFalse(report["release_allowed"])

    def test_replayed_historical_input_cannot_satisfy_real_time_shadow_observation(self):
        cutoff = self.shadow_facts(20, replay=True)
        report = operations_report(self.app.store, self.plan, cutoff)
        self.assertEqual(next(g for g in report["gates"] if g["id"] == "shadow_trading_days")["observed"], 0)

    def test_platform_latency_uses_actual_completion_and_deduplicates_group_requests(self):
        cutoff = self.shadow_facts(1)
        with self.app.store.connect() as db:
            for index, minute in enumerate((1, 2, 3)):
                payload = {"signal": {"strategy_version": "shadow-test", "evidence": {"simulated": False}},
                           "event": {"snapshot_id": "fake-0-%d" % minute}}
                response = {"delivery_id": "same-physical-request", "request_completed_at": "2026-08-03T02:02:00Z"} if minute < 3 else {"cutoff": cutoff}
                db.execute("INSERT INTO outbox(id,channel,status,created_at,updated_at,payload,response) VALUES(?,'dingtalk','accepted',?,?,?,?)",
                           ("fake-%d" % index, cutoff, cutoff, dumps(payload), dumps(response)))
        report = operations_report(self.app.store, self.plan, cutoff)
        gate = next(g for g in report["gates"] if g["id"] == "platform_acceptance_p95")
        self.assertEqual(gate["request_count"], 1)
        self.assertEqual(gate["observed_seconds"], 60)
        self.assertFalse(report["release_allowed"])

    def test_storage_budget_and_retention_report_without_deleting_inputs(self):
        with WorkerRuntime(self.app.store, self.app.config, "jsonl") as runtime:
            runtime.scan(self.app, self.batches[0])
        self.plan["max_database_bytes"] = 1
        report = operations_report(self.app.store, self.plan, "2027-01-01T00:00:00Z")
        self.assertEqual(next(g for g in report["gates"] if g["id"] == "storage_budget")["status"], "fail")
        self.assertEqual(report["retention"]["archivable_input_rows"], 1)
        self.assertFalse(report["retention"]["automatic_deletion"])
        self.assertEqual(report["table_rows"]["scans"], 1)

    def test_unknown_contract_or_ops_schema_rejected(self):
        with self.assertRaises(ValueError):
            validate_operations_plan(dict(self.plan, unknown=1))
        initialize(self.app.store)
        with self.app.store.connect() as db:
            db.execute("UPDATE ops_meta SET schema_version=999")
        with self.assertRaises(StoreError):
            operations_report(self.app.store, self.plan)
        with self.assertRaises(StoreError):
            initialize(self.app.store)

    def test_archive_roundtrip_checksums_and_backup_preserve_all_business_evidence(self):
        with WorkerRuntime(self.app.store, self.app.config, "jsonl") as runtime:
            runtime.scan(self.app, self.batches[0]); runtime.scan(self.app, self.batches[1])
        before = self.app.store.detail(self.app.store.signals()[0]["id"])
        target = self.root / "archive.jsonl.gz"
        manifest = archive_scans(self.app.store, self.app.config["id"], "2027-01-01T00:00:00Z", target)
        header, rows = read_archive(target, manifest["sha256"])
        self.assertEqual(header["row_count"], 2)
        self.assertEqual([r["input"] for r in rows], self.batches[:2])
        self.assertLess(manifest["compressed_bytes"], manifest["uncompressed_bytes"])
        self.assertEqual(self.app.store.detail(before["id"]), before)
        backup = self.root / "backup.sqlite3"
        self.app.store.backup(backup)
        restored = Store(backup)
        self.assertEqual(restored.detail(before["id"]), before)
        with restored.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM ops_observations").fetchone()[0], 2)
        with self.assertRaises(ValueError):
            read_archive(target, "invalid-checksum")
        with self.assertRaises(ValueError):
            archive_scans(self.app.store, self.app.config["id"], "2027-01-01T00:00:00Z", target)

    def test_experiments_never_overwrite_existing_output(self):
        target = self.root / "evidence.json"
        write_new_json(target, {"first": True})
        with self.assertRaises(FileExistsError):
            write_new_json(target, {"replacement": True})
        self.assertEqual(load_json(target), {"first": True})

    def test_process_crash_releases_lock_restart_detects_interruption_without_duplicate_signal(self):
        marker = self.root / "ready"
        code = ("import time; from pathlib import Path; from stockradar.service import Application; "
                "from stockradar.operations import WorkerRuntime; from stockradar.fixtures import fixture_batches; "
                "app=Application(%r, seed=False); runtime=WorkerRuntime(app.store,app.config,'test-child'); "
                "runtime.__enter__(); runtime.scan(app,fixture_batches()[0]); Path(%r).touch(); time.sleep(30)" % (self.app.store.path, str(marker)))
        process = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() and time.monotonic() < deadline and process.poll() is None:
                time.sleep(.02)
            self.assertTrue(marker.exists())
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        with WorkerRuntime(self.app.store, self.app.config, "restart") as runtime:
            result = runtime.scan(self.app, self.batches[0])
            self.assertTrue(result["duplicate"])
            self.assertEqual(operations_report(self.app.store, self.plan)["incidents"][0]["code"], "WORKER_INTERRUPTED")
            runtime.scan(self.app, self.batches[1])
        self.assertEqual(len(self.app.store.signals()), 7)

    def test_supervisor_bounded_restart_and_no_live_release_bypass(self):
        first, second = Mock(pid=999001), Mock(pid=999002)
        first.poll.return_value = first.wait.return_value = 1
        second.poll.return_value = second.wait.return_value = 0
        factory, pause = Mock(side_effect=[first, second]), Mock()
        result = supervise_worker(self.app.store, self.app.config, self.plan, input_path="unused", process_factory=factory, pause=pause)
        self.assertEqual(result["restarts"], 1)
        self.assertEqual(pause.call_args.args[0], 1)
        self.plan["restart_limit"] = 0
        with self.assertRaises(StoreError):
            supervise_worker(self.app.store, self.app.config, self.plan, input_path="unused", process_factory=Mock(return_value=first), pause=pause)
        with self.assertRaises(StoreError):
            supervise_worker(self.app.store, dict(self.app.config, mode="live_alert"), self.plan, input_path="unused")

    def test_watchdog_terminates_only_its_hung_child_and_records_failure(self):
        class Child:
            pid = 99999999
            exit_code = None
            def poll(self): return self.exit_code
            def terminate(self): self.exit_code = 1
            def wait(self, **kwargs): return self.exit_code
        child = Child()
        elapsed = [0]
        def pause(seconds): elapsed[0] += seconds
        self.plan.update(restart_limit=0, heartbeat_timeout_seconds=10)
        with self.assertRaises(StoreError):
            supervise_worker(self.app.store, self.app.config, self.plan, input_path="unused", process_factory=Mock(return_value=child), pause=pause, clock=lambda: elapsed[0])
        self.assertEqual(child.exit_code, 1)
        self.assertIn("WORKER_HEARTBEAT_STALE", {r["code"] for r in operations_report(self.app.store, self.plan)["incidents"]})
