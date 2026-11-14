import copy
import json
import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from stockradar.config import load_config
from stockradar.notifier import MAX_MESSAGE_BYTES
from stockradar.outbox import dispatch_pending, enqueue, recover_inflight
from stockradar.store import Store, StoreError, dumps


NOW = datetime(2026, 10, 28, 2, 1, tzinfo=timezone.utc)


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "test.sqlite3")
        config = load_config()
        config.update(id="live-test", mode="live_alert", purpose="experimental")
        config["runtime"]["group_window_seconds"] = 0
        self.store.register_version(config)
        clock_patch = patch("stockradar.outbox.now", return_value=NOW.isoformat())
        self.clock = clock_patch.start()
        self.addCleanup(clock_patch.stop)
        self.group_sequence = 0
        self.notifier = Mock()
        self.notifier.send.return_value = {"status": "accepted", "retryable": False, "receipt": {"errcode": 0}}

    def tearDown(self):
        self.temp.cleanup()

    def signal(self, signal_id="s-1", **changes):
        signal = {"id": signal_id, "instrument_id": "SZSE.000001", "code": "000001", "name": "测试证券",
                  "status": "PREALERT", "actionability": "eligible", "revision": 1,
                  "trigger_time": NOW.isoformat(), "latest_time": NOW.isoformat(),
                  "expires_at": (NOW + timedelta(minutes=15)).isoformat(), "latest_price": "10.10",
                  "trigger_price": "10.10", "entry_low": "10.05", "entry_high": "10.50",
                  "breakout_price": "10.00", "invalidation_price": "9.80", "score": 82,
                  "evidence": {"simulated": False, "source": "test-only-fake"}, "simulated": False,
                  "strategy_version": "live-test"}
        signal.update(changes)
        return signal

    def event(self, signal, **changes):
        event = {"id": signal["id"] + "-event-" + str(signal["revision"]), "signal_id": signal["id"],
                 "revision": signal["revision"], "from_status": "DETECTED", "to_status": signal["status"],
                 "at": NOW.isoformat(), "reason_codes": ["TEST"]}
        event.update(changes)
        return event

    def save_signal(self, signal):
        with self.store.connect() as db:
            db.execute("INSERT OR REPLACE INTO signals VALUES(?,?,?)", (signal["id"], signal["strategy_version"], dumps(signal)))

    def grouped_signal(self, signal_id, group="chips", group_version="members-v1", version="group-test", **changes):
        config = load_config()
        config.update(id=version, mode="live_alert", purpose="experimental")
        self.store.register_version(config)
        self.group_sequence += 1
        code = "%06d" % self.group_sequence
        signal = self.signal(signal_id, strategy_version=version, trading_date="2026-10-28",
                             code=code, instrument_id="SZSE." + code, name="聚合证券" + signal_id,
                             sector_name="测试热点", evidence={"simulated": False, "source": "test-only-fake",
                             "notification_group": {"id": group, "version": group_version}})
        signal.update(changes)
        return signal

    def queue(self, signal=None, event=None):
        signal = signal or self.signal()
        self.save_signal(signal)
        with self.store.connect() as db:
            return enqueue(db, signal, event or self.event(signal))

    def test_idempotent_queue_and_transaction_rollback(self):
        signal = self.signal()
        notification_id = self.queue(signal)
        with self.store.connect() as db:
            self.assertEqual(enqueue(db, signal, self.event(signal)), notification_id)
        self.assertEqual(len(self.store.notifications()), 1)
        with self.assertRaises(StoreError):
            with self.store.connect() as db:
                enqueue(db, dict(signal, score=90), self.event(signal))
        with self.assertRaises(RuntimeError):
            with self.store.connect() as db:
                enqueue(db, self.signal("rollback"), self.event(self.signal("rollback")))
                raise RuntimeError("rollback")
        self.assertEqual(len(self.store.notifications()), 1)

    def test_success_once_attempt_is_recorded_and_deduplicated(self):
        notification_id = self.queue()
        result = dispatch_pending(self.store, self.notifier, NOW.isoformat())
        self.assertEqual(result[0]["status"], "accepted")
        self.assertEqual(self.notifier.send.call_args.args[1], notification_id)
        self.assertEqual(dispatch_pending(self.store, self.notifier, NOW.isoformat()), [])
        notification = self.store.notifications()[0]
        self.assertEqual(notification["attempts"], 1)
        self.assertEqual(len(notification["delivery_attempts"]), 2)

    def test_latest_revision_and_actionability_cancel_old_opportunity(self):
        for change, expected in [({"revision": 2}, "SUPERSEDED_REVISION"),
                                 ({"actionability": "extended"}, "NOT_ELIGIBLE"),
                                 ({"latest_price": "12"}, "PRICE_OUTSIDE_RANGE")]:
            signal = self.signal(expected)
            self.queue(signal)
            self.save_signal(dict(signal, **change))
            result = dispatch_pending(self.store, self.notifier, NOW.isoformat())
            self.assertEqual(result[0]["reason_code"], expected)
        self.notifier.send.assert_not_called()

    def test_expiry_stale_and_future_times_do_not_send(self):
        cases = [({"expires_at": NOW.isoformat()}, "ENTRY_TTL_EXPIRED"),
                 ({"latest_time": (NOW - timedelta(seconds=91)).isoformat()}, "DATA_STALE"),
                 ({"latest_time": (NOW + timedelta(seconds=1)).isoformat()}, "FUTURE_QUOTE")]
        for changes, reason in cases:
            self.queue(self.signal(reason, **changes))
            result = dispatch_pending(self.store, self.notifier, NOW.isoformat())
            self.assertEqual(result[0]["reason_code"], reason)
        self.notifier.send.assert_not_called()

    def test_simulation_and_nonlive_versions_cannot_send(self):
        self.queue(self.signal("simulation", evidence={"simulated": True}, simulated=True))
        result = dispatch_pending(self.store, self.notifier, NOW.isoformat())
        self.assertEqual(result[0]["reason_code"], "SIMULATION_BLOCKED")
        self.queue(self.signal("shadow"))
        with self.store.connect() as db:
            db.execute("UPDATE versions SET config=?", (dumps({"mode": "shadow"}),))
        result = dispatch_pending(self.store, self.notifier, NOW.isoformat())
        self.assertEqual(result[0]["reason_code"], "MODE_FORBIDDEN")
        self.notifier.send.assert_not_called()

    def test_unknown_delivery_is_never_retried(self):
        self.queue()
        self.notifier.send.return_value = {"status": "unknown", "retryable": True}
        first = dispatch_pending(self.store, self.notifier, NOW.isoformat())
        self.assertFalse(first[0]["retryable"])
        self.assertEqual(dispatch_pending(self.store, self.notifier, (NOW + timedelta(minutes=1)).isoformat()), [])
        self.assertEqual(self.notifier.send.call_count, 1)

    def test_explicit_failure_has_backoff_and_three_attempt_limit(self):
        signal = self.signal()
        self.queue(signal)
        self.notifier.send.return_value = {"status": "failed", "retryable": True, "receipt": {"errcode": 130101}}
        first = dispatch_pending(self.store, self.notifier, NOW.isoformat())
        self.assertEqual(first[0]["next_attempt_at"], (NOW + timedelta(seconds=30)).isoformat())
        self.assertEqual(dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=29)).isoformat()), [])
        dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=30)).isoformat())
        signal["latest_time"] = (NOW + timedelta(seconds=90)).isoformat()
        self.save_signal(signal)
        result = dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=90)).isoformat())
        self.assertEqual(result[0]["attempt"], 3)
        self.assertFalse(result[0]["retryable"])
        self.assertEqual(dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=300)).isoformat()), [])
        self.assertEqual(self.notifier.send.call_count, 3)

    def test_recheck_before_retry_cancels_deteriorated_signal(self):
        signal = self.signal()
        self.queue(signal)
        self.notifier.send.return_value = {"status": "failed", "retryable": True}
        dispatch_pending(self.store, self.notifier, NOW.isoformat())
        self.save_signal(dict(signal, status="INVALIDATED", revision=2))
        result = dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=30)).isoformat())
        self.assertEqual(result[0]["reason_code"], "SUPERSEDED_REVISION")
        self.assertEqual(self.notifier.send.call_count, 1)

    def test_risk_update_ignores_entry_expiry_and_has_queue_priority(self):
        self.queue(self.signal("ordinary"))
        signal = self.signal("risk", status="INVALIDATED", actionability="expired", revision=2,
                             expires_at=(NOW - timedelta(minutes=5)).isoformat(),
                             latest_time=(NOW - timedelta(minutes=10)).isoformat())
        self.queue(signal, self.event(signal, from_status="PREALERT"))
        result = dispatch_pending(self.store, self.notifier, NOW.isoformat(), max_messages=1)
        self.assertEqual(result[0]["status"], "accepted")
        self.assertIn("策略失效", self.notifier.send.call_args.args[0]["markdown"]["title"])

    def test_crash_recovery_marks_sending_unknown(self):
        notification_id = self.queue()
        with self.store.connect() as db:
            db.execute("UPDATE outbox SET status='sending',attempts=1 WHERE id=?", (notification_id,))
        reopened = Store(self.store.path)
        self.assertEqual(recover_inflight(reopened), 1)
        self.assertEqual(recover_inflight(reopened), 0)
        self.assertEqual(reopened.notifications()[0]["status"], "unknown")
        self.assertEqual(dispatch_pending(reopened, self.notifier, NOW.isoformat()), [])
        self.notifier.send.assert_not_called()

    def test_network_exception_is_unknown_and_redacted(self):
        self.queue()
        self.notifier.send.side_effect = RuntimeError("secret URL")
        result = dispatch_pending(self.store, self.notifier, NOW.isoformat())
        self.assertEqual(result[0]["status"], "unknown")
        self.assertNotIn("secret", json.dumps(result))

    def test_concurrent_workers_claim_once_and_send_outside_transaction(self):
        self.queue()
        entered, finish = threading.Event(), threading.Event()
        def send(*args):
            entered.set()
            # This write would deadlock if dispatch held its DB transaction over I/O.
            self.store.log("DURING_SEND", "test")
            finish.wait(5)
            return {"status": "accepted", "retryable": False}
        self.notifier.send.side_effect = send
        results = []
        thread = threading.Thread(target=lambda: results.extend(dispatch_pending(self.store, self.notifier, NOW.isoformat())))
        thread.start()
        self.assertTrue(entered.wait(5))
        try:
            self.assertEqual(dispatch_pending(self.store, self.notifier, NOW.isoformat()), [])
        finally:
            finish.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.notifier.send.call_count, 1)
        self.assertEqual(results[0]["status"], "accepted")

    def test_channel_rate_limit_persists_across_dispatch_calls(self):
        for i in range(21):
            self.queue(self.signal("rate-%02d" % i))
        dispatch_pending(self.store, self.notifier, NOW.isoformat(), max_messages=100)
        self.assertEqual(self.notifier.send.call_count, 20)
        dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=30)).isoformat())
        self.assertEqual(self.notifier.send.call_count, 20)
        dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=61)).isoformat())
        self.assertEqual(self.notifier.send.call_count, 21)

    def test_group_window_merges_new_stocks_and_keeps_individual_evidence(self):
        a = self.grouped_signal("group-a", primary_sector_id="chips")
        b = self.grouped_signal("group-b", primary_sector_id="ai", latest_price="10.20")
        ids = [self.queue(a), self.queue(b)]
        before = {r["id"]: r["payload"] for r in self.store.notifications()}
        latest_a = dict(a, latest_price="10.30", latest_time=(NOW + timedelta(seconds=2)).isoformat())
        self.save_signal(latest_a)
        self.assertEqual(dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=4, milliseconds=999)).isoformat()), [])
        self.notifier.send.assert_not_called()
        result = dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=5)).isoformat())
        self.assertEqual({r["id"] for r in result}, set(ids))
        self.assertTrue(all(r["status"] == "accepted" and r["attempt"] == 1 for r in result))
        self.assertEqual(self.notifier.send.call_count, 1)
        message, key = self.notifier.send.call_args.args
        self.assertIn("2条", message["markdown"]["title"])
        for signal in (a, b):
            self.assertIn(signal["code"], message["markdown"]["text"])
            self.assertIn(signal["id"], message["markdown"]["text"])
        self.assertIn("10\\.20", message["markdown"]["text"])
        self.assertIn("10\\.30", message["markdown"]["text"])
        rows = self.store.notifications()
        self.assertEqual({r["id"]: r["payload"] for r in rows}, before)
        self.assertEqual(len({r["response"]["delivery_id"] for r in rows}), 1)
        self.assertEqual(key, rows[0]["response"]["delivery_id"])
        self.assertTrue(all(len(r["delivery_attempts"]) == 2 for r in rows))
        sent_a = next(r for r in rows if r["signal_id"] == a["id"])
        self.assertEqual(sent_a["delivery_attempts"][0]["dispatch_snapshot"], latest_a)
        self.assertEqual(dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=6)).isoformat()), [])

    def test_late_arrivals_do_not_slide_window_and_boundary_starts_next_batch(self):
        first = self.grouped_signal("window-first")
        first_id = self.queue(first)
        self.clock.return_value = (NOW + timedelta(seconds=4)).isoformat()
        self.queue(self.grouped_signal("window-later"))
        self.clock.return_value = (NOW + timedelta(seconds=5)).isoformat()
        last_id = self.queue(self.grouped_signal("window-boundary"))
        with self.store.connect() as db:
            # Retrying enqueue cannot move an already-persisted deadline.
            self.assertEqual(enqueue(db, first, self.event(first)), first_id)
        result = dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=5)).isoformat())
        self.assertEqual(len(result), 2)
        self.assertNotIn(last_id, {r["id"] for r in result})
        self.assertEqual(dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=9)).isoformat()), [])
        result = dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=10)).isoformat())
        self.assertEqual(result[0]["id"], last_id)
        self.assertEqual(self.notifier.send.call_count, 2)

    def test_group_window_survives_restart_without_a_dispatch_before_restart(self):
        self.queue(self.grouped_signal("restart-a"))
        self.queue(self.grouped_signal("restart-b"))
        reopened = Store(self.store.path)
        self.assertEqual(recover_inflight(reopened), 0)
        self.assertEqual(dispatch_pending(reopened, self.notifier, (NOW + timedelta(seconds=4)).isoformat()), [])
        result = dispatch_pending(reopened, self.notifier, (NOW + timedelta(seconds=5)).isoformat())
        self.assertEqual(len(result), 2)
        self.assertEqual(self.notifier.send.call_count, 1)

    def test_cancelling_window_anchor_does_not_delay_survivors_after_restart(self):
        anchor = self.grouped_signal("anchor")
        self.queue(anchor)
        self.save_signal(dict(anchor, revision=2))
        # Cancellation happens before a later member even joins the window.
        result = dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=2)).isoformat())
        self.assertEqual(result[0]["reason_code"], "SUPERSEDED_REVISION")
        self.clock.return_value = (NOW + timedelta(seconds=4)).isoformat()
        survivor_id = self.queue(self.grouped_signal("survivor"))
        reopened = Store(self.store.path)
        result = dispatch_pending(reopened, self.notifier, (NOW + timedelta(seconds=5)).isoformat())
        self.assertEqual(result[0]["id"], survivor_id)
        self.assertEqual(self.notifier.send.call_count, 1)

    def test_risk_bypasses_group_wait_and_preempts_ready_groups(self):
        self.queue(self.grouped_signal("ordinary-a"))
        self.queue(self.grouped_signal("ordinary-b"))
        for i, seconds in enumerate((0, 5)):
            risk = self.grouped_signal("risk-%d" % i, status="INVALIDATED", revision=2, actionability="expired",
                                       expires_at=(NOW - timedelta(minutes=1)).isoformat(),
                                       latest_time=(NOW - timedelta(minutes=10)).isoformat())
            risk_id = self.queue(risk, self.event(risk, from_status="PREALERT"))
            result = dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=seconds)).isoformat(), max_messages=1)
            self.assertEqual(result[0]["id"], risk_id)
            self.assertEqual(result[0]["status"], "accepted")
            self.assertNotIn("同热点新机会", self.notifier.send.call_args.args[0]["markdown"]["title"])
        result = dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=5)).isoformat(), max_messages=1)
        self.assertEqual(len(result), 2)

    def test_old_revision_cancels_during_window_and_confirmation_is_not_delayed(self):
        a, b = self.grouped_signal("superseded-a"), self.grouped_signal("survivor-b")
        old_id, b_id = self.queue(a), self.queue(b)
        newer = dict(a, revision=2, status="CONFIRMED")
        new_id = self.queue(newer, self.event(newer, from_status="PREALERT"))
        result = dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=1)).isoformat())
        by_id = {r["id"]: r for r in result}
        self.assertEqual(by_id[old_id]["reason_code"], "SUPERSEDED_REVISION")
        self.assertEqual(by_id[new_id]["status"], "accepted")
        self.assertNotIn(b_id, by_id)
        result = dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=5)).isoformat())
        self.assertEqual(result[0]["id"], b_id)
        self.assertNotIn(a["id"], self.notifier.send.call_args.args[0]["markdown"]["text"])

    def test_each_group_member_revalidated_for_price_ttl_quality_and_revision(self):
        cases = [({"latest_price": "11"}, "PRICE_OUTSIDE_RANGE"),
                 ({"expires_at": (NOW + timedelta(seconds=5)).isoformat()}, "ENTRY_TTL_EXPIRED"),
                 ({"latest_time": (NOW - timedelta(seconds=90)).isoformat()}, "DATA_STALE"),
                 ({"actionability": "paused"}, "NOT_ELIGIBLE"),
                 ({"revision": 2}, "SUPERSEDED_REVISION")]
        for i, (changes, reason) in enumerate(cases):
            bad = self.grouped_signal("bad-%d" % i, group="checks-%d" % i)
            good = self.grouped_signal("good-%d" % i, group="checks-%d" % i)
            self.queue(bad)
            self.queue(good)
            self.save_signal(dict(bad, **changes))
        result = dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=5)).isoformat())
        self.assertEqual({r["reason_code"] for r in result if r["status"] == "expired"}, {reason for _, reason in cases})
        self.assertEqual(sum(r["status"] == "accepted" for r in result), len(cases))
        for call in self.notifier.send.call_args_list:
            self.assertNotIn("bad-", call.args[0]["markdown"]["text"])

    def test_group_isolated_by_strategy_day_hotspot_and_membership_version(self):
        for signal in (self.grouped_signal("base"), self.grouped_signal("other-members", group_version="members-v2"),
                       self.grouped_signal("other-strategy", version="group-test-v2"),
                       self.grouped_signal("other-day", trading_date="2026-10-27"),
                       self.grouped_signal("other-sector", group="robotics")):
            self.queue(signal)
        result = dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=5)).isoformat())
        self.assertEqual(len(result), 5)
        self.assertEqual(self.notifier.send.call_count, 5)

    def test_provider_pause_cancels_waiting_group_but_risk_still_sends(self):
        self.queue(self.grouped_signal("paused-a"))
        self.queue(self.grouped_signal("paused-b"))
        risk = self.grouped_signal("paused-risk", status="INVALIDATED", actionability="expired", revision=2)
        risk_id = self.queue(risk, self.event(risk, from_status="PREALERT"))
        self.store.pause("group-test", "PROVIDER_LIMITED")
        result = dispatch_pending(self.store, self.notifier, NOW.isoformat())
        self.assertEqual([r["id"] for r in result if r["status"] == "accepted"], [risk_id])
        self.assertEqual([r["reason_code"] for r in result if r["status"] == "expired"], ["PROVIDER_PAUSED"] * 2)
        self.assertEqual(self.notifier.send.call_count, 1)

    def test_zero_window_and_legacy_without_group_evidence_send_individually(self):
        a = self.grouped_signal("zero", version="unused-group")
        a["strategy_version"] = "live-test"
        b = self.grouped_signal("legacy")
        del b["evidence"]["notification_group"]
        self.queue(a)
        self.queue(b)
        result = dispatch_pending(self.store, self.notifier, NOW.isoformat())
        self.assertEqual(len(result), 2)
        self.assertEqual(self.notifier.send.call_count, 2)

    def test_missing_window_config_is_rejected_without_silent_defaults(self):
        signal = self.grouped_signal("missing-window")
        with self.store.connect() as db:
            config = self.store.version("group-test")
            del config["runtime"]["group_window_seconds"]
            db.execute("UPDATE versions SET config=? WHERE id='group-test'", (dumps(config),))
        with self.assertRaises(StoreError) as caught:
            self.queue(signal)
        self.assertEqual(caught.exception.code, "CONFIG_INCOMPLETE")
        self.assertEqual(self.store.notifications(), [])

    def test_group_timeout_marks_every_member_unknown_and_never_retries(self):
        self.queue(self.grouped_signal("timeout-a"))
        self.queue(self.grouped_signal("timeout-b"))
        self.notifier.send.side_effect = TimeoutError("private credential URL")
        result = dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=5)).isoformat())
        self.assertEqual(len(result), 2)
        self.assertTrue(all(r["status"] == "unknown" and not r["retryable"] for r in result))
        self.assertNotIn("credential", dumps(result))
        reopened = Store(self.store.path)
        self.assertEqual(dispatch_pending(reopened, self.notifier, (NOW + timedelta(seconds=35)).isoformat()), [])
        self.assertEqual(self.notifier.send.call_count, 1)

    def test_group_crash_recovery_is_atomic_and_preserves_request_members(self):
        ids = {self.queue(self.grouped_signal("crash-a")), self.queue(self.grouped_signal("crash-b"))}
        self.notifier.send.side_effect = SystemExit("injected crash after claim")
        with self.assertRaises(SystemExit):
            dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=5)).isoformat())
        rows = self.store.notifications()
        self.assertTrue(all(r["status"] == "sending" for r in rows))
        self.assertEqual({tuple(sorted(r["delivery_attempts"][0]["notification_ids"])) for r in rows}, {tuple(sorted(ids))})
        reopened = Store(self.store.path)
        self.assertEqual(recover_inflight(reopened), 2)
        self.assertTrue(all(r["status"] == "unknown" for r in reopened.notifications()))
        self.assertEqual(dispatch_pending(reopened, self.notifier, (NOW + timedelta(seconds=35)).isoformat()), [])

    def test_group_claim_failure_rolls_back_every_member_before_network(self):
        ids = sorted(self.queue(self.grouped_signal("claim-%s" % suffix)) for suffix in ("a", "b"))
        with self.store.connect() as db:
            db.execute("CREATE TRIGGER fail_claim BEFORE INSERT ON attempts WHEN NEW.notification_id='%s' "
                       "BEGIN SELECT RAISE(ABORT, 'injected second claim failure'); END" % ids[1])
        with self.assertRaises(sqlite3.IntegrityError):
            dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=5)).isoformat())
        rows = self.store.notifications()
        self.assertTrue(all(r["status"] == "pending" and r["attempts"] == 0 and not r["delivery_attempts"] for r in rows))
        self.notifier.send.assert_not_called()
        with self.store.connect() as db:
            db.execute("DROP TRIGGER fail_claim")
        result = dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=5)).isoformat())
        self.assertEqual(len(result), 2)
        self.assertEqual(self.notifier.send.call_count, 1)

    def test_group_result_write_failure_recovers_all_members_as_unknown(self):
        ids = sorted(self.queue(self.grouped_signal("result-%s" % suffix)) for suffix in ("a", "b"))
        with self.store.connect() as db:
            db.execute("CREATE TRIGGER fail_result BEFORE UPDATE OF status ON outbox "
                       "WHEN NEW.id='%s' AND NEW.status='accepted' "
                       "BEGIN SELECT RAISE(ABORT, 'injected second result failure'); END" % ids[1])
        with self.assertRaises(sqlite3.IntegrityError):
            dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=5)).isoformat())
        rows = self.store.notifications()
        self.assertTrue(all(r["status"] == "sending" and len(r["delivery_attempts"]) == 1 for r in rows))
        self.assertEqual(self.notifier.send.call_count, 1)
        reopened = Store(self.store.path)
        self.assertEqual(recover_inflight(reopened), 2)
        self.assertTrue(all(r["status"] == "unknown" for r in reopened.notifications()))
        self.assertEqual(dispatch_pending(reopened, self.notifier, (NOW + timedelta(seconds=35)).isoformat()), [])

    def test_retry_shrinks_original_group_and_does_not_absorb_new_arrivals(self):
        a, b = self.grouped_signal("retry-a"), self.grouped_signal("retry-b")
        self.queue(a)
        self.queue(b)
        self.notifier.send.return_value = {"status": "failed", "retryable": True}
        result = dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=5)).isoformat())
        self.assertTrue(all(r["next_attempt_at"] == (NOW + timedelta(seconds=35)).isoformat() for r in result))
        self.clock.return_value = (NOW + timedelta(seconds=30)).isoformat()
        self.queue(self.grouped_signal("new-arrival"))
        self.save_signal(dict(b, revision=2, status="INVALIDATED"))
        self.notifier.send.return_value = {"status": "accepted", "retryable": False}
        result = dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=35)).isoformat(), max_messages=1)
        self.assertEqual(sum(r["status"] == "accepted" for r in result), 1)
        text = self.notifier.send.call_args.args[0]["markdown"]["text"]
        self.assertIn(a["id"], text)
        self.assertNotIn(b["id"], text)
        self.assertNotIn("new-arrival", text)
        dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=35)).isoformat())
        self.assertEqual(self.notifier.send.call_count, 3)

    def test_group_message_size_splits_without_losing_or_repeating_members(self):
        ids = []
        for i in range(8):
            signal = self.grouped_signal("large-%d" % i, name="测" * 1000)
            ids.append(signal["id"])
            self.queue(signal)
        self.queue(self.grouped_signal("too-large", name="测" * 7000))
        result = dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=5)).isoformat())
        self.assertEqual(sum(r["status"] == "accepted" for r in result), 8)
        self.assertEqual([r["reason_code"] for r in result if r["status"] == "expired"], ["MESSAGE_TOO_LARGE"])
        self.assertGreater(self.notifier.send.call_count, 1)
        self.assertLess(self.notifier.send.call_count, 8)
        texts = [call.args[0]["markdown"]["text"] for call in self.notifier.send.call_args_list]
        for call in self.notifier.send.call_args_list:
            self.assertLessEqual(len(json.dumps(call.args[0], ensure_ascii=False).encode()), MAX_MESSAGE_BYTES)
        for signal_id in ids:
            self.assertEqual(sum(text.count(signal_id) for text in texts), 1)

    def test_channel_limit_counts_http_requests_not_aggregate_member_traces(self):
        for i in range(21):
            for suffix in ("a", "b"):
                self.queue(self.grouped_signal("quota-%02d-%s" % (i, suffix), group="quota-%02d" % i))
        result = dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=5)).isoformat(), max_messages=100)
        self.assertEqual(sum(r["status"] == "accepted" for r in result), 40)
        self.assertEqual(self.notifier.send.call_count, 20)
        reopened = Store(self.store.path)
        self.assertEqual(dispatch_pending(reopened, self.notifier, (NOW + timedelta(seconds=64)).isoformat()), [])
        result = dispatch_pending(reopened, self.notifier, (NOW + timedelta(seconds=65)).isoformat())
        self.assertEqual(len(result), 2)
        self.assertEqual(self.notifier.send.call_count, 21)

    def test_group_claim_blocks_same_signal_revision_overtaking_across_workers(self):
        a, b = self.grouped_signal("inflight-a"), self.grouped_signal("inflight-b")
        self.queue(a)
        self.queue(b)
        entered, finish = threading.Event(), threading.Event()
        def send(*args):
            self.store.log("GROUP_SEND", "transaction must already be committed")
            entered.set()
            finish.wait(5)
            return {"status": "accepted", "retryable": False}
        self.notifier.send.side_effect = send
        results, errors = [], []
        def dispatch():
            try:
                results.extend(dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=5)).isoformat(), max_messages=1))
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=dispatch)
        thread.start()
        self.assertTrue(entered.wait(5))
        try:
            newer = dict(a, revision=2, status="INVALIDATED", actionability="expired")
            newer_id = self.queue(newer, self.event(newer, from_status="PREALERT"))
            self.assertEqual(dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=5)).isoformat()), [])
        finally:
            finish.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.notifier.send.side_effect = None
        result = dispatch_pending(self.store, self.notifier, (NOW + timedelta(seconds=5)).isoformat())
        self.assertEqual(result[0]["id"], newer_id)
        self.assertEqual(self.notifier.send.call_count, 2)


if __name__ == "__main__":
    unittest.main()
