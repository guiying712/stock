from copy import deepcopy
from datetime import timedelta
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from threading import Event
import time
import unittest
from unittest.mock import Mock, patch
from contextlib import redirect_stderr

from stockradar.__main__ import main
from stockradar.config import load_config
from stockradar.contracts import load_json, utc
from stockradar.dispatcher import SimulationDispatcher, SimulationClock, dispatch_report, dispatcher_status, validate_dispatch_plan
from stockradar.fixtures import fixture_batches
from stockradar.notifier import SimulationNotifier
from stockradar.operations import operations_report
from stockradar.outbox import SIMULATION_CHANNEL, dispatch_pending, enqueue
from stockradar.service import Application
from stockradar.store import Store, StoreError, dumps
from stockradar.worker import run_worker, supervise_worker


class Clock:
    def __init__(self, value): self.value = utc(value)
    def __call__(self): return self.value.isoformat()
    def advance_to(self, value): self.value = max(self.value, utc(value))
    def add(self, seconds): self.value += timedelta(seconds=seconds)


class ControlledNotifier(SimulationNotifier):
    def __init__(self, outcomes):
        super().__init__(); self.outcomes = list(outcomes); self.calls = []
    def send(self, payload, key):
        self.calls.append((deepcopy(payload), key))
        outcome = self.outcomes.pop(0) if self.outcomes else 'accepted'
        if outcome == 'accepted': return super().send(payload, key)
        return {'status': 'failed' if outcome in ('retry', 'failed') else 'unknown', 'retryable': outcome == 'retry', 'receipt': None}


class DispatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.batches = fixture_batches()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.app = Application(str(self.root/'run.sqlite3'), seed=False)
        self.plan = load_json(Path(__file__).resolve().parents[1]/'configs/dispatcher-fixture.json')
        self.clock = Clock('2026-10-28T02:00:00Z'); self.wall = Clock('2026-10-29T16:00:00Z')
        for name in ('stockradar.outbox.now', 'stockradar.store.now'):
            p = patch(name, side_effect=self.wall); p.start(); self.addCleanup(p.stop)

    def dispatcher(self, **kwargs):
        return SimulationDispatcher(self.app.store, self.plan, clock=self.clock, wall_clock=self.wall, autostart=False, **kwargs)

    def scan(self, dispatcher, batch):
        r = self.app.scan(batch, simulation_delivery=dispatcher.delivery_for(batch['as_of']))
        dispatcher.after_scan(batch['as_of'], r.get('duplicate', False)); return r

    def seed(self, dispatcher):
        for b in self.batches[:2]: self.scan(dispatcher, b)

    def advance(self, seconds): self.clock.add(seconds); self.wall.add(seconds)

    def rows(self, channel=SIMULATION_CHANNEL):
        return [r for r in self.app.store.notifications() if r['channel']==channel]

    def wait_for(self, condition, timeout=3):
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            if condition(): return
            time.sleep(.01)
        self.fail('condition did not become true')

    def test_plan_is_complete_strict_and_never_selects_real_transport(self):
        for changes in ({'transport':'dingtalk'}, {'unknown':1}, {'schema_version':True}, {'clock_mode':[]},
                        {'simulation_start':None}, {'poll_interval_seconds':float('nan')},
                        {'shutdown_timeout_seconds':0}, {'max_messages_per_tick':0}, {'clock_mode':'wall'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): validate_dispatch_plan({**self.plan, **changes})
        self.assertEqual(validate_dispatch_plan(dict(self.plan, clock_mode='wall', simulation_start=None))['clock_mode'], 'wall')
        with self.assertRaises(StoreError): self.dispatcher(notifier=Mock())
        with self.assertRaises(StoreError): dispatch_pending(self.app.store, Mock(), self.clock(), channel=SIMULATION_CHANNEL)
        cfg=load_config(); cfg.update(id='live-blocked', purpose='experimental', mode='live_alert')
        self.app.store.register_version(cfg)
        with self.assertRaises(StoreError): SimulationDispatcher(self.app.store, dict(self.plan, strategy_version=cfg['id']))

    def test_report_without_runtime_is_read_only_and_no_platform_latency(self):
        self.assertIsNone(dispatcher_status(self.app.store, self.app.config['id']))
        report=dispatch_report(self.app.store,self.plan)
        self.assertFalse(report['release_allowed']); self.assertIsNone(report['platform_acceptance_p95_seconds'])
        with self.app.store.connect() as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='dispatcher_meta'").fetchone())

    def test_scan_signal_inbox_and_simulation_queue_commit_or_rollback_together(self):
        with self.dispatcher() as d:
            self.scan(d,self.batches[0])
            with self.app.store.connect() as db:
                db.execute("CREATE TRIGGER fail_sim BEFORE INSERT ON outbox WHEN NEW.channel='dingtalk_simulation' BEGIN SELECT RAISE(ABORT,'test'); END")
            with self.assertRaises(sqlite3.IntegrityError): self.scan(d,self.batches[1])
            with self.app.store.connect() as db:
                self.assertEqual([db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('scans','signals','events','outbox')],[1,0,0,0])
                self.assertEqual(db.execute('SELECT logical_at FROM dispatcher_watermarks').fetchone()[0], utc(self.batches[0]['as_of']).isoformat())
                db.execute('DROP TRIGGER fail_sim')
            self.scan(d,self.batches[1]); self.assertEqual(len(self.rows()),7); self.assertEqual(len(self.rows('inbox')),7)

    def test_duplicate_input_does_not_backfill_history_or_advance_clock(self):
        for b in self.batches[:2]: self.app.scan(b)
        with self.dispatcher() as d:
            before=self.clock()
            self.assertTrue(self.scan(d,self.batches[1])['duplicate'])
            self.assertEqual(self.clock(),before); self.assertEqual(self.rows(),[])
            self.assertEqual(len(self.rows('inbox')),7)

    def test_fixed_deadline_aggregation_retains_truthful_signal_evidence(self):
        notifier=ControlledNotifier([])
        with self.dispatcher(notifier=notifier) as d:
            self.seed(d); before=[deepcopy(r['payload']) for r in self.rows()]
            self.advance(4.999); self.assertEqual(d.tick(),[])
            self.advance(.001); result=d.tick()
            self.assertEqual(len(result),7); self.assertEqual(len(notifier.calls),1)
            self.assertTrue(notifier.calls[0][0]['markdown']['title'].startswith('【本地投递演练】'))
            self.assertEqual([r['payload'] for r in self.rows()],before)
            self.assertTrue(all(r['payload']['signal']['evidence']['simulated'] is True for r in self.rows()))
            self.assertTrue(all(r['response']['simulation'] and r['response']['receipt']['transport']=='local' for r in self.rows()))

    def test_lock_rejects_second_owner_before_any_recovery(self):
        with self.dispatcher() as d:
            self.seed(d)
            with self.app.store.connect() as db:
                first=self.rows()[0]['id']; db.execute("UPDATE outbox SET status='sending' WHERE id=?",(first,))
            with self.assertRaises(StoreError) as caught:
                with self.dispatcher(): pass
            self.assertEqual(caught.exception.code,'DISPATCHER_BUSY')
            self.assertEqual(next(r['status'] for r in self.rows() if r['id']==first),'sending')
        with self.dispatcher() as resumed:
            self.assertEqual(resumed.counts['recovered'],1)
            self.assertEqual(next(r['status'] for r in self.rows() if r['id']==first),'unknown')

    def test_restart_preserves_remaining_window_including_downtime(self):
        with self.dispatcher() as d:
            self.seed(d); ready={r['payload']['aggregation']['ready_at'] for r in self.rows()}; self.advance(2)
        self.wall.add(3)
        self.clock=Clock(self.plan['simulation_start'])
        with self.dispatcher() as d:
            self.assertGreaterEqual(utc(self.clock()),utc(next(iter(ready))))
            self.assertEqual({r['payload']['aggregation']['ready_at'] for r in self.rows()},ready)
            self.assertEqual(len(d.tick()),7)

    def test_committed_scan_clock_survives_before_after_scan_notification(self):
        with self.dispatcher() as d:
            for b in self.batches[:2]: self.app.scan(b,simulation_delivery=d.delivery_for(b['as_of']))
            # Emulate interruption before the producer's after_scan callback.
            self.assertLess(utc(self.clock()),utc(self.batches[1]['as_of']))
        self.clock=Clock(self.plan['simulation_start'])
        with self.dispatcher() as d:
            self.assertGreaterEqual(utc(self.clock()),utc(self.batches[1]['as_of']))
            self.advance(5); self.assertEqual(len(d.tick()),7)

    def test_future_simulation_rows_wait_instead_of_being_cancelled(self):
        with self.dispatcher() as d:
            self.seed(d)
            self.assertEqual(dispatch_pending(self.app.store,SimulationNotifier(),self.plan['simulation_start'],channel=SIMULATION_CHANNEL),[])
            self.assertEqual({r['status'] for r in self.rows()},{'pending'})

    def test_retry_backoff_and_attempt_watermark_survive_restart(self):
        first=ControlledNotifier(['retry'])
        with self.dispatcher(notifier=first) as d:
            self.seed(d); self.advance(5); d.tick()
            retry_at={r['next_attempt_at'] for r in self.rows()}
            self.advance(29); self.assertEqual(d.tick(),[])
        with self.dispatcher() as d:
            self.assertEqual({r['next_attempt_at'] for r in self.rows()},retry_at)
            self.advance(1); self.assertEqual(len(d.tick()),7)
        self.assertEqual(dispatch_report(self.app.store,self.plan)['simulation_request_count'],2)
        self.assertTrue(all(r['attempts']==2 for r in self.rows()))

    def test_unknown_and_permanent_failure_are_terminal_and_not_blindly_retried(self):
        for outcome in ('unknown','failed'):
            with self.subTest(outcome=outcome):
                # Independent DBs keep terminal outcomes and plan/clock evidence distinct.
                self.app=Application(str(self.root/(outcome+'.sqlite3')),seed=False)
                self.clock=Clock(self.plan['simulation_start'])
                fake=ControlledNotifier([outcome])
                with self.dispatcher(notifier=fake) as d:
                    self.seed(d); self.advance(5); d.tick(); self.assertEqual(d.pending_count(),0)
                with self.dispatcher() as d:
                    self.advance(60); self.assertEqual(d.tick(),[]); self.assertEqual(d.notifier.sent_count,0)
                self.assertEqual({r['status'] for r in self.rows()},{outcome})

    def test_simulation_isolated_from_external_channel_and_latency_counts(self):
        with patch('stockradar.notifier.DingTalkNotifier',side_effect=AssertionError('real notifier')), \
             patch('urllib.request.urlopen',side_effect=AssertionError('network')):
            with self.dispatcher() as d:
                self.seed(d); self.advance(5); d.tick()
        health=self.app.health()
        self.assertEqual(health['outbox']['accepted'],0); self.assertEqual(health['simulation_outbox']['accepted'],7)
        ops_plan=load_json(Path(__file__).resolve().parents[1]/'configs/operations-fixture.json')
        report=operations_report(self.app.store,ops_plan)
        gate=next(g for g in report['gates'] if g['id']=='platform_acceptance_p95')
        self.assertIsNone(gate['observed_seconds']); self.assertEqual(gate['request_count'],0)

    def test_immutable_plan_and_unknown_schema_never_recover_or_send(self):
        with self.dispatcher(): pass
        with self.assertRaises(StoreError) as caught:
            with SimulationDispatcher(self.app.store,dict(self.plan,poll_interval_seconds=.5),autostart=False): pass
        self.assertEqual(caught.exception.code,'PLAN_IMMUTABLE')
        with self.app.store.connect() as db: db.execute('UPDATE dispatcher_meta SET schema_version=99')
        with self.assertRaises(StoreError): dispatch_report(self.app.store,self.plan)
        with self.assertRaises(StoreError):
            with self.dispatcher(): pass
        with self.app.store.connect() as db: db.execute('UPDATE dispatcher_meta SET schema_version=1')
        with self.dispatcher(): pass

    def test_clock_domain_conflict_is_explicit_and_scan_rolls_back(self):
        with self.dispatcher() as d: self.seed(d)
        wall_plan=dict(self.plan,id='wall-plan',clock_mode='wall',simulation_start=None)
        with self.assertRaises(StoreError) as caught:
            with SimulationDispatcher(self.app.store,wall_plan,autostart=False): pass
        self.assertEqual(caught.exception.code,'CLOCK_DOMAIN_CONFLICT')
        with self.dispatcher():
            with self.assertRaises(StoreError):
                self.app.scan(self.batches[2],simulation_delivery={'plan_id':'wall-plan','clock_mode':'wall','enqueued_at':self.wall()})
        with self.app.store.connect() as db: self.assertEqual(db.execute('SELECT count(*) FROM scans').fetchone()[0],2)

    def test_background_scheduler_closes_window_without_another_scan(self):
        config=load_config(); config.update(id='short-window'); config['runtime']['group_window_seconds']=1
        self.app=Application(str(self.root/'timed.sqlite3'),config,seed=False)
        plan=dict(self.plan,id='short-window-plan',strategy_version=config['id'])
        with SimulationDispatcher(self.app.store,plan,wall_clock=self.wall) as d:
            self.seed(d)
            self.wait_for(lambda: len([r for r in self.rows() if r['status']=='accepted'])==7)
            self.assertEqual(d.notifier.sent_count,1)
        self.assertEqual(dispatcher_status(self.app.store,config['id'])['state'],'stopped')

    def test_stop_timeout_retains_owner_and_new_scans_are_not_blocked_by_send(self):
        started, release=Event(),Event()
        class Blocking(SimulationNotifier):
            def send(inner,payload,key): started.set(); release.wait(3); return super().send(payload,key)
        config=load_config();config.update(id='blocking');config['runtime']['group_window_seconds']=0
        self.app=Application(str(self.root/'blocked.sqlite3'),config,seed=False)
        self.plan=dict(self.plan,id='blocking-plan',strategy_version=config['id'],shutdown_timeout_seconds=.05)
        d=SimulationDispatcher(self.app.store,self.plan,notifier=Blocking(),wall_clock=self.wall); d.__enter__()
        try:
            self.seed(d); self.assertTrue(started.wait(2))
            self.scan(d,self.batches[2])  # sender is outside the scan transaction
            start=time.monotonic()
            with self.assertRaises(StoreError) as caught: d.close()
            self.assertEqual(caught.exception.code,'DISPATCHER_STOP_TIMEOUT'); self.assertLess(time.monotonic()-start,.5)
            with self.assertRaises(StoreError) as caught:
                with SimulationDispatcher(self.app.store,self.plan,autostart=False): pass
            self.assertEqual(caught.exception.code,'DISPATCHER_BUSY')
        finally:
            release.set(); self.wait_for(lambda:d._lock_file is None)
        self.assertEqual(d.notifier.sent_count,1)
        self.assertGreater(d.pending_count(),0)  # stop prevented any further claim
        with SimulationDispatcher(self.app.store,self.plan,autostart=False): pass

    def test_background_database_failure_is_visible_and_releases_owner(self):
        with self.dispatcher() as d:
            self.seed(d); self.advance(5)
        with self.app.store.connect() as db:
            db.execute("CREATE TRIGGER fail_claim BEFORE UPDATE OF status ON outbox WHEN NEW.status='sending' BEGIN SELECT RAISE(ABORT,'test'); END")
        d=SimulationDispatcher(self.app.store,self.plan,clock=self.clock,wall_clock=self.wall); d.__enter__()
        self.wait_for(lambda:d.error is not None)
        with self.assertRaises(StoreError): d.wait()
        self.wait_for(lambda:d._lock_file is None)
        self.assertEqual(dispatcher_status(self.app.store,self.app.config['id'])['state'],'failed')
        self.assertEqual({r['status'] for r in self.rows()},{'pending'})
        with self.app.store.connect() as db: db.execute('DROP TRIGGER fail_claim')
        with self.dispatcher() as resumed: self.assertEqual(len(resumed.tick()),7)

    def test_worker_integration_opt_in_and_normal_worker_does_not_enqueue_simulation(self):
        class Provider:
            def capabilities(inner): return {'full_market_verified':False}
            def iter_batches(inner): return iter(self.batches[:2])
        run_worker(self.app,input_path='fake',provider=Provider())
        self.assertEqual(self.rows(),[])
        self.app=Application(str(self.root/'integrated.sqlite3'),seed=False)
        plan=dict(self.plan,id='fast-drain',drain_timeout_seconds=.1)
        run_worker(self.app,input_path='fake',provider=Provider(),dispatch_plan=plan)
        self.assertEqual(len(self.rows()),7)
        self.assertTrue(all(r['payload']['signal']['simulated'] for r in self.rows()))
        self.assertEqual(dispatcher_status(self.app.store,self.app.config['id'])['state'],'stopped')

    def test_cli_requires_explicit_simulation_before_creating_any_database(self):
        target=self.root/'absent.sqlite3'
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            main(['dispatcher','--db',str(target),'--plan','unused'])
        self.assertEqual(caught.exception.code,2); self.assertFalse(target.exists())

    def test_supervisor_propagates_only_the_explicit_simulation_plan(self):
        path=self.root/'dispatch.json';path.write_text(dumps(self.plan))
        ops=load_json(Path(__file__).resolve().parents[1]/'configs/operations-fixture.json')
        child=Mock(pid=123456);child.poll.return_value=child.wait.return_value=0
        factory=Mock(return_value=child)
        supervise_worker(self.app.store,self.app.config,ops,input_path='unused',process_factory=factory,simulation_dispatch_plan=path)
        self.assertIn('--simulation-dispatch-plan',factory.call_args.args[0]); self.assertIn(str(path.resolve()),factory.call_args.args[0])

    def test_process_kill_releases_lock_and_recovers_claimed_batch_without_resending(self):
        with self.dispatcher() as d: self.seed(d); self.advance(5)
        plan_path=self.root/'plan.json'; plan_path.write_text(dumps(self.plan))
        marker=self.root/'claimed'
        script='''
import sys,time
from pathlib import Path
from stockradar.contracts import load_json
from stockradar.dispatcher import SimulationDispatcher,SimulationClock
from stockradar.notifier import SimulationNotifier
from stockradar.store import Store
class Blocked(SimulationNotifier):
    def send(self,payload,key):
        Path(sys.argv[3]).write_text('claimed')
        time.sleep(3600)
with SimulationDispatcher(Store(sys.argv[1]),load_json(sys.argv[2]),notifier=Blocked(),
                          clock=SimulationClock(sys.argv[4]),wall_clock=lambda:sys.argv[5]) as d:
    d.wait()
'''
        child=subprocess.Popen([sys.executable,'-c',script,self.app.store.path,str(plan_path),str(marker),self.clock(),self.wall()],
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            self.wait_for(marker.exists,timeout=5)
            self.assertEqual({r['status'] for r in self.rows()},{'sending'})
            with self.assertRaises(StoreError) as caught:
                with self.dispatcher(): pass
            self.assertEqual(caught.exception.code,'DISPATCHER_BUSY')
        finally:
            child.kill(); child.wait(timeout=5)
        with self.dispatcher() as d:
            self.assertEqual(d.counts['recovered'],7); self.assertEqual(d.tick(),[])
            self.assertEqual(d.notifier.sent_count,0)
        self.assertEqual({r['status'] for r in self.rows()},{'unknown'})
        with self.app.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM dispatcher_runs WHERE state='interrupted'").fetchone()[0],1)

    def test_recovery_is_scoped_to_selected_version_and_channel(self):
        with self.dispatcher() as d: self.seed(d)
        config=load_config(); config['id']='other-fixture'
        other=Application(self.app.store.path,config,seed=False)
        other_plan=dict(self.plan,id='other-plan',strategy_version=config['id'])
        with SimulationDispatcher(other.store,other_plan,clock=self.clock,wall_clock=self.wall,autostart=False) as d:
            for b in self.batches[:2]:
                other.scan(b,simulation_delivery=d.delivery_for(b['as_of'])); d.after_scan(b['as_of'])
        original=[r for r in self.rows() if r['payload']['signal']['strategy_version']==self.app.config['id']]
        with self.app.store.connect() as db:
            for row in original: enqueue(db,row['payload']['signal'],row['payload']['event'])
            db.execute("UPDATE outbox SET status='sending' WHERE channel!='inbox'")
        with self.dispatcher() as d: self.assertEqual(d.counts['recovered'],7)
        self.assertEqual({r['status'] for r in self.rows('dingtalk')},{'sending'})
        self.assertEqual({r['status'] for r in self.rows() if r['payload']['signal']['strategy_version']==config['id']},{'sending'})

    def test_scheduled_request_limit_resumes_at_exact_rolling_boundary(self):
        with self.dispatcher() as d:
            self.seed(d); self.advance(5)
            with self.app.store.connect() as db:
                for i in range(20):
                    db.execute('INSERT INTO attempts(notification_id,at,data) VALUES(?,?,?)',
                               (self.rows()[0]['id'],self.clock(),dumps({'phase':'started','channel':SIMULATION_CHANNEL,'delivery_id':'rate-'+str(i)})))
            self.assertEqual(d.tick(),[]); self.advance(59.999); self.assertEqual(d.tick(),[])
            self.advance(.001); self.assertEqual(len(d.tick()),7)
