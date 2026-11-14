// Coordinates only: strategy levels and candle eligibility come from the API.
export function evidenceChart(chart, f) {
  if (!chart) return '';
  const {e, price, number, datetime, timeOnly, human, jsonDetails} = f;
  const numeric = value => value === null || value === undefined || value === '' || typeof value === 'boolean' ? NaN : Number(value);
  function view(data, key) {
    const candles = (data?.candles || []).filter(q => ['open','high','low','close'].every(k => Number.isFinite(numeric(q[k]))) && Number.isFinite(Date.parse(q.event_time)));
    if (!candles.length) return `<p class="notice-block">此视图没有可展示的完成分钟。缺失行情保持未知，请查看记录中的原因。</p>${jsonDetails(data?.reason_counts || {},'查看未展示原因')}`;
    const levels = [['breakout','冻结突破位 H'],['invalidation','冻结失效位 S']].map(([key,label]) => ({key,label,value:numeric(chart.levels?.[key])})).filter(item=>Number.isFinite(item.value));
    const values = [...candles.flatMap(q=>[numeric(q.high),numeric(q.low)]),...levels.map(item=>item.value)];
    const low = Math.min(...values), high = Math.max(...values), padding = Math.max((high-low)*0.12,high*0.001);
    const bottom = low-padding, top = high+padding;
    const start = Date.parse(candles[0].event_time), end = Date.parse(candles.at(-1).event_time);
    const x = at => end===start ? 305 : 62+(Date.parse(at)-start)/(end-start)*480;
    const y = value => 212-(numeric(value)-bottom)/(top-bottom)*182;
    const barWidth = Math.min(14, Math.max(2,460/candles.length*0.55));
    const amounts = candles.map(q=>numeric(q.amount_cny)).filter(Number.isFinite);
    const maxAmount = Math.max(1,...amounts);
    const grid = [bottom,(top+bottom)/2,top].map(value=>`<line class="chart-grid" x1="58" x2="548" y1="${y(value)}" y2="${y(value)}"/><text x="3" y="${y(value)+4}">${e(price(value))}</text>`).join('');
    const reference = levels.map(item=>`<line class="chart-reference ${item.key}" x1="58" x2="548" y1="${y(item.value)}" y2="${y(item.value)}"/><text x="552" y="${y(item.value)+4}">${item.key==='breakout'?'H':'S'} ${e(price(item.value))}</text>`).join('');
    const bodies = candles.map(q=>{
      const cx=x(q.event_time), up=numeric(q.close)>=numeric(q.open), cls=up?'chart-up':'chart-down';
      const label=`${datetime(q.event_time,true)} ${up?'上涨或平盘':'下跌'}，开 ${q.open}，高 ${q.high}，低 ${q.low}，收 ${q.close}`;
      const amount=numeric(q.amount_cny);
      return `<g class="${cls}"><title>${e(label)}</title><line x1="${cx}" x2="${cx}" y1="${y(q.high)}" y2="${y(q.low)}"/><rect x="${cx-barWidth/2}" y="${Math.min(y(q.open),y(q.close))}" width="${barWidth}" height="${Math.max(1,Math.abs(y(q.open)-y(q.close)))}"/>${Number.isFinite(amount)?`<rect class="chart-amount" x="${cx-barWidth/2}" y="${280-amount/maxAmount*32}" width="${barWidth}" height="${amount/maxAmount*32}"/>`:''}</g>`;
    }).join('');
    const markers=(data.events||[]).filter(event=>Date.parse(event.at)>=start && Date.parse(event.at)<=end).map(event=>`<g><title>${e(datetime(event.at,true))} ${e(human(event.status))} · revision ${e(event.revision)}</title><path class="chart-event" d="M ${x(event.at)-4} 18 l 8 0 l -4 7 z"/></g>`).join('');
    const times=[candles[0],candles[Math.floor(candles.length/2)],candles.at(-1)].filter((q,index,all)=>all.findIndex(item=>item.event_time===q.event_time)===index).map(q=>`<text x="${x(q.event_time)}" y="232" text-anchor="middle">${e(timeOnly(q.event_time))}</text>`).join('');
    return `<div class="chart-scroll" tabindex="0" role="region" aria-label="分钟K线，可横向滚动"><svg class="evidence-chart" viewBox="0 0 640 300" role="img" aria-labelledby="chart-${key}-title"><title id="chart-${key}-title">${e(chart.trading_date)} 已保存分钟K线，含冻结突破位H、失效位S和状态事件</title>${grid}${reference}${bodies}${markers}${times}<text x="58" y="296">同分钟累计成交额（元），柱高仅用于展示</text></svg></div><p class="chart-caption">${candles.length} 个完成分钟 · 北京时间 · 截至 ${e(datetime(data.as_of,true))}${data.limited?' · 仅显示最近120个点':''}<br>红色实线为涨或平，绿色为跌；三角标记对应下方状态时间线。时间缺口保留。</p><details class="json-details"><summary>查看K线数值、来源与可见时间</summary><div class="signal-table-wrap"><table class="data-table"><thead><tr><th>分钟（北京）</th><th>开 / 高 / 低 / 收</th><th>累计成交额</th><th>来源 / 修订</th><th>可见 / 接收时间</th></tr></thead><tbody>${candles.map(q=>`<tr><td>${e(datetime(q.event_time,true))}</td><td>${['open','high','low','close'].map(k=>e(q[k])).join(' / ')}</td><td>${number(q.amount_cny,2)}</td><td>${e(q.source)} / ${e(q.revision)}</td><td>${e(datetime(q.available_at,true))}<br>${e(datetime(q.ingested_at,true))}</td></tr>`).join('')}</tbody></table></div>${jsonDetails({snapshot_id:data.snapshot_id,input_hash:data.input_hash,reason_counts:data.reason_counts},'查看来源快照与未展示原因')}</details>`;
  }
  return `<section class="detail-section"><h3>分钟K线与冻结证据</h3><p class="small muted">${chart.simulated?'合成行情 · ':''}${e(chart.trading_date)} · 同一复权基准 ${e(chart.adjustment_factor ?? '未知')}。参考位冻结于 ${e(datetime(chart.levels?.frozen_at,true))}。</p><h4 class="chart-view-title">触发时可见</h4>${view(chart.trigger,'trigger')}<details class="chart-latest"><summary>查看截至最近扫描的行情</summary><p class="small muted">后续行情仅用于跟踪，单独保留原触发视图。</p>${view(chart.latest,'latest')}</details><p class="chart-caption">${(chart.limitations||[]).map(e).join('；')}。</p></section>`;
}
