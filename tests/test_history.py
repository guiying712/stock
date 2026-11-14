"""Evidence views over completed captures, scans and studies."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from stockradar.evidence import sector_timeline
from stockradar.fixtures import fixture_batches
from stockradar.minute_quality import minute_quality_report
from stockradar.research import run_study
from stockradar.service import Application
from stockradar.source_health import source_health, _quality_projection
from stockradar.store import digest, dumps, StoreError
from stockradar.study_fixture import make_study_fixture
from stockradar.study_jobs import get_job, study_cards, study_cases
from stockradar.vendor_samples import collect_samples, request_specs


class Response(BytesIO):
    def __init__(self, data):
        super().__init__(json.dumps(data).encode())
        self.code, self.headers = 200, {}


class SourceHistoryTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.symbols = [{"symbol": "600000.SH", "board": "MAIN"}]

    def capture(self, name, dataset, at, *, limited=False, authorized=True, simulated=False, directory="source-samples"):
        plan = {"schema_version": 1, "id": name, "purpose": "experimental", "provider": "tushare",
                "authorization": {"confirmed": authorized, "reference": "synthetic test" if authorized else None},
                "symbols": self.symbols, "datasets": [dataset], "start_date": "2026-11-06", "end_date": "2026-11-06",
                "request_interval_seconds": "6.1", "request_timeout_seconds": 15, "max_requests": 1}
        fields = request_specs(plan)[0]["fields"].split(",")
        quote = dict(ts_code="600000.SH", trade_date="20261106", time="2026-11-06 09:31:00",
                     trade_time="2026-11-06 09:31:00", freq="1MIN", open=10, high=10, low=10, close=10,
                     pre_close=10, vol=100, amount=1000)
        opener = Mock()
        opener.open.return_value = Response({"code": 0, "data": {"fields": fields, "items": [[quote.get(k) for k in fields]]}})
        if limited:
            opener.open.side_effect = HTTPError("https://api.tushare.pro", 429, "limit", {}, BytesIO())
        path = self.root / directory / name
        with patch("stockradar.vendor_samples.now", return_value=at):
            report = collect_samples(plan, path, opener=opener, environ={"TUSHARE_TOKEN": "synthetic-test-token"})
        self.assertEqual(opener.open.call_count, int(authorized))
        if simulated:
            report["simulated"] = True
            report["output_hash"] = digest({k: v for k, v in report.items() if k != "output_hash"})
            (path / "report.json").write_text(dumps(report))
        return path

    def test_attempts_are_deduplicated_and_separate_by_endpoint_and_mode(self):
        at = "2026-11-06T01:31:08+00:00"
        self.capture("daily", "daily_bars", at)
        latest = self.capture("live", "minute_quotes", at, directory="minute-data")
        shutil.copytree(latest, self.root / "source-samples" / "copied")
        self.capture("limited", "minute_quotes", "2026-11-06T01:33:08+00:00", limited=True)
        self.capture("skip", "minute_quotes", at, authorized=False)
        self.capture("historical", "minute_history", at, simulated=True)
        corrupted = self.capture("corrupted", "minute_history", at)
        with (corrupted / "report.json").open("w") as stream:
            stream.write('{"provider":"unverified"}')
        health = source_health(self.root)
        self.assertEqual(health["ignored_count"], 1)
        self.assertEqual(health["capture_count"], 5)
        rows = {row["operation"]: row for row in health["items"]}
        self.assertEqual(set(rows), {"daily", "rt_min", "stk_mins"})
        self.assertEqual(rows["rt_min"]["attempt_count"], 2)
        self.assertEqual(rows["rt_min"]["limited_count"], 1)
        self.assertEqual(rows["rt_min"]["latest_status"], "failed")
        self.assertEqual(rows["rt_min"]["last_success_at"], at)
        self.assertIsNone(rows["rt_min"]["minute_quality"])
        self.assertTrue(rows["stk_mins"]["simulated"])
        self.assertNotIn("synthetic-test-token", dumps(health))

    def test_quality_requires_linked_capture_and_late_is_latest_only(self):
        late = self.capture("latest", "minute_quotes", "2026-11-06T01:31:20+00:00")
        history = self.capture("history", "minute_history", "2026-11-10T01:40:00+00:00")
        profile = {"provider": "tushare", "dataset": "minute_quotes", "timestamp_label": "end",
                   "timestamp_timezone": "Asia/Shanghai", "completion": "provider_closed",
                   "volume_unit": "shares", "amount_unit": "CNY", "turnover_mode": "interval", "adjustment": "none",
                   "max_observation_delay_seconds": 10,
                   "evidence": dict.fromkeys(("timestamp", "completion", "units", "turnover", "adjustment"), "synthetic test")}
        plan = {"schema_version": 1, "id": "history-quality-test", "purpose": "experimental", "symbols": self.symbols,
                "calendar": {"version": "synthetic-test", "evidence": "synthetic test",
                             "dates": ["2026-11-06"], "sessions": [["09:30", "09:32"]]},
                "profiles": [profile, dict(profile, dataset="minute_history", max_observation_delay_seconds=None)]}
        quality = minute_quality_report(plan, [late, history])
        (self.root / "source-quality").mkdir()
        (self.root / "source-quality" / "quality.json").write_text(dumps(quality))
        rows = {row["operation"]: row["minute_quality"] for row in source_health(self.root)["items"]}
        self.assertEqual(rows["rt_min"]["late_count"], 1)
        self.assertEqual(rows["rt_min"]["max_observed_delay_seconds"], 20)
        self.assertEqual(rows["rt_min"]["expected_minutes"], 2)
        self.assertEqual(rows["stk_mins"]["coverage"], 0.5)
        self.assertIsNone(rows["stk_mins"]["late_count"])
        late.rename(self.root / "moved-capture")
        self.assertIsNone(source_health(self.root)["items"][0]["minute_quality"])

    def test_phase_reports_keep_record_totals_separate_from_minute_totals(self):
        path = self.capture("phase", "minute_history", "2026-11-10T01:40:00+00:00")
        plan = json.loads((Path(__file__).resolve().parent.parent / "configs/minute-quality-phases-template.json").read_text())
        plan.update(symbols=self.symbols, security_days=[dict(symbol="600000.SH", date="2026-11-06", status="trading", evidence="synthetic-complete-list", intervals=[])])
        plan["calendar"] = dict(version="synthetic-test", evidence="synthetic-only", dates=["2026-11-06"],
                                phases=[dict(id="opening", kind="opening_auction", start="09:15", end="09:25")])
        profile = plan["profiles"][-1]
        profile.update(timestamp_label="end", timestamp_timezone="Asia/Shanghai", completion="provider_closed", volume_unit="shares", amount_unit="CNY", turnover_mode="interval", adjustment="none",
                       evidence=dict.fromkeys(("timestamp", "completion", "units", "turnover", "adjustment"), "synthetic-only"),
                       phase_rules=[dict(phase_id="opening", mode="aggregate", label_at="09:31", evidence="synthetic-only")], no_trade_policy=dict(mode="emit", evidence="synthetic-only"))
        plan["profiles"] = [profile]
        report = minute_quality_report(plan, [path])
        (self.root / "source-quality").mkdir()
        (self.root / "source-quality" / "phase.json").write_text(dumps(report))
        quality = source_health(self.root)["items"][0]["minute_quality"]
        self.assertEqual((quality["expected_records"], quality["usable_records"], quality["record_coverage"]), (1, 1, 1))
        self.assertIsNone(quality["coverage"])
        self.assertIsNone(quality["expected_minutes"])
        report["schema_version"] = 1
        report["output_hash"] = digest({k: v for k, v in report.items() if k != "output_hash"})
        with self.assertRaisesRegex(ValueError, "版本不一致"):
            _quality_projection(report, {})


class WorkbenchHistoryTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.app = Application(str(Path(directory.name) / "history.sqlite3"), seed=False)

    def test_sector_projection_keeps_pause_recovery_and_version_boundary(self):
        for batch in fixture_batches():
            self.app.scan(batch)
        timeline = sector_timeline(self.app.store, self.app.config["id"], "chips")
        events = timeline["events"]
        self.assertEqual(timeline["scanned_slices"], 11)
        self.assertTrue(all(event["simulated"] is True for event in events))
        pause = next(i for i, event in enumerate(events) if event["quality"] == "paused")
        self.assertTrue(any(event["quality"] == "good" for event in events[pause + 1:]))
        self.assertTrue(any(event["leaders"] for event in events))
        self.assertEqual(events[-1]["snapshot_id"], fixture_batches()[-1]["snapshot_id"])
        with self.assertRaises(StoreError):
            sector_timeline(self.app.store, "other-version", "chips")
        self.assertEqual(sector_timeline(self.app.store, self.app.config["id"], "chips"), timeline)

    def test_study_cards_preserve_run_denominators_and_legacy_cases(self):
        batches, plan = make_study_fixture(12)
        plan.update(reaction_delays_minutes=[1], holding_windows_days=[1], bootstrap_samples=0)
        for rule in plan["rules"]:
            rule["fees"]["commission_fraction"] = "0.02"
        report = run_study(batches, plan)
        old = deepcopy(report)
        for profile in old["profiles"]:
            profile.pop("signal_refs")
        old["output_hash"] = digest({k: v for k, v in old.items() if k != "output_hash"})
        for identifier, result in (("new", report), ("duplicate", report), ("legacy", old)):
            self.app.store.save_job(identifier, {"kind": "study", "dataset_id": "fixture", "plan_id": "fixture"})
            self.app.store.update_job(identifier, "completed", result=result)
        cards = study_cards(self.app.store)
        self.assertEqual(cards["report_count"], 2)
        self.assertEqual(len(cards["items"]), 4)
        early = next(card for card in cards["items"] if card["profile_id"] == "early")
        self.assertEqual(len(early["runs"]), 2)
        self.assertEqual(early["runs"][0]["counts"], early["runs"][1]["counts"])
        cases = study_cases(self.app.store, "new", "early")
        legacy = study_cases(self.app.store, "legacy", "early")
        self.assertGreater(cases["failure_count"], 6)
        failures = [item for item in cases["items"] if item["status"] == "closed"]
        self.assertEqual(len(failures), 6)
        self.assertEqual(failures, sorted(failures, key=lambda item: (item["net_return"], item["signal_id"])))
        self.assertTrue(all(item["revenue_failure"] for item in failures))
        self.assertTrue(any(item["status"] == "pending" for item in cases["items"]))
        self.assertTrue(all(item["signal"] and item["holding_days"] == 1 for item in cases["items"]))
        self.assertTrue(all(item["signal"] is None for item in legacy["items"]))
        self.assertEqual(get_job(self.app.store, "new", full=True)["result"]["output_hash"], report["output_hash"])
        self.assertNotIn("signal_refs", get_job(self.app.store, "new")["result"]["profiles"][0])
