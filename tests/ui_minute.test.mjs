import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('../stockradar/static/minute-view.js',import.meta.url),'utf8');
const {minutePage,minuteResult,minutePayload,minuteFormDraft}=await import(`data:text/javascript,${encodeURIComponent(source)}`);
const e=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const h={e,datetime:value=>value||'未知',number:value=>value==null?'—':String(value),price:value=>String(value)};
const draft={mode:'session',symbols:'600519.SH,300750.SZ,688981.SH',start_date:'',end_date:'',access_confirmed:false};
const connection={market:[{id:'tushare',credential:{configured:true},authorization:{confirmed:true}}]};

test('minute screen describes account requirements and keeps keys out of the form',()=>{
  const html=minutePage({capture:null},null,{...draft,api_key:'synthetic-must-not-render'},null,false,'',h);
  assert.match(html,/待配置 Token/);
  assert.match(html,/A股分钟RT/);
  assert.match(html,/A股历史分钟/);
  assert.match(html,/value="fetch" disabled/);
  assert(!html.includes('synthetic-must-not-render'));
  assert(!html.includes('name="api_key"'));
  assert.match(html,/本次计划 3 次请求/);
});

test('explicit current and historical payloads preserve codes and do not include credentials',()=>{
  const fields=new Map(Object.entries({mode:{value:'latest'},symbols:{value:'000001.SZ， 600519.SH'},start_date:{value:'2026-11-02'},end_date:{value:'2026-11-04'},access_confirmed:{checked:true},api_key:{value:'synthetic-secret'}}));
  const form={elements:{namedItem:name=>fields.get(name)}};
  assert.deepEqual(minutePayload(form),{schema_version:1,mode:'latest',symbols:['000001.SZ','600519.SH'],start_date:null,end_date:null,access_confirmed:true});
  fields.get('mode').value='history';
  assert.equal(minutePayload(form).start_date,'2026-11-02');
  assert(!JSON.stringify(minuteFormDraft(form)).includes('synthetic-secret'));
});

test('zero-request preparation does not claim a verified minute permission',()=>{
  const preview={planned_requests:3,sent_requests:0,reason_codes:[]};
  const html=minutePage({capture:null},connection,{...draft,access_confirmed:true},preview,false,'',h);
  assert.match(html,/请求已准备，接口权限仍待实测/);
  assert.match(html,/实际 0 次/);
  assert.match(html,/获取分钟数据 · 3 次/);
  const blocked=minutePage({capture:null},connection,draft,{...preview,reason_codes:['CREDENTIAL_MISSING']},false,'',h);
  assert.match(blocked,/尚未配置 Tushare Token/);
});

test('vendor errors and raw numbers are escaped and unknown amounts never become zero',()=>{
  const data={capture:{status:'incomplete',dataset:'intraday',completed_at:'2026-11-06T07:01:00Z',bar_count:1,sent_requests:1,captured_responses:1,simulated:false,requests:[{status:'failed',symbol:'<img onerror=bad>',reason_code:'<svg onload=bad>',api_code:2002}]},groups:[{symbol:'600519.SH',total_rows:1,last_label:'2026-11-06T07:00:00Z',bars:[{label:'2026-11-06T15:00:00+08:00',prices:{open:'10',high:'11',low:'9',close:'<img onerror=bad>'},volume_shares:null,amount_cny:null,available_at:'2026-11-06T07:01:00Z',is_complete:null}],reason_counts:{}}]};
  const html=minuteResult(data,h);
  assert(!html.includes('<img'));
  assert(!html.includes('<svg onload'));
  assert.match(html,/&lt;img/);
  assert.match(html,/<td>—<\/td>/);
  assert.match(html,/时点待核验/);
  assert.match(html,/尚未送入策略/);
});

test('raw minute chart and unfinished attempt remain explicit',()=>{
  const row={label:'2026-11-06T15:00:00+08:00',prices:{open:'10',high:'11',low:'9',close:'10.5'},volume_shares:'100',amount_cny:'1010',available_at:'2026-11-06T07:01:00Z',is_complete:null};
  const data={attempt:{status:'unfinished'},capture:{dataset:'intraday',completed_at:'2026-11-06T07:01:00Z',bar_count:1,sent_requests:1,captured_responses:1,simulated:true,requests:[]},groups:[{symbol:'600519.SH',total_rows:1,last_label:row.label,bars:[row],reason_counts:{}}]};
  const html=minuteResult(data,h);
  assert.match(html,/上次获取没有完成记录/);
  assert.match(html,/模拟验收样本/);
  assert.match(html,/分钟原始标签图/);
  assert.match(html,/标签尚未确认为策略分钟结束时点/);
  data.groups[0].bars[0].prices.close='1e999999';
  assert(!minuteResult(data,h).includes('Infinity'));
});
