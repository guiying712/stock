from copy import deepcopy
from datetime import timedelta
import json
import unittest

from stockradar.config import ConfigError, config_hash, load_config, validate_config
from stockradar.engine import DataError, _group_sectors, _valid_at, evaluate, iso, timestamp
from stockradar.fixtures import fixture_batches
from stockradar.providers import validate_batch


class StrategyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batches = fixture_batches()

    def setUp(self):
        self.config = load_config()

    def run_to(self, count, config=None):
        state, outputs = None, []
        for batch in self.batches[:count]:
            result = evaluate(batch, config or self.config, state)
            state = result["state"]
            outputs.append(result)
        return outputs[-1]

    def test_fixture_contract_and_deterministic_roundtrip(self):
        first, second = None, None
        for batch in self.batches:
            validate_batch(batch)
            a = evaluate(batch, self.config, first)
            b = evaluate(json.loads(json.dumps(batch)), self.config, second)
            self.assertEqual(a, b)
            first, second = a["state"], json.loads(json.dumps(b["state"]))

    def test_early_prealert_then_confirmation_without_duplicate_topics(self):
        detected = self.run_to(2)
        self.assertEqual(len(detected["signals"]), 7)
        self.assertTrue(all(s["status"] == "PREALERT" for s in detected["signals"]))
        self.assertTrue(all(len(s["related_sectors"]) == 2 for s in detected["signals"]))
        self.assertTrue(all(1 <= s["score"] <= 100 for s in detected["signals"]))
        confirmed = self.run_to(3)
        self.assertEqual({s["id"] for s in detected["signals"]}, {s["id"] for s in confirmed["signals"]})
        self.assertTrue(all(s["status"] == "CONFIRMED" for s in confirmed["signals"]))
        self.assertEqual(len(confirmed["events"]), 7)

    def test_coverage_uses_eligible_expected_universe_and_exclusions(self):
        first = self.run_to(1)
        self.assertEqual(first["quality"]["expected_count"], 15)
        self.assertEqual(first["quality"]["excluded_count"], 6)
        self.assertEqual(first["quality"]["coverage"], 1)
        missing = self.run_to(6)
        self.assertAlmostEqual(missing["quality"]["coverage"], 14 / 15)
        self.assertEqual(missing["market"]["status"], "UNKNOWN")
        self.assertTrue(all(s["actionability"] == "paused" for s in missing["signals"]))
        self.assertTrue(all(s["status"] != "INVALIDATED" for s in missing["signals"]))

    def test_notification_group_records_membership_version_and_stays_frozen(self):
        first = self.run_to(2)
        groups = {s["id"]: deepcopy(s["evidence"]["notification_group"]) for s in first["signals"]}
        self.assertEqual(len({(g["id"], g["version"]) for g in groups.values()}), 1)
        changed = deepcopy(self.batches[1])
        removed = next(m for m in changed["memberships"] if m["sector_id"] == "ai")
        changed["memberships"].remove(removed)
        fresh = evaluate(changed, self.config)
        self.assertTrue(fresh["signals"])
        self.assertTrue(all(s["evidence"]["notification_group"]["version"] != next(iter(groups.values()))["version"]
                            for s in fresh["signals"]))
        # A later membership change affects current calculations, not an
        # already-alerted episode's notification grouping or trigger snapshot.
        later = deepcopy(self.batches[2])
        later["memberships"] = changed["memberships"]
        result = evaluate(later, self.config, first["state"])
        self.assertEqual({s["id"]: s["evidence"]["notification_group"] for s in result["signals"]}, groups)

    def test_jaccard_groups_are_transitive_canonical_and_keep_raw_members(self):
        # A-B and B-C pass 0.8, while A-C does not. Assigning each node its
        # smallest immediate neighbour used to split this connected hotspot.
        sectors = [{"id": "a", "members": ["1", "2", "3", "4", "5"]},
                   {"id": "b", "members": ["1", "2", "3", "4", "5", "6"]},
                   {"id": "c", "members": ["2", "3", "4", "5", "6"]},
                   {"id": "d", "members": ["7", "8"]}, {"id": "empty", "members": []}]
        original = deepcopy(sectors)
        _group_sectors(sectors, 0.8, "features-test")
        self.assertEqual([s["group_id"] for s in sectors], ["a", "a", "a", "d", "empty"])
        self.assertEqual([s["members"] for s in sectors], [s["members"] for s in original])
        reversed_sectors = list(reversed(deepcopy(original)))
        _group_sectors(reversed_sectors, 0.8, "features-test")
        self.assertEqual({s["id"]: s["group_id"] for s in sectors},
                         {s["id"]: s["group_id"] for s in reversed_sectors})

    def test_single_member_rally_cannot_replace_sector_breadth(self):
        batch = deepcopy(self.batches[1])
        chip_ids = {m["instrument_id"] for m in batch["memberships"] if m["sector_id"] == "chips"}
        for quote in (q for q in batch["quotes"] if q["instrument_id"] in chip_ids and q["instrument_id"] != batch["quotes"][0]["instrument_id"]):
            quote.update(close=quote["prev_close"], open=quote["prev_close"], high=quote["prev_close"], low=quote["prev_close"])
        result = evaluate(batch, self.config)
        self.assertFalse(any(s["status"] in {"PREALERT", "CONFIRMED"} for s in result["signals"]))
        chip = next(s for s in result["sectors"] if s["id"] == "chips")
        self.assertIn("SECTOR_BREAKOUTS_LOW", chip["reason_codes"])

    def test_risk_above_ten_percent_cannot_be_compensated_by_score(self):
        for stock in self.config["stock"].values():
            stock["invalidation_buffer_atr"] = 3
        result = self.run_to(2)
        self.assertTrue(result["signals"])
        self.assertTrue(all(s["status"] == "DETECTED" and s["score"] is None for s in result["signals"]))
        rejected = [e for e in result["evaluations"] if e.get("signal_id")]
        self.assertTrue(all("RISK_DISTANCE_EXCEEDED" in e["reason_codes"] for e in rejected))

    def test_price_extension_and_restoration_update_same_episode(self):
        extended = self.run_to(4)
        restored = self.run_to(5)
        self.assertTrue(all(s["actionability"] == "extended" for s in extended["signals"]))
        self.assertTrue(all(s["actionability"] == "eligible" for s in restored["signals"]))
        self.assertEqual([s["id"] for s in extended["signals"]], [s["id"] for s in restored["signals"]])
        self.assertEqual([s["invalidation_price"] for s in extended["signals"]], [s["invalidation_price"] for s in restored["signals"]])

    def test_structure_failure_and_entry_ttl_are_separate(self):
        broken = self.run_to(8)
        self.assertTrue(all(s["status"] == "INVALIDATED" for s in broken["signals"]))
        pre = self.run_to(3)
        result = evaluate(self.batches[-1], self.config, pre["state"])
        self.assertTrue(all(s["status"] == "EXPIRED" for s in result["signals"]))
        self.assertTrue(all("ENTRY_TTL_EXPIRED" in e["reason_codes"] for e in result["events"]))

    def test_future_quotes_and_unseen_membership_are_never_used(self):
        batch = deepcopy(self.batches[1])
        future = iso(timestamp(batch["as_of"]) + timedelta(minutes=1))
        for quote in batch["quotes"][:4]:
            quote["event_time"] = quote["available_at"] = quote["ingested_at"] = future
        result = evaluate(batch, self.config)
        self.assertEqual(result["market"]["status"], "UNKNOWN")
        self.assertFalse(result["signals"])
        batch = deepcopy(self.batches[1])
        for member in batch["memberships"]:
            member["available_at"] = future
        result = evaluate(batch, self.config)
        self.assertFalse(any(s["status"] == "PREALERT" for s in result["signals"]))
        self.assertTrue(any("MEMBERSHIP_NOT_VISIBLE" in e["reason_codes"] for e in result["evaluations"]))

    def test_benchmark_must_match_stock_slice(self):
        batch = deepcopy(self.batches[1])
        quote = batch["benchmark"]["quote"]
        quote["event_time"] = quote["available_at"] = quote["ingested_at"] = self.batches[0]["as_of"]
        result = evaluate(batch, self.config)
        self.assertEqual(result["market"]["status"], "UNKNOWN")
        self.assertIn("SLICE_MISMATCH", result["market"]["reason_codes"])
        self.assertFalse(any(s["status"] == "PREALERT" for s in result["signals"]))

    def test_effective_utc_boundaries_include_start_exclude_end(self):
        for collection in ("instruments", "memberships"):
            for boundary, offset, active in (("valid_from", -1, True), ("valid_from", 0, True),
                                             ("valid_from", 1, False), ("valid_to", -1, False),
                                             ("valid_to", 0, False), ("valid_to", 1, True)):
                with self.subTest(collection=collection, boundary=boundary, offset=offset):
                    batch = deepcopy(self.batches[1])
                    for record in batch[collection]:
                        record[boundary] = iso(timestamp(batch["as_of"]) + timedelta(seconds=offset))
                    original = deepcopy(batch)
                    validate_batch(batch)
                    result = evaluate(batch, self.config)
                    if collection == "instruments":
                        self.assertEqual(result["quality"]["expected_count"], 15 if active else 0)
                    self.assertEqual(any(s["status"] == "PREALERT" for s in result["signals"]), active)
                    self.assertEqual(batch, original)

    def test_effective_dates_use_shanghai_midnight_and_open_boundaries(self):
        record = {"available_at": "2026-10-27T00:00:00Z",
                  "valid_from": "2026-10-28", "valid_to": "2026-10-29"}
        for instant, expected in (("2026-10-27T15:59:59Z", False),
                                  ("2026-10-27T16:00:00Z", True),
                                  ("2026-10-28T15:59:59Z", True),
                                  ("2026-10-28T16:00:00Z", False)):
            with self.subTest(instant=instant):
                self.assertEqual(_valid_at(record, timestamp(instant)), expected)
        record.update(valid_from=None, valid_to=None)
        self.assertTrue(_valid_at(record, timestamp("2026-10-28T02:01:00Z")))

    def test_effective_interval_does_not_skip_lunch_or_future_visibility(self):
        record = {"available_at": "2026-10-28T00:00:00Z",
                  "valid_from": "2026-10-28T04:00:00Z", "valid_to": "2026-10-28T05:01:00+00:00"}
        for instant, expected in (("2026-10-28T03:30:00Z", False),
                                  ("2026-10-28T04:00:00Z", True),
                                  ("2026-10-28T05:00:00Z", True),
                                  ("2026-10-28T05:01:00Z", False)):
            with self.subTest(instant=instant):
                self.assertEqual(_valid_at(record, timestamp(instant)), expected)
        record["available_at"] = "2026-10-28T05:00:01Z"
        self.assertFalse(_valid_at(record, timestamp("2026-10-28T05:00:00Z")))
        self.assertTrue(_valid_at(record, timestamp("2026-10-28T05:00:01Z")))
        batch = deepcopy(self.batches[1])
        for collection in ("instruments", "memberships"):
            for item in batch[collection]:
                item["valid_from"] = batch["as_of"]
                item["available_at"] = iso(timestamp(batch["as_of"]) + timedelta(seconds=1))
        self.assertFalse(evaluate(batch, self.config)["signals"])

    def test_invalid_effective_interval_fails_direct_evaluation(self):
        for collection in ("instruments", "memberships"):
            batch = deepcopy(self.batches[1])
            batch[collection][0].update(valid_from="2026-10-29", valid_to="2026-10-28")
            with self.subTest(collection=collection), self.assertRaises(DataError):
                evaluate(batch, self.config)

    def test_corporate_action_pauses_without_fake_failure_or_moved_stop(self):
        before = self.run_to(2)
        after = deepcopy(self.batches[2])
        alerted = {s["instrument_id"] for s in before["signals"]}
        for quote in (q for q in after["quotes"] if q["instrument_id"] in alerted):
            for key in ("open", "high", "low", "close", "prev_close"):
                quote[key] = str(float(quote[key]) / 2)
            quote["adjustment_factor"] = "2"
        result = evaluate(after, self.config, before["state"])
        self.assertTrue(all(s["status"] == "PREALERT" for s in result["signals"]))
        self.assertTrue(all(s["actionability"] == "paused" for s in result["signals"]))
        self.assertTrue(all(s["reason_codes"] == ["CORPORATE_ACTION_REVIEW"] for s in result["signals"]))
        self.assertEqual([s["invalidation_price"] for s in before["signals"]], [s["invalidation_price"] for s in result["signals"]])

    def test_missing_history_has_no_invented_score_or_zero_denominator(self):
        batch = deepcopy(self.batches[1])
        batch["daily_bars"] = []
        result = evaluate(batch, self.config)
        self.assertEqual(result["quality"]["expected_count"], 0)
        self.assertIsNone(result["quality"]["coverage"])
        self.assertFalse(result["signals"])
        batch = deepcopy(self.batches[1])
        for row in batch["benchmark"]["daily_bars"]:
            row["amount_cny"] = None
        result = evaluate(batch, self.config)
        self.assertEqual(result["market"]["status"], "UNKNOWN")

    def test_duplicate_late_revision_and_restart_preserve_frozen_evidence(self):
        before = self.run_to(3)
        duplicate = evaluate(self.batches[2], self.config, before["state"])
        self.assertTrue(duplicate["duplicate"])
        self.assertFalse(duplicate["events"])
        late = deepcopy(self.batches[1])
        late["snapshot_id"] += "-correction"
        result = evaluate(late, self.config, json.loads(json.dumps(before["state"])))
        self.assertIn("LATE_CORRECTION", result["quality"]["reason_codes"])
        self.assertTrue(all(s["actionability"] == "paused" for s in result["signals"]))
        self.assertEqual([s["trigger_price"] for s in before["signals"]], [s["trigger_price"] for s in result["signals"]])
        self.assertEqual([s["latest_time"] for s in before["signals"]], [s["latest_time"] for s in result["signals"]])

    def test_non_trading_session_and_timezone_independence(self):
        batch = deepcopy(self.batches[1])
        batch["calendar"]["trading_dates"].remove("2026-10-28")
        result = evaluate(batch, self.config)
        self.assertIn("OUTSIDE_SESSION", result["quality"]["reason_codes"])
        self.assertFalse(result["signals"])
        batch = deepcopy(self.batches[1])
        batch["calendar"]["sessions"] = [["09:30", "09:59"], ["13:00", "14:57"]]
        result = evaluate(batch, self.config)
        self.assertIn("OUTSIDE_SESSION", result["quality"]["reason_codes"])

    def test_unknown_config_and_version_drift_fail_closed(self):
        cfg = deepcopy(self.config)
        cfg["scoring"]["unexpected"] = 1
        with self.assertRaises(ConfigError):
            validate_config(cfg)
        before = self.run_to(2)
        cfg = deepcopy(self.config)
        cfg["id"] += "-new"
        self.assertNotEqual(config_hash(cfg), config_hash(self.config))
        with self.assertRaisesRegex(ValueError, "独立运行"):
            evaluate(self.batches[2], cfg, before["state"])

    def test_broken_continuity_rebuilds_confirmation_count(self):
        self.config["sector"]["confirm_slices"] = 3
        before = self.run_to(2)
        # Omit the next complete minute; having price references in a later
        # packet must not pretend that the strategy evaluated that missing step.
        later = evaluate(self.batches[3], self.config, before["state"])
        self.assertTrue(all(s["status"] == "PREALERT" for s in later["signals"]))
        self.assertLess(later["state"]["sectors"]["chips"]["confirm_count"], 3)

    def test_current_volume_failure_pauses_existing_alert(self):
        before = self.run_to(2)
        batch = deepcopy(self.batches[2])
        alerted = {s["instrument_id"] for s in before["signals"]}
        for quote in (q for q in batch["quotes"] if q["instrument_id"] in alerted):
            quote["amount_cny"] = "100000"
            quote["volume_shares"] = 100
        result = evaluate(batch, self.config, before["state"])
        self.assertTrue(all(s["status"] == "PREALERT" for s in result["signals"]))
        self.assertTrue(all(s["actionability"] == "paused" for s in result["signals"]))

    def test_corrupt_historical_minute_is_not_a_scoring_input(self):
        batch = deepcopy(self.batches[1])
        for quote in batch["minute_history"]:
            if quote["event_time"].startswith("2026-10-28"):
                quote["quality"] = "bad"
        result = evaluate(batch, self.config)
        self.assertFalse(any(s["status"] == "PREALERT" for s in result["signals"]))
        self.assertTrue(all(s["score"] is None for s in result["signals"]))


if __name__ == "__main__":
    unittest.main()
