# 组件构建、校验和分发

本项目的registry当前是文档中的内部组件/模块清单。没有独立`registry.json`、组件下载API、npm包、公共组件站点或第三方安装CLI。内部UI资源与业务模块随`stockradar` Python wheel整体分发。

## 当前组件清单

| 逻辑组件 | 位置/入口 | 消费数据 | 使用页面 |
|---|---|---|---|
| ModeBanner / ErrorBanner | app.js:modeBanner、errorBanner | health、质量原因 | 四页 |
| StatusTag / ValueFormat | tag、deliveryTag、number/percent/price、datetime | 状态和已计算数值 | 列表、详情、研究 |
| SignalTable | signalTable | signals | 概览、机会 |
| ReviewQueue | reviewTasks、reviewPanel、signalNextStep | health质量/外部投递、当前已加载signals | 四页异常区、信号详情 |
| ScoreBreakdown | scoreParts | signal.score_parts | 信号详情 |
| EvidenceDetails | jsonDetails、details元素 | 版本、证据、原始计算 | 详情、研究、诊断 |
| DetailDrawer | drawerShell、showDrawer、closeDrawer | 信号/热点/通知 | 公共侧栏 |
| SignalDetail | signalDetail、openSignal | signals/{id} | 机会详情 |
| SectorDetail | openSector | sectors | 热点详情 |
| ReplayJobs | replayListHTML、pollReplay | replays | 策略研究 |
| EvidenceChart | evidence-chart.js:evidenceChart | signals/{id}.chart原始快照投影 | 信号详情 |
| StudyComparison | study-view.js:studyPanel/studyResult | study-sources、studies | 策略研究 |
| NotificationCenter | openNotifications | notifications | 公共通知入口 |
| ConnectionForms | connection-view.js、renderConnections | connections只读状态、独立保存/测试 | 行情API、大模型配置页 |
| MinuteFeedView | minute-view.js、renderMinutes | minute-data、零请求prepare与手动fetch | 独立分钟行情页 |
| 证据记录视图 | history-view.js | source-health、sector-timeline、study-cards、studies/{id}/cases | 行情 API、热点侧栏、策略与研究 |

这些名称用于协作说明，不是已导出的独立类、包或可安装组件ID。设计、输入和状态约束见[组件规范](COMPONENT-GUIDELINES.md)。

业务模块provider/notifier采用接口替换方式，不提供自动插件下载。FixtureProvider、JSONLProvider、HTTPJSONProvider、DingTalkNotifier及仅本地的SimulationNotifier能力见[接入契约](development/data-contract.md)。

## 构建输入与产物

构建声明来自 `pyproject.toml`，项目名 `stockradar`，当前版本 `0.2.7`。包发现范围为 stockradar*。`package-data` 包含 `static/*` 和 `fixture*.json`，包括当前及历史 v1 配置模板。

wheel 包含全部 Python 模块、八份静态资源和新旧两份配置模板。数据库、令牌、录制、采样和研究报告在运行环境中独立保存。

`configs/fixture.json`与包内`stockradar/fixture.json`同步，当前schema2/id=fixture-v2-star；另两份fixture-v1.json保留原模板与哈希。已有数据库默认继续最后扫描版本，不因默认模板升级而自动切换。operations-fixture、dispatcher-fixture、provider-poc及vendor-sample计划是源码样例，不是wheel默认运行资源；安装包用户需另存完整计划。研究样例通过export-study-fixture生成，打包需在仓库外验证两种格式。

0.2.3另包含public_sources.py；3份vendor-sample公开计划和minute-quality-public-template.json为源码样例，不混入wheel或默认策略。0.2.2另包含minute_quality.py；两份vendor-minute计划和minute-quality口径模板也是源码样例，须另外保存，不自动装入包内默认策略。离线分钟报告不是可直接交给worker的资源。

0.2.4新增fuyao_source.py、connection_settings.py和connection-view.js。Fuyao采样计划仍为源码样例，不作为包内默认配置；本地`.connections`元数据和令牌不打包。新静态模块同步进入HTTP白名单；本轮30个Python模块、6份静态文件和两份fixture的离线wheel逐字核对见[包证据](development/evidence/connection-settings-20261105/wheel.json)。

## 校验清单

2026-11-14新增独立 `zsxq_events.py` 手动采集模块与 `zsxq_store.py` 独立事件库模块（跨次去重、修订、覆盖水位/缺口与预先记账预算）。官方 `zsxq-cli` 原生二进制、私有主题快照与独立事件数据库位于本机 `.local/` 忽略目录，不进入 wheel。新增模块专项 16 项测试、单页真实读取及跨次导入通过，本轮没有构建或发布包。[本轮说明](development/zsxq-events.md)

0.2.7新增 `minute_grid.py`、`minute_acceptance.py`，两份新验收模板仍为源码样例。源码与零请求检查见[本轮记录](development/evidence/minute-acceptance-20261112/README.md)；本轮未构建或发布wheel，以下旧包验证不作为0.2.7包验收。

0.2.6 新增 `source_health.py` 和 `history-view.js`，同步静态资源白名单。32 个 Python 模块、8 份静态文件和 2 份 fixture 与源码逐字匹配，Python 3.9 仓库外导入及空记录检查通过。 [包证据](development/evidence/history-workbench-20261110/wheel.json)

0.2.5新增minute_feed.py和minute-view.js，HTTP白名单同步。临时源码的31模块、7静态、2fixture逐字匹配，Python3.9仓库外配置/零请求导入通过；分钟请求样例和运行记录不打包，见[本轮包证据](development/evidence/tushare-minute-20261108/wheel.json)。

1. 软件版本在`__init__.py`与pyproject一致，CHANGELOG说明实际变化。
2. 按变更影响运行策略/API/并发/反馈等测试，前端检查语法与交互。
3. 检查package-data、静态白名单和资源引用；如新增拆分JS/CSS，确认可被服务并打入wheel。
4. 检查两份fixture配置一致，不包含凭据或真实行情伪装。
5. 在隔离安装/导入路径下加载配置、fixture和静态资源；保存构建及校验结果。
6. 分发说明标注离线/影子/真实提醒状态、需求边界和已知问题，不将本地测试记作真实路径验证。

构建、安装命令与部署方式见[DEPLOYMENT](DEPLOYMENT.md)。NEXT04本轮针对当前未发布源码离线重建0.1.0 wheel，核对22份Python模块、三份静态资源及新旧模板；仓库外Python3.9隔离扫描分别取得15/12分母、本地模拟接受7/4条且各1次调用。代码/包哈希见[验证记录](development/verification.md)，没有上传或发布。

0.2.0四项改进另于临时源码副本用已有setuptools84.1.0离线构建，25模块/5静态资源/2模板与最终197项测试的资源清单匹配；Python3.9仓库外新旧配置分母12/15、触发图表均通过。最终wheel及哈希见[本轮证据](development/evidence/four-priorities/wheel.json)。旧0.1.0产物与验收记录保持原日期，本次未上传或发布。

## 分发边界

0.2.2于2026-10-30 18:10:44—18:10:45 UTC在独立源码副本使用已有Python3.12/setuptools84.1.0离线构建，27模块/5静态资源/2模板与本阶段250项回归资源匹配。Python3.9仓库外导入验证新旧分母12/15、触发图各6分钟、零请求准备和无分钟报告。wheel为169179字节，SHA-256为de5b05e80a8884ffa45ffc21d908dce7f936064fd4362cdbe297b673663f5ab3，未上传/发布；计划不混入包，见[包核对](development/evidence/next03-minute-prep-20261030/wheel.json)。未执行新的UI视觉验收。

0.2.1于2026-10-30 06:17:30 UTC从独立源码副本离线构建，26模块/5静态资源/2模板与当时工作区逐字匹配；含NEXT11界面源码，但未执行其视觉验收。Python3.9仓库外新旧配置分母12/15、图表各6分钟、vendor-sample缺配置0请求通过，源码哈希匹配真实原始样本采集。wheel为160820字节，SHA-256为87a27165b2345437cb6c91144d4b98be60464641e0427ac588db3e76c31c1cba，未上传/发布，见[包核对](development/evidence/next03-sources-20261030/wheel.json)。

当前分发单位是源码目录或本地wheel，不存在公共包索引发布记录，也没有组件独立语义版本。若以后需要公共组件服务，须另行定义清单schema、资源/依赖解析、兼容性和版本策略；不能把本文件中的登记表当成已实现的服务。

常规本地构建产物可在data/wheels下并被忽略，本轮验收产物在临时目录，位置记录于证据索引；不保证全新源码目录已经带有wheel。原研究资料的上游许可和源码不因“登记”自动纳入应用；当前代码为独立实现。

0.2.3的28模块/5静态资源/2fixture与本轮270项回归资源逐字核对。独立临时源码离线构建、Python3.9仓库外新旧配置扫描/图表、3份公开计划零请求准备及原始分钟重解析记录见[本轮wheel](development/evidence/next03-public-20261031/wheel.json)。无新增运行依赖、原始行情/研究计划不打包，未上传或发布；当前calm静态资源打包不构成本次浏览器重验。

0.2.7源码补充real_market.py与static/real-market-view.js，静态白名单和包资源声明覆盖新模块。实际实采、352项Python、33项Node与浏览器记录见[真实行情验证](development/evidence/real-market-20261113/README.md)。本轮未构建或发布wheel。
