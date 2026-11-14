import {evidenceChart} from './evidence-chart.js';
import {studyPanel, studyList, studyResult} from './study-view.js';
import {connectionPage, connectionTabs, connectionPayload, connectionDraft} from './connection-view.js';
import {minutePage, minutePayload, minuteFormDraft} from './minute-view.js';
import {realMarketPanel} from './real-market-view.js';
import {sourceHealthPanel, sectorTimeline, studyCardsPanel, studyCaseList} from './history-view.js';
import {boardScope, setupPanel, strategyForm, strategyDraft, preferenceConfig} from './setup-view.js';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const e = escapeHTML;
const icons = {
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.4"/><rect x="14" y="3" width="7" height="7" rx="1.4"/><rect x="3" y="14" width="7" height="7" rx="1.4"/><rect x="14" y="14" width="7" height="7" rx="1.4"/>',
  radar:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="m12 12 7-7"/><circle cx="12" cy="12" r="1"/>',
  flask:'<path d="M9 3h6m-5 0v7l-5.5 8.5A2 2 0 0 0 6.2 22h11.6a2 2 0 0 0 1.7-3.5L14 10V3M8 15h8"/><path d="m10 18 1 1m4-2h.01"/>',
  sliders:'<path d="M4 7h8m4 0h4M4 17h3m4 0h9"/><circle cx="14" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  refresh:'<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6.1 7a7 7 0 0 1 11.6-2L20 8M4 16l2.3 3A7 7 0 0 0 18 17"/>',
  bell:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
  logout:'<path d="M9 4H4v16h5m6-12 4 4-4 4m-6-4h10"/>',
  arrow:'<path d="M5 12h14m-5-5 5 5-5 5"/>',
  arrowUp:'<path d="m4 16 6-6 4 3 6-8m-6 0h6v6"/>',
  play:'<path d="m8 5 11 7-11 7z"/>',
  reset:'<path d="M4 5v5h5M4 10a8 8 0 1 1 1.5 8"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10h.01"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  signal:'<path d="M4 20v-5m5 5V9m6 11V5m5 15V2"/>',
  shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z"/><path d="m8 12 3 3 5-6"/>',
  close:'<path d="m6 6 12 12M6 18 18 6"/>',
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  download:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  eye:'<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7"/><circle cx="12" cy="12" r="3"/>',
  code:'<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18"/>'
};
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.info}</svg>`;
$$('[data-icon]').forEach(node => { node.innerHTML = icon(node.dataset.icon); });

const labels = {
  UP:'上涨环境', RANGE:'震荡环境', DOWN:'下跌环境', HIGH_VOL:'高波动', UNKNOWN:'状态未知',
  NORMAL:'常态', UNUSUAL:'异动', CANDIDATE:'启动候选', CONFIRMED:'已确认', FADING:'退潮',
  DETECTED:'内部观察', PREALERT:'启动预警', INVALIDATED:'已失效', EXPIRED:'已过期',
  eligible:'满足参与条件', extended:'当前已偏离', paused:'更新暂停', expired:'参与已过期',
  pending:'待处理', sending:'投递中', accepted:'平台已受理', failed:'失败', unknown:'结果未知',
  frozen:'已冻结', draft:'草稿', retired:'已停用', fixture:'离线模拟', replay:'历史回放', shadow:'真实影子', live_alert:'受控提醒',
  queued:'排队中', running:'运行中', completed:'已完成', succeeded:'已完成', finished:'已完成',
  watch:'观察', ignore:'忽略', bought:'已买入反馈', internal:'内置中心', inbox:'内置中心', dingtalk:'钉钉机器人', dingtalk_simulation:'本地投递演练',
  healthy:'正常', good:'正常', ok:'正常', stale:'过期', unverified:'待验证', degraded:'降级', unavailable:'不可用', configured:'已配置', unconfigured:'未配置', dingtalk_test:'钉钉连接测试'
};
const reasonLabels = {
  DATA_STALE:'行情已过期，暂停新的机会提醒', COVERAGE_LOW:'有效行情覆盖不足', HISTORY_INSUFFICIENT:'历史样本不足',
  CONFIG_INCOMPLETE:'策略参数尚未完整配置', PROVIDER_LIMITED:'数据源能力或速率受限', NO_ACTIONABLE_RANGE:'当前无有效参与区间',
  DELIVERY_UNKNOWN:'平台可能已接收，请核对投递结果', FUTURE_DATA:'数据在评估时点尚不可见', DATA_INCOMPLETE:'关键数据缺失',
  MARKET_UNKNOWN:'市场状态无法计算', MARKET_BLOCKED:'市场环境未通过策略门槛', SECTOR_NOT_READY:'板块尚未满足启动条件',
  BREAKOUT_DETECTED:'价格突破预先确定的整理上沿', BREAKOUT_CONFIRMED:'突破与板块确认条件成立', PRICE_INVALIDATED:'价格跌破冻结结构失效位',
  ENTRY_EXPIRED:'参与窗口已结束', SCORE_LOW:'评分低于当前版本提醒门槛', RISK_TOO_HIGH:'结构失效距离超过风险边界',
  DISTANCE_EXCEEDED:'价格已超出可参与区间', OUTSIDE_SESSION:'当前不属于连续竞价完成切片', NON_TRADING_DAY:'版本化日历标记为非交易日',
  SECTOR_FADING:'主关联板块进入退潮', DATA_RECOVERED:'新鲜度与覆盖恢复，重新积累确认', MARKET_CHANGED:'市场环境变化',
  LOW_LIQUIDITY:'流动性未达到门槛', SUSPENDED:'证券停牌', ST:'特别处理证券已排除', UNSUPPORTED_BOARD:'不在首版市场范围',
  PRICE_EXTENDED:'价格偏离参与区间', DUPLICATE:'重复输入已去重', SIMULATED:'合成样例数据', FIXTURE_ONLY:'仅用于功能验证',
  MARKET_GATE:'市场环境未通过新机会门槛', SECTOR_GATE:'板块尚未满足启动条件', RISK_DISTANCE_EXCEEDED:'结构失效距离超过风险边界',
  SECTOR_DATA_INCOMPLETE:'主关联板块数据不完整', SECTOR_BREADTH_LOW:'板块上涨广度不足', SECTOR_BREAKOUTS_LOW:'板块内同步突破数量不足',
  SECTOR_CONCENTRATED:'成交集中于少数成分股', SECTOR_EXTENDED:'板块前期涨幅超出实验门槛', SECTOR_MOMENTUM_LOW:'相对强度改善不足',
  SECTOR_RS_LOW:'板块相对强度不足', SECTOR_SAMPLE_LOW:'有效成分股数量不足', SECTOR_VOLUME_LOW:'板块同分钟量能不足',
  STOCK_RELATIVE_LOW:'个股相对板块强度不足', STOCK_VOLUME_LOW:'个股同分钟量能不足', STRUCTURE_BROKEN:'价格跌破冻结结构失效位',
  ENTRY_TTL_EXPIRED:'参与窗口已结束', EXISTING_EPISODE:'同一突破机会已记录，未重复新建', NO_NEW_BREAKOUT:'未出现新的价格上穿事件',
  BELOW_ENTRY_RANGE:'价格回落至参与下界以下', PARTICIPATION_RESTORED:'当前参与条件恢复', WAITING_CONFIRMATION:'等待确认切片',
  SCORE_BELOW_THRESHOLD:'评分未达到本版本提醒门槛', SCORE_INPUT_INCOMPLETE:'评分关键输入缺失', DAILY_NEW_LIMIT:'达到当日新机会额度',
  BOARD_EXCLUDED:'证券板块不在当前范围', NEW_LISTING:'上市历史不足', INSTRUMENT_NOT_VISIBLE:'证券状态在评估时点尚不可见',
  MEMBERSHIP_NOT_VISIBLE:'板块成员关系在评估时点尚不可见', NOT_YET_AVAILABLE:'数据在评估时点尚不可见', QUOTE_MISSING:'本切片行情缺失',
  INCOMPLETE_SLICE:'分钟切片尚未完成', SLICE_MISMATCH:'行情不属于当前切片', RANGE_TOO_WIDE:'历史整理区间过宽',
  DATA_QUALITY:'行情质量不达标', DATA_INVALID:'行情格式或内容无效', HISTORY_INVALID:'历史数据不符合契约',
  BENCHMARK_MISSING:'市场基准数据缺失', BENCHMARK_MISMATCH:'基准与配置不匹配', UNIT_MISMATCH:'数据单位不一致',
  ZERO_DENOMINATOR:'有效分母为零', LATE_CORRECTION:'迟到修正已记录，原快照保留', SYNTHETIC_DATA_ONLY:'当前仅为合成样例', NO_DATA:'尚未接收切片'
};
reasonLabels.CORPORATE_ACTION_REVIEW='复权基准发生变化，冻结原结构位并暂停参与，等待核验';
reasonLabels.HOTSPOT_BREAKOUT='热点启动突破规则触发';
const pageTitles = {market:'市场与热点',signals:'机会信号',research:'策略与研究',setup:'首次设置',settings:'设置与诊断','market-api':'行情 API 配置','minute-data':'真实行情',models:'大模型配置'};
const state = {
  token:sessionStorage.getItem('stockradar-token') || '', page:'market', connected:false, data:{}, errors:[],
  signalStatus:'', signalQuery:'', signalQueryDraft:'', signals:[], nextCursor:null, detailId:null, loading:false, polling:null, toastTimer:null,
  configDraft:null, drawerKind:null, refreshing:false, replayPolling:false, lastFocus:null, dataReady:false, signalsLoaded:false,
  studyJob:null, studyFilter:{}, studyDataset:'fixture', studyPlan:'fixture', studyPolling:new Set(),
  strategyPreferences:null, savedStrategyId:null, replayVersion:'',
  connectionProvider:'fuyao', connectionDrafts:{}, connectionDirty:false, historyErrors:{},
  minuteDraft:{mode:'session',symbols:'600519.SH,300750.SZ,688981.SH',start_date:'',end_date:'',access_confirmed:false},minutePreview:null,minuteDirty:false,minuteBusy:false,minuteError:''
};
function human(value) { return labels[value] || value || '未知'; }
function reason(value) { return reasonLabels[value] || (String(value||'').startsWith('STATUS_') ? `证券状态排除：${String(value).slice(7)}` : value) || '未提供原因'; }
function number(value, digits = 0) { if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return '—'; return Number(value).toLocaleString('zh-CN', {minimumFractionDigits:digits,maximumFractionDigits:digits}); }
function percent(value, digits = 1, signed = false) { if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—'; return `${signed && Number(value)>0 ? '+' : ''}${number(Number(value)*100,digits)}%`; }
function price(value) { return number(value,2); }
function datetime(value, full = false) { if (!value) return '尚无记录'; const date = new Date(value); if (!Number.isFinite(date.getTime())) return String(value); return new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',...(full ? {year:'numeric',month:'2-digit',day:'2-digit'} : {month:'2-digit',day:'2-digit'}),hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(date); }
function timeOnly(value) { if (!value) return '—'; const date = new Date(value); return Number.isFinite(date.getTime()) ? new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(date) : String(value); }
function list(value) { return Array.isArray(value) ? value : []; }
function items(value) { return Array.isArray(value) ? value : list(value?.items); }
function statusClass(value) { return ['INVALIDATED','DOWN','failed'].includes(value) ? 'danger' : ['PREALERT','CANDIDATE','UNUSUAL','FADING','HIGH_VOL','extended','unknown','degraded','paused','unconfigured','pending','sending','running','queued'].includes(value) ? 'warning' : ['EXPIRED','DETECTED','NORMAL','UNKNOWN','expired','draft','retired','unavailable','stale','unverified'].includes(value) ? 'neutral' : value === 'shadow' ? 'blue' : ''; }
function tag(value, text) { return `<span class="tag ${statusClass(value)}">${e(text || human(value))}</span>`; }
function empty(title, text = '') { return `<div class="empty-state">${icon('radar')}<strong>${e(title)}</strong>${e(text)}</div>`; }
function draftConfig(config) { const value=structuredClone(config||{}); if(value.id)value.id=`${value.id}-exp-${new Date().toISOString().replace(/\D/g,'').slice(0,14)}`;return JSON.stringify(value,null,2); }
function deliveryTag(notification) { const simulated={pending:'演练待处理',sending:'演练处理中',accepted:'模拟器已记录',failed:'模拟失败',unknown:'模拟结果未知',expired:'演练已取消'};return tag(notification.status, notification.channel==='dingtalk_simulation'?simulated[notification.status]:notification.channel==='inbox'&&notification.status==='accepted'?'已存入内置中心':undefined); }
function jsonDetails(data, title = '查看结构化记录') { return `<details class="json-details"><summary>${e(title)}</summary><pre>${e(JSON.stringify(data ?? {}, null, 2))}</pre></details>`; }
const presentation = {e,price,number,percent,datetime,timeOnly,human,reason,tag,jsonDetails,empty};
function modeBanner() {
  const mode = state.data.health?.mode || 'fixture';
  const message = ({fixture:'合成样例仅用于策略与工程验证，不是真实行情，不代表全市场。',replay:'回放结果用于研究，数据时点和研究局限请查看评估报告。',shadow:'保存真实行情计算结果，外部机会提醒暂未启用。'})[mode] || '信号仅供自行判断，软件不执行交易。';
  return `<div class="demo-banner" role="note">${icon('info')}<div class="mode-content"><div class="mode-heading"><strong class="mode-label ${mode==='shadow'?'blue':'warning'}">${e(human(mode))}</strong><span>行情时点 · ${e(datetime(state.data.health?.as_of,true))}</span></div><p>${e(message)}</p></div>${['fixture','replay','shadow'].includes(mode)?'<span class="banner-tail">真实机会推送未启用</span>':''}</div>`;
}
function pageHeading(title, subtitle, actions = '') { return `<div class="page-heading"><div><h1 id="page-title">${e(title)}</h1><p>${e(subtitle)}</p></div><div class="heading-actions">${actions}</div></div>`; }
function demoActions() { return state.data.health?.mode === 'fixture' ? `<button class="button" data-action="reset-demo" data-busy-label="正在重置…">${icon('reset')}重置演示</button><button class="button primary" data-action="advance-demo" data-busy-label="正在推进…">${icon('play')}推进一分钟</button>` : `<button class="button" data-action="refresh" data-busy-label="正在刷新…">${icon('refresh')}刷新数据</button>`; }
function signalNextStep(signal) {
  if(signal.status==='INVALIDATED')return {title:'核对失效依据',text:'查看冻结失效位与状态事件，再记录你的处理。'};
  if(signal.status==='EXPIRED'||signal.actionability==='expired')return {title:'查看到期记录',text:'核对参与期限与最近行情，保留本次机会的记录。'};
  if(signal.status==='DETECTED')return {title:'查看观察依据',text:'这是内部观察记录；查看尚未满足的条件与原始证据。'};
  if(!['eligible','paused','extended'].includes(signal.actionability))return {title:'核对参与状态',text:'参与状态未知，请核对最新行情、到期时间与原始记录。'};
  if(signal.actionability==='paused')return {title:'核对暂停原因',text:'当前参与状态为暂停；先核对数据质量、最近时点与保存的原因。'};
  if(signal.actionability==='extended')return {title:'核对偏离范围',text:'当前价格已偏离参与范围；对照冻结区间与最新参考价。'};
  return {title:'查看触发依据',text:'对照触发快照与最新行情，再记录观察、忽略或已买入反馈。'};
}
function participationTag(signal) { return ['eligible','paused','extended','expired'].includes(signal.actionability)?tag(signal.actionability):tag('UNKNOWN','参与状态未知'); }
function signalReasons(signal) { return list(signal.reason_codes).map(reason); }
function reviewTasks() {
  const health=state.data.health||{}, tasks=[], warnings=[...new Set([...list(health.warnings),...list(health.quality?.reason_codes)])].filter(code=>code!=='SYNTHETIC_DATA_ONLY');
  if(health.updates_paused===true||warnings.length)tasks.push({kind:'data',title:health.updates_paused?'数据更新暂停':'数据质量需核对',detail:warnings.length?warnings.map(reason).join('；'):'暂停原因尚未提供，请核对数据诊断。',context:`行情时点 ${datetime(health.as_of,true)}`,label:'核对数据诊断',href:'#settings'});
  for(const [status,title,detail] of [['unknown','外部投递结果未知','平台可能已接收；先人工核对记录，避免重复发送。'],['failed','外部投递失败','查看失败响应与尝试记录，核对渠道和错误原因。']]) {
    const count=health.outbox?.[status];
    if(count!=null&&Number.isFinite(Number(count))&&Number(count)>0)tasks.push({kind:status,title:`${title} · ${number(count)} 条`,detail,context:'外部渠道记录 · 与信号状态独立',label:'核对投递记录',action:'notifications'});
  }
  if(['market','signals'].includes(state.page))for(const signal of state.signals.filter(s=>['PREALERT','CONFIRMED'].includes(s.status)&&['paused','extended'].includes(s.actionability))) {
    const step=signalNextStep(signal);
    tasks.push({kind:'signal',title:`${signal.name||signal.code||signal.instrument_id} · ${human(signal.actionability)}`,detail:signalReasons(signal)[0]||'当前原因未提供，请查看保存的快照与事件。',context:`${signal.code||signal.instrument_id||'代码未知'} · 最新行情 ${datetime(signal.latest_time,true)}`,label:step.title,signal:signal.id});
  }
  return tasks;
}
function reviewPanel() {
  const tasks=reviewTasks();if(!tasks.length)return '';
  return `<section class="panel review-panel" aria-labelledby="review-heading"><div class="review-header"><div><h2 id="review-heading">需要核对</h2><p>先核对数据与投递依赖，再查看暂停或偏离的活跃信号。</p></div><span class="tag warning">${tasks.length} 项</span></div><ul class="review-list">${tasks.slice(0,3).map(task=>`<li class="review-row"><span class="review-icon">${icon(task.kind==='data'?'shield':task.kind==='signal'?'radar':'bell')}</span><div class="review-object"><strong>${e(task.title)}</strong><span>${e(task.context)}</span></div><p>${e(task.detail)}</p>${task.href?`<a class="button" href="${task.href}">${e(task.label)}${icon('arrow')}</a>`:`<button class="button" ${task.signal?`data-signal="${e(task.signal)}"`:`data-action="${task.action}"`}>${e(task.label)}${icon('arrow')}</button>`}</li>`).join('')}</ul>${tasks.length>3?`<div class="review-footer">显示前3项，另有 ${tasks.length-3} 项。<a class="text-button" href="#signals">继续核对信号</a><a class="text-button" href="#settings">查看运行诊断</a></div>`:''}${['market','signals'].includes(state.page)?`<p class="review-scope">信号项仅来自当前已加载的 ${state.signals.length} 条记录；此处顺序用于核对，不是投资优先级。</p>`:''}</section>`;
}
function errorBanner() { return (state.errors.length ? `<div class="error-banner" role="alert">${icon('info')}<p>部分数据未能加载：${state.errors.map(item=>e(item)).join('；')}。<br>相关页面显示的是上次成功结果，请检查服务后刷新。</p><button class="button" data-action="refresh" data-busy-label="正在重试…">重试加载</button></div>` : '')+reviewPanel(); }

async function api(path, {method='GET',body,signal,raw=false} = {}) {
  const response = await fetch(`/api/v1/${path}`, {method,headers:{Authorization:`Bearer ${state.token}`,...(body !== undefined ? {'Content-Type':'application/json'} : {})},body:body === undefined ? undefined : JSON.stringify(body),cache:'no-store',signal});
  if(raw&&response.ok)return response.text();
  let payload;
  try { payload = await response.json(); } catch { payload = {}; }
  if (!response.ok) {
    const error = new Error(payload.error?.message || payload.message || `请求失败（HTTP ${response.status}）`);
    error.code = payload.error?.code || payload.code; error.status = response.status; error.details = payload.error?.details;
    if (response.status === 401 && state.connected) logout('访问令牌已失效，请重新连接。');
    throw error;
  }
  return payload;
}
function toast(message, error=false) { clearTimeout(state.toastTimer); const node=$('#toast'); node.setAttribute('role',error?'alert':'status');node.textContent=message;node.classList.toggle('error',error);node.hidden=false;state.toastTimer=setTimeout(()=>{node.hidden=true;},6000); }
function setConnection(connected) { state.connected=connected;$('#connection-status').innerHTML=`<span class="status-dot ${connected ? '' : 'red'}"></span>${connected?'服务已连接':'连接中断'}`; }
async function connect(token) {
  state.token=token.trim();
  const button=$('#login-form button'), label=button.innerHTML;button.disabled=true;button.setAttribute('aria-busy','true');button.textContent='正在连接…';$('#login-error').textContent='';$('#access-token').removeAttribute('aria-invalid');
  try { state.data.health=await api('health');state.dataReady=false;sessionStorage.setItem('stockradar-token',state.token);setConnection(true);$('#login').hidden=true;$('#application').hidden=false;$('#access-token').value='';route();await refreshData();startPolling(); }
  catch(error) { $('#login-error').textContent=error.status === 401 ? '令牌不正确，请复制终端中的完整访问令牌。' : error.message;if(error.status===401)$('#access-token').setAttribute('aria-invalid','true'); }
  finally { button.disabled=false;button.removeAttribute('aria-busy');button.innerHTML=label; }
}
function logout(message='') { clearInterval(state.polling);sessionStorage.removeItem('stockradar-token');state.token='';state.connected=false;state.dataReady=false;state.signalsLoaded=false;state.data={};state.historyErrors={};state.signals=[];state.detailId=null;state.configDraft=null;state.strategyPreferences=null;state.savedStrategyId=null;state.replayVersion='';state.connectionDrafts={};state.connectionDirty=false;state.minuteDraft={mode:'session',symbols:'600519.SH,300750.SZ,688981.SH',start_date:'',end_date:'',access_confirmed:false};state.minutePreview=null;state.minuteDirty=false;state.minuteBusy=false;state.minuteError='';$('#main-content').innerHTML='';closeDrawer();$('#application').hidden=true;$('#login').hidden=false;$('#login-error').textContent=message;$('#access-token').focus(); }
function startPolling() { clearInterval(state.polling);state.polling=setInterval(async()=>{if(document.hidden || !state.connected || state.loading || state.refreshing)return;await refreshData({quiet:true});},12000); }
async function refreshData({quiet=false}={}) {
  if (state.refreshing || !state.token) return;
  state.refreshing=true;
  const entries=[['health','health'],['market','market'],['sectors','sectors'],['notifications','notifications'],['versions','strategy-versions'],['replays','replays'],['diagnostics','diagnostics'],['studySources','study-sources'],['studies','studies'],['connections','connections']];
  if(state.page==='minute-data')entries.push(['minutes','minute-data']);
  if(state.page==='minute-data')entries.push(['realMarket','real-market']);
  const responses=await Promise.allSettled(entries.map(([,path])=>api(path)));
  if(!state.token){state.refreshing=false;return;}
  state.errors=[];
  responses.forEach((result,index)=>{if(result.status==='fulfilled')state.data[entries[index][0]]=result.value;else state.errors.push(`${({health:'运行健康',market:'市场状态',sectors:'板块',notifications:'通知',versions:'参数版本',replays:'回放',diagnostics:'诊断',studySources:'研究数据与计划',studies:'成本研究',connections:'连接配置',minutes:'分钟记录'})[entries[index][0]]}：${result.reason.message}`);});
  setConnection(responses[0].status==='fulfilled');
  try { if(!quiet || state.page==='market' || state.page==='signals') await loadSignals(false,false); }catch(error){state.errors.push(`信号：${error.message}`);}
  state.dataReady=true;
  const health=state.data.health||{};$('#sidebar-mode').textContent=human(health.mode||'fixture');$('#sidebar-scope').textContent=boardScope(health.boards);$('#nav-signal-count').textContent=state.signalsLoaded?String(state.signals.filter(signal=>['PREALERT','CONFIRMED'].includes(signal.status)).length):'—';$('#notification-dot').hidden=!items(state.data.notifications).some(item=>['pending','failed','unknown'].includes(item.status));
  const editingSearch=document.activeElement?.id==='signal-query';
  if(!quiet || (['market','signals','setup','settings','minute-data'].includes(state.page)&&!editingSearch)) render();
  if(quiet && state.page==='research') { renderReplayList(); renderStudies(false); }
  if(state.drawerKind==='signal' && state.detailId) {
    if(!quiet) await openSignal(state.detailId);
    else {
      const detailId=state.detailId;
      try {const signal=await api(`signals/${encodeURIComponent(detailId)}`);if(state.detailId===detailId&&state.drawerKind==='signal'){
        const content=$('.drawer-content',$('#drawer'));const scroll=$('#drawer').scrollTop;
        if(content){const expanded=$$('details',content).map(item=>item.open);const focused=document.activeElement?.dataset?.feedback,focusedId=content.contains(document.activeElement)?document.activeElement.id:null;
          const horizontal=$$('.chart-scroll,.signal-table-wrap',content).map(item=>item.scrollLeft);
          const focusedChart=$$('.chart-scroll',content).indexOf(document.activeElement),focusedSummary=$$('summary',content).indexOf(document.activeElement);
          content.innerHTML=signalDetail(signal);$$('details',content).forEach((item,index)=>{item.open=Boolean(expanded[index]);});
          $$('.chart-scroll,.signal-table-wrap',content).forEach((item,index)=>{item.scrollLeft=horizontal[index]||0;});
          if(focused)$(`[data-feedback="${focused}"]`,content)?.focus({preventScroll:true});
          else if(focusedChart>=0)$$('.chart-scroll',content)[focusedChart]?.focus({preventScroll:true});
          else if(focusedSummary>=0)$$('summary',content)[focusedSummary]?.focus({preventScroll:true});
          else if(focusedId)document.getElementById(focusedId)?.focus({preventScroll:true});
          $('#drawer').scrollTop=scroll;}
      }}catch(error){toast(`详情更新失败：${error.message}`,true);}
    }
  }
  state.refreshing=false;
}
async function loadSignals(append=false, rerender=true) {
  const query=new URLSearchParams({limit:'50'});if(state.page==='signals'&&state.signalStatus)query.set('status',state.signalStatus);if(state.page==='signals'&&state.signalQuery)query.set('q',state.signalQuery);if(append&&state.nextCursor)query.set('cursor',state.nextCursor);
  const response=await api(`signals?${query}`);state.signals=append?[...state.signals,...items(response)]:items(response);state.signalsLoaded=true;state.nextCursor=response.next_cursor||null;
  if(rerender)render();
}
function route() {
  const previousPage=state.page;
  const hash=location.hash.slice(1);const [page,detail]=hash.split('/');state.page=Object.hasOwn ? (Object.hasOwn(pageTitles,page)?page:'market') : (pageTitles[page]?page:'market');
  if(!state.token || $('#application').hidden)return;
  if(previousPage!==state.page){state.connectionDirty=false;state.minuteDirty=false;}
  $$('[data-nav]').forEach(link=>{const active=link.dataset.nav===(['setup','market-api','models','minute-data'].includes(state.page)?'settings':state.page);link.classList.toggle('active',active);if(active)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');});$('#breadcrumb-page').textContent=pageTitles[state.page];document.title=`${pageTitles[state.page]} · 观势`;
  if(previousPage!==state.page)window.scrollTo(0,0);
  render();if(state.dataReady&&state.connected&&['market','signals'].includes(state.page))loadSignals().catch(error=>toast(error.message,true));if(page==='signals'&&detail)openSignal(decodeURIComponent(detail));else if(state.drawerKind==='signal')closeDrawer();
  if(page==='research'&&detail==='strategy-preferences')$('#strategy-preferences-title')?.focus();
  if(state.page==='minute-data'&&state.dataReady)api('minute-data').then(data=>{if(state.token){state.data.minutes=data;render();}}).catch(error=>toast(error.message,true));
  if(state.page==='minute-data'&&state.dataReady)api('real-market').then(data=>{if(state.token){state.data.realMarket=data;render();}}).catch(error=>toast(error.message,true));
}
function render() {
  if(!state.token || $('#application').hidden)return;
  const container=$('#main-content');container.setAttribute('aria-busy',String(!state.dataReady));
  if(!state.dataReady){container.innerHTML='<div class="workspace-loading" role="status"><strong>正在读取工作台</strong><p>正在核对市场、信号与运行诊断…</p></div>';return;}
  const main=$('#main-content'), focused=document.activeElement, inside=main.contains(focused);
  if(state.connectionDirty&&$('#connection-form')?.dataset.page===state.page)return;
  if(state.page==='minute-data'&&(state.realMarketBusy||state.realMarketConsent||(state.minuteDirty&&$('#minute-form'))))return;
  const scroll=$('#signals-scroll')?.scrollLeft||0;
  const focusId=inside?focused.id:null, filter=inside?focused.dataset?.filter:undefined;
  const content=({market:renderMarket,signals:renderSignals,research:renderResearch,setup:renderSetup,settings:renderSettings,'market-api':renderConnections,'minute-data':renderMinutes,models:renderConnections})[state.page]();
  main.innerHTML=content;
  const region=$('#signals-scroll');if(region)region.scrollLeft=scroll;
  if(focusId)document.getElementById(focusId)?.focus({preventScroll:true});
  else if(filter!==undefined)$$('[data-filter]',main).find(node=>node.dataset.filter===filter)?.focus({preventScroll:true});
  if(state.page==='research'&&location.hash==='#research/strategy-preferences'&&!inside){
    const title=$('#strategy-preferences-title');
    title?.focus();
    title?.scrollIntoView?.({block:'start'});
  }
}

function renderMarket() {
  const health=state.data.health||{}, market=state.data.market||{}, sectors=items(state.data.sectors), activeSectors=sectors.filter(sector=>['CANDIDATE','CONFIRMED'].includes(sector.status));
  const activeSignals=state.signals.filter(signal=>['PREALERT','CONFIRMED'].includes(signal.status));
  const coverage=health.coverage??health.quality?.coverage;const expected=health.expected_count??health.quality?.expected_count;const valid=health.valid_count??health.quality?.valid_count;
  const sortedSectors=[...sectors].sort((a,b)=>(Number(b.rs)||0)-(Number(a.rs)||0));
  const signalOverview=`<section class="panel signal-panel"><div class="panel-header"><div><h2>机会与当前状态</h2><p>状态、价格与原因对齐核对。</p></div><a class="text-button" href="#signals">查看全部信号 ${icon('arrow')}</a></div>${signalTable(state.signals.slice(0,6))}<div class="table-footer"><span>概览显示当前列表前6条 · 顺序不代表投资优先级</span><span>规则分不是上涨概率</span></div></section>`;
  return `${pageHeading('市场与热点','先看异常与当前信号，再核对市场、板块及个股依据。',demoActions())}${modeBanner()}${errorBanner()}
  <section class="stat-grid overview-strip" aria-label="市场概览">
  <div class="stat-card"><div class="stat-top"><span>市场环境</span>${icon('signal')}</div><div class="stat-number word ${['UP','RANGE'].includes(market.status)?'text-green':''}">${e(human(market.status||'UNKNOWN'))}</div><p class="stat-note">${['UP','RANGE'].includes(market.status)?'<span class="positive">通过市场门槛</span>':'新机会暂停'}</p></div>
  <div class="stat-card"><div class="stat-top"><span>启动热点</span>${icon('signal')}</div><div class="stat-number">${number(state.data.sectors==null?null:activeSectors.length)}<small>/ ${number(state.data.sectors==null?null:sectors.length)} 个板块</small></div><p class="stat-note">${number(state.data.sectors==null?null:sectors.filter(s=>s.status==='CONFIRMED').length)} 个已确认 · ${number(state.data.sectors==null?null:sectors.filter(s=>s.status==='CANDIDATE').length)} 个候选</p></div>
  <div class="stat-card"><div class="stat-top"><span>活跃机会</span>${icon('radar')}</div><div class="stat-number">${number(state.signalsLoaded?activeSignals.length:null)}<small>条信号</small></div><p class="stat-note">${number(state.signalsLoaded?activeSignals.filter(s=>s.actionability==='eligible').length:null)} 条当前满足参与条件</p></div>
  <div class="stat-card"><div class="stat-top"><span>样本有效行情覆盖</span>${icon('shield')}</div><div class="stat-number">${percent(coverage,0)}<small>${number(valid)} / ${number(expected)}</small></div><p class="stat-note">缺失 ${number(health.missing_count??(expected!=null&&valid!=null?expected-valid:null))} 个 · 仅当前股票池</p></div>
  </section>
  ${signalOverview}
  <div class="content-grid"><section class="panel"><div class="panel-header"><div><h2>热点雷达</h2><p>按相对强度排序 · 不以单只股票拉升替代广度</p></div><span class="panel-label">SECTOR PULSE</span></div><div class="panel-body">${sortedSectors.length?`<div class="sector-columns column-heading"><span>#</span><span>板块 / 状态</span><span>上涨广度</span><span>相对强度</span><span>量能比</span></div>${sortedSectors.map((sector,index)=>`<div class="sector-row clickable" data-sector="${e(sector.id)}" role="button" tabindex="0" aria-label="查看 ${e(sector.name||sector.id)} 板块证据"><span class="sector-rank">${String(index+1).padStart(2,'0')}</span><div><div class="sector-name">${e(sector.name||sector.id)}</div><div class="sector-sub">${tag(sector.status)} <span>${number(sector.member_count??sector.valid_count)} 只</span></div></div><div><span class="small muted">${percent(sector.breadth,0)}</span><div class="strength-bar-track"><div class="strength-bar" style="width:${Math.max(0,Math.min(100,Number(sector.breadth||0)*100))}%"></div></div></div><div class="sector-rs ${Number(sector.rs)<0?'negative':''}">${percent(sector.rs,2,true)}<div class="sector-sub">Δ ${percent(sector.delta_rs,2,true)}</div></div><div class="small mono" style="text-align:right">${number(sector.rvol,2)}<div class="sector-sub">倍</div></div></div>`).join('')}`:empty('等待板块数据','推进一个模拟切片后，将展示板块状态与证据。')}</div></section>
  <section class="panel market-panel"><div class="panel-header"><h2>市场温度</h2><span class="panel-label">${e(timeOnly(market.as_of))}</span></div><div class="panel-body"><div class="market-summary"><div><span class="column-heading">当前判断</span><div class="market-large-status">${e(human(market.status||'UNKNOWN'))}</div></div><div class="market-indicator ${statusClass(market.status||'UNKNOWN')}">${icon(market.status==='UP'?'arrowUp':market.status==='UNKNOWN'||!market.status?'info':'signal')}</div></div><div class="metric-line"><span class="key">全样本上涨广度</span><span class="value">${percent(market.breadth,1)}</span></div><div class="breadth-meter"><span style="width:${Math.max(0,Math.min(100,Number(market.breadth||0)*100))}%"></span></div><div class="metric-line"><span class="key">有效行情</span><span class="value">${number(valid)} / ${number(expected)}</span></div><div class="metric-line"><span class="key">最近成功扫描</span><span class="value mono">${e(datetime(health.last_scan||health.as_of,true))}</span></div><p class="market-footnote">${list(market.reason_codes).length?list(market.reason_codes).map(code=>e(reason(code))).join('；'):'基于基准均线、历史波动与当前上涨广度计算。关键输入不足时暂停新机会。'}</p></div></section></div>
  `;
}
function signalTable(signals) {
  if(!state.signalsLoaded&&!signals.length)return empty('信号数据尚未读取成功','请使用上方重试入口；未读取的数据不表示没有机会。');
  if(!signals.length)return empty('等待符合条件的机会','未触发时保留空列表；拒绝原因可在设置与诊断中查询。');
  return `<p class="table-scroll-hint">${icon('arrow')}横向滚动核对价格、原因和处理入口</p><div id="signals-scroll" class="signal-table-wrap" role="region" aria-label="机会信号表，可横向滚动" tabindex="0"><table class="data-table signals-table"><caption class="sr-only">机会信号及当前状态，使用股票名称按钮打开完整证据</caption><thead><tr><th scope="col">股票 / 关联热点</th><th scope="col">信号 / 参与状态</th><th scope="col" class="numeric-cell">最新参考价</th><th scope="col" class="numeric-cell">规则分</th><th scope="col">触发时点</th><th scope="col">已保存的原因</th><th scope="col">下一步</th></tr></thead><tbody>${signals.map(signal=>{
    const step=signalNextStep(signal), reasons=signalReasons(signal), attention=['PREALERT','CONFIRMED'].includes(signal.status)&&['paused','extended'].includes(signal.actionability);
    return `<tr class="clickable ${attention?'signal-row-attention':''}" data-signal="${e(signal.id)}"><td><button type="button" class="signal-open" id="signal-open-${e(signal.id)}" data-signal="${e(signal.id)}" aria-label="查看 ${e(signal.name||signal.code||signal.instrument_id)} 信号详情"><span class="stock-link-heading"><span class="stock-name">${e(signal.name||signal.code||signal.instrument_id)}</span>${icon('arrow')}</span><span class="stock-code">${e(signal.code||signal.instrument_id)}</span></button><div class="cell-secondary stock-sector">${e(signal.sector_name||signal.primary_sector_id||'尚未关联')}${list(signal.related_sectors).length>1?` · 另${list(signal.related_sectors).length-1}个关联`:''}</div></td><td><div class="signal-state-stack">${tag(signal.status)}${participationTag(signal)}</div></td><td class="mono numeric-cell">${price(signal.latest_price)}<div class="cell-secondary">触发 ${price(signal.trigger_price)}</div><div class="cell-secondary">最新 ${e(timeOnly(signal.latest_time))}</div></td><td class="numeric-cell"><div class="score-cell">${number(signal.score)}<small>/ 100</small></div></td><td class="mono">${e(timeOnly(signal.trigger_time))}<div class="cell-secondary">${e(datetime(signal.trigger_time).split(' ')[0])}</div></td><td class="signal-reason">${reasons.length?reasons.slice(0,2).map(text=>`<span>${e(text)}</span>`).join(''):'<span class="muted">原因尚未提供，请核对原始快照</span>'}${reasons.length>2?`<small>另 ${reasons.length-2} 项，详见证据</small>`:''}</td><td><button type="button" class="text-button signal-next" data-signal="${e(signal.id)}" aria-label="${e(step.title)} · ${e(signal.name||signal.code||signal.instrument_id)}">${e(step.title)}${icon('arrow')}</button></td></tr>`;
  }).join('')}</tbody></table></div>`;
}
function renderSignals() {
  const filters=[['','全部'],['PREALERT','预警'],['CONFIRMED','确认'],['INVALIDATED','失效'],['EXPIRED','过期'],['DETECTED','内部观察']];
  return `${pageHeading('机会信号','追踪从首次突破到确认、失效的完整过程。',demoActions())}${modeBanner()}${errorBanner()}<section class="panel"><div class="filter-bar"><div class="filter-tabs" role="group" aria-label="信号状态筛选">${filters.map(([value,label])=>`<button class="filter-tab ${state.signalStatus===value?'active':''}" data-filter="${value}" aria-pressed="${state.signalStatus===value}">${label}</button>`).join('')}</div><form id="signal-search" class="search-wrap" role="search">${icon('search')}<input id="signal-query" type="search" enterkeyhint="search" autocomplete="off" aria-label="搜索股票代码或名称" placeholder="搜索代码或名称" value="${e(state.signalQueryDraft)}"><button type="submit" class="text-button" aria-label="搜索">搜索</button></form></div>${signalTable(state.signals)}<div class="table-footer"><span>已加载 ${number(state.signalsLoaded?state.signals.length:null)} 条 · 忽略信号仍保留在评价样本中</span>${state.nextCursor?'<button class="text-button" data-action="more-signals">加载更多 ↓</button>':'<span>已显示当前查询结果</span>'}</div></section><div class="notice-block section-gap"><strong>触发快照与当前行情分别保存。</strong> 点击任一信号查看冻结突破位、结构失效价、分项评分、证据及投递记录。记录“已买入”仅表示手动反馈，不会生成实际成交或持仓数据。</div>`;
}
function renderResearch() {
  const versions=items(state.data.versions), selected=versions[0];
  const base=versions.find(item=>item.id===state.strategyPreferences?.baseId)||
    versions.find(item=>item.id===state.data.health?.strategy_version)||selected;
  const draft=base&&(state.strategyPreferences?.baseId===base.id?state.strategyPreferences:strategyDraft(base.config));
  const replayVersion=state.replayVersion||selected?.id;
  return `${pageHeading('策略与研究','核对策略版本、研究输入与结果；新版本保存后不会自动启用。',`<button class="button" data-action="export-config">${icon('download')}导出配置</button>`)}${modeBanner()}${errorBanner()}
  ${strategyForm(base,versions,draft,state.savedStrategyId,presentation)}
  <div id="study-cards">${studyCardsPanel(state.data.studyCards,state.historyErrors.studyCards,presentation)}</div>
  <div class="two-columns"><section class="panel"><div class="panel-header"><div><h2>策略版本</h2><p>热点启动突破 · hotspot_breakout_v1</p></div><span class="tag neutral">参数不可原地覆盖</span></div><div class="panel-body">${versions.length?versions.map(version=>`<div class="version-card"><div class="version-card-header"><span class="version-id">${e(version.id)}</span>${tag(version.status||'frozen')}</div><div class="version-meta">创建时间 ${e(datetime(version.created_at,true))}<br>配置哈希 <span class="mono">${e(version.config_hash||'—')}</span><br>代码版本 <span class="mono">${e(version.code_version||version.code_commit||'—')}</span></div><button class="button" data-config-version="${e(version.id)}">${icon('code')}基于此版本编辑</button></div>`).join(''):empty('还没有策略版本','完整参数通过校验后才能创建版本。')}</div></section>
  <section class="panel"><div class="panel-header"><div><h2>离线回放</h2><p>使用与运行模式相同的策略实现</p></div>${icon('flask')}</div><div class="panel-body"><div class="settings-entry"><label class="field-label" for="replay-version">策略版本</label><select class="select" id="replay-version">${versions.map(version=>`<option value="${e(version.id)}"${version.id===replayVersion?' selected':''}>${e(version.id)}</option>`).join('')}</select><p style="margin-top:15px">数据集为内置合成样例，报告展示四组对照。</p><button class="button primary" data-action="start-replay" ${versions.length?'':'disabled'}>${icon('play')}运行样例回放</button></div><div class="notice-block">研究任务在后台运行。真实历史样本、交易成本与样本外验证未齐备时，不输出未经验证的收益结论。</div></div></section></div>
  <section class="panel"><div class="panel-header"><div><h2>参数实验</h2><p>编辑完整 JSON 后创建新版本。新版本不会自动切换运行策略。</p></div><span class="panel-label">EXPERIMENTAL</span></div><div class="editor-panel"><label class="field-label" for="config-editor">策略配置</label><textarea id="config-editor" class="config-editor" spellcheck="false" aria-label="完整策略配置 JSON">${e(state.configDraft??draftConfig(selected?.config||state.data.diagnostics?.config||{}))}</textarea><div class="editor-actions"><span class="small muted">使用新的 id；缺失必需项或含未知参数时将拒绝创建。</span><button class="button primary" data-action="save-version">创建新版本 ${icon('arrow')}</button></div></div></section>
  <section class="panel section-gap"><div class="panel-header"><div><h2>回放记录</h2><p>包括失败尝试；模拟结果与真实运行结果分开保存</p></div><button class="text-button" data-action="refresh-replays">${icon('refresh')}刷新记录</button></div><div id="replay-list" class="panel-body">${replayListHTML()}</div></section>${studyPanel(state,presentation)}`;
}
function replayListHTML() {
  const runs=items(state.data.replays);
  return runs.length?runs.map(run=>{
    const result=run.result||{}, primary=list(result.baselines).find(item=>item.id===(result.selected_baseline_id||'early'))||list(result.baselines)[0]||{}, metrics=result.metrics||result.summary||primary;
    return `<div class="replay-job"><div class="replay-job-header"><span class="replay-job-id">${e(run.id||run.run_id)}</span>${tag(run.status)}</div><div class="version-meta">${e(datetime(run.created_at,true))} · ${e(run.strategy_version||run.request?.strategy_version||'当前冻结版本')}</div>${['completed','succeeded','finished'].includes(run.status)?`<div class="replay-metrics"><div class="metric"><b>${number(metrics.signal_count??result.signals?.length)}</b><span>信号数</span></div><div class="metric"><b>${number(metrics.event_count??result.events?.length)}</b><span>状态事件</span></div><div class="metric"><b>${number(result.batch_count??metrics.slice_count??metrics.batch_count)}</b><span>处理切片</span></div></div>`:''}${run.error?`<p class="form-error">${e(typeof run.error==='string'?run.error:JSON.stringify(run.error))}</p>`:''}${result.limitations?`<p class="small muted" style="margin:12px 0 0">${e(Array.isArray(result.limitations)?result.limitations.join('；'):result.limitations)}</p>`:''}${list(result.baselines).length?`<div class="signal-table-wrap section-gap"><table class="data-table"><thead><tr><th>比较基线</th><th>信号</th><th>失效</th><th>最低覆盖</th></tr></thead><tbody>${result.baselines.map(baseline=>`<tr><td>${e(baseline.name)}</td><td>${number(baseline.signal_count)}</td><td>${number(baseline.invalidated_count)}</td><td>${percent(baseline.min_coverage)}</td></tr>`).join('')}</tbody></table></div>`:''}${jsonDetails(result,'查看结果与可复现性记录')}</div>`;
  }).join(''):empty('尚无回放记录','运行一次内置样例，检查策略的确定性与状态变化。');
}
function renderReplayList() { const container=$('#replay-list');if(container)container.innerHTML=replayListHTML(); }
function renderSetup() {
  return `${pageHeading('首次设置','核对行情连接、钉钉测试和当前运行版本。')}${modeBanner()}${connectionTabs('setup')}${errorBanner()}${setupPanel(state.data,presentation)}`;
}

function readStrategyPreferences(form) {
  const field=name=>form.elements.namedItem(name).value;
  return {baseId:field('base_id'), alertStage:field('alert_stage'), dailyLimit:field('daily_new_limit'),
    riskPercent:field('max_loss_percent')};
}

async function saveStrategyPreferences(form, button) {
  await action(button, async()=>{
    const error=$('#strategy-preferences-error',form);
    error.textContent='';
    const draft=readStrategyPreferences(form), previous=state.strategyPreferences;
    const base=items(state.data.versions).find(item=>item.id===draft.baseId);
    const retry=previous?.requestId&&Object.entries(draft).every(([key,value])=>previous[key]===value);
    const id=retry?previous.requestId:`strategy-${idempotencyKey()}`;
    state.strategyPreferences={...draft,requestId:id};
    const token=state.token;
    const fields=$('#strategy-preferences-fields',form);
    fields.disabled=true;
    try {
      if(!base)throw new Error('基准版本尚未读取，请刷新后重试。');
      const config=preferenceConfig(base.config,draft,id);
      const saved=await api('strategy-versions',{method:'POST',body:{config}});
      if(token!==state.token)return;
      const cached=items(state.data.versions).filter(item=>item.id!==saved.id);
      state.data.versions={items:[saved,...cached]};
      state.savedStrategyId=saved.id;
      state.replayVersion=saved.id;
      state.strategyPreferences={...draft,baseId:saved.id};
      try {
        const versions=await api('strategy-versions');
        if(token!==state.token)return;
        state.data.versions=versions;
      }catch{
        if(token!==state.token)return;
        toast('草稿已保存。可刷新版本列表查看完整记录。');
      }
      if(state.page==='research'){
        render();
        $('#save-strategy-preferences')?.focus({preventScroll:true});
      }
    }catch(err){
      const currentError=$('#strategy-preferences-error');
      if(token===state.token&&state.page==='research'&&currentError)currentError.textContent=err.message;
    }finally{fields.disabled=false;}
  });
}

function renderSettings() {
  const health=state.data.health||{}, diagnostics=state.data.diagnostics||{}, provider=health.provider||{}, outbox=health.outbox||{};
  const rejections=list(diagnostics.rejections), logs=list(diagnostics.logs), gates=list(diagnostics.release_gates);
  return `${pageHeading('设置与诊断','先核对数据与投递异常，再查看发布条件和原始记录。',`<button class="button" data-action="export-config">${icon('download')}导出配置</button>`)}${modeBanner()}${connectionTabs('settings')}${errorBanner()}
  <div class="two-columns"><section class="panel"><div class="panel-header"><h2>数据与运行</h2><span class="panel-label">DATA SOURCE</span></div><div class="panel-body"><div class="settings-entry"><div class="setting-status"><h3>${e(provider.name||'合成样例数据源')}</h3>${tag(provider.status||'fixture')}</div><p>${health.mode==='fixture'?'用于本地功能验证；暂未配置真实行情服务商。':'当前提供方能力与授权边界请查看数据契约。'}</p><div class="metric-line"><span class="key">运行模式</span><span class="value">${e(human(health.mode||'fixture'))}</span></div><div class="metric-line"><span class="key">行情时点</span><span class="value mono">${e(datetime(health.as_of,true))}</span></div><div class="metric-line"><span class="key">最后扫描</span><span class="value mono">${e(datetime(health.last_scan,true))}</span></div><div class="metric-line"><span class="key">覆盖率 / 缺失</span><span class="value">${percent(health.coverage)} / ${number(health.missing_count)}</span></div><div class="metric-line"><span class="key">服务版本</span><span class="value mono">${e(health.version||'v0.1')}</span></div>${jsonDetails(provider.capabilities||provider,'查看数据源能力声明')}</div><div class="notice-block">真实行情接入需要完整股票池、分钟数据、历史参考数据和交易日历。合成样例覆盖率不代表真实全市场能力。</div></div></section>
  <section class="panel"><div class="panel-header"><h2>通知渠道</h2><span class="panel-label">DELIVERY</span></div><div class="panel-body"><div class="settings-entry"><div class="setting-status"><h3>内置通知中心</h3><span class="tag">已启用</span></div><p>信号事件、投递尝试和失败原因保存在本地数据库。</p><div class="metric-line"><span class="key">待处理 / 失败 / 结果未知</span><span class="value">${number(outbox.pending??0)} / ${number(outbox.failed??0)} / ${number(outbox.unknown??0)}</span></div><button class="button" data-action="notifications" style="margin-top:15px">${icon('bell')}查看通知中心</button></div><div class="settings-entry"><div class="setting-status"><h3>钉钉群机器人</h3>${tag(health.dingtalk_configured?'configured':'unconfigured')}</div><p>在服务端配置机器人 Webhook 与加签密钥后，点击测试会向已配置的群发送一条明确标记的测试消息。</p><code class="env-command">DINGTALK_WEBHOOK=…<br>DINGTALK_SECRET=…</code><button class="button" data-action="test-dingtalk">${icon('arrow')}发送钉钉测试消息</button><p style="margin-top:12px;margin-bottom:0">平台受理不代表用户已读。超时状态为“结果未知”，不会盲目重试。</p></div></div></section></div>
  <section class="panel"><div class="panel-header"><div><h2>受控提醒发布条件</h2><p>所有条件满足前，真实机会推送保持关闭</p></div><span class="tag warning">需完成真实环境验证</span></div><div class="panel-body">${gates.length?gates.map(gate=>`<div class="release-gate"><span class="gate-icon ${gate.passed?'passed':''}">${icon(gate.passed?'check':'clock')}</span><div><strong style="font-weight:500">${e(gate.name||gate.id)}</strong><p>${e(gate.detail||gate.reason||'')}</p></div></div>`).join(''):'<div class="notice-block">待验证：真实行情路径、钉钉投递、冻结参数与样本外研究、连续影子运行及故障恢复演练。详见产品需求中的发布门槛。</div>'}</div></section>
  <section class="panel section-gap"><div class="panel-header"><div><h2>候选过滤记录</h2><p>未生成提醒的原因同样保留，避免用空列表掩盖失败</p></div><span class="panel-label">${rejections.length} RECORDS</span></div><div class="panel-body">${rejections.length?rejections.slice(0,40).map(item=>`<div class="log-row"><span class="log-time">${e(item.code||item.instrument_id||item.entity_id||'全局检查')}</span><div class="log-text">${e(list(item.reason_codes||item.reasons).map(reason).join('；')||item.reason||'未提供原因')}<div class="code-tag">${e(datetime(item.as_of||item.at||item.created_at))}</div></div></div>`).join(''):empty('暂无过滤记录','扫描后将显示数据质量、市场与个股门槛未通过的原因。')}</div></section>
  <section class="panel section-gap"><div class="panel-header"><h2>运行日志与恢复记录</h2><span class="panel-label">AUDIT TRAIL</span></div><div class="panel-body">${logs.length?logs.slice(0,35).map(log=>`<div class="log-row"><span class="log-time">${e(datetime(log.at||log.created_at||log.time))}</span><div class="log-text">${e(log.message||log.detail||log.event||log.type||JSON.stringify(log))}</div></div>`).join(''):empty('暂无运行事件','任务失败、配置变更和恢复操作将在这里留痕。')}</div></section>`;
}

function renderConnections() {
  const model=state.page==='models';
  const history=model?'':`<div id="source-health">${sourceHealthPanel(state.data.sourceHealth,state.historyErrors.sourceHealth,presentation)}</div>`;
  return `${pageHeading(model?'大模型配置':'行情 API 配置',model?'管理模型服务地址、模型 ID 和访问凭据。':'分别管理行情来源的 Key、访问依据和连接状态。', '<button class="button" data-action="reload-connections">刷新状态</button>')}${modeBanner()}${errorBanner()}${connectionPage(state.page,state.data.connections,state.connectionProvider,state.connectionDrafts,presentation)}${history}`;
}

async function readHistory(key, endpoint, containerId, renderPanel) {
  const region=document.getElementById(containerId), token=state.token;
  if(!region)return;
  try {
    const result=await api(endpoint);
    if(state.token!==token)return;
    state.data[key]=result;
    delete state.historyErrors[key];
  }catch(error){
    if(state.token!==token)return;
    state.historyErrors[key]=error.message;
  }
  if(region.isConnected){
    const focused=document.activeElement;
    region.innerHTML=renderPanel(state.data[key],state.historyErrors[key],presentation);
    if(focused===document.body || !focused?.isConnected)$('button[data-action]',region)?.focus({preventScroll:true});
  }
}

function renderMinutes() {
  return `${pageHeading('真实行情','查看 Fuyao 报价与日线；下方另提供 Tushare 分钟获取。','<button class="button" data-action="reload-minutes">刷新本机记录</button>')}${connectionTabs('minute-data')}${realMarketPanel(state.data.realMarket,presentation,state.realMarketError||'')}<p class="notice-block">以下为 Tushare 分钟研究。策略运行模式：${e(human(state.data.health?.mode))}；真实提醒尚未发布。</p>${errorBanner()}${minutePage(state.data.minutes,state.data.connections,state.minuteDraft,state.minutePreview,state.minuteBusy,state.minuteError,presentation)}`;
}

function updateMinuteDraft(event) {
  const form=event.target.closest?.('#minute-form');if(!form)return;
  state.minuteDraft=minuteFormDraft(form);state.minutePreview=null;state.minuteError='';state.minuteDirty=true;
  $('#minute-preparation')?.remove();
  if(event.type==='change'){
    if(event.target.name==='mode')state.minuteDraft.access_confirmed=false;
    state.minuteDirty=false;render();
  }
}

async function submitMinute(form,operation) {
  const payload=minutePayload(form);
  state.minuteDraft=minuteFormDraft(form);state.minutePreview=null;state.minuteDirty=false;state.minuteBusy=true;state.minuteError='';render();
  await action(null,async()=>{
    try{
      const result=await api(`minute-data/${operation==='fetch'?'fetch':'prepare'}`,{method:'POST',body:payload});
      if(!state.token)return;
      if(operation==='fetch'){state.data.minutes=result;toast(result.capture?.bar_count?'分钟记录已保存，请核对来源与时点。':'本次没有取得分钟记录，请核对接口权限和返回状态。',!result.capture?.bar_count);}
      else state.minutePreview=result;
    }catch(error){state.minuteError=error.message;throw error;}
    finally{state.minuteBusy=false;render();}
  });
}

function updateConnectionDraft(event) {
  const form=event.target.closest?.('#connection-form');if(!form)return;
  state.connectionDirty=true;
  state.connectionDrafts[form.dataset.profile]=connectionDraft(form,form.dataset.profile==='model');
  const dirty=$('#connection-dirty');if(dirty)dirty.textContent='有未保存的修改，请先保存再测试';
  const test=$('[data-connection-test]',form);if(test)test.disabled=true;
  if(event.target.name==='api_key'&&event.target.value){const clear=form.elements.namedItem('clear_key');if(clear)clear.checked=false;}
}

async function saveConnection(form) {
  const identifier=form.dataset.profile, model=identifier==='model', button=$('button[type="submit"]',form);
  const payload=connectionPayload(form,model), secret=form.elements.namedItem('api_key');
  // Clear the input immediately; the request is the only remaining owner of the supplied Key.
  secret.value='';
  const controls=$$('input,textarea,button',form), disabled=controls.map(node=>node.disabled);
  controls.forEach(node=>{node.disabled=true;});form.setAttribute('aria-busy','true');
  try {await action(button,async()=>{
    const fieldset=$('#connection-form-error');if(fieldset)fieldset.textContent='';
    try {
      const result=await api(model?'connections/model':`connections/market/${identifier}`,{method:'POST',body:payload});
      if(!state.token)return;
      if(model)state.data.connections.model=result;else state.data.connections.market=state.data.connections.market.map(p=>p.id===identifier?result:p);
      delete state.connectionDrafts[identifier];state.connectionDirty=false;
      render();toast('连接配置已保存。');
    } catch(error) {
      if(fieldset?.isConnected)fieldset.textContent=`保存失败：${error.message}${payload.key_action==='replace'?' 请重新输入 Key 后再保存。':''}`;
      throw error;
    } finally {payload.api_key='';}
  });} finally {controls.forEach((node,index)=>{if(node.isConnected)node.disabled=disabled[index];});if(form.isConnected)form.removeAttribute('aria-busy');}
}

function drawerShell(title, content) { return `<div class="drawer-top"><h2 id="drawer-title">${e(title)}</h2><button class="icon-button" data-action="close-drawer" aria-label="关闭详情">${icon('close')}</button></div><div class="drawer-content">${content}</div>`; }
function showDrawer(title, content) { if($('#drawer').hidden){const element=document.activeElement;state.lastFocus={element,id:element?.id,signal:element?.dataset?.signal,sector:element?.dataset?.sector};}$('#drawer').innerHTML=drawerShell(title,content);$('#drawer').hidden=false;$('#drawer').setAttribute('aria-label',title);$('#drawer-backdrop').hidden=false;$('#application').inert=true;document.body.style.overflow='hidden';$('#drawer .icon-button')?.focus({preventScroll:true}); }
function closeDrawer() { $('#drawer').hidden=true;$('#drawer-backdrop').hidden=true;$('#application').inert=false;document.body.style.overflow='';state.detailId=null;state.drawerKind=null;const origin=state.lastFocus;const target=origin?.element?.isConnected?origin.element:(origin?.id?document.getElementById(origin.id):null)||(origin?.signal?$$('.signal-open').find(node=>node.dataset.signal===origin.signal):null)||(origin?.sector?$$('[data-sector]').find(node=>node.dataset.sector===origin.sector):null)||$('.nav-link.active');if(!$('#application').hidden)target?.focus({preventScroll:true});state.lastFocus=null; }
async function openSignal(id) {
  state.detailId=id;state.drawerKind='signal';showDrawer('信号详情','<div class="loading-block">正在加载信号证据…</div>');
  try { const signal=await api(`signals/${encodeURIComponent(id)}`);if(state.detailId!==id)return;showDrawer('机会详情 · 触发证据与状态',signalDetail(signal.signal?{...signal.signal,...signal}:signal)); }
  catch(error){if(state.detailId===id)showDrawer('信号详情',`<div class="error-banner">${e(error.message)}</div>`);}
}
function scoreParts(signal) {
  const parts=signal.score_parts||{};
  const names={market:'市场匹配',sector:'板块质量',stock:'个股相对表现',entry:'入场位置',market_fit:'市场匹配',sector_quality:'板块质量',stock_strength:'个股相对表现',entry_quality:'入场位置'};
  let values=Array.isArray(parts)?parts.map(part=>[part.name||part.id||part.feature,part]):Object.entries(parts);
  if(!values.length)return '<p class="small muted">当前候选未通过全部硬门槛，评分为空。</p>';
  return values.map(([key,part])=>{const value=typeof part==='number'?part:(part.points??part.value??part.normalized??part.score??part.contribution??part.weighted_score);const numeric=Number(value);const width=Number.isFinite(numeric)?Math.max(0,Math.min(100,numeric<=1?numeric*100:numeric)):0;return `<div class="score-part"><span class="score-part-name">${e(part.label||names[key]||key)}</span><div class="score-part-bar"><span style="width:${width}%"></span></div><span class="score-part-value">${number(value,2)}${typeof part==='object'&&part.points!=null?' 分':''}</span></div>`;}).join('')+jsonDetails(parts,'查看权重、归一化与原始分项');
}
function openSector(id) {
  const sector=items(state.data.sectors).find(item=>item.id===id);if(!sector)return;
  state.detailId=id;state.drawerKind='sector';
  const members=list(sector.active_members);
  showDrawer('热点证据 · '+(sector.name||sector.id),`
    <div class="detail-heading"><div><h1>${e(sector.name||sector.id)}</h1><span class="stock-code">${e(datetime(sector.as_of,true))}</span></div>${tag(sector.status)}</div>
    <div class="detail-metrics">
      <div class="detail-metric"><span>相对强度 / 改善</span><strong>${percent(sector.rs,2,true)}</strong><small>Δ ${percent(sector.delta_rs,2,true)}</small></div>
      <div class="detail-metric"><span>上涨广度</span><strong>${percent(sector.breadth,1)}</strong><small>同步突破 ${number(sector.breakout_count)} 只</small></div>
      <div class="detail-metric"><span>同分钟累计成交额比</span><strong>${number(sector.rvol,2)} 倍</strong><small>历史可比覆盖 ${percent(sector.historical_coverage)}</small></div>
      <div class="detail-metric"><span>有效行情覆盖</span><strong>${percent(sector.coverage)}</strong><small>${number(sector.valid_count)} / ${number(sector.member_count)} 只成分股</small></div>
    </div>
    <div class="notice-block">板块收益采用有效成分等权平均。当前量能与历史相同时点比较；每只股票在板块内只计算一次。</div>
    <section class="detail-section"><h3>门槛与质量依据</h3>
      ${list(sector.reason_codes).length?`<ul class="reason-list">${sector.reason_codes.map(code=>`<li>${e(reason(code))}</li>`).join('')}</ul>`:'<p class="small muted">当前所需数据与板块门槛通过。</p>'}
      <button class="button" data-detail-target="sector-timeline-title">查看热点阶段时间线</button>
    </section>
    <section class="detail-section"><h3 id="sector-timeline-title" tabindex="-1">热点阶段时间线</h3><div id="sector-timeline" aria-live="polite"></div></section>
    <section class="detail-section"><h3>当前有效成分股</h3>
      ${members.length?`<div class="signal-table-wrap" tabindex="0" role="region" aria-label="当前有效成分股，可横向滚动"><table class="data-table"><thead><tr><th scope="col">股票</th><th scope="col">代码</th><th scope="col">当前收益</th></tr></thead><tbody>${members.map(member=>`<tr><td>${e(member.name)}</td><td class="mono">${e(member.code||member.id)}</td><td>${percent(member.return,2,true)}</td></tr>`).join('')}</tbody></table></div>`:empty('暂无有效成分行情')}
      ${jsonDetails(sector,'查看完整板块计算结果')}
    </section>`);
  loadSectorTimeline(id);
}
async function loadSectorTimeline(id) {
  const region=$('#sector-timeline');
  if(!region || state.drawerKind!=='sector' || state.detailId!==id)return;
  if(region.contains(document.activeElement))$('#sector-timeline-title')?.focus({preventScroll:true});
  region.innerHTML='<p class="small muted" role="status">正在读取已保存的热点切片…</p>';
  try {
    const data=await api(`sector-timeline?sector_id=${encodeURIComponent(id)}`);
    if(region.isConnected && state.drawerKind==='sector' && state.detailId===id)region.innerHTML=sectorTimeline(data,presentation);
  }catch(error){
    if(region.isConnected && state.drawerKind==='sector' && state.detailId===id)
      region.innerHTML=`<p class="form-error" role="alert">${e(error.message)}</p><button class="button" data-action="retry-sector-timeline">重试时间线</button>`;
  }
}
async function openStudyCases(id,profile) {
  state.detailId=null;state.drawerKind='study-cases';
  showDrawer('研究案例','<p class="small muted" role="status">正在读取保存的案例…</p>');
  const drawer=$('#drawer'), region=$('.drawer-content',drawer);
  drawer.scrollTop=0;
  try {
    const data=await api(`studies/${encodeURIComponent(id)}/cases?profile=${encodeURIComponent(profile)}`);
    if(region.isConnected && state.drawerKind==='study-cases')region.innerHTML=studyCaseList(data,presentation);
  }catch(error){
    if(region.isConnected && state.drawerKind==='study-cases')
      region.innerHTML=`<p class="form-error" role="alert">${e(error.message)}</p><button class="button" data-case-study="${e(id)}" data-case-profile="${e(profile)}">重试读取案例</button>`;
  }
}
function signalDetail(signal) {
  const events=list(signal.events), feedback=list(signal.feedback), notifications=list(signal.notifications);
  const reasonCodes=list(signal.reason_codes), latestFeedback=feedback.at(-1);
  const related=list(signal.related_sectors).map(item=>typeof item==='string'?item:(item.name||item.sector_id||item.id));
  const evidence=signal.evidence||{}, step=signalNextStep(signal);
  return `<div class="detail-heading"><div><h1>${e(signal.name||signal.code||signal.instrument_id)}</h1><span class="stock-code">${e(signal.code||signal.instrument_id)} · ${e(signal.sector_name||signal.primary_sector_id||'尚未关联热点')}</span></div><div class="detail-score">${number(signal.score)}<small>/ 100</small></div></div><div class="detail-tags">${tag(signal.status)}${participationTag(signal)}<span class="tag neutral">${e(human(state.data.health?.mode||'fixture'))}</span></div><p class="detail-version">策略版本 · <span class="mono">${e(signal.strategy_version||'v1')}</span></p>
  <div class="decision-brief"><strong>${e(step.title)}</strong><p>${reasonCodes.length?e(reason(reasonCodes[0])):'当前原因尚未提供，请核对保存的快照。'}</p><p class="muted">${e(step.text)}</p><div class="detail-jumps"><button type="button" class="text-button" data-detail-target="signal-evidence">查看完整依据 ${icon('arrow')}</button><button type="button" class="text-button" data-detail-target="signal-feedback">记录我的处理 ${icon('arrow')}</button></div></div>
  <div class="detail-metrics"><div class="detail-metric"><span>触发参考价 · 冻结快照</span><strong>${price(signal.trigger_price)}</strong><small>${e(datetime(signal.trigger_time,true))}</small></div><div class="detail-metric"><span>最新参考价</span><strong>${price(signal.latest_price)}</strong><small>${e(datetime(signal.latest_time,true))}</small></div><div class="detail-metric"><span>盘前突破参考位 H</span><strong>${price(signal.breakout_price)}</strong><small>冻结 ATR ${price(signal.atr)}</small></div><div class="detail-metric"><span>结构失效参考价 S</span><strong>${price(signal.invalidation_price)}</strong><small>失效位不代表保证成交价</small></div></div>
  <div class="price-range ${signal.actionability!=='eligible'?'paused':''}"><span>当前参与范围 · ${e(signal.actionability?human(signal.actionability):'参与状态未知')}</span><strong>${price(signal.entry_low)} — ${price(signal.entry_high)}</strong><span>有效至 ${e(datetime(signal.expires_at,true))}</span></div>
  <section class="detail-section" aria-labelledby="signal-evidence"><h3 id="signal-evidence" tabindex="-1">触发依据与当前限制</h3>${reasonCodes.length?`<ul class="reason-list">${reasonCodes.map(code=>`<li>${e(reason(code))}</li>`).join('')}</ul>`:'<p class="small muted">详见保存的结构化证据与事件记录。</p>'}${related.length?`<p class="small muted">全部关联：${related.map(e).join('、')}。主关联板块在首次提醒后冻结。</p>`:''}${jsonDetails(evidence,'查看输入快照、来源与质量')}${list(signal.tags).length?jsonDetails(signal.tags,'查看动态标签与定义版本'):''}</section>
  ${evidenceChart(signal.chart,presentation)}
  <section class="detail-section"><h3>分项评分 <span class="muted small">· 规则匹配度，非上涨概率</span></h3>${scoreParts(signal)}</section>
  <section class="detail-section" aria-labelledby="signal-feedback"><h3 id="signal-feedback" tabindex="-1">记录我的处理</h3><div class="feedback-buttons"><button class="button" data-feedback="watch" data-id="${e(signal.id)}">${icon('eye')}继续观察</button><button class="button" data-feedback="ignore" data-id="${e(signal.id)}">忽略此机会</button><button class="button" data-feedback="bought" data-id="${e(signal.id)}">标记已买入</button></div><p class="small muted" style="margin:11px 0 0;line-height:1.8">仅保存反馈；买入价格和数量未记录时，不计算持仓浮亏，不会下单。</p>${latestFeedback?`<p class="feedback-status">最近反馈：${e(human(latestFeedback.action))} · ${e(datetime(latestFeedback.at||latestFeedback.user_time||latestFeedback.created_at))}</p>`:''}</section>
  <section class="detail-section"><h3>信号状态时间线</h3>${events.length?`<ol class="timeline">${events.map(event=>`<li><time>${e(datetime(event.at||event.created_at,true))} · revision ${e(event.revision)}</time><strong>${e(human(event.from_status))} → ${e(human(event.to_status||event.status))}</strong><p>${list(event.reason_codes).map(code=>e(reason(code))).join('；')}</p></li>`).join('')}</ol>`:'<p class="small muted">暂无状态事件。</p>'}</section>
  <section class="detail-section"><h3>通知投递记录</h3>${notifications.length?notifications.map(notification=>`<div class="notification-card"><div class="notification-card-top"><span>${e(human(notification.channel))} · revision ${e(notification.revision??'—')}</span>${deliveryTag(notification)}</div><p>${e(datetime(notification.created_at,true))} · 尝试 ${number(notification.attempts)} 次</p>${notification.last_error?`<p class="text-red">${e(notification.last_error)}</p>`:''}${jsonDetails(notification,'查看投递响应与时效记录')}</div>`).join(''):'<p class="small muted">暂无投递记录。内部观察不会自动触发外部通知。</p>'}</section>
  <p class="code-tag" style="margin-top:28px">Signal ID · ${e(signal.id)}</p>`;
}
async function openNotifications() {
  state.detailId=null;state.drawerKind='notifications';showDrawer('通知中心','<div class="loading-block">正在加载通知…</div>');
  try {const response=await api('notifications');state.data.notifications=response;if(state.drawerKind!=='notifications')return;const notifications=items(response);showDrawer('通知中心',`<div class="notice-block" style="margin-bottom:20px">通知状态与信号状态独立。平台受理不代表用户已读或已成交；模拟信号会明确标记。</div>${notifications.length?notifications.map(notification=>{const payload=notification.payload||{};return `<article class="notification-card"><div class="notification-card-top"><span>${e(human(notification.channel))}</span>${deliveryTag(notification)}</div><h3>${e(payload.title||payload.signal?.name||payload.name||notification.title||'信号状态更新')}</h3><p>${e(payload.text||payload.markdown?.text||payload.content||payload.message||(payload.event?`${human(payload.event.to_status)} · ${list(payload.event.reason_codes).map(reason).join('；')}`:notification.reason)||'查看关联信号以追踪完整状态和依据。')}</p><p>${e(datetime(notification.created_at,true))} · 尝试 ${number(notification.attempts)} 次</p>${notification.last_error?`<p class="text-red">${e(notification.last_error)}</p>`:''}${notification.signal_id?`<button class="text-button" data-signal="${e(notification.signal_id)}">打开关联信号 ${icon('arrow')}</button>`:''}${jsonDetails(notification,'查看投递详情')}</article>`;}).join(''):empty('通知中心暂时为空','推进样例切片，符合条件时将在这里出现状态消息。')}`);}
  catch(error){showDrawer('通知中心',`<div class="error-banner">${e(error.message)}</div>`);}
}
async function action(button, operation) { const label=button?.innerHTML;if(button){button.disabled=true;button.setAttribute('aria-busy','true');if(button.dataset.busyLabel)button.textContent=button.dataset.busyLabel;}state.loading=true;try{await operation();}catch(error){toast(error.message,true);}finally{if(button?.isConnected){button.disabled=false;button.removeAttribute('aria-busy');if(button.dataset.busyLabel)button.innerHTML=label;}state.loading=false;} }
function idempotencyKey() { return globalThis.crypto?.randomUUID?globalThis.crypto.randomUUID():`feedback-${Date.now()}-${Math.random().toString(36).slice(2)}`; }
async function pollReplay(id) {
  if(state.replayPolling)return;state.replayPolling=true;
  try {for(let count=0;count<60&&state.token;count++){await new Promise(resolve=>setTimeout(resolve,2000));const run=await api(`replays/${encodeURIComponent(id)}`);const runs=items(state.data.replays);const index=runs.findIndex(item=>(item.id||item.run_id)===id);if(index>=0)runs[index]=run;else runs.unshift(run);state.data.replays={items:runs};if(state.page==='research')renderReplayList();if(!['queued','running','pending'].includes(run.status)){toast(run.status==='failed'?'回放失败，请查看失败原因。':'回放已完成，结果已保存。',run.status==='failed');break;}}}catch(error){toast(`回放状态查询失败：${error.message}`,true);}finally{state.replayPolling=false;}
}

function renderStudies(result=true) {
  const listNode=$('#study-list'), resultNode=$('#study-result');
  if(listNode)listNode.innerHTML=studyList(state,presentation);
  if(result&&resultNode)resultNode.innerHTML=studyResult(state,presentation);
}
async function openStudy(id,filter=null) {
  const job=await api(`studies/${encodeURIComponent(id)}`);
  if(filter)state.studyFilter=filter;
  state.studyJob=job;renderStudies();
  const result=$('#study-result');
  if(filter&&result){result.tabIndex=-1;result.focus();}
  if(['pending','running'].includes(job.status))pollStudy(id);
}
async function pollStudy(id) {
  if(state.studyPolling.has(id))return;
  state.studyPolling.add(id);
  try {
    for(let count=0;count<240&&state.token;count++) {
      await new Promise(resolve=>setTimeout(resolve,2000));
      const job=await api(`studies/${encodeURIComponent(id)}`);
      state.data.studies=await api('studies');
      if(state.studyJob?.id===id)state.studyJob=job;
      if(state.page==='research')renderStudies(state.studyJob?.id===id);
      if(!['pending','running'].includes(job.status)) {toast(job.status==='failed'?'成本研究未完成，请核对数据与计划。':'成本研究已完成，请查看样本分母与局限。',job.status==='failed');break;}
    }
  } catch(error) {toast(`研究状态查询失败：${error.message}`,true);}
  finally {state.studyPolling.delete(id);}
}
function downloadJSONText(value,filename) {
  const url=URL.createObjectURL(new Blob([value],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download=filename;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),5000);
}

$('#login-form').addEventListener('submit',event=>{event.preventDefault();connect($('#access-token').value);});
$('#logout').addEventListener('click',()=>logout());
$('#refresh').addEventListener('click',event=>action(event.currentTarget,()=>refreshData()));
$('#open-notifications').addEventListener('click',openNotifications);
$('#drawer-backdrop').addEventListener('click',closeDrawer);
window.addEventListener('hashchange',route);
document.addEventListener('input',event=>{
  if(event.target.id==='config-editor')state.configDraft=event.target.value;
  if(event.target.id==='signal-query')state.signalQueryDraft=event.target.value;
  updateConnectionDraft(event);
  updateMinuteDraft(event);
  const form=event.target.form;
  if(form?.id==='strategy-preferences-form' && event.target.name!=='base_id'){
    state.strategyPreferences=readStrategyPreferences(form);
    $('#strategy-preferences-error',form).textContent='';
  }
});
document.addEventListener('change',event=>{
  updateConnectionDraft(event);
  updateMinuteDraft(event);
  if(event.target.id==='replay-version')state.replayVersion=event.target.value;
  if(event.target.id==='strategy-base'){
    const base=items(state.data.versions).find(item=>item.id===event.target.value);
    if(base){
      state.strategyPreferences={baseId:base.id,...strategyDraft(base.config)};
      render();
      $('#strategy-base')?.focus({preventScroll:true});
    }
  }
  if(event.target.id==='real-market-consent')state.realMarketConsent=event.target.checked;
  if(event.target.id==='study-dataset')state.studyDataset=event.target.value;
  if(event.target.id==='study-plan')state.studyPlan=event.target.value;
  const key=event.target.dataset.studyFilter;
  if(key){state.studyFilter[key]=['delay','horizon'].includes(key)?Number(event.target.value):event.target.value;const result=$('#study-result');if(result)result.innerHTML=studyResult(state,presentation);$(`[data-study-filter="${key}"]`)?.focus({preventScroll:true});}
});
document.addEventListener('submit',event=>{
  if(event.target.id==='strategy-preferences-form'){
    event.preventDefault();
    if(!state.loading)saveStrategyPreferences(event.target,event.submitter||$('#save-strategy-preferences'));
    return;
  }
  if(event.target.id==='minute-form'){event.preventDefault();if(!state.loading&&!state.minuteBusy)submitMinute(event.target,event.submitter?.value||'prepare');return;}
  if(event.target.id==='connection-form'){event.preventDefault();if(!state.loading)saveConnection(event.target);return;}
  if(event.target.id==='signal-search'){event.preventDefault();state.signalQuery=$('#signal-query').value.trim();action(event.target.querySelector('button'),()=>loadSignals());}
});
document.addEventListener('keydown',event=>{
  if((event.key==='Enter'||event.key===' ')&&event.target.matches('[data-sector]')){event.preventDefault();openSector(event.target.dataset.sector);return;}
  if(event.key==='Escape'&&!$('#drawer').hidden){closeDrawer();return;}
  if((event.key==='Enter'||event.key===' ')&&event.target.matches('[data-signal][role="button"]')){event.preventDefault();openSignal(event.target.dataset.signal);}
  if(event.key==='Tab'&&!$('#drawer').hidden){const focusable=$$('button:not(:disabled),a[href],input,select,textarea,summary,[tabindex="0"]',$('#drawer'));const first=focusable[0],last=focusable.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}
});
document.addEventListener('click',event=>{
  const minuteConnection=event.target.closest('[data-minute-connection]');if(minuteConnection){state.connectionProvider='tushare';state.connectionDirty=false;location.hash='#market-api';return;}
  const provider=event.target.closest('[data-connection-provider]');if(provider){state.connectionProvider=provider.dataset.connectionProvider;state.connectionDirty=false;render();return;}
  const connectionTest=event.target.closest('[data-connection-test]');if(connectionTest){
    if(state.connectionDirty||state.loading)return;
    const id=connectionTest.dataset.connectionTest;
    action(connectionTest,async()=>{
      const result=await api(id==='model'?'connections/model/test':`connections/market/${id}/test`,{method:'POST',body:{}});
      if(!state.token)return;
      const profile=id==='model'?state.data.connections.model:state.data.connections.market.find(p=>p.id===id);
      if(profile)profile.last_test=result;
      render();toast(result.message,result.status!=='reachable');
    });return;
  }
  const jump=event.target.closest('[data-detail-target]');if(jump){const target=document.getElementById(jump.dataset.detailTarget);if(target&&$('#drawer').contains(target)){target.scrollIntoView({block:'start',behavior:'auto'});target.focus({preventScroll:true});}return;}
  const sample=event.target.closest('[data-case-study]');if(sample){sample.focus({preventScroll:true});openStudyCases(sample.dataset.caseStudy,sample.dataset.caseProfile);return;}
  const study=event.target.closest('[data-study-id]');
  if(study){
    const filter=study.dataset.cardDelay===undefined?null:{split:'test',delay:Number(study.dataset.cardDelay),horizon:Number(study.dataset.cardHorizon),exit:'fixed'};
    action(study,()=>openStudy(study.dataset.studyId,filter));return;
  }
  const studyDownload=event.target.closest('[data-study-download]');if(studyDownload){action(studyDownload,async()=>{const id=studyDownload.dataset.studyDownload;const report=await api(`studies/${encodeURIComponent(id)}/report`,{raw:true});downloadJSONText(report,`stockradar-study-${id}.json`);});return;}
  const sectorTarget=event.target.closest('[data-sector]');if(sectorTarget){openSector(sectorTarget.dataset.sector);return;}
  const signalTarget=event.target.closest('[data-signal]');if(signalTarget){(signalTarget.matches('.signal-open')?signalTarget:$('.signal-open',signalTarget))?.focus({preventScroll:true});openSignal(signalTarget.dataset.signal);return;}
  const filter=event.target.closest('[data-filter]');if(filter){state.signalStatus=filter.dataset.filter;action(filter,()=>loadSignals());return;}
  const feedback=event.target.closest('[data-feedback]');if(feedback){action(feedback,async()=>{await api(`signals/${encodeURIComponent(feedback.dataset.id)}/feedback`,{method:'POST',body:{action:feedback.dataset.feedback,idempotency_key:idempotencyKey()}});toast(`已记录：${human(feedback.dataset.feedback)}`);await openSignal(feedback.dataset.id);});return;}
  const version=event.target.closest('[data-config-version]');if(version){const selected=items(state.data.versions).find(item=>item.id===version.dataset.configVersion);if(selected){state.configDraft=draftConfig(selected.config||{});$('#config-editor').value=state.configDraft;$('#config-editor').focus();$('#config-editor').scrollIntoView({behavior:'smooth',block:'center'});}return;}
  const button=event.target.closest('[data-action]');if(!button)return;
  const name=button.dataset.action;
  if(name==='skip-content'){$('#main-content').focus();return;}
  if(name==='close-drawer'){closeDrawer();return;}
  if(name==='notifications'){openNotifications();return;}
  if(name==='focus-replay'){$('#replay-version')?.focus();return;}
  action(button,async()=>{
    if(name==='load-source-health')await readHistory('sourceHealth','source-health','source-health',sourceHealthPanel);
    if(name==='load-study-cards')await readHistory('studyCards','study-cards','study-cards',studyCardsPanel);
    if(name==='retry-sector-timeline')await loadSectorTimeline(state.detailId);
    if(name==='reload-connections'){state.data.connections=await api('connections');render();toast(state.connectionDirty?'配置状态已刷新，未保存的内容继续保留。':'连接配置状态已刷新。');}
    if(name==='reload-minutes'){const [minutes,market]=await Promise.all([api('minute-data'),api('real-market')]);state.data.minutes=minutes;state.data.realMarket=market;render();toast('本机行情记录已刷新，没有发起行情请求。');}
    if(name==='read-real-market'){state.data.realMarket=await api('real-market');state.realMarketError='';render();}
    if(name==='fetch-real-market'){
      if(state.realMarketBusy)return;
      if(!$('#real-market-consent')?.checked){toast('请先确认本次两请求用于个人研究。',true);return;}
      state.realMarketBusy=true;
      try{state.data.realMarket=await api('real-market/fetch',{method:'POST',body:{schema_version:1,mode:'latest',symbols:['600000.SH','300750.SZ','688981.SH'],access_confirmed:true}});state.realMarketError='';}
      catch(error){state.realMarketError=error.message;}
      finally{state.realMarketBusy=false;state.realMarketConsent=false;}render();
    }
    if(name==='reset-connection'){const id=$('#connection-form')?.dataset.profile;if(id)delete state.connectionDrafts[id];state.connectionDirty=false;render();}
    if(name==='refresh'){await refreshData();}
    if(name==='advance-demo'){const result=await api('demo/advance',{method:'POST',body:{}});await refreshData();toast(result.message||'已推进模拟切片，状态与证据已更新。');}
    if(name==='reset-demo'){await api('demo/reset',{method:'POST',body:{}});state.signalStatus='';state.signalQuery='';state.signalQueryDraft='';await refreshData();toast('演示已重置。');}
    if(name==='more-signals')await loadSignals(true);
    if(name==='save-version'){let config;try{config=JSON.parse($('#config-editor').value);}catch{throw new Error('配置不是有效 JSON，请检查引号、逗号和括号。');}const result=await api('strategy-versions',{method:'POST',body:{config}});state.data.versions=await api('strategy-versions');state.configDraft=null;render();toast(`新版本已保存${result.id?`：${result.id}`:''}。运行配置保持当前版本。`);}
    if(name==='start-replay'){const strategyVersion=$('#replay-version')?.value;const result=await api('replays',{method:'POST',body:{dataset_id:'fixture',...(strategyVersion?{strategy_version:strategyVersion}:{})}});state.data.replays=await api('replays');renderReplayList();toast('回放任务已提交。');pollReplay(result.run_id||result.id);}
    if(name==='refresh-replays'){state.data.replays=await api('replays');renderReplayList();}
    if(name==='start-study'){const result=await api('studies',{method:'POST',body:{dataset_id:$('#study-dataset').value,plan_id:$('#study-plan').value}});state.data.studies=await api('studies');await openStudy(result.run_id);toast('成本研究已提交，运行策略与原信号不会改变。');}
    if(name==='refresh-studies'){state.data.studySources=await api('study-sources');state.data.studies=await api('studies');if(state.studyJob)await openStudy(state.studyJob.id);render();}
    if(name==='test-dingtalk'){const result=await api('channels/dingtalk/test',{method:'POST',body:{}});toast(result.message||`钉钉测试：${human(result.status||result.delivery?.status||'accepted')}`,['failed','unknown'].includes(result.status));await refreshData();}
    if(name==='export-config'){const config=await api('config/export');const blob=new Blob([JSON.stringify(config,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='stockradar-config.json';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),5000);toast('配置已导出。密钥不会包含在导出文件中。');}
  });
});
if(state.token)connect(state.token);
