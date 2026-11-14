import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from stockradar.zsxq_events import GROUP_ID, fetch, main, normalize, save
from stockradar.zsxq_store import EventStore, fetch_once, import_capture, main as store_main


class ZsxqTests(unittest.TestCase):
    def payload(self):
        return {"success": True, "count": 1, "has_more": True, "topics_brief": [{
            "topic_id": "123", "group": {"group_id": GROUP_ID},
            "title": "研究线索", "content": "<e type='hashtag' title='%23机器人%23' />",
            "create_time": "2026-11-14T16:00:00+0800", "modify_time": "", "images": [], "files": []}]}

    def normalize(self, payload=None):
        return normalize(payload or self.payload(), "2026-11-14T10:00:00+00:00")

    def test_time_and_release_boundary(self):
        report = self.normalize()
        topic = report["topics"][0]
        self.assertEqual(topic["published_at"], "2026-11-14T08:00:00+00:00")
        self.assertIsNone(topic["event_time"])
        self.assertIsNone(topic["available_at"])
        self.assertEqual(topic["content"], "#机器人#")
        self.assertFalse(report["strategy_input_ready"])
        self.assertFalse(report["release_allowed"])

    def test_drops_signed_urls_and_profile(self):
        payload = self.payload()
        row = payload["topics_brief"][0]
        row["owner"] = {"avatar_url": "https://example.com/?token=PRIVATE"}
        row["images"] = [{"image_id": "456", "large": {"url": "https://example.com/?token=PRIVATE"}}]
        row["content"] = "链接 https://example.com/file?token=PRIVATE#secret"
        report = self.normalize(payload)
        self.assertNotIn("PRIVATE", json.dumps(report))
        self.assertEqual(report["topics"][0]["content"], "链接 https://example.com/file")
        self.assertIn("ATTACHMENTS_NOT_PARSED", report["topics"][0]["reason_codes"])

    def test_image_only_is_not_event(self):
        payload = self.payload()
        payload["topics_brief"][0]["content"] = "「图片」"
        self.assertIn("NO_TEXT_CONTENT", self.normalize(payload)["topics"][0]["reason_codes"])

    def test_duplicate_and_conflicting_revision(self):
        payload = self.payload()
        payload["topics_brief"] *= 2
        payload["count"] = 2
        self.assertEqual(self.normalize(payload)["unique_count"], 1)
        payload["topics_brief"][1] = copy.deepcopy(payload["topics_brief"][0])
        payload["topics_brief"][1]["content"] = "新内容"
        with self.assertRaises(ValueError):
            self.normalize(payload)

    def test_revision_does_not_depend_on_likes_or_capture_time(self):
        payload = self.payload()
        first = self.normalize(payload)["topics"][0]["content_hash"]
        payload["topics_brief"][0]["counts"] = {"likes": 100}
        second = normalize(payload, "2026-11-15T10:00:00Z")["topics"][0]["content_hash"]
        self.assertEqual(first, second)
        payload["topics_brief"][0]["content"] = "修订内容"
        self.assertNotEqual(first, self.normalize(payload)["topics"][0]["content_hash"])

    def test_other_group_and_numeric_id_rejected(self):
        for field, value in [("group", {"group_id": "123"}), ("topic_id", 123)]:
            payload = self.payload()
            payload["topics_brief"][0][field] = value
            with self.assertRaises(ValueError):
                self.normalize(payload)

    def test_bad_response_or_count_fails(self):
        for key, value in [("success", False), ("has_more", None), ("count", 2), ("topics_brief", {})]:
            payload = self.payload()
            payload[key] = value
            with self.assertRaises(ValueError):
                self.normalize(payload)

    def test_unknown_timezone_rejected_and_future_flagged(self):
        payload = self.payload()
        payload["topics_brief"][0]["create_time"] = "2026-11-14T16:00:00"
        with self.assertRaises(ValueError):
            self.normalize(payload)
        payload["topics_brief"][0]["create_time"] = "2027-01-01T00:00:00Z"
        self.assertIn("SOURCE_TIME_AFTER_OBSERVATION", self.normalize(payload)["topics"][0]["reason_codes"])

    def test_existing_output_stops_before_network(self):
        with tempfile.TemporaryDirectory() as tmp, patch("stockradar.zsxq_events.fetch") as mocked:
            with self.assertRaises(SystemExit):
                main(["--cli", "/not-installed", "--output", tmp])
            mocked.assert_not_called()

    def test_budget_rejected_before_network(self):
        with patch("stockradar.zsxq_events.subprocess.run") as mocked:
            for limit in [0, 21, True]:
                with self.assertRaises(ValueError):
                    fetch("/not-installed", limit)
            mocked.assert_not_called()

    def test_archive_hash_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "capture"
            manifest = save(self.normalize(), target)
            import hashlib
            self.assertEqual(manifest["topics_sha256"], hashlib.sha256((target / "topics.json").read_bytes()).hexdigest())
            with self.assertRaises(FileExistsError):
                save(self.normalize(), target)


class ZsxqStoreTests(unittest.TestCase):
    def make_page(self, items, observed_at="2026-11-14T10:00:00Z", has_more=True):
        rows = [
            {
                "topic_id": str(topic_id),
                "group": {"group_id": GROUP_ID},
                "title": "标题",
                "content": content,
                "create_time": published_at,
                "modify_time": "",
                "images": [],
                "files": [],
            }
            for topic_id, published_at, content in items
        ]
        payload = {"success": True, "count": len(rows), "has_more": has_more, "topics_brief": rows}
        return normalize(payload, observed_at, max(1, len(rows)))

    def test_import_dedup_and_manifest_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = EventStore(root / "events.sqlite3", clock=lambda: "2026-11-14T10:05:00+00:00")
            cap1 = root / "cap1"
            cap2 = root / "cap2"
            save(self.make_page([("101", "2026-11-14T08:00:00Z", "首次采集")], "2026-11-14T10:00:00Z"), cap1)
            save(self.make_page([("101", "2026-11-14T08:00:00Z", "首次采集")], "2026-11-14T10:02:00Z"), cap2)

            first = import_capture(store, cap1)
            self.assertFalse(first["duplicate"])
            self.assertEqual(first["new_topics"], 1)
            self.assertEqual(first["coverage"], "initial")

            dup = import_capture(store, cap1)
            self.assertTrue(dup["duplicate"])
            self.assertEqual(dup["run_id"], first["run_id"])

            second = import_capture(store, cap2)
            self.assertFalse(second["duplicate"])
            self.assertEqual(second["unchanged"], 1)
            self.assertEqual(second["coverage"], "contiguous")
            stat = store.status()
            self.assertEqual(stat["topics"], 1)
            self.assertEqual(stat["revisions"], 1)
            self.assertEqual(stat["revised_topics"], 0)
            self.assertFalse(stat["strategy_input_ready"])
            self.assertFalse(stat["release_allowed"])
            self.assertFalse(stat["automatic_collection"])

            bad = root / "bad"
            save(self.make_page([("102", "2026-11-14T09:00:00Z", "被篡改")]), bad)
            (bad / "manifest.json").write_text(json.dumps({"group_id": GROUP_ID, "topics_sha256": "0" * 64}))
            with self.assertRaises(ValueError):
                import_capture(store, bad)
            self.assertEqual(store.status()["topics"], 1)

    def test_revisions_and_out_of_order_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EventStore(Path(tmp) / "events.sqlite3", clock=lambda: "2026-11-14T12:05:00+00:00")
            first = self.make_page([("101", "2026-11-14T08:00:00Z", "初稿")], "2026-11-14T10:00:00Z")
            revised = self.make_page([("101", "2026-11-14T08:00:00Z", "修订版")], "2026-11-14T12:00:00Z")
            older = self.make_page([("101", "2026-11-14T08:00:00Z", "更早草稿")], "2026-11-14T09:00:00Z")

            store.apply(first, mode="capture_import")
            res = store.apply(revised, mode="capture_import")
            self.assertEqual(res["new_revisions"], 1)
            store.apply(older, mode="capture_import")

            with store.connect() as db:
                row = dict(db.execute("SELECT * FROM topics WHERE topic_id='101'").fetchone())
            self.assertEqual(row["first_observed_at"], "2026-11-14T09:00:00+00:00")
            self.assertEqual(row["last_observed_at"], "2026-11-14T12:00:00+00:00")
            self.assertEqual(row["latest_hash"], revised["topics"][0]["content_hash"])
            self.assertEqual(row["revision_count"], 3)
            self.assertEqual(row["observation_count"], 3)

            mutated_time = self.make_page([("101", "2026-11-14T08:01:00Z", "修订版")], "2026-11-14T13:00:00Z")
            with self.assertRaises(ValueError):
                store.apply(mutated_time, mode="capture_import")
            self.assertEqual(store.status()["revisions"], 3)

    def test_coverage_watermarks_and_gap_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EventStore(Path(tmp) / "events.sqlite3", clock=lambda: "2026-11-14T12:00:00+00:00")
            p1 = self.make_page([("102", "2026-11-14T08:00:00Z", "B"), ("101", "2026-11-14T07:00:00Z", "A")])
            p2 = self.make_page([("103", "2026-11-14T09:00:00Z", "C"), ("102", "2026-11-14T08:00:00Z", "B")])
            p3 = self.make_page([("105", "2026-11-14T12:00:00Z", "E"), ("104", "2026-11-14T11:00:00Z", "D")])
            unordered = self.make_page([("101", "2026-11-14T07:00:00Z", "A"), ("102", "2026-11-14T08:00:00Z", "B")])
            full = self.make_page(
                [("105", "2026-11-14T12:00:00Z", "E"), ("100", "2026-11-14T06:00:00Z", "Z")],
                has_more=False,
            )

            self.assertEqual(store.apply(p1)["coverage"], "initial")
            self.assertEqual(store.apply(p2)["coverage"], "contiguous")
            self.assertEqual(len(store.status()["open_gaps"]), 0)

            self.assertEqual(store.apply(p3)["coverage"], "gap_recorded")
            gaps = store.status()["open_gaps"]
            self.assertEqual(len(gaps), 1)
            self.assertEqual(gaps[0]["after_published_at"], "2026-11-14T09:00:00+00:00")
            self.assertEqual(gaps[0]["before_published_at"], "2026-11-14T11:00:00+00:00")
            self.assertFalse(store.status()["history_complete"])

            self.assertEqual(store.apply(unordered)["coverage"], "order_unverified")
            self.assertEqual(store.apply(full)["coverage"], "complete_to_start")
            stat = store.status()
            self.assertEqual(stat["open_gaps"], [])
            self.assertTrue(stat["history_complete"])
            self.assertEqual(stat["coverage_segments"][0]["oldest_published_at"], "2026-11-14T06:00:00+00:00")
            self.assertEqual(stat["coverage_segments"][0]["newest_published_at"], "2026-11-14T12:00:00+00:00")

    def test_daily_budget_precharged_and_interrupted_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EventStore(Path(tmp) / "events.sqlite3", clock=lambda: "2026-11-14T10:00:00+00:00")
            raw = {
                "success": True,
                "count": 1,
                "has_more": True,
                "topics_brief": [{
                    "topic_id": "101",
                    "group": {"group_id": GROUP_ID},
                    "title": "",
                    "content": "内容",
                    "create_time": "2026-11-14T16:00:00+0800",
                    "modify_time": "",
                    "images": [],
                    "files": [],
                }],
            }
            res = fetch_once(store, "/unused", 1, 3, fetcher=lambda cli, limit: raw)
            self.assertEqual(res["new_topics"], 1)

            def failing_fetcher(cli, limit):
                raise ValueError("模拟断连")

            with self.assertRaises(ValueError):
                fetch_once(store, "/unused", 1, 3, fetcher=failing_fetcher)

            # Simulate an interrupted process that pre-charged the 3rd budget unit.
            store.begin_fetch(1, 3)
            called = []
            with self.assertRaises(ValueError):
                fetch_once(store, "/unused", 1, 3, fetcher=lambda cli, limit: called.append(1))
            self.assertEqual(called, [])

            stat = store.status(daily_budget=3)
            self.assertEqual(stat["budget"]["used"], 3)
            self.assertEqual(stat["budget"]["remaining"], 0)
            self.assertEqual(stat["runs"], {"completed": 1, "failed": 1, "interrupted": 1})

    def test_locks_symlinks_and_cli_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "events.sqlite3"
            store = EventStore(db_path)
            with store.lock():
                with self.assertRaises(ValueError):
                    with store.lock():
                        pass

            link_db = root / "link.sqlite3"
            link_db.symlink_to(db_path)
            with self.assertRaises(ValueError):
                EventStore(link_db)

            with store.transaction() as db:
                db.execute("UPDATE meta SET value='999' WHERE key='group_id'")
            with self.assertRaises(ValueError):
                EventStore(db_path)

            clean_db = root / "clean.sqlite3"
            cap = root / "cap"
            save(self.make_page([("101", "2026-11-14T08:00:00Z", "CLI导入")]), cap)
            store_main(["--db", str(clean_db), "import", str(cap)])
            self.assertEqual(EventStore(clean_db).status()["topics"], 1)


if __name__ == "__main__":
    unittest.main()
