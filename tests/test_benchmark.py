import unittest

from stockradar.benchmark import load_batches, run_benchmark
from stockradar.providers import validate_batch


class BenchmarkTests(unittest.TestCase):
    def test_scaled_tape_has_unique_consistent_codes_and_references(self):
        batches = load_batches(24)
        for batch in batches:
            validate_batch(batch)
            ids = {item["id"] for item in batch["instruments"]}
            self.assertEqual(len(ids), 24)
            for item in batch["instruments"]:
                self.assertEqual(item["id"], item["exchange"] + "." + item["code"])
                self.assertEqual(len(item["code"]), 6)
            self.assertEqual({q["instrument_id"] for q in batch["quotes"]}, ids)
        for invalid in (0, 13, 6001, True):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                load_batches(invalid)

    def test_benchmark_is_explicitly_synthetic_without_platform_latency(self):
        report = run_benchmark([12], iterations=1, concurrent_replays=0)
        self.assertTrue(report["simulated"])
        self.assertFalse(report["full_market_verified"])
        self.assertIsNone(report["platform_acceptance_p95_seconds"])
        self.assertEqual(report["cases"][0]["scans"], 2)
        self.assertGreater(report["cases"][0]["database_and_wal_bytes"], 0)
