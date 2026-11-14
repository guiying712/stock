"""Data PoC evidence, frozen charts, channel identity and independent studies."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from stockradar.acceptance import channel_report, provider_report, validate_provider_plan
from stockradar.config import load_config
from stockradar.contracts import load_json
from stockradar.fixtures import fixture_batches
from stockradar.providers import record_batches
from stockradar.service import Application
from stockradar.store import digest, dumps, now, StoreError
from stockradar.study_jobs import get_job, list_jobs, prepare_request, run_job, sources


class ImprovementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = Application(str(self.root / "test.sqlite3"), seed=False)
        self.batches = fixture_batches()
        self.config = load_config()
        self.plan = load_json(Path(__file__).resolve().parent.parent / "configs/provider-poc-fixture.json")

    def tearDown(self):
        for process in self.app.processes:
            process.wait(timeout=60)
        self.temp.cleanup()

    def signal(self):
        for batch in self.batches[:2]:
            self.app.scan(batch)
        return self.app.store.signals()[0]

    def test_provider_sample_and_duplicate_keep_full_market_unverified(self):
        report = provider_report(self.batches[:2] + [self.batches[1]], self.config, self.plan)
        self.assertEqual((report["status"], report["sample_count"], report["duplicate_count"]), ("sample_checked", 2, 1))
        self.assertFalse(report["full_market_verified"])
        self.assertFalse(report["release_allowed"])
        self.assertEqual(report["output_hash"], digest({k: v for k, v in report.items() if k != "output_hash"}))

    def test_fault_samples_do_not_pass_coverage(self):
        report = provider_report(self.batches, self.config, self.plan)
        self.assertEqual(report["status"], "incomplete")
        self.assertIn("SAMPLE_COVERAGE_BELOW_TARGET", report["reason_codes"])

    def test_conflicting_snapshot_does_not_replace_original(self):
        corrected = deepcopy(self.batches[0])
        corrected["quotes"][0]["close"] = "99"
        report = provider_report([self.batches[0], corrected], self.config, self.plan)
        self.assertEqual(report["correction_count"], 1)
        self.assertEqual(report["samples"][0]["input_hash"], digest(self.batches[0]))
        self.assertIn("SNAPSHOT_CONTENT_CONFLICT", report["reason_codes"])

    def test_unknown_capabilities_authorization_and_denominator_stay_unknown(self):
        self.plan["authorization"] = {"confirmed": False, "reference": None}
        self.plan["declared_capabilities"]["minute_history"] = "unknown"
        self.plan["expected_instrument_count"] = None
        self.plan["minimum_trading_dates"] = 3
        report = provider_report(self.batches[:2], self.config, self.plan)
        for code in ("AUTHORIZATION_NOT_CONFIRMED", "CAPABILITY_NOT_ESTABLISHED:minute_history", "EXTERNAL_UNIVERSE_DENOMINATOR_UNKNOWN", "INSUFFICIENT_TRADING_DATES"):
            self.assertIn(code, report["reason_codes"])

    def test_provider_plan_rejects_missing_unknown_and_simulation_mismatch(self):
        for mutate in (lambda p: p.pop("max_batches"), lambda p: p.update(extra=True), lambda p: p.update(minimum_coverage=True)):
            bad = deepcopy(self.plan)
            mutate(bad)
            with self.assertRaises(ValueError):
                validate_provider_plan(bad)
        batch = deepcopy(self.batches[0])
        batch["simulated"] = False
        with self.assertRaises(ValueError):
            provider_report([batch], self.config, self.plan)

    def test_provider_empty_and_sample_bound_are_explicit(self):
        empty = provider_report([], self.config, self.plan)
        self.assertIn("NO_SAMPLES", empty["reason_codes"])
        self.assertFalse(any(c["present_in_every_sample"] for c in empty["capabilities"].values()))
        self.plan["max_batches"] = 1
        bounded = provider_report(self.batches[:2], self.config, self.plan)
        self.assertTrue(bounded["sample_limit_reached"])
        self.assertEqual(bounded["sample_count"], 1)

    def test_trigger_chart_is_frozen_and_latest_is_separate(self):
        signal = self.signal()
        before = self.app.signal_detail(signal["id"])["chart"]
        self.app.scan(self.batches[2])
        after = self.app.signal_detail(signal["id"])["chart"]
        self.assertEqual(before["trigger"], after["trigger"])
        self.assertEqual(before["levels"], after["levels"])
        self.assertNotEqual(before["latest"]["input_hash"], after["latest"]["input_hash"])
        self.assertTrue(all(q["event_time"] <= signal["trigger_time"] for q in after["trigger"]["candles"]))
        self.assertTrue(all(e["at"] <= signal["trigger_time"] for e in after["trigger"]["events"]))

    def test_chart_does_not_rewrite_signals_or_events(self):
        signal = self.signal()
        before = self.app.store.detail(signal["id"])
        self.app.signal_detail(signal["id"])
        self.assertEqual(before, self.app.store.detail(signal["id"]))

    def test_later_first_alert_does_not_replace_original_trigger_input(self):
        from stockradar.evidence import signal_chart
        signal = self.signal()
        self.app.scan(self.batches[2])
        # A delayed alert has a distinct alert snapshot while its episode and
        # original trigger time remain frozen. The chart must use that input.
        signal["evidence"]["prealert_snapshot_id"] = self.batches[2]["snapshot_id"]
        chart = signal_chart(self.app.store, signal)
        self.assertEqual(chart["trigger"]["snapshot_id"], signal["evidence"]["snapshot_id"])
        self.assertEqual(chart["trigger"]["input_hash"], digest(self.batches[1]))

    def test_chart_excludes_future_ingestion_and_changed_adjustment_basis(self):
        signal = self.signal()
        batch = deepcopy(self.batches[2])
        quote = next(q for q in batch["quotes"] if q["instrument_id"] == signal["instrument_id"])
        quote["ingested_at"] = "2099-01-01T00:00:00Z"
        self.app.scan(batch)
        chart = self.app.signal_detail(signal["id"])["chart"]
        self.assertGreater(chart["latest"]["reason_counts"].get("NOT_VISIBLE_AT_VIEW_TIME", 0), 0)
        self.assertFalse(any(q["ingested_at"].startswith("2099") for q in chart["latest"]["candles"]))
        batch = deepcopy(self.batches[3])
        next(q for q in batch["quotes"] if q["instrument_id"] == signal["instrument_id"])["adjustment_factor"] = "2"
        self.app.scan(batch)
        self.assertGreater(self.app.signal_detail(signal["id"])["chart"]["latest"]["reason_counts"].get("ADJUSTMENT_BASIS_CHANGED", 0), 0)

    def test_chart_unknown_ohlc_is_not_zero_filled(self):
        signal = self.signal()
        batch = deepcopy(self.batches[2])
        next(q for q in batch["quotes"] if q["instrument_id"] == signal["instrument_id"])["open"] = None
        self.app.scan(batch)
        chart = self.app.signal_detail(signal["id"])["chart"]
        self.assertGreater(chart["latest"]["reason_counts"].get("OHLC_UNKNOWN_OR_INVALID", 0), 0)
        self.assertTrue(all(q["open"] is not None for q in chart["latest"]["candles"]))

    def test_channel_preparation_and_missing_configuration_never_send(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(self.app, "test_channel") as send:
            self.assertEqual(channel_report(self.app)["status"], "not_sent")
            missing = channel_report(self.app, True)
            self.assertEqual((missing["status"], missing["network_requests"]), ("blocked_missing_configuration", 0))
            send.assert_not_called()

    def test_channel_test_is_scoped_to_current_target_without_secret_export(self):
        webhook = "https://oapi.dingtalk.com/robot/send?access_token=fake-unit-test-only"
        accepted = {"status": "accepted", "retryable": False, "response_code": 200, "receipt": {"errcode": 0}, "error": None}
        with patch.dict(os.environ, {"DINGTALK_WEBHOOK": webhook, "DINGTALK_SECRET": "fake-signature-only"}, clear=True), patch("stockradar.notifier.DingTalkNotifier.send", return_value=accepted) as send:
            report = channel_report(self.app, True)
            self.assertEqual(report["network_requests"], 1)
            self.assertTrue(self.app._tested_channel())
            last = self.app.health()["dingtalk_last_test"]
            self.assertEqual(last["status"], "accepted")
            self.assertEqual(set(last), {"status", "at"})
            self.assertFalse(report["opportunity_path_verified"])
            self.assertNotIn(webhook, dumps(report))
            self.assertNotIn("fake-signature-only", dumps(self.app.store.notifications()))
            os.environ["DINGTALK_SECRET"] = "changed-fake-signature"
            self.assertFalse(self.app._tested_channel())
            self.assertIsNone(self.app.health()["dingtalk_last_test"])
            send.assert_called_once()

    def test_old_unscoped_accepted_record_does_not_validate_new_target(self):
        with self.app.store.connect() as db:
            db.execute("INSERT INTO outbox(id,channel,status,created_at,updated_at,payload) VALUES('legacy','dingtalk_test','accepted',?,?,?)", (now(), now(), dumps({})))
        with patch.dict(os.environ, {"DINGTALK_WEBHOOK": "https://oapi.dingtalk.com/robot/send?access_token=fake-new-target"}, clear=True):
            self.assertFalse(self.app._tested_channel())

    def test_channel_unknown_is_reported_once_and_never_retried(self):
        with patch.dict(os.environ, {"DINGTALK_WEBHOOK": "https://oapi.dingtalk.com/robot/send?access_token=fake-unknown-only"}, clear=True), patch("stockradar.notifier.DingTalkNotifier.send", return_value={"status": "unknown", "retryable": False}) as send:
            report = channel_report(self.app, True)
            self.assertEqual(self.app.health()["dingtalk_last_test"]["status"], "unknown")
            self.assertEqual(report["status"], "unknown")
            self.assertFalse(self.app._tested_channel())
            send.assert_called_once()

    def test_study_inputs_reject_unknown_keys_paths_and_mixed_fixture(self):
        for request in ({}, {"dataset_id": "fixture", "plan_id": "fixture", "extra": 1}, {"dataset_id": "fixture", "plan_id": "other"}, {"dataset_id": "../secret", "plan_id": "p"}):
            with self.assertRaises(StoreError):
                prepare_request(self.app.store, request)

    def test_study_sources_ignore_symlinks_and_invalid_identifiers(self):
        root = self.root / "datasets"
        root.mkdir()
        (root / "valid.jsonl").write_text("")
        (root / "bad name.jsonl").write_text("")
        (root / "linked.jsonl").symlink_to(root / "valid.jsonl")
        self.assertEqual(sources(self.app.store)["datasets"], ["fixture", "valid"])
        with self.assertRaises(StoreError):
            prepare_request(self.app.store, {"dataset_id": "linked", "plan_id": "p"})

    def prepare_local_study(self):
        from stockradar.study_fixture import make_study_fixture
        batches, plan = make_study_fixture(9)
        (self.root / "datasets").mkdir()
        (self.root / "study-plans").mkdir()
        record_batches(self.root / "datasets/sample.jsonl", batches)
        (self.root / "study-plans/sample.json").write_text(dumps(plan))
        request = prepare_request(self.app.store, {"dataset_id": "sample", "plan_id": "sample"})
        self.app.store.save_job("study-local", request)
        return request

    def test_completed_study_projects_summaries_and_preserves_full_export(self):
        self.prepare_local_study()
        before = self.app.store.signals()
        run_job(self.app.store, "study-local")
        compact, full = get_job(self.app.store, "study-local"), get_job(self.app.store, "study-local", full=True)
        self.assertEqual(compact["status"], "completed")
        self.assertNotIn("samples", compact["result"]["profiles"][0])
        self.assertIn("samples", full["result"]["profiles"][0])
        self.assertFalse(full["result"]["parameter_freeze"]["eligible"])
        self.assertEqual(before, self.app.store.signals())
        self.assertEqual([job["id"] for job in list_jobs(self.app.store)], ["study-local"])

    def test_study_dataset_change_after_submission_fails_visibly(self):
        self.prepare_local_study()
        with (self.root / "datasets/sample.jsonl").open("a") as stream:
            stream.write("\n")
        run_job(self.app.store, "study-local")
        job = get_job(self.app.store, "study-local")
        self.assertEqual(job["status"], "failed")
        self.assertIsNone(job["result"])

    def test_study_plan_is_frozen_at_submission_and_job_types_are_separate(self):
        prepared = self.prepare_local_study()
        (self.root / "study-plans/sample.json").write_text("{}")
        self.assertEqual(prepared["plan"], self.app.store.job("study-local")["request"]["plan"])
        self.app.store.save_job("old-replay", {"dataset_id": "fixture"})
        with self.assertRaises(StoreError):
            get_job(self.app.store, "old-replay")
        self.assertEqual(len(list_jobs(self.app.store)), 1)

    def test_replay_listing_does_not_decode_or_get_displaced_by_studies(self):
        self.app.store.save_job("retained-replay", {"dataset_id": "fixture"})
        with self.app.store.connect() as db:
            for index in range(101):
                db.execute("INSERT INTO jobs VALUES(?, 'completed', ?, ?, ?, ?, NULL)",
                           ("study-%d" % index, "2099-01-01T00:00:00Z", now(), dumps({"kind": "study"}), dumps({"samples": [None] * 100})))
        parse = self.app.store._job
        def replay_only(row):
            self.assertNotEqual(json.loads(row["request"]).get("kind"), "study")
            return parse(row)
        with patch.object(self.app.store, "_job", side_effect=replay_only):
            jobs = self.app.store.jobs(kind="replay")
        self.assertEqual([job["id"] for job in jobs], ["retained-replay"])

    def test_code_change_during_study_does_not_save_mixed_version_report(self):
        request = self.prepare_local_study()
        with patch("stockradar.replay.source_hash", side_effect=[request["submitted_code_hash"], "changed-during-computation"]):
            run_job(self.app.store, "study-local")
        job = get_job(self.app.store, "study-local")
        self.assertEqual(job["status"], "failed")
        self.assertIsNone(job["result"])


if __name__ == "__main__":
    unittest.main()
