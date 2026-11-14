const boardNames = {MAIN:'沪深主板', CHINEXT:'创业板', STAR:'科创板'};

export function boardScope(boards) {
  return Array.isArray(boards) && boards.length
    ? boards.map(board => boardNames[board] || board).join(' · ')
    : '股票范围未知';
}

export function setupPanel(data, f) {
  const {e,tag,human,datetime}=f;
  const health=data.health||{}, market=data.connections?.market||[];
  const last=health.dingtalk_last_test;
  const testStatus={accepted:'平台已受理',failed:'测试失败',unknown:'结果未知',sending:'正在发送'};
  return `<div class="setup-grid">
    <section class="panel"><div class="panel-header"><h2>行情连接</h2></div><div class="panel-body">
      ${market.length?market.map(profile=>{
        const configured=profile.credential?.configured;
        const label=profile.credential?.error?'凭据需核对':!configured?'尚未配置':!profile.authorization?.confirmed?'待确认访问依据':profile.last_test?.status==='reachable'?'连接可达':'待验证连接';
        return `<div class="metric-line"><span class="key">${e(profile.name)}</span>${tag(label==='连接可达'?'good':'unverified',label)}</div>`;
      }).join(''):'<p class="small muted">行情连接状态尚未读取。</p>'}
      <p class="small muted">分钟权限按实际接口单独验收。</p>
      <a class="button" href="#market-api">管理行情连接</a>
    </div></section>
    <section class="panel"><div class="panel-header"><h2>钉钉通知测试</h2>
      ${health.dingtalk_configured==null?tag('unverified','状态未知'):tag(health.dingtalk_configured?'configured':'unconfigured')}</div><div class="panel-body">
      <p>最近测试 <strong>${e(last?testStatus[last.status]||'状态未知':'当前配置暂无测试记录')}</strong>
      ${last?.at?`<span class="small muted"> · ${e(datetime(last.at,true))}</span>`:''}</p>
      ${last?.status==='unknown'?'<p class="notice-block">请先核对群里是否已收到测试消息，再决定是否重发。</p>':''}
      <p class="small muted">${health.dingtalk_configured?'向当前配置的群发送一条标记为测试的消息。':'在服务端设置 DINGTALK_WEBHOOK 和所需的 DINGTALK_SECRET 后重启服务。'}</p>
      <button id="setup-dingtalk-test" class="button" type="button" data-action="test-dingtalk" data-busy-label="正在发送…"${health.dingtalk_configured&&last?.status!=='sending'?'':' disabled'}>发送钉钉测试消息</button>
    </div></section>
    <section class="panel"><div class="panel-header"><h2>运行版本与扫描范围</h2>
      ${health.mode?tag(health.mode,human(health.mode)):tag('unverified','状态未知')}</div><div class="panel-body">
      <div class="metric-line"><span class="key">当前版本</span><strong class="mono">${e(health.strategy_version||'尚未读取')}</strong></div>
      <div class="metric-line"><span class="key">扫描范围</span><strong>${e(boardScope(health.boards))}</strong></div>
      <a class="button" href="#research/strategy-preferences">配置策略草稿</a>
    </div></section>
  </div>`;
}

export function strategyForm(base, versions, draft, saved, f) {
  const {e}=f;
  return `<section id="strategy-preferences" class="panel section-gap" aria-labelledby="strategy-preferences-title">
    <div class="panel-header"><div><h2 id="strategy-preferences-title" tabindex="-1">常用策略配置</h2>
    <p>从已保存的版本创建回放用草稿。</p></div></div>
    <div class="panel-body">${base?`<form id="strategy-preferences-form" class="connection-editor"><fieldset id="strategy-preferences-fields" class="strategy-preferences-fields">
      <div class="connection-field">
        <label for="strategy-base">基准版本</label>
        <select id="strategy-base" class="select" name="base_id" aria-describedby="strategy-base-scope">${versions.map(version=>
          `<option value="${e(version.id)}"${base.id===version.id?' selected':''}>${e(version.id)}</option>`).join('')}</select>
        <p id="strategy-base-scope">继承的扫描范围 · ${e(boardScope(base.config.preferences.boards))}</p>
      </div>
      <div class="strategy-fields">
        <div class="connection-field"><label for="strategy-alert-stage">提醒时机</label>
          <select id="strategy-alert-stage" class="select" name="alert_stage" aria-describedby="strategy-alert-help">
            <option value="early"${draft.alertStage==='early'?' selected':''}>启动预警</option>
            <option value="confirmed"${draft.alertStage==='confirmed'?' selected':''}>确认后提醒</option>
          </select><p id="strategy-alert-help">启动预警更早，确认后提醒需要满足确认条件。</p></div>
        <div class="connection-field"><label for="strategy-daily-limit">每日新机会额度</label>
          <input id="strategy-daily-limit" type="number" name="daily_new_limit" value="${e(draft.dailyLimit)}" min="0" step="1" required aria-describedby="strategy-limit-help">
          <p id="strategy-limit-help">0 表示不限。已发信号的风险更新仍会记录。</p></div>
        <div class="connection-field"><label for="strategy-risk-limit">单笔结构风险上限（%）</label>
          <input id="strategy-risk-limit" type="number" name="max_loss_percent" value="${e(draft.riskPercent)}" min="0" max="10" step="any" required aria-describedby="strategy-risk-help">
          <p id="strategy-risk-help">大于 0 且不超过 10。用于参考价到结构失效位的距离过滤。</p></div>
      </div>
      <p id="strategy-preferences-error" class="form-error" role="alert"></p>
      <div class="connection-actions"><button id="save-strategy-preferences" class="button primary" type="submit" data-busy-label="正在保存…">保存为新实验版本</button>
        ${saved?`<span class="small" role="status">已保存 <strong class="mono">${e(saved)}</strong></span>
        <button class="button" type="button" data-action="focus-replay">前往离线回放</button>`:''}</div>
    </fieldset></form>`:'<p class="small muted">读取到已保存版本后可开始配置。</p>'}</div>
  </section>`;
}

export function strategyDraft(config) {
  return {alertStage:config.research.alert_stage, dailyLimit:String(config.lifecycle.daily_new_limit),
    riskPercent:String(Number((config.preferences.max_loss_fraction*100).toPrecision(15)))};
}

export function preferenceConfig(base, draft, id) {
  if(!['early','confirmed'].includes(draft.alertStage))throw new Error('请选择提醒时机。');
  const dailyLimit=Number(draft.dailyLimit), risk=Number(draft.riskPercent);
  if(!draft.dailyLimit.trim()||!Number.isSafeInteger(dailyLimit)||dailyLimit<0)throw new Error('每日新机会额度须为非负整数。');
  if(!draft.riskPercent.trim()||!Number.isFinite(risk)||risk<=0||risk>10||risk/100===0)throw new Error('单笔结构风险上限须大于 0 且不超过 10%。');
  const config=structuredClone(base);
  Object.assign(config,{id,mode:'replay',purpose:'experimental',status:'draft'});
  config.research.alert_stage=draft.alertStage;
  config.lifecycle.daily_new_limit=dailyLimit;
  if(draft.riskPercent!==strategyDraft(base).riskPercent)config.preferences.max_loss_fraction=risk/100;
  return config;
}
