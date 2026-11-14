from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from stockradar.replay import evaluate_observations, run_replay


START = datetime(2026, 10, 19, 2, 0, tzinfo=timezone.utc)


def time_at(dt):
    return dt.isoformat().replace("+00:00", "Z")


def quote(dt, value="10.10", **changes):
    q = {"instrument_id": "SZSE.000001", "event_time": time_at(dt), "available_at": time_at(dt),
         "ingested_at": time_at(dt), "close": value, "high": value, "low": value,
         "adjustment_factor": "1", "interval": 60, "is_complete": True, "quality": "good", "revision": 1}
    q.update(changes)
    return q


def batch(dt, quotes=(), daily=()):
    return {"as_of": time_at(dt), "quotes": list(quotes), "daily_bars": list(daily),
            "calendar": {"version": "calendar-test-v1", "close_time": "15:00", "trading_dates": [
                "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23", "2026-10-26",
                "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30"]}}


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.signal = {"id": "signal-1", "instrument_id": "SZSE.000001", "trigger_price": "10",
                       "entry_low": "10.01", "entry_high": "10.50", "expires_at": time_at(START + timedelta(minutes=20)),
                       "evidence": {"adjustment_factor": "1"}}
        self.events = {"signal-1": {"at": time_at(START)}}

    def evaluate(self, batches):
        return evaluate_observations([self.signal], self.events, batches)

    def test_retransmitted_old_quote_is_not_future_entry_price(self):
        stale = quote(START, "10.10")
        batches = [batch(START), batch(START + timedelta(minutes=1), [stale])]
        result = self.evaluate(batches)
        self.assertEqual(result["delay_scenarios"][0]["pending"], 1)
        self.assertEqual(result["observation_gaps"]["QUOTE_SLICE_MISMATCH"], 1)

    def test_zero_delay_still_requires_strictly_later_event(self):
        batches = [batch(START, [quote(START)]), batch(START + timedelta(minutes=1), [quote(START + timedelta(minutes=1))])]
        result = self.evaluate(batches)
        self.assertEqual(result["delay_scenarios"][0]["observable_in_range"], 1)
        self.assertEqual(result["delay_scenarios"][1]["pending"], 1)

    def test_null_price_is_gap_not_exception_or_zero(self):
        dt = START + timedelta(minutes=1)
        result = self.evaluate([batch(START), batch(dt, [quote(dt, None)])])
        self.assertEqual(result["delay_scenarios"][0]["pending"], 1)
        self.assertEqual(result["observation_gaps"]["INVALID_OR_MISSING_QUOTE"], 1)

    def test_target_day_missing_does_not_use_earlier_price(self):
        # Calendar says the fifth later trading date is Oct 26. More observed
        # dates do not make an Oct 23 close into a five-trading-day outcome.
        observations = [batch(START)]
        for day in (20, 21, 22, 23, 27):
            dt = datetime(2026, 10, day, 7, 0, tzinfo=timezone.utc)
            observations.append(batch(dt, [quote(dt, "11")]))
        result = self.evaluate(observations)
        window = result["windows"][0]
        self.assertEqual(window["status"], "pending")
        self.assertEqual(window["pending_reasons"], {"TARGET_CLOSE_MISSING": 1})
        self.assertIsNone(window["gross_trigger_return_mean"])

    def test_target_day_requires_close_not_intraday_last_quote(self):
        dt = datetime(2026, 10, 26, 6, 0, tzinfo=timezone.utc)
        result = self.evaluate([batch(START), batch(dt, [quote(dt, "11")])])
        self.assertEqual(result["windows"][0]["pending"], 1)

    def test_completed_close_is_adjusted_and_costs_remain_unknown(self):
        dt = datetime(2026, 10, 26, 7, 0, tzinfo=timezone.utc)
        result = self.evaluate([batch(START), batch(dt, [quote(dt, "5.5", adjustment_factor="2")])])
        window = result["windows"][0]
        self.assertEqual(window["status"], "observed")
        self.assertAlmostEqual(window["gross_trigger_return_mean"], 0.1)
        self.assertIsNone(window["cost_adjusted_return"])
        self.assertIsNone(window["max_adverse"])

    def test_calendar_must_be_visible_at_alert(self):
        start = batch(START)
        start["calendar"]["trading_dates"] = ["2026-10-19"]
        dt = datetime(2026, 10, 26, 7, 0, tzinfo=timezone.utc)
        result = self.evaluate([start, batch(dt, [quote(dt)])])
        self.assertEqual(result["windows"][0]["pending_reasons"], {"CALENDAR_WINDOW_INCOMPLETE": 1})

    def test_unknown_close_time_keeps_window_pending(self):
        first = batch(START)
        del first["calendar"]["close_time"]
        result = self.evaluate([first])
        self.assertEqual(result["windows"][0]["pending_reasons"], {"CALENDAR_CLOSE_UNSPECIFIED": 1})

    def test_mixed_real_and_simulation_rejected_before_engine(self):
        with self.assertRaisesRegex(ValueError, "混入"):
            run_replay([{"simulated": True}, {"simulated": False}], {})


if __name__ == "__main__":
    unittest.main()
