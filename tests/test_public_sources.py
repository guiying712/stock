from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError

from stockradar.contracts import load_json
from stockradar.minute_quality import minute_quality_report, validate_quality_plan
from stockradar.store import dumps
from stockradar.vendor_samples import collect_samples, compare_samples, prepare_samples, request_specs, validate_sample_plan


ROOT = Path(__file__).resolve().parent.parent


class Response(BytesIO):
    def __init__(self, body):
        super().__init__(body if isinstance(body, bytes) else json.dumps(body).encode())
        self.code, self.headers = 200, {}


class NoCredentialEnvironment(dict):
    def get(self, *args, **kwargs):
        raise AssertionError('Public probes must not read any account credential')


class PublicSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.sina_row = {'day':'2024-01-02 09:31:00','open':'10','high':'11','low':'9','close':'10.01','volume':'100','amount':'1000'}

    def tearDown(self):
        self.temp.cleanup()

    def plan(self, provider='sina_public', dataset=None):
        value=load_json(ROOT / ('configs/vendor-sample-'+provider.replace('_','-')+'.json'))
        value.update(id='synthetic-public-test', symbols=[{'symbol':'600000.SH','board':'MAIN'}],
                     datasets=[dataset or ('daily_bars' if provider=='tencent_public' else 'intraday')],
                     start_date='2024-01-02',end_date='2024-01-03',max_requests=1,
                     authorization={'confirmed':True,'reference':'synthetic-test-only'})
        return value

    def collect(self, body, plan=None, name='sample'):
        opener=Mock()
        opener.open.return_value=Response(body)
        report=collect_samples(plan or self.plan(), self.root/name, opener=opener, environ=NoCredentialEnvironment(), sleep=lambda _:None)
        return report, opener

    def bars(self, name='sample'):
        return [json.loads(line) for line in (self.root/name/'bars.jsonl').read_text().splitlines()]

    def east_minute(self, line='2024-01-02 09:31,10,10.01,11,9,100,1000,10'):
        return {'rc':0,'data':{'code':'600000','trends':[line]}}

    def tencent(self, day=None):
        return {'code':0,'data':{'sh600000':{'day':day if day is not None else [['2024-01-02','10','10.01','11','9','100']],
                                           'qt':{'sh600000':['not-a-historical-close','900']}}}}

    def test_fixed_https_requests_and_narrow_budgets(self):
        expected={'sina-public':3,'eastmoney-public':9,'tencent-public':3}
        hosts={'quotes.sina.cn','push2.eastmoney.com','push2his.eastmoney.com','40.push2.eastmoney.com',
               'datacenter-web.eastmoney.com','web.ifzq.gtimg.cn'}
        from urllib.parse import urlsplit
        for source,count in expected.items():
            value=load_json(ROOT / ('configs/vendor-sample-'+source+'.json'))
            specs=request_specs(validate_sample_plan(value))
            self.assertEqual(len(specs),count)
            self.assertFalse(value['authorization']['confirmed'])
            self.assertTrue(all(urlsplit(s['operation']).scheme=='https' and urlsplit(s['operation']).hostname in hosts for s in specs))
        value=self.plan(); value['endpoint']='https://example.invalid'
        with self.assertRaises(ValueError):
            validate_sample_plan(value)

    def test_public_preparation_and_collection_never_read_or_send_credentials(self):
        plan=self.plan()
        prepared=prepare_samples(plan,environ=NoCredentialEnvironment())
        self.assertFalse(prepared['credential_present'])
        self.assertNotIn('CREDENTIAL_MISSING',prepared['reason_codes'])
        result,opener=self.collect([self.sina_row],plan)
        req=opener.open.call_args[0][0]
        self.assertIsNone(req.data)
        self.assertIsNone(req.get_header('Authorization'))
        self.assertIsNone(req.get_header('X-api-key'))
        self.assertIsNone(req.get_header('Cookie'))
        self.assertEqual(result['sent_requests'],1)

    def test_unconfirmed_access_still_performs_zero_requests(self):
        plan=self.plan(); plan['authorization']={'confirmed':False,'reference':None}
        opener=Mock()
        result=collect_samples(plan,self.root/'blocked',opener=opener,environ=NoCredentialEnvironment())
        self.assertEqual(result['sent_requests'],0)
        opener.open.assert_not_called()
        self.assertIn('ACCESS_AUTHORIZATION_NOT_CONFIRMED',result['reason_codes'])

    def test_sina_literal_jsonp_preserves_raw_prices_and_unknown_units(self):
        row=deepcopy(self.sina_row); row['close']='10.000000000000000001'
        raw=b'/* public wrapper; never execute */\n=('+json.dumps([row]).encode()+b');'
        report,_=self.collect(raw)
        bar=self.bars()[0]
        self.assertEqual((self.root/'sample'/report['requests'][0]['raw_file']).read_bytes(),raw)
        self.assertEqual(bar['prices']['close'],'10.000000000000000001')
        self.assertEqual(bar['source_time'],'2024-01-02T01:31:00+00:00')
        self.assertIsNone(bar['event_time']); self.assertIsNone(bar['is_complete'])
        self.assertIsNone(bar['volume_shares']); self.assertIsNone(bar['amount_cny'])
        self.assertEqual(bar['symbol_basis'],'request_parameter_not_response_identity')
        self.assertFalse(report['strategy_input_ready'] or report['release_allowed'])

    def test_jsonp_executable_trailing_code_is_rejected_without_execution(self):
        raw=b'=([]);globalThis.steal()'
        report,_=self.collect(raw)
        self.assertIn('PUBLIC_JSONP_ENVELOPE_INVALID',report['reason_codes'])
        self.assertEqual(list((self.root/'sample'/'raw').iterdir()),[])

    def test_sina_missing_amount_is_unknown_not_inferred_from_volume(self):
        row=deepcopy(self.sina_row); row.pop('amount')
        report,_=self.collect([row])
        self.assertIsNone(self.bars()[0]['amount_raw'])
        self.assertIn('TURNOVER_UNKNOWN',report['reason_codes'])

    def test_recent_window_limit_is_explicit_without_false_truncation(self):
        report,_=self.collect([self.sina_row])
        self.assertEqual(report['status'],'sample_captured')
        self.assertIn('RECENT_WINDOW_NOT_DATE_RANGE',report['reason_codes'])
        report,_=self.collect([self.sina_row]*241,name='excess')
        self.assertIn('PUBLIC_WINDOW_LIMIT_EXCEEDED',report['reason_codes'])
        self.assertEqual(report['bar_count'],0)

    def test_eastmoney_zero_open_becomes_null_with_original_zero_preserved(self):
        plan=self.plan('eastmoney_public')
        report,_=self.collect(self.east_minute('2024-01-02 09:31,0,10.01,11,9,100,1000,10'),plan)
        bar=self.bars()[0]
        self.assertIsNone(bar['prices']['open'])
        self.assertEqual(bar['raw_price_values']['open'],'0')
        self.assertIn('SOURCE_ZERO_PRICE_AS_UNKNOWN',report['reason_codes'])
        self.assertIn('OHLC_UNKNOWN_OR_NONPOSITIVE',report['reason_codes'])

    def test_eastmoney_wrong_symbol_width_and_api_errors_have_fixed_reasons(self):
        plan=self.plan('eastmoney_public')
        cases=[({'rc':-1,'message':'vendor-private-text'},'PUBLIC_API_ERROR'),
               ({'rc':0,'data':{'code':'000001','trends':[]}},'RESPONSE_SCHEMA_INVALID'),
               (self.east_minute('2024-01-02 09:31,10,10'),'PUBLIC_BAR_WIDTH_INVALID'),
               (self.east_minute('2024-01-02 09:31,not-a-price,10,11,9,100,1000,10'),'RESPONSE_DATA_INVALID')]
        for index,(body,reason) in enumerate(cases):
            report,_=self.collect(body,plan,name=str(index))
            self.assertIn(reason,report['reason_codes'])
            self.assertNotIn('vendor-private-text',dumps(report))

    def test_eastmoney_quote_codes_keep_leading_zero_and_missing_symbols_visible(self):
        plan=self.plan('eastmoney_public','quotes')
        plan['symbols']=[{'symbol':'000001.SZ','board':'MAIN'},{'symbol':'600000.SH','board':'MAIN'}]
        report,_=self.collect({'rc':0,'data':{'diff':[{'f12':'000001','f13':0,'f14':'sample'}]}},plan)
        self.assertEqual(report['requests'][0]['missing_symbols'],['600000.SH'])
        self.assertEqual(report['requests'][0]['status'],'partial')
        snapshot=json.loads((self.root/'sample'/'snapshots.jsonl').read_text())
        self.assertEqual(snapshot['rows'][0]['symbol'],'000001.SZ')

    def test_current_memberships_are_not_historical_or_full_sector_denominators(self):
        plan=self.plan('eastmoney_public','memberships')
        report,_=self.collect({'rc':0,'data':{'diff':{'0':{'f12':'BK0001','f14':'sample-sector'}},'total':1}},plan)
        snapshot=json.loads((self.root/'sample'/'snapshots.jsonl').read_text())
        self.assertFalse(snapshot['historical_eligibility_established'])
        self.assertIsNone(snapshot['source_effective_from'])
        self.assertEqual(snapshot['scope'],'sample_instruments_not_complete_sector_universe')
        self.assertTrue(report['requests'][0]['page_info']['all_pages_verified'])

    def test_risk_first_page_incomplete_is_reported_without_automatic_pagination(self):
        plan=self.plan('eastmoney_public','risk_status')
        report,opener=self.collect({'rc':0,'data':{'diff':[{'f12':'600000','f13':1}],'total':2}},plan)
        self.assertEqual(opener.open.call_count,1)
        self.assertEqual(report['requests'][0]['status'],'partial')
        self.assertIn('PARTIAL_PUBLIC_SNAPSHOT',report['reason_codes'])
        self.assertFalse(report['requests'][0]['page_info']['all_pages_verified'])

    def test_suspension_page_scope_and_empty_result_are_explicit(self):
        plan=self.plan('eastmoney_public','suspensions')
        report,opener=self.collect({'success':True,'result':{'pages':2,'count':501,'data':[{'SECURITY_CODE':'600000'}]}},plan)
        self.assertEqual(opener.open.call_count,1)
        self.assertIn('PARTIAL_PUBLIC_SNAPSHOT',report['reason_codes'])
        report,_=self.collect({'success':True,'result':{'pages':0,'count':0,'data':[]}},plan,name='empty')
        self.assertEqual(report['requests'][0]['status'],'empty')
        self.assertFalse(report['strategy_input_ready'])

    def test_invalid_public_totals_cannot_claim_complete_snapshots(self):
        plan=self.plan('eastmoney_public','memberships')
        report,_=self.collect({'rc':0,'data':{'diff':[{'f12':'BK001'}],'total':0}},plan)
        self.assertIn('PUBLIC_PAGE_TOTAL_INVALID',report['reason_codes'])

    def test_tencent_only_uses_unadjusted_daily_and_does_not_splice_latest_quote(self):
        report,_=self.collect(self.tencent(),self.plan('tencent_public'))
        bar=self.bars()[0]
        self.assertEqual(bar['prices']['close'],'10.01')
        self.assertIsNone(bar['amount_raw'])
        self.assertIsNone(bar['amount_cny'])
        self.assertEqual(bar['adjustment'],'none')
        bad={'code':0,'data':{'sh600000':{'qfqday':[['2024-01-02','9','9','10','8','100']]}}}
        report,_=self.collect(bad,self.plan('tencent_public'),name='qfq')
        self.assertIn('UNADJUSTED_SERIES_MISSING',report['reason_codes'])

    def test_tencent_out_of_window_is_rejected_without_partial_projection(self):
        report,_=self.collect(self.tencent([['2024-01-01','10','10','11','9','100']]),self.plan('tencent_public'))
        self.assertEqual(report['bar_count'],0)
        self.assertIn('PERIOD_OUTSIDE_REQUESTED_WINDOW',report['reason_codes'])

    def test_permission_rate_limit_or_redirect_does_not_retry_or_switch_source(self):
        for status in (403,429,302):
            plan=self.plan(); plan['symbols'].append({'symbol':'688981.SH','board':'STAR'});plan['max_requests']=2
            opener=Mock();opener.open.side_effect=HTTPError('https://quotes.sina.cn',status,'private',{},BytesIO())
            report=collect_samples(plan,self.root/str(status),opener=opener,environ=NoCredentialEnvironment(),sleep=lambda _:None)
            self.assertEqual(opener.open.call_count,1)
            self.assertEqual(report['requests'][1]['status'],'skipped')

    def test_sensitive_public_responses_are_not_archived(self):
        report,_=self.collect({'token':'private-token'})
        self.assertIn('SENSITIVE_RESPONSE_SUPPRESSED',report['reason_codes'])
        self.assertEqual(list((self.root/'sample'/'raw').iterdir()),[])
        self.assertNotIn('private-token',dumps(report))

    def test_public_jsonp_is_reparsed_by_minute_quality_with_unknown_semantics(self):
        report,_=self.collect(b'=('+json.dumps([self.sina_row]).encode()+b');')
        value=load_json(ROOT/'configs/minute-quality-public-template.json')
        value.update(symbols=self.plan()['symbols']);value['profiles']=value['profiles'][:1]
        value['calendar']['dates']=['2024-01-02']
        validate_quality_plan(value)
        quality=minute_quality_report(value,[self.root/'sample'])
        self.assertEqual(quality['observation_count'],1)
        self.assertIsNone(quality['observations'][0]['is_complete'])
        self.assertIsNone(quality['observations'][0]['interval_end'])
        self.assertIsNone(quality['coverage'][0]['coverage'])
        self.assertFalse(quality['strategy_input_ready'] or quality['release_allowed'])

    def test_public_daily_comparison_remains_exact_with_unknown_turnover(self):
        self.collect(self.tencent(),self.plan('tencent_public'),name='tencent')
        plan=self.plan('tencent_public');plan.update(provider='tickflow_free',id='synthetic-tickflow',datasets=['daily_bars'])
        stamp=1704153600000
        body={'data':{'timestamp':[stamp],'open':['10'],'close':['10.01'],'high':['11'],'low':['9'],'volume':['100'],'amount':['1000']}}
        self.collect(body,plan,name='tickflow')
        report=compare_samples(self.root/'tencent',self.root/'tickflow')
        self.assertEqual(report['common_bars'],1)
        self.assertEqual(report['comparisons'][0]['differences'],[])
        self.assertEqual(report['comparisons'][0]['unknown_fields'],['volume_shares','amount_cny'])

