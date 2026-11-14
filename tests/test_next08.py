from copy import deepcopy
from pathlib import Path
from decimal import Decimal
import json
import tempfile
import unittest

from stockradar.__main__ import replay_job
from stockradar.config import ConfigError, LEGACY_CONFIG_PATH, load_config, validate_config
from stockradar.engine import DataError, evaluate
from stockradar.fixtures import fixture_batches
from stockradar.providers import ProviderError, validate_batch
from stockradar.service import Application
from stockradar.store import StoreError, digest


class StarScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batches = fixture_batches()
        cls.legacy = fixture_batches(1)

    def setUp(self):
        self.config = load_config()
        self.star_id = 'SSE.688101'

    def run_to(self, count, config=None):
        state = None
        for batch in self.batches[:count]:
            result = evaluate(batch, config or self.config, state)
            state = result['state']
        return result

    def test_v2_requires_explicit_star_parameters_and_rejects_unknown_schemas(self):
        self.assertEqual(self.config['schema_version'], 2)
        self.assertEqual(self.config['preferences']['boards'], ['MAIN', 'CHINEXT', 'STAR'])
        for kind in ('missing_star', 'missing_field', 'unknown_field', 'missing_schema', 'unknown_schema', 'duplicate_board', 'bse', 'risk'):
            invalid = deepcopy(self.config)
            if kind == 'missing_star': del invalid['stock']['STAR']
            elif kind == 'missing_field': del invalid['stock']['STAR']['min_rvol']
            elif kind == 'unknown_field': invalid['stock']['STAR']['fallback'] = True
            elif kind == 'missing_schema': del invalid['schema_version']
            elif kind == 'unknown_schema': invalid['schema_version'] = 3
            elif kind == 'duplicate_board': invalid['preferences']['boards'].append('STAR')
            elif kind == 'bse': invalid['preferences']['boards'].append('BSE')
            elif kind == 'risk': invalid['preferences']['max_loss_fraction'] = .10001
            with self.subTest(kind=kind), self.assertRaises(ConfigError): validate_config(invalid)

    def test_legacy_config_data_and_all_strategy_outputs_remain_exact(self):
        expected = json.loads((Path(__file__).parent / 'fixtures/fixture-v1-hashes.json').read_text())
        config = load_config(LEGACY_CONFIG_PATH)
        outputs, state = [], None
        for batch in self.legacy:
            result = evaluate(batch, config, state)
            state = result['state']; outputs.append(result)
        self.assertEqual({'config_hash': digest(config), 'data_hash': digest(self.legacy), 'outputs_hash': digest(outputs)}, expected)
        self.assertFalse(set(b['snapshot_id'] for b in self.legacy) & set(b['snapshot_id'] for b in self.batches))
        self.assertNotEqual(config['id'], self.config['id'])

    def test_star_instrument_denominator_and_sector_comparable_members(self):
        result = self.run_to(2)
        self.assertEqual((result['quality']['expected_count'], result['quality']['valid_count'], result['quality']['excluded_count']), (15, 15, 6))
        stars = [s for s in result['signals'] if s['board'] == 'STAR']
        self.assertEqual(len(stars), 3)
        self.assertTrue(all(s['status'] == 'PREALERT' and s['actionability'] == 'eligible' for s in stars))
        sector = next(s for s in result['sectors'] if s['id'] == 'chips')
        self.assertEqual(sector['member_count'], 7)
        for signal in stars:
            self.assertIn(signal['instrument_id'], sector['members'])
            self.assertEqual(Decimal(signal['breakout_price']), Decimal({'688101': '10', '688102': '12', '688103': '14'}[signal['code']]))
            self.assertGreater(signal['evidence']['features']['stock_rvol'], self.config['stock']['STAR']['min_rvol'])
            self.assertIsNotNone(signal['evidence']['features']['stock_relative'])
        self.assertEqual(len(result['signals']), 7)

    def test_star_uses_its_own_thresholds_without_other_board_fallback(self):
        self.config['stock']['STAR']['min_rvol'] = 100
        result = self.run_to(2)
        self.assertTrue(all(s['status'] == 'DETECTED' and s['score'] is None for s in result['signals'] if s['board'] == 'STAR'))
        self.assertEqual(sum(s['status'] == 'PREALERT' for s in result['signals']), 4)
        rejected = [e for e in result['evaluations'] if e['instrument_id'].startswith('SSE.6881')]
        self.assertTrue(all('STOCK_VOLUME_LOW' in e['reason_codes'] for e in rejected))

    def test_star_risk_gate_and_frozen_episode_levels_survive_lifecycle(self):
        config = deepcopy(self.config); config['stock']['STAR']['invalidation_buffer_atr'] = 3
        filtered = self.run_to(2, config)
        rejected = [e for e in filtered['evaluations'] if e['instrument_id'].startswith('SSE.6881')]
        self.assertTrue(all('RISK_DISTANCE_EXCEEDED' in e['reason_codes'] and e['score'] is None for e in rejected))
        first, confirmed, extended, failed = [self.run_to(n) for n in (2, 3, 4, 8)]
        key = lambda r: next(s for s in r['signals'] if s['instrument_id'] == self.star_id)
        original = key(first)
        self.assertEqual((key(confirmed)['status'], key(extended)['actionability'], key(failed)['status']), ('CONFIRMED', 'extended', 'INVALIDATED'))
        for result in (confirmed, extended, failed):
            self.assertEqual(tuple(key(result)[k] for k in ('id', 'breakout_price', 'atr', 'invalidation_price')), tuple(original[k] for k in ('id', 'breakout_price', 'atr', 'invalidation_price')))

    def test_missing_star_quote_lowers_coverage_pauses_then_recovers_same_signal(self):
        before, missing, recovered = [self.run_to(n) for n in (5, 6, 7)]
        self.assertEqual(missing['quality']['missing_ids'], [self.star_id])
        self.assertAlmostEqual(missing['quality']['coverage'], 14 / 15)
        self.assertEqual(missing['market']['status'], 'UNKNOWN')
        self.assertTrue(all(s['actionability'] == 'paused' and s['status'] != 'INVALIDATED' for s in missing['signals']))
        self.assertEqual({s['id'] for s in before['signals']}, {s['id'] for s in recovered['signals']})
        self.assertEqual(recovered['quality']['coverage'], 1)

    def test_star_status_listing_history_and_liquidity_exclusions_are_explicit(self):
        for kind, expected in (('st', 'STATUS_ST'), ('suspended', 'STATUS_SUSPENDED'), ('delisting', 'STATUS_DELISTING'),
                               ('delisted', 'STATUS_DELISTED'), ('listing', 'NEW_LISTING'), ('history', 'HISTORY_INSUFFICIENT'), ('liquidity', 'LOW_LIQUIDITY')):
            batch = deepcopy(self.batches[1])
            item = next(i for i in batch['instruments'] if i['id'] == self.star_id)
            if kind in ('st', 'suspended', 'delisting', 'delisted'): item['status'] = kind
            elif kind == 'listing': item['listed_on'] = '2026-10-28'
            elif kind == 'history': batch['daily_bars'] = [b for b in batch['daily_bars'] if b['instrument_id'] != self.star_id]
            else:
                for row in batch['daily_bars']:
                    if row['instrument_id'] == self.star_id: row['amount_cny'] = '0'
            with self.subTest(kind=kind):
                result = evaluate(batch, self.config)
                excluded = next(i for i in result['quality']['excluded'] if i['instrument_id'] == self.star_id)
                self.assertEqual(excluded['reason_codes'], [expected])
                self.assertEqual(result['quality']['expected_count'], 14)
                self.assertFalse(any(s['instrument_id'] == self.star_id for s in result['signals']))

    def test_wrong_exchange_board_combinations_fail_both_boundaries(self):
        for exchange, board in (('SZSE', 'STAR'), ('SSE', 'CHINEXT'), ('BSE', 'MAIN')):
            batch = deepcopy(self.batches[0]); batch['instruments'][0].update(exchange=exchange, board=board)
            with self.subTest(exchange=exchange, board=board):
                with self.assertRaises(ProviderError): validate_batch(batch)
                with self.assertRaises(DataError): evaluate(batch, self.config)
        valid = self.run_to(1)
        self.assertIn('BOARD_EXCLUDED', next(x['reason_codes'] for x in valid['quality']['excluded'] if x['instrument_id'] == 'BSE.920001'))

    def test_old_running_version_is_retained_until_explicit_new_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / 'versions.sqlite3')
            legacy = load_config(LEGACY_CONFIG_PATH)
            app = Application(path, legacy, seed=False); app.scan(self.legacy[0])
            before = app.store.latest(legacy['id'])
            app.store.register_version(self.config)
            resumed = Application(path, seed=False)
            self.assertEqual(resumed.config, legacy)
            self.assertEqual(resumed.health()['boards'], ['MAIN', 'CHINEXT'])
            resumed.advance_demo()
            explicit = Application(path, self.config, seed=False); explicit.scan(self.batches[0])
            self.assertEqual(explicit.health()['boards'], ['MAIN', 'CHINEXT', 'STAR'])
            self.assertEqual(explicit.store.version(legacy['id']), legacy)
            with self.assertRaises(StoreError): explicit.store.register_version(dict(self.config, id=legacy['id']))
            self.assertEqual(before['quality']['expected_count'], 12)

    def test_fixture_replay_jobs_choose_data_version_from_saved_config(self):
        with tempfile.TemporaryDirectory() as temp:
            app = Application(str(Path(temp) / 'jobs.sqlite3'), seed=False)
            legacy = load_config(LEGACY_CONFIG_PATH); app.store.register_version(legacy)
            for config, count in ((legacy, 4), (self.config, 7)):
                job_id = config['id']; app.store.save_job(job_id, {'dataset_id': 'fixture', 'strategy_version': job_id})
                replay_job(app.store, job_id)
                job = app.store.job(job_id)
                self.assertEqual(job['status'], 'completed', job.get('error'))
                baseline = next(b for b in job['result']['baselines'] if b['id'] == 'early')
                self.assertEqual(baseline['signal_count'], count)
