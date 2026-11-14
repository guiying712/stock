# 项目文档索引

主文档按约定的根目录＋docs结构维护。软件当前为 0.2.7 离线增强版，新增阶段/状态分钟诊断与四阶段零请求准备。进度见 TODO，运行操作见 DEPLOYMENT。 [分钟验收工具](development/minute-acceptance-engineering.md) · [工作台证据口径](development/history-workbench.md)

NEXT03新增[Fuyao首轮采样](development/next03-fuyao-poc.md)：12请求、9成功，取得日线/当前资料，公司行为3002待核实。此前[免费公开接口PoC](development/next03-public-poc.md)已取得真实原始分钟/当前元数据和日线参考；时间/单位、完整性、历史可见性及标准batch尚未验收。0.2.2的[分钟诊断与零请求准备](development/next03-minute-quality.md)保留原阶段证据。

## 主文档

0.2.5新增[Tushare分钟接入与查看](development/tushare-minute-feed.md)：最新/当日/历史分钟的独立页面、零请求检查和手动获取；账户权限与Token待用户配置，真实策略输入仍待验收。

| 文件 | 内容 |
|---|---|
| [AGENTS.md](../AGENTS.md) | 协作、代码约束、验证与交付规范 |
| [README.md](../README.md) | 简介、技术栈、快速开始和文档树 |
| [DESIGN.md](../DESIGN.md) | 当前工作台的颜色、布局与交互规范 |
| [CHANGELOG.md](../CHANGELOG.md) | 已发生的版本及文档变化 |
| [TODO.md](../TODO.md) | 完成程度、已知问题、NEXT任务和计划 |
| [PROJECT-SPEC.md](PROJECT-SPEC.md) | 定位、目标、范围及发布门槛 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 模块、目录、事务和数据组织 |
| [COMPONENT-GUIDELINES.md](COMPONENT-GUIDELINES.md) | 内部UI开发、样式、依赖和无障碍要求 |
| [PAGE-STRUCTURE.md](PAGE-STRUCTURE.md) | 路由、四页、详情侧栏与验收要点 |
| [DEVELOPMENT.md](DEVELOPMENT.md) | 开发、测试与组件交付流程 |
| [REGISTRY.md](REGISTRY.md) | 内部清单、打包资源、校验和分发边界 |
| [DEPLOYMENT.md](DEPLOYMENT.md) | 启动、模式、环境变量、备份、构建和部署 |

“官网/组件”目录名称按用户结构保留，内容按当前产品填写：现有形态为本地工作台，组件随Python应用交付，没有新增营销站或公共组件服务。

## 补充契约与历史证据

| 资料 | 用途 |
|---|---|
| [需求基线](requirements/README.md) | 原FR/NFR编号、策略公式、用户决定与项目借鉴 |
| [用户配置与选择](requirements/04-用户配置与选择.md) | 设置入口、策略与研究参数、建议开放的用户选择 |
| [API参考](development/api.md) | 实际HTTP路径、字段、输入和错误语义 |
| [数据与通知契约](development/data-contract.md) | JSONL/网关、时间/单位、钉钉及投递约定 |
| [交付与验收映射](development/acceptance.md) | 需求对照与未完成验收 |
| [NEXT04本地模拟调度](development/next04-dispatch-lifecycle.md) | 显式计划、独占生命周期、时钟/恢复、worker接线及模拟证据 |
| [NEXT06/07本地工程](development/next06-07-local-acceptance.md) | 成交成本模型、时间隔离、运行计划、负载、归档恢复及合成证据 |
| [NEXT08科创板](development/next08-star-acceptance.md) | schema2、新旧版本兼容、科创板股票池/执行规则、页面与合成证据 |
| [四项改进](development/four-priorities.md) | 20项目取舍、数据/连接PoC、分钟K线、页面成本研究及真实完成条件 |
| [NEXT03可信数据来源](development/next03-data-sources.md) | 上游来源、免密原始样本/单位疑点、TickFlow/Tushare计划及历史成分缺口 |
| [数据源取舍与分钟验收方案](development/source-selection-and-acceptance.md) | 主源/核对源建议，完整性、单位、历史和权限验收；三股10请求首轮计划，尚未实采 |
| [分钟验收工程](development/minute-acceptance-engineering.md) | 0.2.7阶段/证券状态分母、整段竞价比较、旧格式兼容及四阶段离线计划 |
| [NEXT03免费公开PoC](development/next03-public-poc.md) | 新浪分钟、东方财富配套小样本、腾讯日线，真实缺口与270项测试/包核对 |
| [NEXT03同花顺Fuyao文档评估](development/next03-fuyao-review.md) | 11月5日全站接口索引、外部/客户端限制、日线/当前板块用途及分钟/历史资格缺口；当轮仅文档核对 |
| [连接配置页面与Fuyao准备](development/connection-settings.md) | 0.2.4行情/模型独立配置、本地Key管理、单次连接检查、12请求模板及零请求/模拟验收；后续真实采样另留证，无模型生成 |
| [NEXT03 Fuyao首轮采样](development/next03-fuyao-poc.md) | 11月8日确认计划、12次实际请求、9条日线/当前资料及公司行为3002；原始哈希和离线检查，未接入分钟策略 |
| [实际验证记录](development/verification.md) | NEXT03/11各220项Python、各自样本/前端/打包证据及历次研究/页面/负载记录 |
| [研究资料库](../research/investment-agent/README.md) | 32 个上游项目的固定版本资料，含原 19 个 Star 项目及 13 个用户增补项目 |

原[status](development/status.md)、[architecture](development/architecture.md)和[operations](development/operations.md)只保留迁移导航，不再作为独立进度/架构/运行副本。

## 维护规则

需求变化更新PROJECT-SPEC并保持FR映射；实现变化更新架构/API/页面或组件规范；计划只改TODO，实际变化记CHANGELOG。只有执行验证后才能新增验证结论，历史证据保留原日期。发布前区分离线工程交付和真实提醒门槛，不能将目标规格写成已通过验收。
