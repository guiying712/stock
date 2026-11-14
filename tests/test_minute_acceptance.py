from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from stockradar.__main__ import main
from stockradar.contracts import load_json
from stockradar.minute_acceptance import acceptance_plan, write_acceptance_plan
from stockradar.store import digest
from stockradar.vendor_samples import request_specs


ROOT = Path(__file__).resolve().parent.parent


class MinuteAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = load_json(ROOT / 'configs/minute-acceptance-template.json')

    def scheduled(self):
        self.plan['calendar'] = dict(version='synthetic-test', evidence='synthetic-only', is_trading_day=True)
        self.plan['capture_times'] = dict(latest='2026-11-06T02:01:05Z', session='2026-11-06T07:01:00Z',
                                          history='2026-11-07T00:30:00Z', daily='2026-11-07T00:31:00Z')

    def test_three_symbols_four_interfaces_ten_requests_zero_credentials_or_network(self):
        original = deepcopy(self.plan)
        with patch('stockradar.vendor_samples._credential', side_effect=AssertionError('credential access')), patch('urllib.request.build_opener', side_effect=AssertionError('network')):
            result = acceptance_plan(self.plan)
        self.assertEqual(self.plan, original)
        self.assertEqual((result['planned_requests'], result['sent_requests']), (10, 0))
        self.assertEqual([s['operation'] for s in result['stages']], ['rt_min', 'rt_min_daily', 'stk_mins', 'daily'])
        self.assertEqual(result['account_permissions'], 'not_tested')
        for stage in result['stages']:
            self.assertFalse(stage['sample_plan']['authorization']['confirmed'])
            self.assertEqual(stage['sample_plan']['start_date'], self.plan['trade_date'])
            self.assertEqual(len(request_specs(stage['sample_plan'])), stage['planned_requests'])
        self.assertEqual(result['output_hash'], digest({k: v for k, v in result.items() if k != 'output_hash'}))

    def test_scheduled_does_not_authorize_execute_or_claim_permissions(self):
        self.scheduled()
        result = acceptance_plan(self.plan)
        self.assertEqual(result['status'], 'planned_not_permission_verified')
        self.assertFalse(result['automatic_execution'] or result['schedule_enforced'] or result['credentials_accessed'])
        self.assertTrue(all(not stage['sample_plan']['authorization']['confirmed'] for stage in result['stages']))

    def test_budget_scope_dates_and_unknown_keys_fail_before_output(self):
        self.scheduled()
        mutations = [lambda p: p.update(max_requests=9), lambda p: p.update(token='must-not-accept-token'),
                     lambda p: p['calendar'].update(is_trading_day=False),
                     lambda p: p['calendar'].update(is_trading_day=True, evidence=None),
                     lambda p: p['capture_times'].update(latest='2026-11-05T02:00:00Z'),
                     lambda p: p['capture_times'].update(session='2026-11-06T01:00:00Z'),
                     lambda p: p['capture_times'].update(history='2026-11-06T08:00:00Z'),
                     lambda p: p['capture_times'].update(daily='2026-11-06T08:00:00Z'),
                     lambda p: p['capture_times'].update(latest='2026-11-06T10:00:00'),
                     lambda p: p['symbols'].append(dict(symbol='000001.SZ', board='MAIN')),
                     lambda p: p.update(symbols=None)]
        for mutation in mutations:
            value = deepcopy(self.plan)
            mutation(value)
            out = self.root / 'invalid'
            with self.subTest(plan=value), self.assertRaises(ValueError):
                write_acceptance_plan(value, out)
            self.assertFalse(out.exists())

    def test_shanghai_day_and_missing_schedule_stay_explicit(self):
        self.scheduled()
        # UTC previous date is already the target date in Shanghai; no host timezone.
        self.plan['capture_times']['latest'] = '2026-11-05T23:59:00Z'
        self.assertEqual(acceptance_plan(self.plan)['status'], 'planned_not_permission_verified')
        self.plan['capture_times']['session'] = None
        result = acceptance_plan(self.plan)
        self.assertEqual(result['status'], 'needs_schedule_or_calendar')
        self.assertIn('CAPTURE_TIME_MISSING_SESSION', result['reason_codes'])

    def test_one_stock_budget_is_four_and_files_remain_private_unapproved(self):
        self.plan['symbols'] = self.plan['symbols'][:1]
        self.plan['max_requests'] = 4
        out = self.root / 'first'
        result = write_acceptance_plan(self.plan, out)
        self.assertEqual(result['planned_requests'], 4)
        self.assertEqual({p.name for p in out.iterdir()}, {'latest.json', 'session.json', 'history.json', 'daily.json', 'report.json'})
        self.assertEqual(out.stat().st_mode & 0o777, 0o700)
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in out.iterdir()))
        before = {p.name: p.read_bytes() for p in out.iterdir()}
        with self.assertRaises(FileExistsError):
            write_acceptance_plan(self.plan, out)
        self.assertEqual(before, {p.name: p.read_bytes() for p in out.iterdir()})

    def test_cli_is_offline_and_never_creates_application(self):
        out = self.root / 'cli'
        with patch('stockradar.service.Application', side_effect=AssertionError('database')), patch('stockradar.vendor_samples._credential', side_effect=AssertionError('credentials')), patch('urllib.request.build_opener', side_effect=AssertionError('network')), redirect_stdout(StringIO()):
            main(['minute-acceptance-plan', '--plan', str(ROOT / 'configs/minute-acceptance-template.json'), '--output-dir', str(out)])
        self.assertEqual(load_json(out / 'report.json')['sent_requests'], 0)
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            main(['minute-acceptance-plan', '--plan', str(ROOT / 'configs/minute-acceptance-template.json'), '--output-dir', str(out)])
