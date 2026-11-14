const vendors={tushare:'Tushare',fuyao:'同花顺 Fuyao',tickflow:'TickFlow',tickflow_free:'TickFlow 免密',
  sina_public:'新浪',eastmoney_public:'东方财富',tencent_public:'腾讯'};
const datasets={daily_bars:'日线',minute_quotes:'最新分钟',intraday:'当日分钟',minute_history:'历史分钟',
  quotes:'报价',instruments:'证券资料',calendar:'交易日历',memberships:'板块关系',adjustment_factors:'复权因子',
  corporate_actions:'公司行为'};
const outcomes={captured:'完整响应',partial:'部分响应',empty:'空响应',failed:'请求失败'};
const outcomeStates={captured:'good',partial:'degraded',empty:'unverified',failed:'failed'};
const requestReasons={RATE_LIMITED:'限流',TRANSPORT_ERROR:'连接异常',AUTHENTICATION_FAILED:'鉴权失败',
  PERMISSION_DENIED:'权限拒绝',VENDOR_PERMISSION_DENIED:'接口权限不足',VENDOR_API_ERROR:'接口返回错误',
  FUYAO_API_ERROR:'接口返回错误',NO_ROWS:'空响应',REQUESTED_SYMBOLS_MISSING:'缺少请求证券',
  EMPTY_SYMBOL_GROUPS:'有证券组为空',PARTIAL_PUBLIC_SNAPSHOT:'仅取得部分数据',
  POSSIBLE_RESPONSE_TRUNCATION:'响应可能截断',SENSITIVE_RESPONSE_SUPPRESSED:'响应已隔离',
  RESPONSE_TOO_LARGE:'响应超出大小上限',RESPONSE_DATA_INVALID:'响应字段无效',OTHER_CAPTURE_ISSUE:'其他采样异常'};
const changes={trading_date:'交易日变化',status:'阶段变化',quality:'数据质量变化',candidate_gate:'候选门槛变化',
  confirm_gate:'确认门槛变化',member_hash:'成分集合变化',source:'来源变化',reason_codes:'依据变化'};
const profileNames={stock_only:'个股规则基线',sector_filter:'板块资格过滤',early:'早期提醒',confirmed:'确认后提醒'};
const weightNames={market:'市场',sector:'板块',stock:'个股',entry:'入场'};
const freezeReasons={REAL_PATH_AND_SHADOW_RELEASE_EVIDENCE_REQUIRED:'待补真实路径与影子证据',
  SYNTHETIC_DATA_ONLY:'合成样本',RULES_AND_COSTS_NOT_VERIFIED:'待核验执行规则与成本',
  HOLDOUT_EVIDENCE_INSUFFICIENT:'样本外证据不足'};
const caseReasons={CALENDAR_WINDOW_INCOMPLETE:'交易日历尚未覆盖完整持有期',
  SETTLEMENT_CALENDAR_INCOMPLETE:'缺少结算后的可卖出交易日',TARGET_CLOSE_MISSING:'目标交易日收盘行情缺失',
  EXIT_NOT_YET_EXECUTABLE_OR_WINDOW_INCOMPLETE:'退出尚不可执行或持有期行情不完整',
  NO_EXECUTABLE_QUOTE_BEFORE_TTL:'参与窗口内缺少可成交行情',EXPIRED_BEFORE_REACTION:'反应时点已超出参与窗口',
  SIGNAL_NOT_ACTIONABLE:'信号当时不可参与',OUTSIDE_ENTRY_RANGE:'价格超出参与区间',
  HOLDING_WINDOW_END:'固定持有期结束',STRUCTURE_OR_COST_RISK:'触发结构或成本风险退出'};

export function sourceHealthPanel(data,error,f) {
  const {e,tag,number,percent,datetime,empty}=f;
  const header=`<div class="panel-header"><div><h2>数据源健康</h2><p>按供应商、数据集和接口核对本机采样历史</p></div>
    <button id="refresh-source-health" class="button" data-action="load-source-health" data-busy-label="读取中…">${data?'刷新本机记录':'读取本机记录'}</button></div>`;
  const rows=data?.items||[];
  const body=rows.length?rows.map(item=>{
    const counts=item.status_counts, quality=item.minute_quality;
    const minute=['minute_quotes','intraday','minute_history'].includes(item.dataset);
    return `<details class="history-record"><summary><strong>${e(vendors[item.provider]||item.provider)} · ${e(datasets[item.dataset]||item.dataset)}</strong>
      <span class="mono">${e(item.operation)}</span>${tag(outcomeStates[item.latest_status]||'unverified',outcomes[item.latest_status]||'未知')}
      <span>完整响应 ${number(counts.captured??0)} / ${number(item.attempt_count)}</span>${item.simulated?tag('unverified','模拟样本'):''}</summary>
      <div class="history-record-body">
        <p>最近完整响应 ${e(datetime(item.last_success_at,true))} · 限流 ${number(item.limited_count)} 次
          · 部分 ${number(counts.partial??0)} · 空响应 ${number(counts.empty??0)} · 失败 ${number(counts.failed??0)}</p>
        ${minute?`<p><strong>诊断样本有效分钟</strong> ${quality?.coverage!=null?`${percent(quality.coverage)}（${number(quality.usable_minutes)} / ${number(quality.expected_minutes)}）`:'待核验日历与分钟口径'}
          ${quality?`<span class="muted"> · ${e(datetime(quality.at,true))}</span>`:''}</p>`:''}
        ${quality?.max_observed_delay_seconds!=null?`<p>最新分钟首次观测最大间隔 ${number(quality.max_observed_delay_seconds,1)} 秒
          · 样本 ${number(quality.delay_observations)}
          ${quality.delay_budget_seconds!=null?` · 超出 ${number(quality.delay_budget_seconds)} 秒预算 ${number(quality.late_count)} 次`:' · 延迟预算待定'}</p>`:''}
        <h3>最近请求</h3><ul class="history-list">${item.recent.map(row=>`<li>
          <span>${e(datetime(row.received_at||row.started_at,true))}</span><strong>${e(outcomes[row.status]||'未知')}</strong>
          ${row.reason_code?`<span>${e(requestReasons[row.reason_code]||row.reason_code)}</span>`:''}
          <span class="code-tag" title="${e(row.report_hash)}">报告 ${e(row.report_hash.slice(0,12))}</span></li>`).join('')}</ul>
        ${quality?`<p class="code-tag">诊断报告 ${e(quality.report_hash)}</p>`:''}
      </div></details>`;
  }).join(''):data?empty('尚无接口请求记录','可在分钟行情保存一组样本，或将已有采样报告放入本机资料目录。')
    :'<p class="small muted">读取后可核对最近成功时间、请求结果和已诊断的有效分钟分母。</p>';
  return `<section class="panel section-gap">${header}<div class="panel-body">${error?`<p class="form-error" role="alert">${e(error)}</p>`:''}
    ${data?`<p class="chart-caption">已读取 ${number(data.capture_count)} 份采样报告
      ${data.ignored_count?` · ${number(data.ignored_count)} 份记录无法校验`:''}
      ${data.older_capture_count||data.older_quality_count?' · 当前窗口仅展示较近的报告':''}。次数按已发请求统计，覆盖率来自匹配的分钟诊断。</p>`:''}
    ${body}<a class="button history-link" href="#minute-data">前往分钟行情</a></div></section>`;
}

export function sectorTimeline(data,f) {
  const {e,datetime,tag,number,percent,reason}=f;
  return `<p class="chart-caption">最近 ${number(data.scanned_slices)} 个已保存切片${data.limited?' · 窗口已截取':''}
      · 版本 <span class="mono">${e(data.strategy_version)}</span></p>
    <ol class="timeline">${data.events.map((event,index)=>{
      const m=event.metrics, label=event.changes.map(key=>changes[key]||key).join(' · ')||(index===0?'窗口首条':'最新切片');
      const recovered=event.quality==='good'&&['paused','missing'].includes(data.events[index-1]?.quality);
      return `<li><time datetime="${e(event.as_of)}">${e(datetime(event.as_of,true))}</time><strong>${e(label)}</strong>
        <div class="history-tags">${event.status?tag(event.status):''}${event.quality==='paused'?tag('paused','数据暂停'):''}
          ${recovered?tag('good','数据恢复'):''}
          ${event.quality==='missing'?tag('unknown','切片缺少板块'):''}${event.simulated===true?tag('unverified','模拟'):''}</div>
        <p>相对强度 ${percent(m.rs,2,true)} · 改善 ${percent(m.delta_rs,2,true)} · 广度 ${percent(m.breadth)}
          · 同期量能 ${number(m.rvol,2)} · 有效成分 ${number(m.valid_count)} / ${number(m.member_count)}</p>
        ${event.quality==='good'?`<p>候选门槛 ${event.candidate_gate===true?'通过':'未通过'} · 确认门槛 ${event.confirm_gate===true?'通过':'未通过'}</p>`:''}
        ${event.reason_codes.length?`<p>${event.reason_codes.map(code=>e(reason(code))).join(' · ')}</p>`:''}
        ${event.leaders.length?`<p>当时涨幅靠前 ${event.leaders.map(stock=>`${e(stock.name||stock.code||'未知')} ${e(stock.code||'')} ${percent(stock.return,2,true)}`).join(' · ')}</p>`:''}
        <p class="code-tag">${e(event.source||'来源未知')} · ${e(event.snapshot_id)}</p></li>`;
    }).join('')}</ol>`;
}

function windowLabel(window) {
  return `样本外 · 反应 ${window.delay_minutes} 分钟 · ${window.holding_days} 个交易日 · 固定退出`;
}

export function studyCardsPanel(data,error,f) {
  const {e,empty,tag,number,percent,datetime,reason,jsonDetails}=f;
  const cards=data?.items||[];
  return `<section class="panel section-gap"><div class="panel-header"><div><h2>研究策略卡</h2>
    <p>按固定配置查看多次研究、成熟分母和代表案例</p></div>
    <button id="refresh-study-cards" class="button" data-action="load-study-cards" data-busy-label="读取中…">${data?'刷新策略卡':'读取策略卡'}</button></div>
    <div class="panel-body">${error?`<p class="form-error" role="alert">${e(error)}</p>`:''}
    ${data?`<p class="chart-caption">已读取 ${number(data.report_count)} 份独立报告${data.skipped_count?` · ${number(data.skipped_count)} 份未纳入预览`:''}。每次研究单独显示样本和收益。</p>`:''}
    ${cards.length?cards.map(card=>{
      const latest=card.runs[0];
      return `<details class="history-record"><summary><strong>${e(profileNames[card.profile_id]||card.profile_id)}</strong>
        ${tag('unverified',card.simulated?'合成研究':'自备数据研究')}
        <span>已闭合 ${number(latest.counts.closed_count)} / ${number(latest.counts.eligible_denominator)} · 超额 ${percent(latest.benchmark_excess.mean,2,true)}</span></summary>
        <div class="history-record-body"><p class="code-tag">${e(card.strategy_version)} · ${e(card.config_hash)}</p>
        <p>基准 ${e(card.requirements.benchmark_id)} · ${card.requirements.sector_filter?'启用板块资格':'个股资格基线'}
          · ${Object.entries(card.weights).map(([name,weight])=>`${e(weightNames[name]||name)} ${percent(weight,0)}`).join(' · ')}</p>
        ${card.runs.map(run=>`<div class="history-run">
          <strong>${e(run.dataset_id)} / ${e(run.plan_id)}</strong><p>${e(datetime(run.created_at,true))} · ${e(windowLabel(run.window))}</p>
          <p>测试区间 ${e(datetime(run.split_start,true))} 至 ${e(datetime(run.split_end,true))}</p>
          <p>闭合 ${number(run.counts.closed_count)} / ${number(run.counts.eligible_denominator)}
            · 待定 ${number(run.counts.status_counts.pending??0)} · 未成交 ${number(run.counts.status_counts.not_filled??0)}
            · 跨段剔除 ${number(run.counts.status_counts.purged??0)}
            · 净收益 ${percent(run.net_return_mean,2,true)} · 超额 ${percent(run.benchmark_excess.mean,2,true)}
            （分母 ${number(run.benchmark_excess.denominator)}）</p>
          <p>结构失效 ${number(run.counts.structure_failures)} / ${number(run.counts.structure_failure_denominator)}
            · 负净收益 ${number(run.counts.revenue_failures)} / ${number(run.counts.revenue_failure_denominator)}</p>
          <p>${run.freeze_reasons.map(code=>e(freezeReasons[code]||reason(code))).join(' · ')}</p>
          ${jsonDetails({plan_hash:run.plan_hash,data_hash:run.data_hash,code_hash:run.code_hash,output_hash:run.output_hash,
            reason_counts:run.counts.reason_counts,observation_gaps:run.observation_gaps},'查看样本缺口与报告标识')}
          <div class="history-actions"><button class="button" data-study-id="${e(run.job_id)}" data-card-delay="${e(run.window.delay_minutes)}"
            data-card-horizon="${e(run.window.holding_days)}">打开研究比较</button>
            <button class="button" data-case-study="${e(run.job_id)}" data-case-profile="${e(card.profile_id)}">查看案例</button></div>
        </div>`).join('')}</div></details>`;
    }).join(''):data?empty('尚无可展示的研究报告','完成成本研究后，可从这里查看各策略版本的结果和案例。')
    :'<p class="small muted">读取已保存的研究报告后，按版本查看样本外结果。</p>'}</div></section>`;
}

export function studyCaseList(data,f) {
  const {e,datetime,number,percent,price,reason,tag,empty}=f;
  return `<p class="chart-caption">${e(windowLabel(data.window))} · ${data.simulated?'合成研究':'自备数据研究'}</p>
    <p class="small muted">符合条件的失效或负收益样本 ${number(data.failure_count)} 条，待定或未成交 ${number(data.unresolved_count)} 条。
      展示最多 6 条失败案例及 4 条待核对案例。</p>
    ${data.items.length?data.items.map(sample=>{
      const signal=sample.signal, state=sample.status==='closed'
        ?[sample.structure_failure?'结构失效':null,sample.revenue_failure?'负净收益':null].filter(Boolean).join(' · ')
        :sample.status==='pending'?'待定':'未成交';
      const cause=sample.reason_code||sample.exit?.reason;
      const leg=value=>value?`${e(datetime(value.at,true))} · ¥${price(value.price)}`:'—';
      return `<article class="history-case"><div class="history-tags"><strong>${e(signal?.name||'历史案例')}</strong>
        <span class="mono">${e(signal?.code||'')}</span>${tag(sample.status==='closed'?'failed':'pending',state)}</div>
        <p>触发 ${e(datetime(signal?.trigger_time,true))} · 首次提醒 ${e(datetime(signal?.first_alert_at,true))}</p>
        <p>入场 ${leg(sample.entry)} · 退出 ${leg(sample.exit)}</p>
        <p>净收益 ${percent(sample.net_return,2,true)} · 超额 ${percent(sample.benchmark_excess,2,true)}</p>
        ${cause?`<p>${e(caseReasons[cause]||reason(cause))}</p>`:''}
        <p class="code-tag">信号 ${e(sample.signal_id)}${signal?.snapshot_id?` · 触发快照 ${e(signal.snapshot_id)}`:''}</p></article>`;
    }).join(''):empty('该窗口暂无代表案例')}
    <p class="code-tag">研究报告 ${e(data.output_hash)}</p>`;
}
