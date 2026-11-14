import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

const source = (await readFile(new URL('../stockradar/static/app.js', import.meta.url), 'utf8'))
  .replace(/^import .*;\n/gm, '');
const loadUI = async name => import(`data:text/javascript,${encodeURIComponent(await readFile(new URL(`../stockradar/static/${name}`,import.meta.url),'utf8'))}`);
const {evidenceChart} = await loadUI('evidence-chart.js');
const {studyPanel,studyList,studyResult} = await loadUI('study-view.js');
const {connectionPage,connectionTabs,connectionPayload,connectionDraft} = await loadUI('connection-view.js');
const {minutePage,minutePayload,minuteFormDraft} = await loadUI('minute-view.js');
const {realMarketPanel} = await loadUI('real-market-view.js');
const {sourceHealthPanel,sectorTimeline,studyCardsPanel,studyCaseList} = await loadUI('history-view.js');
const {boardScope,setupPanel,strategyForm,strategyDraft,preferenceConfig} = await loadUI('setup-view.js');

// Exercise the actual renderers and refresh lifecycle without browser or network access.
// Layout, native input behavior and accessibility still require browser verification.
function workbench() {
  const nodes = new Map(), listeners = {};
  const document = {
    activeElement: null, body: {style: {}}, title: '',
    addEventListener: (type, listener) => {listeners[type] = listener;},
    querySelectorAll: () => [],
    querySelector: selector => node(selector),
    getElementById: id => nodes.get(`#${id}`) || null,
  };
  function node(selector) {
    if (!nodes.has(selector)) nodes.set(selector, {
      id: selector.startsWith('#') ? selector.slice(1) : '',
      hidden: selector === '#drawer', inert: false, dataset: {},
      innerHTML: '', textContent: '', disabled: false, isConnected: true, scrollLeft: 0,
      attributes: {}, style: {}, classList: {toggle() {}},
      contains: () => false, querySelectorAll: () => [],
      addEventListener() {},
      setAttribute(name, value) {this.attributes[name] = value;},
      removeAttribute(name) {delete this.attributes[name];},
      remove() {this.isConnected=false;nodes.delete(selector);},
      focus() {document.activeElement = this;},
    });
    return nodes.get(selector);
  }
  document.activeElement = document.body;
  const context = vm.createContext({
    document, sessionStorage: {getItem: () => '', setItem() {}, removeItem() {}},
    window: {addEventListener() {}, scrollTo() {}}, location: {hash: '#market'},
    setTimeout: () => 1, clearTimeout() {}, setInterval: () => 1, clearInterval() {},
    URLSearchParams, Intl, structuredClone, evidenceChart, studyPanel, studyList, studyResult,
    connectionPage, connectionTabs, connectionPayload, connectionDraft,
    minutePage, minutePayload, minuteFormDraft, realMarketPanel, sourceHealthPanel, sectorTimeline, studyCardsPanel, studyCaseList,
    boardScope, setupPanel, strategyForm, strategyDraft, preferenceConfig,
  });
  vm.runInContext(source, context);
  vm.runInContext('state.dataReady=true;state.signalsLoaded=true;',context);
  const run = code => vm.runInContext(code, context);
  return {node, nodes, listeners, document, run};
}

test('setup shows current strategy scope and the result of testing the current target', () => {
  const {run,node}=workbench();
  run(`state.token='synthetic';state.data.health={mode:'fixture',strategy_version:'run<old>',boards:['MAIN','STAR'],
    dingtalk_configured:true,dingtalk_last_test:{status:'unknown',at:'2026-11-13T04:00:00Z'}};
    state.data.connections={market:[{name:'Tushare',credential:{configured:true},authorization:{confirmed:true},last_test:{status:'reachable'}}]};
    location.hash='#setup';route();`);
  const html=node('#main-content').innerHTML;
  assert.match(html,/首次设置/);
  assert.match(html,/run&lt;old&gt;/);
  assert.match(html,/沪深主板 · 科创板/);
  assert.match(html,/结果未知/);
  assert.match(html,/核对群里是否已收到/);
  assert.match(html,/连接可达/);
  assert.match(html,/分钟权限按实际接口单独验收/);
});

test('common settings generate an independent replay draft and validate all three fields', async () => {
  for (const file of ['fixture.json','fixture-v1.json']) {
    const config=JSON.parse(await readFile(new URL(`../stockradar/${file}`,import.meta.url),'utf8'));
    const draft={...strategyDraft(config),alertStage:'confirmed',dailyLimit:'0',riskPercent:'7.5'};
    const output=preferenceConfig(config,draft,'strategy-test');
    const expected=structuredClone(config);
    Object.assign(expected,{id:'strategy-test',mode:'replay',purpose:'experimental',status:'draft'});
    expected.research.alert_stage='confirmed';
    expected.lifecycle.daily_new_limit=0;
    expected.preferences.max_loss_fraction=.075;
    assert.deepEqual(output,expected);
    assert.notEqual(config.id,output.id);
    assert.throws(()=>preferenceConfig(config,{...draft,alertStage:'other'},'x'),/提醒时机/);
    for(const dailyLimit of ['', '1.5','-1','9007199254740992'])assert.throws(()=>preferenceConfig(config,{...draft,dailyLimit},'x'),/非负整数/);
    for(const riskPercent of ['', '0','10.01'])assert.throws(()=>preferenceConfig(config,{...draft,riskPercent},'x'),/不超过 10%/);
  }
});

test('minute route stays under settings and only reads the local API', async () => {
  const {run,node,document}=workbench(),settings=node('#nav-settings');settings.dataset.nav='settings';
  document.querySelectorAll=selector=>selector==='[data-nav]'?[settings]:[];
  run('var minuteCalls=[];api=async(path,options={})=>{minuteCalls.push({path,method:options.method||"GET"});return path==="minute-data"?{capture:null,groups:[]}:path==="health"?{mode:"fixture",boards:[]}:{};};state.token="synthetic-ui";state.connected=true;location.hash="#minute-data";route();');
  await Promise.resolve();
  assert.equal(settings.attributes['aria-current'],'page');
  assert.match(node('#main-content').innerHTML,/真实行情/);
  await run('refreshData({quiet:true})');
  const calls=JSON.parse(run('JSON.stringify(minuteCalls)'));
  assert(calls.some(call=>call.path==='minute-data'));
  assert(calls.some(call=>call.path==='real-market'));
  assert(calls.every(call=>call.method==='GET'));
  assert(!calls.some(call=>call.path.includes('/fetch')));
});

test('background repaint preserves an edited minute request and renders a separate strategy mode', () => {
  const {run,node}=workbench();
  node('#main-content').innerHTML='minute-request-in-progress';
  run('state.token="synthetic-ui";state.page="minute-data";state.minuteDirty=true;render()');
  assert.equal(node('#main-content').innerHTML,'minute-request-in-progress');
  run('state.minuteDirty=false;state.data.health={mode:"fixture"};state.data.minutes={capture:null,groups:[]}');
  const html=run('renderMinutes()');
  assert.match(html,/策略运行模式：离线模拟/);
  assert.match(html,/尚无 Tushare 分钟记录/);
  assert.match(html,/href="#minute-data" aria-current="page"/);
});

test('mode banner distinguishes the data timestamp from the current clock and escapes invalid values', () => {
  const {run} = workbench();
  run('state.data.health={mode:"fixture",as_of:"2026-10-28T02:01:00Z"}');
  const html = run('modeBanner()');
  assert.match(html, /离线模拟/);
  assert.match(html, /行情时点/);
  assert.match(html, /2026\/10\/28 10:01:00/);
  assert.match(html, /不是真实行情/);
  assert.match(html, /真实机会推送未启用/);
  run('state.data.health.as_of="<img src=x onerror=bad>"');
  assert.match(run('modeBanner()'), /&lt;img/);
  assert(!run('modeBanner()').includes('<img'));
  run('state.data.health.as_of=null');
  assert.match(run('modeBanner()'), /尚无记录/);
});

test('connection pages escape configuration and do not render any saved or draft key', () => {
  const {run}=workbench();
  run(`state.page='models';state.data.connections={market:[],model:{id:'model',name:'兼容模型',revision:'new',base_url:'https://example.invalid/v1',model:'<script>bad</script>',timeout_seconds:15,credential:{configured:true,source:'local_file',local_key_saved:true}}};state.connectionDrafts={model:{base_url:'https://example.invalid/v1',model:'<img onerror=bad>',timeout_seconds:15,api_key:'synthetic-must-not-render'}};`);
  const html=run('renderConnections()');
  assert(!html.includes('<img'));
  assert(!html.includes('<script>'));
  assert(!html.includes('synthetic-must-not-render'));
  assert.match(html,/&lt;img/);
  assert.match(html,/type="password" autocomplete="new-password"/);
  assert.match(html,/不会提交生成请求/);
  assert.match(html,/href="#models" aria-current="page"/);
});

test('connection payload separates keep, replacement and clearing without retaining a key in drafts', () => {
  const fields=new Map(Object.entries({api_key:{value:'synthetic-new-key'},clear_key:{checked:false},base_url:{value:'https://example.invalid/v1'},model:{value:'test-model'},timeout_seconds:{value:'15'}}));
  const form={dataset:{revision:'new'},elements:{namedItem:name=>fields.get(name)}};
  assert.equal(connectionPayload(form,true).key_action,'replace');
  assert.equal(connectionPayload(form,true).api_key,'synthetic-new-key');
  assert(!JSON.stringify(connectionDraft(form,true)).includes('synthetic-new-key'));
  fields.get('api_key').value='';
  assert.equal(connectionPayload(form,true).key_action,'keep');
  fields.get('clear_key').checked=true;
  assert.equal(connectionPayload(form,true).key_action,'clear');
  assert.equal(connectionPayload(form,true).timeout_seconds,15);
});

test('refresh preserves an actively edited connection form and its unsaved password input', () => {
  const {run,node}=workbench();
  node('#connection-form').dataset.page='models';
  const main=node('#main-content');main.innerHTML='editing-form-with-new-password';
  run('state.token="synthetic-ui-test";state.page="models";state.connectionDirty=true;render()');
  assert.equal(main.innerHTML,'editing-form-with-new-password');
});

test('dedicated connection routes stay under settings navigation', () => {
  const {run,node,document}=workbench(), settings=node('#nav-settings');settings.dataset.nav='settings';
  document.querySelectorAll=selector=>selector==='[data-nav]'?[settings]:[];
  run('state.token="synthetic-ui-test";location.hash="#market-api";route()');
  assert.equal(run('state.page'),'market-api');
  assert.equal(settings.attributes['aria-current'],'page');
  assert.match(node('#main-content').innerHTML,/行情 API 配置/);
  assert.match(node('#main-content').innerHTML,/连接配置尚未读取/);
});

test('signals retain native table semantics, a keyboard button, escaped fields and unknown prices', () => {
  const {run} = workbench();
  const signal = {id: 'case-"<>', name: '<img src=x onerror=bad>', code: '000001',
    status: 'PREALERT', score: null, latest_price: null, trigger_price: '10.12',
    actionability: 'paused', trigger_time: '2026-10-28T02:01:00Z'};
  const html = run(`signalTable(${JSON.stringify([signal])})`);
  assert.match(html, /<caption class="sr-only">/);
  assert.equal((html.match(/scope="col"/g) || []).length, 7);
  assert(!/<tr[^>]*role="button"/.test(html));
  assert.match(html, /<button type="button" class="signal-open"/);
  assert.match(html, /aria-label="查看 &lt;img/);
  assert.match(html, /000001/);
  assert.match(html, /<td class="[^"]*\bmono\b[^"]*">—<div class="cell-secondary">触发 10.12/);
  assert(!html.includes('<img'));
  assert(!/NaN|Infinity/.test(html));
});

test('unknown or falling market states never inherit the upward status icon', () => {
  const {run} = workbench();
  for (const status of ['UNKNOWN', 'DOWN', 'HIGH_VOL', 'UP']) {
    run(`state.data={health:{},market:{status:${JSON.stringify(status)}}}`);
    const html = run('renderMarket()');
    const indicator = html.match(/<div class="market-indicator[^>]*>(.*?)<\/div>/)[0];
    assert.equal(indicator.includes(run('icons.arrowUp')), status === 'UP');
    if (status === 'UNKNOWN') {
      assert.match(indicator, /neutral/);
      assert.match(html, /新机会暂停/);
      assert.match(html, /stat-number">—/);
    }
    if (status === 'DOWN') assert.match(indicator, /danger/);
  }
});

test('unsubmitted search text survives refresh without silently changing the applied query', () => {
  const {run, listeners} = workbench();
  run('state.signalQuery="000001";state.signalStatus="PREALERT"');
  listeners.input({target: {id: 'signal-query', value: '科创"<待查>'}});
  const html = run('renderSignals()');
  assert.match(html, /value="科创&quot;&lt;待查&gt;"/);
  assert.equal(run('state.signalQuery'), '000001');
  assert.match(html, /data-filter="PREALERT" aria-pressed="true"/);
  assert.match(html, /data-filter="CONFIRMED" aria-pressed="false"/);
});

test('rerender restores the signal button and horizontal position without stealing external focus', () => {
  const {run, node, nodes, document} = workbench();
  run('state.token="synthetic-ui-test";state.page="signals"');
  const main = node('#main-content'), original = node('#signal-open-test');
  main.contains = target => target === original;
  document.activeElement = original;
  node('#signals-scroll').scrollLeft = 164;
  let markup, replacement, region;
  Object.defineProperty(main, 'innerHTML', {
    get: () => markup,
    set: value => {
      markup = value;
      replacement = {...original, focus() {document.activeElement = this;}};
      region = {scrollLeft: 0};
      nodes.set('#signal-open-test', replacement);
      nodes.set('#signals-scroll', region);
    },
  });
  run('render()');
  assert.equal(document.activeElement, replacement);
  assert.equal(region.scrollLeft, 164);
  document.activeElement = document.body;
  run('render()');
  assert.equal(document.activeElement, document.body);
});

test('a failed health refresh keeps cached data visible with a retry path', async () => {
  const {run, node} = workbench();
  run('state.token="synthetic-ui-test";state.connected=true;state.data.health={mode:"fixture"};api=async()=>{throw new Error("测试连接中断")};');
  await run('refreshData()');
  assert.equal(run('state.connected'), false);
  assert.match(node('#connection-status').innerHTML, /连接中断/);
  assert.match(node('#main-content').innerHTML, /上次成功结果/);
  assert.match(node('#main-content').innerHTML, /data-action="refresh"[^>]*>重试加载/);
  assert.match(node('#main-content').innerHTML, /role="alert"/);
});

test('disconnected navigation still matches the cached page and current-page semantics', () => {
  const {run, node, document} = workbench();
  const market = node('#nav-market'), settings = node('#nav-settings');
  market.dataset.nav = 'market';
  market.attributes['aria-current'] = 'page';
  settings.dataset.nav = 'settings';
  document.querySelectorAll = selector => selector === '[data-nav]' ? [market, settings] : [];
  run('state.token="synthetic-ui-test";state.connected=false;state.errors=["测试断线"];location.hash="#settings";route()');
  assert.equal(run('state.page'), 'settings');
  assert.equal(node('#breadcrumb-page').textContent, '设置与诊断');
  assert.equal(settings.attributes['aria-current'], 'page');
  assert.equal(market.attributes['aria-current'], undefined);
  assert.match(node('#main-content').innerHTML, /<h1 id="page-title">设置与诊断/);
  assert.match(node('#main-content').innerHTML, /测试断线/);
  assert.match(node('#main-content').innerHTML, /重试加载/);
});

test('drawer isolates background controls and restores a replaced opener by its stable id', () => {
  const {run, node, nodes, document} = workbench();
  const original = node('#signal-open-case');
  document.activeElement = original;
  run('showDrawer("测试详情","内容")');
  assert.equal(node('#application').inert, true);
  assert.match(node('#drawer').innerHTML, /id="drawer-title"/);
  assert.equal(document.body.style.overflow, 'hidden');
  original.isConnected = false;
  const replacement = {...original, isConnected: true, focus() {document.activeElement = this;}};
  nodes.set('#signal-open-case', replacement);
  run('closeDrawer()');
  assert.equal(node('#application').inert, false);
  assert.equal(node('#drawer').hidden, true);
  assert.equal(document.body.style.overflow, '');
  assert.equal(document.activeElement, replacement);
});

test('busy actions announce progress and restore the button after a rejected operation', async () => {
  const {run, node, document} = workbench();
  const button = node('#busy-button');
  button.innerHTML = '推进一分钟';
  button.dataset.busyLabel = '正在推进…';
  document.activeElement = button;
  const promise = run('action(document.activeElement,async()=>{await Promise.resolve();throw new Error("测试失败")})');
  assert.equal(button.disabled, true);
  assert.equal(button.attributes['aria-busy'], 'true');
  assert.equal(button.textContent, '正在推进…');
  await promise;
  assert.equal(button.disabled, false);
  assert.equal(button.attributes['aria-busy'], undefined);
  assert.equal(button.innerHTML, '推进一分钟');
  assert.equal(node('#toast').attributes.role, 'alert');
  assert.equal(node('#toast').textContent, '测试失败');
});

test('review tasks prioritize data and external delivery without mixing simulation records', () => {
  const {run} = workbench();
  run('state.data.health={updates_paused:true,warnings:["COVERAGE_LOW","SYNTHETIC_DATA_ONLY"],quality:{reason_codes:["COVERAGE_LOW"]},outbox:{unknown:2,failed:1},simulation_outbox:{unknown:99}};state.signals=[{id:"pause",name:"模拟股票",status:"CONFIRMED",actionability:"paused",reason_codes:["DATA_STALE"]},{id:"expired",status:"EXPIRED",actionability:"paused"}]');
  const tasks = JSON.parse(run('JSON.stringify(reviewTasks())'));
  assert.deepEqual(tasks.map(task=>task.kind), ['data','unknown','failed','signal']);
  assert.equal(tasks[0].detail, '有效行情覆盖不足');
  assert.equal(tasks[1].title, '外部投递结果未知 · 2 条');
  const html=run('reviewPanel()');
  assert(!html.includes('99'));
  assert.match(html,/另有 1 项/);
  assert.match(html,/当前已加载的 2 条记录/);
  assert.match(html,/避免重复发送/);
});

test('review tasks do not invent alerts for a synthetic but healthy slice or missing counts', () => {
  const {run} = workbench();
  run('state.data.health={updates_paused:false,warnings:["SYNTHETIC_DATA_ONLY"],quality:{status:"good"},outbox:{unknown:null,failed:null}};state.signals=[{id:"ok",status:"CONFIRMED",actionability:"eligible"}]');
  assert.equal(run('reviewPanel()'),'');
  assert.equal(run('reviewTasks().length'),0);
});

test('review rows escape names, unknown reason codes and object identifiers', () => {
  const {run} = workbench();
  run(`state.signals=${JSON.stringify([{id:'"<id>',name:'<img onerror=bad>',status:'PREALERT',actionability:'extended',reason_codes:['<script>bad</script>']}])}`);
  const html=run('reviewPanel()');
  assert(!html.includes('<img'));
  assert(!html.includes('<script>'));
  assert.match(html,/&lt;img/);
  assert.match(html,/&lt;script&gt;/);
  assert.match(html,/核对偏离范围/);
});

test('next steps distinguish terminal, paused, internal and unknown participation states', () => {
  const {run} = workbench();
  for(const [signal,title] of [[{status:'INVALIDATED',actionability:'paused'},'核对失效依据'],[{status:'EXPIRED'},'查看到期记录'],[{status:'DETECTED',actionability:'paused'},'查看观察依据'],[{status:'CONFIRMED'},'核对参与状态'],[{status:'CONFIRMED',actionability:'paused'},'核对暂停原因']]) {
    assert.equal(run(`signalNextStep(${JSON.stringify(signal)}).title`),title);
  }
  assert.match(run('participationTag({})'),/参与状态未知/);
  assert(!run('participationTag({})').includes('更新暂停'));
});

test('market places the object list before supporting sector panels and keeps sample scope visible', () => {
  const {run} = workbench();
  run('state.data.health={mode:"fixture",coverage:null};');
  const html=run('renderMarket()');
  assert(html.indexOf('机会与当前状态')<html.indexOf('热点雷达'));
  assert.match(html,/仅当前股票池/);
  assert.match(html,/stat-number">—/);
  assert.match(html,/顺序不代表投资优先级/);
});

test('detail keeps the reason near the decision and offers navigation instead of automatic feedback', () => {
  const {run} = workbench();
  const html=run('signalDetail({id:"test",status:"CONFIRMED",actionability:"paused",reason_codes:["DATA_STALE"],trigger_price:"10.12",latest_price:null,score:null})');
  assert(html.indexOf('行情已过期')<html.indexOf('触发参考价'));
  assert.match(html,/data-detail-target="signal-evidence"/);
  assert.match(html,/data-detail-target="signal-feedback"/);
  assert.match(html,/id="signal-evidence" tabindex="-1"/);
  assert.match(html,/仅保存反馈/);
  assert.match(html,/<strong>—<\/strong>/);
});

test('initial loading does not mix partial requests with zero market or signal counts', () => {
  const {run,node} = workbench();
  run('state.token="synthetic-ui-test";state.dataReady=false;state.signalsLoaded=false;state.signals=[{status:"PREALERT"}];render()');
  assert.equal(node('#main-content').attributes['aria-busy'],'true');
  assert.match(node('#main-content').innerHTML,/正在读取工作台/);
  assert(!node('#main-content').innerHTML.includes('stat-grid'));
  run('state.signals=[];state.data={health:{mode:"fixture"}}');
  const html=run('renderMarket()');
  assert.match(html,/信号数据尚未读取成功/);
  assert.match(html,/—<small>条信号/);
});

 test('real market consent and inflight capture survive background repaint',()=>{
  const {run,node}=workbench();node('#main-content').innerHTML='capture-form';
  run('state.token="synthetic";state.page="minute-data";state.realMarketConsent=true;render()');
  assert.equal(node('#main-content').innerHTML,'capture-form');
  run('state.realMarketConsent=false;state.realMarketBusy=true;render()');
  assert.equal(node('#main-content').innerHTML,'capture-form');
});

test('real market errors and symbols are escaped, unknown prices stay unknown',()=>{
  const {run}=workbench();
  run('state.data.realMarket={capture:{simulated:false,status:"incomplete",completed_at:null,batch_time:null,reception_age_seconds:600,sent_requests:2,bar_count:0,requests:[],output_hash:"<script>"},groups:[{symbol:"<img>",prices:{last_price:null},daily:[],quote_available:false}]};state.realMarketError="<img onerror=bad>"');
  const html=run('renderMinutes()');
  assert(!html.includes('<img'));assert(!html.includes('<script>'));
  assert.match(html,/&lt;img/);assert.match(html,/已保存旧记录/);assert.match(html,/逐股行情时间未知/);assert.match(html,/采集不完整/);assert.match(html,/<td>—<\/td>/);
});
