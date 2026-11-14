// Connection forms keep credentials out of rendered values and persisted browser state.
export function connectionTabs(active) {
  return `<nav class="settings-tabs" aria-label="设置页面">${[['setup','首次设置'],['settings','运行诊断'],['market-api','行情 API'],['minute-data','真实行情'],['models','大模型']].map(([id,label])=>`<a href="#${id}"${id===active?' aria-current="page"':''}>${label}</a>`).join('')}</nav>`;
}

function localModel(profile) {
  try {return profile?.id==='model'&&['localhost','127.0.0.1','[::1]'].includes(new URL(profile.base_url).hostname);} catch {return false;}
}

function keyStatus(profile) {
  const credential=profile?.credential;
  return credential?.error?'配置需修复':credential?.source==='environment'?'使用环境变量':credential?.configured?'本地 Key 已保存':localModel(profile)?'本机服务可不填 Key':'尚未配置 Key';
}

function keyFields(profile,e) {
  const credential=profile.credential||{};
  return `<div class="connection-field"><label for="connection-key">${profile.id==='tushare'?'Token':'API Key'}</label><input id="connection-key" name="api_key" type="password" autocomplete="new-password" spellcheck="false" maxlength="4096" aria-describedby="connection-key-help" placeholder="${credential.configured?'留空保留现有 Key':'粘贴 Key，保存到本机'}"><p id="connection-key-help">${credential.source==='environment'?'当前环境变量优先。本地 Key 更新将在移除环境变量后使用。':'Key 单独保存到本机令牌文件；页面只读取配置状态。'}</p>${credential.local_key_saved?'<label class="connection-check"><input name="clear_key" type="checkbox">清除已保存的本地 Key</label>':''}${credential.error?`<p class="form-error" role="alert">${e(credential.error)}</p>`:''}</div>`;
}

function testResult(profile,h) {
  const result=profile.last_test;
  if(!result)return '<div class="connection-result neutral" role="status"><strong>尚未测试连接</strong><p>保存配置后，按需发起一次连接测试。</p></div>';
  return `<div class="connection-result ${result.status==='reachable'?'good':'warning'}" role="status"><strong>${h.e(result.status==='reachable'?'接口可达':result.status==='model_not_listed'?'请核对模型 ID':result.status==='blocked'?'连接测试未发送':'连接尚未验证')}</strong><p>${h.e(result.message)}</p><span>${h.e(h.datetime(result.tested_at,true))} · ${h.e(result.sent_requests)} 次请求</span></div>`;
}

export function connectionPage(page,connections,selected,drafts,h) {
  const {e,datetime}=h;
  if(!connections)return `${connectionTabs(page)}<section class="panel panel-body connection-loading"><h2>连接配置尚未读取</h2><p>检查本地服务后重新加载，已有配置不会因此被清除。</p><button class="button" data-action="reload-connections">重新加载配置</button></section>`;
  const model=page==='models', providers=connections.market||[], profile=model?connections.model:providers.find(p=>p.id===selected)||providers[0];
  if(!profile)return `${connectionTabs(page)}<p role="alert">连接配置不完整，请刷新后重试。</p>`;
  const draft=drafts[profile.id]||profile, credential=profile.credential||{};
  const selection=model?'':`<aside class="connection-sources" aria-label="行情服务商"><h2>行情服务商</h2><p>分别管理各来源的凭据与访问依据。</p><div class="connection-source-list">${providers.map(p=>`<button type="button" class="connection-source" data-connection-provider="${e(p.id)}" aria-pressed="${p.id===profile.id}"><strong>${e(p.name)}</strong><span>${e(keyStatus(p))}</span></button>`).join('')}</div><p class="connection-footnote">配置供独立研究采样使用。工作台当前行情来源仍以运行诊断为准。</p></aside>`;
  const fields=model?`<div class="connection-field"><label for="connection-url">API 基础地址</label><input id="connection-url" name="base_url" type="url" maxlength="500" value="${e(draft.base_url)}" placeholder="https://服务商地址/v1" spellcheck="false" aria-describedby="connection-url-help"><p id="connection-url-help">填写服务商提供的兼容 API 基础地址。本机服务可填 http://127.0.0.1:11434/v1。</p></div><div class="connection-field-row"><div class="connection-field"><label for="connection-model">模型 ID</label><input id="connection-model" name="model" value="${e(draft.model)}" maxlength="200" placeholder="填写服务商的完整模型 ID" spellcheck="false"></div><div class="connection-field"><label for="connection-timeout">连接超时（秒）</label><input id="connection-timeout" name="timeout_seconds" type="number" min="1" max="30" step="1" value="${e(draft.timeout_seconds)}"></div></div>`:`<div class="connection-field"><label for="connection-url">服务地址</label><input id="connection-url" value="${e(profile.base_url)}" readonly aria-describedby="connection-url-help"><p id="connection-url-help">${e(profile.scope)}</p></div>`;
  const auth=model?'':`<fieldset class="connection-authorization"><legend>个人研究访问</legend><label class="connection-check"><input name="access_confirmed" type="checkbox"${draft.authorization?.confirmed?' checked':''}>已确认目标接口可用于本人的研究采样</label><label for="connection-reference">访问依据</label><textarea id="connection-reference" name="reference" rows="2" maxlength="1000" placeholder="例如：账户已开通的接口权限及允许用途；不要填写 Key">${e(draft.authorization?.reference||'')}</textarea><p>Key 已保存与接口已获权限分别核对；尚未确认时不会发送测试请求。</p></fieldset>`;
  const canTest=model?Boolean(profile.base_url&&profile.model):Boolean(credential.configured&&profile.authorization?.confirmed);
  return `${connectionTabs(page)}<div class="connection-layout${model?' connection-model-layout':''}">${selection}<section class="panel connection-editor" aria-labelledby="connection-editor-title"><div class="panel-header"><div><h2 id="connection-editor-title">${model?'模型连接':e(profile.name)}</h2><p>${model?'兼容 OpenAI API 的服务，可自定义地址和模型。':'保存凭据、核对权限，再按需测试。'}</p></div><span class="tag ${credential.configured||localModel(profile)?'neutral':'warning'}">${e(keyStatus(profile))}</span></div><div class="panel-body"><form id="connection-form" data-page="${e(page)}" data-profile="${e(profile.id)}" data-revision="${e(profile.revision)}">${fields}${keyFields(profile,e)}${auth}<p id="connection-form-error" class="form-error" role="alert"></p><div class="connection-actions"><button class="button primary" type="submit" data-busy-label="正在保存…">保存${model?'模型配置':'行情配置'}</button><button class="button" type="button" data-connection-test="${e(profile.id)}" data-busy-label="正在测试…"${canTest?'':' disabled'}>${model?'检查模型目录':'测试接口连接'}</button><button class="button" type="button" data-action="reset-connection">恢复已保存配置</button><span id="connection-dirty" class="small muted" role="status">${drafts[profile.id]?'有未保存的修改':profile.updated_at?`保存于 ${e(datetime(profile.updated_at,true))}`:'尚未保存配置'}</span></div></form><div id="connection-test-result">${testResult(profile,h)}</div></div></section>${model?'<aside class="connection-guidance"><h2>配置与使用</h2><p>这里管理模型连接，为后续解释功能准备。</p><dl><dt>连接检查</dt><dd>仅获取模型目录，核对所选模型是否列出。不会提交生成请求。</dd><dt>当前使用范围</dt><dd>模型尚未接入解释业务；策略评分、风险过滤和提醒保持确定性计算。</dd><dt>本机服务</dt><dd>本机兼容服务可不填 Key；远程服务使用 HTTPS 和 Key。</dd></dl></aside>':''}</div>`;
}

export function connectionPayload(form,model) {
  const get=name=>form.elements.namedItem(name);
  const secret=get('api_key').value;
  const action=secret?'replace':get('clear_key')?.checked?'clear':'keep';
  const common={schema_version:1,revision:form.dataset.revision,key_action:action,api_key:secret};
  return model?{...common,base_url:get('base_url').value.trim(),model:get('model').value.trim(),timeout_seconds:Number(get('timeout_seconds').value)}:
    {...common,authorization:{confirmed:get('access_confirmed').checked,reference:get('reference').value.trim()||null}};
}

export function connectionDraft(form,model) {
  const get=name=>form.elements.namedItem(name);
  // Deliberately exclude the Key, its replacement action and the clear-Key checkbox.
  return model?{base_url:get('base_url').value,model:get('model').value,timeout_seconds:get('timeout_seconds').value}:
    {authorization:{confirmed:get('access_confirmed').checked,reference:get('reference').value}};
}
