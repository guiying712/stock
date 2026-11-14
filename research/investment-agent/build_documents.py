"""Build the Markdown research catalogue from captured evidence and editorial notes."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
records = json.loads((ROOT / 'sources/manifest.json').read_text())
# repo | category | purpose | dependencies | intended reuse | validation | priority
NOTES = '''sngyai/Sequoia-X|规则选股|A 股日线形态扫描，包含海龟突破、均线放量、旗形、RPS 等策略，增量更新后推送飞书|Python ≥3.10；BaoStock；SQLite；飞书 Webhook|研究确定性筛选规则、策略基类、增量更新和盘后任务；许可确认前仅参考设计|核对复权口径、交易日增量和重复执行；用冻结行情检查每个信号是否只使用当时可见数据|P1
YoungCan-Wang/WyckoffTradingAgent|量价分析|威科夫量价分析、A 股筛选，提供 CLI、MCP、React Web 与桌面形态|Python ≥3.11；TickFlow；云端涉及 Supabase、Cloudflare 等服务|借鉴形态证据、持仓诊断、信号复盘；是否复用代码先评估 AGPL 及具体部署方式|用相同 K 线复现形态；区分本地可用功能与云端会员功能，测数据 Key 缺失时的降级|P1
simonlin1212/Vibe-Research|综合投研|覆盖 A 股、美股、港股的复盘、产业研究、候选池、个股深挖、研究记录、自选与持仓|TypeScript / React + Vite；Node 与 Python ≥3.11；模型 API 或受支持 CLI；外部数据端点|优先验证产品流程与研究产物归档，重点参考持仓流水、研究记录和来源展示|完整跑通一次自选股研究；验证持仓 CSV 导入、前导零、币种、重复流水和备份；计量单次耗时与模型成本|P0
shy3130/tick-stock-panel|策略工作台|自托管的 A 股策略、监控、因子研究与回测；README 明确定位本地量化研究方案|Python ≥3.11、FastAPI、Polars、Parquet；React 18；Docker；TickFlow / fuyao / TdxQuant 等数据插件|候选策略服务底座，重点参考数据能力路由、扩展契约与回测界面|使用冻结行情跑一个策略，检查同一数据在信号、图表、回测中口径一致；测插件断开和历史缺口|P0
Open-Dev-Society/OpenStock|行情界面|行情展示、股票关注与提醒、公司信息；README 明确其不是券商平台|Next.js 15、React 19、Node 22、MongoDB、Finnhub Key；部分通知与 AI 功能需要其他服务|参考自选列表、公司详情和提醒交互；代码接入先评估 AGPL|核对目标市场覆盖、行情延迟、限流和提醒是否真实发送；不能据此推断具备下单能力|P2
wbh604/UZI-Skill|分析方法与报告|A 股、港股、美股分析 Skills，包含多视角评审、估值及结构化报告|Python ≥3.10；Agent 宿主；akshare、yfinance、公告与公开网站；部分源需要登录或 Key|选择少量可解释分析维度和报告模板，独立封装为受控工具|检查缺数据时是否保持缺失而非生成估值；复核数值计算、来源链接、时点与评分校准|P1
run-bigpig/jcp|桌面产品参考|AI A 股分析桌面应用，多 Agent、记忆和 MCP 扩展|Go + Wails；React 18、TypeScript、Vite；模型配置|参考桌面工作区、记忆和工具组织，不作为默认主干候选，因为仓库已归档|若进入候选，先验证当前 macOS 可构建、依赖可解析和数据接口可用；同时核对版权声明来源|P2
hsliuping/TradingAgents-CN|中文 Agent 应用|中文分析与自然语言选股，v3.0 采用社区版/Pro 版及分层授权|Python 3.11、FastAPI、Vue 3、MongoDB、Redis；Tushare / AKShare / BaoStock；模型凭据|参考中文场景；只在明确目录许可边界后评估核心组件，应用层不得默认按 Apache 复制|逐目录建立许可清单；检查核心引擎能否独立运行，避免把专有 app/frontend/core 带入可分发产品|P2
TauricResearch/TradingAgents|Agent 编排|分析师、多空研究员、交易员与组合管理角色协作；支持结构化输出、决策日志和断点恢复|Python、LangGraph、多种 LLM 提供商；市场数据工具|优先验证研究编排与结构化决策接口；保留独立于 LLM 的计算、风控和执行服务|对相同冻结数据重复运行，检查引用、输出 schema、恢复幂等、调用预算；区分交易建议和真实成交|P0
ZhuLinsen/daily_stock_analysis|日常分析与推送|多市场行情、新闻、决策看板、盘后复盘与定时通知|Python、FastAPI；AkShare、Tushare、Pytdx、BaoStock、YFinance、Longbridge；模型与通知配置|优先验证每日研究任务、数据回退和通知链路，作为最小闭环候选|自选池任务连续运行；主数据源失败时保留来源/时点；通知重试不重复；统计延迟和成本|P0
vnpy/vnpy|交易框架|Python 量化框架，提供多市场交易网关及策略生态，README 列出独立本地仿真模块|Python ≥3.10（README 推荐 3.13）；具体网关和仿真组件常在独立仓库；券商账户/平台要求待核实|第二阶段评估交易网关和模拟成交；独立进程适配，避免把 GUI 框架直接耦合进 Web 产品|按目标券商验证网关、macOS/远程执行兼容性、授权、委托回报、撤单与断线对账；审查外部模块许可|P1
microsoft/qlib|量化研究|特征、模型、数据处理、实验与回测研究流程|Python；历史数据集；不同模型有不同依赖；README 提醒 artifact loading 存在未发布破坏性变更|第三阶段引入离线因子研究和可复现实验，独立环境运行|时间顺序训练/验证/测试；防止财报时点泄漏、幸存者偏差；与简单基线比较并计入交易成本|P1
nautechsystems/nautilus_trader|事件驱动交易|Rust 交易运行时与 Python 策略控制，面向事件驱动研究和执行|Rust / Python / PyO3；具体交易适配器；默认 develop 分支包含 v2 RC 说明|作为后续执行/仿真引擎备选，与 vnpy 按券商覆盖、运行平台和事件一致性比较|固定 v1 稳定版或 v2 RC 之一并匹配文档；验证订单生命周期、恢复重放和市场适配；勿混用两代 API|P2
shiyu-coder/Kronos|金融时序模型|基于行情序列的预测模型，含模型加载、微调及 A 股数据示例|Python ≥3.10；模型权重下载；微调涉及 GPU；数据准备与回测工具|作为可替换信号研究实验，不作为第一版决策核心|核对权重许可、硬件成本、训练数据区间；严格样本外评测、成本后收益与无模型基线比较|P2
HKUDS/Vibe-Trading|综合交易 Agent|个人交易 Agent 平台；README 涵盖研究、因子、回测与交易执行场景|Python ≥3.11、FastAPI、React 19；模型、行情与目标 broker 的配置|参考跨研究/回测/执行的产品组织与失败处理；先验证局部功能，避免整库引入过大范围|复核缺失行情、复权标记、订单异常和重启恢复；仅在模拟环境验证 README 声称的执行能力|P1
virattt/ai-financial-agent|投研聊天界面|教育与研究用途的金融 Agent 概念验证，聊天中展示行情和基本面|TypeScript、pnpm、Vercel AI SDK；OpenAI、Financial Datasets、LangSmith 配置|参考研究问答与生成式 UI；数据提供商依赖单独封装|复核 API 覆盖/费用与当前可用性、流式工具调用和来源展示；不能当作现成交易系统|P2
simonlin1212/a-stock-data|数据工具|以结构化 Markdown 与内嵌 Python 组织 A 股及相关市场数据入口；涵盖行情、财务、公告、研报等|Python ≥3.9；多外部数据源；iwencai 需 Key；部分 TCP 数据源有地域网络限制|优先梳理数据字典并封装成普通代码适配器，避免运行时直接执行任意 Skill 片段|逐个核实 MVP 必需端点的可用性、单位、复权、公告时间、限流和错误值；免费访问不等于数据可再分发|P0
wilsonfreitas/awesome-quant|资源索引|量化金融库、数值工具和研究资源目录|文档/链接索引；每个外部项目独立评估|保留为工具发现入口，不加入产品运行依赖|若选中列表中的其他库，另建版本、许可和可用性档案；不能继承本目录的许可判断|P2
zgwl/chinese-buy-us-stock-guide|背景资料|面向中国大陆读者的美股开户、银行、券商及税务等科普资料|Markdown 资料，不是软件或券商接口|只用作产品需求背景和问题清单，不直接作为开户、税务或资金路径建议来源|实际涉及开户、税务或券商准入时重新核查官方最新资料；正文复用前明确许可|P2
TNT-Likely/PanWatch|盯盘提醒与投研工作台|自托管盯盘、价格条件提醒、定时报告、TradingAgents 深度分析与模拟盘；上游覆盖 A 股、港股、美股|Python ≥3.11；FastAPI、SQLAlchemy、APScheduler；React 18、TypeScript、Vite；Node 24.14.0、pnpm 9.15.9；efinance、akshare、本地 marketdata 包；深度分析依赖 TradingAgents v0.7.0|P1 资料参考：重点比较价格规则、冷却/到期、钉钉通知、来源质量及模块边界；观势继续保持确定性 evaluate 与当前标准库技术栈，不扩展到上游多市场、持仓或聊天范围|固定快照逐项复核数据时点、缺失/修订、冷却幂等、投递 unknown 和重启；采用 fake notifier；不把日历、量能或成交规则直接照搬为观势能力|P1'''
notes = {v[0]: v[1:] for v in (line.split('|') for line in NOTES.splitlines())}
notes['ZhuLinsen/alphasift'] = [
    '候选筛选与日线效果研究',
    '市场快照候选筛选、可审阅 YAML 策略、行业分散、可选 LLM 排序与保存运行后的 T+N 评价',
    'Python 3.10+，pandas、PyYAML、LiteLLM、efinance、AKShare、BaoStock、Tushare、yfinance 和 requests',
    '资料参考。重点核对来源健康、缓存年龄、规则配置和 T+N 成熟分母',
    '以冻结样本核对单位、陈旧回退和完成性，再核验日线评价的成熟窗口、同期基准与成本/执行口径',
    'P1',
]
notes['Weaxs/stock-analysis-plugin'] = [
    '行情路由与策略回测',
    '多市场行情、选股和策略回测工具，多个 Agent 宿主共享 Python CLI',
    'Python 3.10+，pandas、NumPy、PyYAML、exchange-calendars 及多个行情库',
    '资料参考。按报价、K 线和指数选择回退链路，记录数据时点与复权口径。研究保留成交假设、费用与基准',
    '用冻结样本核对权限、完成分钟、单位、时点和复权一致性，再校验研究窗口、成交资格与基准覆盖',
    'P1',
]
notes['suifei/dsh-market-lens'] = [
    '盯盘面板与后台价格提醒',
    'DeepSeek Harness 内的自选股、行情图表及宿主价格提醒',
    'DeepSeek Harness、React 面板及 Node 宿主',
    '参考宿主共用行情服务、轮询与请求去重、规则静默期以及提醒跳转',
    '在隔离样本下核对时点、缺失、请求去重、冷却和重启恢复',
    'P1',
]
notes['theBigGavin/marketingdashboard'] = [
    '市场看板与热点下钻',
    '市场概览、板块排行、成分股、资金流及快讯的一屏看板',
    'React 19、Vite、TypeScript 和 Node.js 数据代理',
    '参考板块到代表股的下钻和多面板共享报价快照',
    '用冻结切片核对面板时点一致性、陈旧状态及窄屏与键盘操作',
    'P1',
]
notes['MiniBtMaster/pylightcharts'] = [
    '金融图表与交互',
    'Python 通过 WebView 桥接 Lightweight Charts，提供 K 线、标记、窗格和联动',
    'Python 3.9+、pandas、NumPy、pywebview',
    '参考触发事件标记、价量同轴定位、十字线同步和增量更新',
    '用合成切片核对冻结价格、数据时点、窄屏与键盘操作',
    'P1',
]
notes['myhhub/stock'] = [
    '日线筛选与指标研究',
    'InStock 的 A 股及 ETF 日线、技术指标、形态筛选和回测',
    'Python、pandas、TA-Lib、MySQL、Tornado 和 Bokeh',
    '参考指标与形态条件的可视化及离线选股验证',
    '固定价格和复权输入，核对指标预热、缺失处理与信号分母',
    'P1',
]
notes['Luciferbobo/KiT'] = [
    '金融时序模型',
    '用流匹配生成多预测周期的 K 线路径，并提供离线推理与回测示例',
    'Python 3.10+、PyTorch 2.4+、CUDA GPU 及独立发布的模型权重',
    '参考按历史锚点切窗、多周期评价和同期基准',
    '核对训练截止、样本重叠和数据授权，在冻结输入上复测',
    'P2',
]
notes.update({
    'Jakeschincariol/day-trader-skill': [
        '日内研究与回放', '日内扫描、风险检查、历史形态匹配和重采样回放',
        'Claude 技能宿主与标准库 Python 工具', '参考冻结信号时点和失败案例回放',
        '核对重采样假设、可见时点和结果分母', 'P1',
    ],
    'mvanhorn/last30days-skill': [
        '多源资讯研究', '聚合多个来源的主题资讯与互动数据',
        'Python 3.12+，Agent 技能宿主或 MCP', '参考来源、发布时间和缺源状态',
        '核对重复转述、采集窗口和引用准确性', 'P2',
    ],
    'Fincept-Corporation/FinceptTerminal': [
        '桌面金融研究终端', '图表、研究面板、可视化工作流和 MCP',
        'C++20、Qt6、内嵌 Python 3.11', '参考市场概览到研究证据的导航',
        '核对来源标注、桌面运行成本和数据权限', 'P2',
    ],
    'freqtrade/freqtrade': [
        '量化回测与偏差诊断', '加密货币策略框架及历史回测工具',
        'Python 3.12+，行情及交易所数据依赖', '参考前视偏差和预热敏感性诊断',
        '用冻结输入复现未来数据泄漏和预热不足案例', 'P2',
    ],
    'openbq-org/OpenBB': [
        '金融数据基础设施', '通过供应商扩展向 Python、REST 和 MCP 提供数据',
        'Python 3.11+ 和供应商扩展', '参考按数据集声明能力和记录来源',
        '核对目标数据集的授权、时点、单位及完成性', 'P1',
    ],
})
license_overrides = {
    'sngyai/Sequoia-X': 'README 声称 MIT；API 未识别许可证，常见根目录许可文件未取到，待确认',
    'run-bigpig/jcp': 'LICENSE 文本为 MIT；API 为 NOASSERTION，版权头来源需复核',
    'hsliuping/TradingAgents-CN': '混合授权：指定目录 Apache-2.0；app/、frontend/、core/ 为专有许可',
    'virattt/ai-financial-agent': 'LICENSE 引用 Apache-2.0；API 为 NOASSERTION，保留文本并待完整复核',
    'wilsonfreitas/awesome-quant': '未确认：API 无许可证，常见根目录许可文件未取到',
    'zgwl/chinese-buy-us-stock-guide': '未确认：API 无许可证，常见根目录许可文件未取到',
    'ZhuLinsen/alphasift': 'Apache-2.0，API、根目录与包声明一致',
    'Weaxs/stock-analysis-plugin': 'MIT，根目录与 Python、npm 包声明一致',
    'MiniBtMaster/pylightcharts': 'MIT，内嵌图表引擎为 Apache-2.0',
}

catalogue = [f'# {len(records)} 个参考项目：研发选型档案', '',
    '2026-10-28 初始采集 19 个公开 Star 项目。按用户提供的 URL 于 2026-10-29 增补 PanWatch，11-09 增补 AlphaSift，11-10 增补 stock-analysis-plugin，11-11 增补 dsh-market-lens 和 marketingdashboard，11-12 增补 pylightcharts、InStock 和 KiT，11-13 从金融与 AI 推荐清单增补五项。日期按 America/Los_Angeles。', '',
    '> 观势是单用户 A 股热点启动与突破提醒工作台。本页 P0/P1/P2 用于资料选型。当前产品范围与任务见[项目规格](../../docs/PROJECT-SPEC.md)和[TODO](../../TODO.md)。', '',
    '证据等级：仓库状态、默认分支和提交编号来自 API；功能、技术栈及依赖来自固定提交的 README；许可证记录来自 API 与下载到的许可文本。本文“拟复用”和“验证任务”是我们的设计判断。尚未安装、运行或审计这些项目，不把 README 的性能、测试数量、免费额度或收益表述当作实测结论。', '',
    'P0 = 第一轮验证；P1 = 后续候选；P2 = 参考或条件成熟后验证。优先级按个人投研 MVP 的适配程度划分，不按 Star 数量或预测收益排序。', '',
    '| 项目 | 类型 | 优先级 | 许可记录 | 上游仓库状态 |', '|---|---|---|---|---|']
registry = []
for i,d in enumerate(records,1):
    repo=d['repo']; m=d['metadata']; n=notes[repo]
    lic=license_overrides.get(repo,(m.get('license') or {}).get('spdx_id','未确认'))
    slug=repo.replace('/','__'); path='projects/'+slug+'.md'
    catalogue.append(f'| [{repo}]({path}) | {n[0]} | {n[5]} | {lic} | '+('已归档' if m.get('archived') else '未归档')+' |')
    pinned=f"https://github.com/{repo}/tree/{d['commit_sha']}"
    readme=f"https://github.com/{repo}/blob/{d['commit_sha']}/{d['readme_path']}"
    text=f'''# {i:02d} · {repo}

## 版本与来源

- 仓库：https://github.com/{repo}
- 固定提交：[查看源码快照]({pinned})，`{d['commit_sha']}`。
- 默认分支：`{m['default_branch']}`。默认分支快照不代表稳定发布版。
- 采集时间（UTC）：{d['retrieved_at_utc']}。
- GitHub pushed_at（UTC）：{m.get('pushed_at','未知')}；该字段不等于已验证的发布频率或维护质量。
- Star：{m.get('stargazers_count','未知')}；Fork：{m.get('forks_count','未知')}；open_issues_count：{m.get('open_issues_count','未知')}（GitHub 该计数含 PR，非未解决 bug 数）。
- 主要语言（API）：{m.get('language') or '未标注'}；归档：{'是' if m.get('archived') else '否'}。
- [固定版本 README]({readme}) · [本地 README](../sources/{slug}/README.txt) · [元数据与哈希](../sources/{slug}/provenance.json)。

## 项目定位与依赖（仓库文档陈述）

{n[1]}。

运行与数据依赖：{n[2]}。

## 在个人投资智能体中的位置（我们的初步判断）

分类：{n[0]}。验证优先级：**{n[5]}**。

{n[3]}。

## 许可与复用边界

{lic}。

'''
    if (ROOT/'sources'/slug/'LICENSE.txt').exists():
        text+=f'已保存[许可原文](../sources/{slug}/LICENSE.txt)。这只覆盖取到的根目录文件；子目录、依赖、模型权重、图标和数据授权仍需逐项确认。\n\n'
    else:
        text+='未取得常见根目录许可文件，不等于已证明整个仓库没有许可证。直接复制代码或文档前，检查文件树并向上游确认。\n\n'
    text+=f'''## 最小验证任务

{n[4]}。

验收材料必须包含：固定 commit、依赖锁定、脱敏配置、输入数据快照、运行日志、输出产物、耗时/调用成本、失败与恢复记录。当前执行状态：**未运行，待 PoC**。

## 当前信息缺口

- 尚未核对所有源文件、依赖清单、完整测试集或近期 Issue/PR。
- 市场覆盖、行情权限、数据费用和券商可交易性需要按最终使用场景逐项实测。
- 原 README 中相对图片和文档链接以在线固定版本为准；本地仅保存文本，未镜像外链资源。
- 采集异常：{'；'.join(d['errors']) if d['errors'] else '本轮必需资料采集无异常'}。
'''
    (ROOT/'projects').mkdir(exist_ok=True)
    (ROOT/path).write_text(text)
    registry.append({'repo':repo,'category':n[0],'priority':n[5],'purpose':n[1],'dependencies_from_readme':n[2],'proposed_reuse':n[3],'validation_task':n[4],'license_note':lic,'commit_sha':d['commit_sha'],'archived':m.get('archived'), 'dossier':path,'execution_verified':False})
catalogue += ['', '## 选型结论', '',
    '第一轮同时比较 Vibe-Research 与 tick-stock-panel 的产品/策略边界，用 a-stock-data 验证数据能力，用 daily_stock_analysis 验证日常任务，用 TradingAgents 验证研究编排。先做可替换适配层，再依据 PoC 决定借用模块还是独立实现。不要直接把五套应用拼成一套。', '',
    '本轮未完成全部依赖和子文件许可审计，因此 P0 是验证顺序，不是可以直接合并上游源码的批准。详细路线见 [开发蓝图](02-开发蓝图.md) 与 [验证任务](03-验证任务与决策记录.md)。', '']
(ROOT/'01-项目选型总览.md').write_text('\n'.join(catalogue))
(ROOT/'project-registry.json').write_text(json.dumps(registry,ensure_ascii=False,indent=2))
