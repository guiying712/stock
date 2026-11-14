# 观势 · A 股热点雷达

个人单用户的A股热点启动与突破提醒工作台。通过市场环境、板块共振、个股突破与风险过滤发现候选，保存证据、状态和用户反馈，由用户自行交易。

**当前软件为 0.2.7，已跑通独立真实行情查看，真实提醒未发布。** 用户已选择钉钉群机器人，暂无已验证可供策略使用的真实行情商，默认使用明确标记的合成数据。规则分不是胜率，软件不自动下单。

股票池已支持**沪深主板＋创业板＋科创板**。默认新配置为fixture-v2-star；已有数据库继续原运行版本，启用科创板需显式选择新配置，见[NEXT08使用与验收](docs/development/next08-star-acceptance.md)。真实数据接入仍待验证。

2026-11-13新增[真实行情页面](docs/development/real-market-view.md)：Fuyao三股报价与15条日线已实采，浏览器可手动刷新；策略数据仍与该查看页分离。

## 技术栈

| 层 | 当前实现 |
|---|---|
| 服务与策略 | Python3.9+标准库，本地HTTP服务，确定性evaluate |
| 前端 | 原生ES modules、HTML、CSS及SVG证据图表，无npm构建步骤 |
| 持久化 | SQLite WAL、事务事件/水位/反馈/通知 |
| 数据与研究 | 合成fixture、JSONL/HTTPS网关、独立回放及显式成本/执行/分段研究 |
| 通知 | 内置中心、钉钉签名适配器、窗口聚合及限流；worker可显式启用本地模拟投递，真实渠道仅开放显式测试 |
| 分发 | setuptools构建Python wheel，静态资源与默认配置随包分发 |

## 快速开始

从项目根目录执行，无需安装第三方运行依赖：

```sh
python3 -m stockradar serve --port 8765
```

访问 <http://127.0.0.1:8765>，在登录页粘贴终端显示的访问令牌。服务只监听本机。默认令牌在数据库目录的.api-token（默认data/.api-token），设置STOCKRADAR_TOKEN时以环境变量为准；按Ctrl+C停止服务。

首次启动加载前两个模拟切片，已有数据库则恢复原状态。点击“推进一分钟”观察预警、确认、偏离、断源、恢复和失效；“重置演示”清除当前fixture版本的演示信号/反馈/通知，保留版本和研究任务。页面时间按Asia/Shanghai。

`serve`不会自动启动真实行情采集，关闭浏览器也不会停止另行运行的worker。配置、环境变量和后台命令见[部署与运行手册](docs/DEPLOYMENT.md)。

## 当前功能与验证

2026-11-14新增[知识星球事件手动接入与独立事件库](docs/development/zsxq-events.md)：官方授权后只读获取指定群最新一页，保存脱敏主题和版本哈希；独立事件库 `stockradar.zsxq_store` 提供跨次去重、修订版本追加、倒序分页连续覆盖水位与缺口记录，以及发网前预先记账的北京时间自然日请求预算。20 主题两次实采导入与 16 项专项测试通过，已形成首轮人工研究候选。自动事件分析、行情筛选和事件页面仍待实现。

0.2.7新增[分钟验收工程](docs/development/minute-acceptance-engineering.md)：按显式交易阶段、证券状态和无成交规则诊断覆盖，整段竞价与一分钟记录分别计数，保留schema1历史行为。四阶段准备生成默认未授权计划，三股合计10请求，实际零请求；真实口径、权限与标准策略批次仍待验收。

0.2.6 增加数据源健康、热点阶段时间线与研究策略卡，可按接口核对历次采样、回看板块暂停与恢复，并从固定配置下的样本外结果打开代表案例。 [使用与验证](docs/development/history-workbench.md)

0.2.5新增[分钟行情接入与查看](docs/development/tushare-minute-feed.md)：Tushare最新/当日/历史1分钟数据的零请求检查、手动获取、原始哈希、分钟图表及错误恢复。完整321项Python、29项Node、多尺寸隔离页面及31模块/7静态wheel核对通过；账户分钟权限与Token仍待用户开通配置，本轮真实Tushare请求0次，分钟记录尚未进入策略。

0.2.4新增独立的“行情 API”“大模型”配置页，支持凭据保存/替换/清除、来源状态与显式连接检查；Fuyao原始采样适配器及三板块12请求模板可做零请求准备。2026-11-08 UTC已在本机配置Fuyao并按用户确认完成[首轮真实接口采样](docs/development/next03-fuyao-poc.md)：12次请求、9次成功，取得9条日线、3条报价及当前板块资料；公司行为3次返回3002。样本尚未接入工作台策略；模型解释业务和分钟策略接入仍未实现。11月5日完整304项Python、22项Node及当轮模拟页面/包核对见[连接配置与使用](docs/development/connection-settings.md)，没有真实模型推理。

已实现市场/热点、区间突破、10%结构风险过滤、分项规则评分、标签、信号/参与状态、事务持久化、幂等反馈、四页中文界面、通知中心、回放及备份恢复。0.2.0新增触发/最近扫描分钟K线、冻结H/S及来源证据，页面可运行四组成本/时间隔离研究并导出完整报告；研究继续共用evaluate，不切换运行策略。

NEXT06/07本地工程与合成验收、NEXT08科创板扩展及NEXT04本地模拟调度已完成。0.2.0补充provider-poc显式数据样本报告、channel-poc连接测试报告，钉钉历史受理须匹配当前目标配置；真实钉钉机会投递仍未接线。四项改进的操作、参考取舍及外部条件见[使用与验收说明](docs/development/four-priorities.md)，本轮实际验证见[验证记录](docs/development/verification.md)；原173项记录保留原日期。

0.2.0最终197项Python、2项Node测试、1280/390/320px新增图表与研究区域浏览器验收、鉴权原文导出和CLI独立合成研究哈希一致、完整备份恢复及wheel新旧配置隔离导入通过。真实行情、测试群和真实样本外仍未验收；这些本地证据不证明投资效果或生产发布。

0.2.1新增独立vendor-sample采集与日线比较命令，准备TickFlow/Tushare小样本计划。已实际取得TickFlow免密5证券25条日线及当前元数据，100个OHLC字段与腾讯公开未复权日线一致；量能存在约100倍单位疑点及科创板口径/舍入差异，保留原值与unknown，未送入策略。本轮完整220项Python测试通过；账号分钟权限、历史成分与真实提醒仍待核验，见[可信数据来源与样本](docs/development/next03-data-sources.md)。

后续[NEXT11界面优化](docs/development/ui-polish.md)改善模式/行情时点、字号与状态对比、信号表固定首列/键盘详情、搜索草稿及失败重试。该阶段完整220项Python、11项Node检查通过；当时未执行浏览器检查；后续补验见下段，不沿用上段历史截图或wheel作为当前界面验收证据。

2026-10-31的[calm工作台调整](docs/development/calm-workspace.md)进一步前置异常与信号，压缩概览，将原因、依据和下一步操作放在相应对象旁。当前源码单独执行250项Python、18项Node及多尺寸Chrome关键路径验收；保留真实/模拟、未知/暂停、规则分非概率和反馈不下单的边界。真机、读屏、缩放与其他浏览器仍待验。

0.2.2新增`vendor-sample --dry-run`零请求准备和`minute-quality`离线分钟报告，提供主板/创业板/科创板窄范围采样计划。显式审阅时间/时区、完成性、单位、增量/累计及复权后才对齐；保留缺口、重复/修订和原始哈希，未知日历或时点不填覆盖率。该0.2.2阶段用户尚未开通账户，没有真实分钟采集或策略接入；使用与实际验证见[分钟诊断与准备](docs/development/next03-minute-quality.md)。

0.2.3按用户确认完成免费公开接口小样本PoC：新浪3只股票720条分钟、东方财富一只股票1205条分钟及当前元数据、腾讯15条日线。ST仅100/392条，东方财富创业板分钟断连、科创板该项未请求；相同原始标签下有205个OHLC字段差异，时间语义/量额单位仍待核实。完整270项Python、CLI与隔离wheel检查通过；未接入策略或改变页面数据，见[采样结果与使用](docs/development/next03-public-poc.md)。

此前含科创板的30日合成研究、12/120证券负载和两路15证券回放见[NEXT08记录](docs/development/next08-star-acceptance.md)；90日研究和最大1200证券负载属于扩展前的[NEXT06/07记录](docs/development/next06-07-local-acceptance.md)。0.2.0的研究演练与这些历史负载记录分别留证，不以新增页面推断全市场能力。

此前NEXT02完成内置浏览器桌面及320px/390px手机尺寸验收；NEXT08页面范围跟随实际配置。默认样例15个合格对象（含3只科创板）、6个排除对象。真机、读屏、真实历史/行情/群路径、正式参数冻结、全市场性能及连续真实影子仍待验收，live_alert锁定。时间与证据见[验证记录](docs/development/verification.md)；覆盖1.0只表示合成样例齐全。

```sh
python3 -m unittest discover -s tests -v
python3 -m stockradar export-fixture --output data/fixture.jsonl
python3 -m stockradar replay --input data/fixture.jsonl --output data/replay-report.json
```

普通测试只使用临时本地HTTP和模拟外部网络，不向真实群发消息。软件无运行依赖，但wheel构建需准备构建后端，见[构建说明](docs/DEPLOYMENT.md)。

## 项目文档树

```text
.
├── AGENTS.md                      # 项目协作与代码开发规范
├── README.md                      # 项目简介、技术栈和快速开始
├── DESIGN.md                      # 视觉风格、布局和交互设计
├── CHANGELOG.md                   # 版本更新记录
├── TODO.md                        # 开发计划和当前进度
└── docs
    ├── PROJECT-SPEC.md            # 定位、产品目标与功能范围
    ├── ARCHITECTURE.md            # 架构、目录与数据组织
    ├── COMPONENT-GUIDELINES.md    # 内部UI组件、样式、依赖与无障碍
    ├── PAGE-STRUCTURE.md          # 页面、详情侧栏与交互结构
    ├── DEVELOPMENT.md             # 开发、验证与组件交付流程
    ├── REGISTRY.md                # 内部组件清单、打包与分发
    └── DEPLOYMENT.md              # 构建、部署与运行手册
```

从[AGENTS](AGENTS.md)、[项目规格](docs/PROJECT-SPEC.md)和[TODO](TODO.md)接手开发。界面变更查看[DESIGN](DESIGN.md)、[组件规范](docs/COMPONENT-GUIDELINES.md)与[页面结构](docs/PAGE-STRUCTURE.md)；代码/交付查看[架构](docs/ARCHITECTURE.md)、[开发流程](docs/DEVELOPMENT.md)、[REGISTRY](docs/REGISTRY.md)和[部署](docs/DEPLOYMENT.md)。变化见[CHANGELOG](CHANGELOG.md)。

[文档索引](docs/README.md)还保留需求公式、数据/API契约、逐项验收和历史验证记录。原development的进度/架构/运行路径已改为兼容入口，避免重复维护。当前没有独立营销官网、React组件库或公共registry；文档中的“组件”对应内部UI和模块。

研发资料库现有 32 个参考项目，包含原 19 个 Star 项目及 13 个用户增补项目。各档案记录固定版本、许可、数据来源与可借鉴的做法。 [研究资料库](research/investment-agent/README.md)
