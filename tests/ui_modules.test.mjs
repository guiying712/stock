import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

const load = async name => import(`data:text/javascript,${encodeURIComponent(await readFile(new URL(`../stockradar/static/${name}`,import.meta.url),'utf8'))}`);
const {evidenceChart}=await load('evidence-chart.js');
const {studyResult}=await load('study-view.js');
const {sourceHealthPanel,studyCaseList}=await load('history-view.js');
const e=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const f={e,price:v=>v==null?'—':String(v),number:v=>v==null?'—':String(v),percent:v=>v==null?'—':`${v*100}%`,datetime:v=>String(v??'未知'),timeOnly:v=>String(v),human:v=>String(v),tag:(v,label)=>e(label??v),reason:v=>String(v),empty:v=>e(v),jsonDetails:v=>`<pre>${e(JSON.stringify(v))}</pre>`};

test('chart escapes source fields and preserves absent candles without fake values',()=>{
  const q={event_time:'2026-10-28T02:01:00Z',available_at:'2026-10-28T02:01:00Z',ingested_at:'2026-10-28T02:01:00Z',open:'10',high:'11',low:'9',close:'10.5',amount_cny:null,source:'<script>alert(1)</script>',revision:1};
  const chart={trading_date:'2026-10-28',simulated:true,levels:{breakout:'10',invalidation:'9',frozen_at:q.event_time},trigger:{candles:[q],events:[],as_of:q.event_time},latest:{candles:[],reason_counts:{MISSING:1}}};
  const html=evidenceChart(chart,f);
  assert(!html.includes('<script>'));
  assert(html.includes('&lt;script&gt;'));
  assert(html.includes('缺失行情保持未知'));
  assert(html.includes('累计成交额'));
  assert(!html.includes('NaN'));
  assert(!html.includes('Infinity'));
  chart.trigger.candles=[{...q,open:null}];
  assert(!evidenceChart(chart,f).includes('class="chart-up"'));
});

test('study compares the selected split and keeps unknown returns unknown',()=>{
  const cell={split:'test',delay_minutes:1,holding_days:5,exit_mode:'risk',eligible_denominator:4,total:6,status_counts:{purged:2,pending:4},closed_count:0,not_filled_count:0,net_return_mean:null,benchmark_excess:{mean:null,denominator:0},clusters:{cluster_count:0,interval_95:null}};
  const state={studyFilter:{},studyJob:{id:'<img onerror="bad">',status:'completed',result:{simulated:true,plan:{splits:[{name:'train'},{name:'validation'},{name:'test'}],reaction_delays_minutes:[0,1],holding_windows_days:[5,20],exit_modes:['fixed','risk']},profiles:[{id:'early',summaries:[cell]}],limitations:['<script>bad</script>'],parameter_freeze:{eligible:false}}}};
  const html=studyResult(state,f);
  assert.deepEqual(state.studyFilter,{split:'test',delay:1,horizon:5,exit:'risk'});
  assert(html.includes('正式参数冻结条件未通过'));
  assert(html.includes('4 / 6'));
  assert(html.includes('跨段剔除 2'));
  assert(html.includes('<td>—</td>'));
  assert(html.includes('未知（独立簇不足）'));
  assert(!html.includes('<img onerror'));
  assert(!html.includes('<script>'));
});

test('source health distinguishes unknown coverage from a measured zero and escapes evidence labels',()=>{
  const latest={provider:'tushare',dataset:'minute_quotes',operation:'<script>rt_min</script>',
    latest_status:'failed',status_counts:{failed:1},attempt_count:1,limited_count:1,recent:[],minute_quality:null};
  const data={items:[latest],capture_count:1};
  const unknown=sourceHealthPanel(data,'<img onerror=bad>',f);
  assert.match(unknown,/待核验日历与分钟口径/);
  assert.doesNotMatch(unknown,/0%|<script>|<img/);
  latest.minute_quality={coverage:0,usable_minutes:0,expected_minutes:2,report_hash:'saved'};
  assert.match(sourceHealthPanel(data,null,f),/0%（0 \/ 2）/);
});

test('legacy case keeps a signal identifier and leaves unavailable timing and returns unknown',()=>{
  const result={window:{delay_minutes:1,holding_days:5},simulated:true,failure_count:0,unresolved_count:1,output_hash:'saved',
    items:[{status:'pending',signal:null,signal_id:'legacy<signal>',reason_code:'<missing>',entry:null,exit:null}]};
  const html=studyCaseList(result,f);
  assert.match(html,/历史案例/);
  assert.match(html,/触发 未知 · 首次提醒 未知/);
  assert.match(html,/净收益 — · 超额 —/);
  assert.match(html,/legacy&lt;signal&gt;/);
  assert.match(html,/&lt;missing&gt;/);
  assert.doesNotMatch(html,/<signal>|<missing>|¥0/);
});
