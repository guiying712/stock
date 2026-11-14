from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch
from test_fuyao import Response, envelope
from stockradar.real_market import RealMarket
from stockradar.store import StoreError


class RealMarketTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        connections=SimpleNamespace(directory=self.root/'connections',environ={'FUYAO_API_KEY':'synthetic-test-key'},
            market_status=lambda _: {'authorization':{'confirmed':True}})
        self.feed=RealMarket(self.root/'market',connections,clock=lambda:datetime(2024,1,4,tzinfo=timezone.utc))
        self.value=dict(schema_version=1,mode='latest',symbols=['600000.SH'],access_confirmed=True)

    def capture(self):
        opener=Mock()
        opener.open.side_effect=[Response(envelope([dict(thscode='600000.SH',last_price='10.123456789',prev_price=10)],timestamp=1704326400000)),
            Response(envelope([dict(thscode='600000.SH',item=[dict(date_ms=1704211200000,open_price=10,high_price=11,low_price=9,close_price=10,volume=100,turnover=1000)])],interval='1d',adjust='none'))]
        result=self.feed.fetch(self.value,opener=opener,sleep=lambda _:None)
        self.assertEqual(opener.open.call_count,2)
        return result

    def test_real_projection_keeps_precision_unknown_event_time_and_daily(self):
        r=self.capture()
        self.assertEqual(r['groups'][0]['prices']['last_price'],'10.123456789')
        self.assertIsNone(r['groups'][0]['quote_event_time'])
        self.assertEqual(len(r['groups'][0]['daily']),1)
        self.assertFalse(r['strategy_input_ready'])
        with patch('urllib.request.build_opener',side_effect=AssertionError('GET must be local')):
            self.assertEqual(self.feed.describe()['capture']['output_hash'],r['capture']['output_hash'])

    def test_unconfirmed_access_is_zero_request(self):
        self.value['access_confirmed']=False
        opener=Mock()
        with self.assertRaises(StoreError): self.feed.fetch(self.value,opener=opener)
        opener.open.assert_not_called()

    def test_cooldown_and_missing_credential_preserve_existing(self):
        r=self.capture()
        with self.assertRaises(StoreError):self.feed.fetch(self.value)
        self.assertEqual(self.feed.describe()['capture']['output_hash'],r['capture']['output_hash'])

    def test_strict_scope_and_finite_prices(self):
        with self.assertRaises(ValueError):self.feed.plan(dict(self.value,extra=True))
        self.value['symbols']=['BAD']
        with self.assertRaises(ValueError):self.feed.plan(self.value)
