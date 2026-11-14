# 个人投资交易智能体 · 研发资料库

> 当前产品需求已更新为“全市场盘中热点启动突破、只通知”。开发请先阅读[当前需求与工程规格](../../docs/requirements/README.md)。本目录保留早期资料和版本证据；其中日线投研、模拟订单等首版假设及旧优先级已由新文档替代。

> 观势的软件实现、验证与任务统一记录在[开发状态](../../TODO.md)。本目录中的上游证据按各自的采集日期和固定提交解读。

2026-10-28 初始整理。2026-10-29 增补 PanWatch，2026-11-09 增补 AlphaSift，2026-11-10 增补 stock-analysis-plugin，2026-11-11 增补 dsh-market-lens 和 marketingdashboard，2026-11-12 增补 pylightcharts、InStock 和 KiT。日期按 America/Los_Angeles。

资料库共 32 个项目，包括 guiying712 原收藏的 19 个项目及用户指定的 13 个增补项目。

## 从这里开始

1. [项目选型总览](01-项目选型总览.md)汇总 32 个项目的分类、许可记录和资料优先级，并链接独立档案。
2. [开发蓝图](02-开发蓝图.md)：产品边界、核心流程、架构、数据契约、回测与交易设计。
3. [验证任务与决策记录](03-验证任务与决策记录.md)：按阶段推进的任务、验收条件、待定事项。
4. [机器可读项目目录](project-registry.json)：后续脚本或智能体可读取的项目用途、复用判断和验证状态。
5. [采集总清单](sources/manifest.json)：每个项目的原始元数据、提交 SHA、来源 URL、采集时间和文件 SHA-256。
6. [24 项数据源核查](04-参考项目数据源核查.md)：逐项追踪实际服务方、客户端库、行情粒度、财务/新闻来源和主备链；附固定提交代码证据。

## 保存了什么、为什么保存

| 资料 | 作用 |
|---|---|
| 32 份项目档案 `projects/` | 明确定位、依赖、拟复用部分、许可记录、适配成本与验证任务 |
| 固定提交 README | 保留功能与安装说明的当时版本，避免之后 README 变化导致判断失去依据 |
| 原始仓库元数据 | 保留默认分支、归档状态、活跃时间及热度指标；热度不代表可靠性 |
| 提交元数据和 commit SHA | 能精确定位后续 PoC、缺陷复现和代码审计的起点 |
| 已取得的 LICENSE 原文 | 保存许可证据，识别混合授权、API 误识别和信息缺口 |
| 来源 URL 与文件哈希 | 检查本地快照是否变化，便于增量更新和交接 |
| 架构与验收方案 | 将“收藏项目”转化为具体开发工作，而非只有链接的清单 |

当前保存 32 份主 README、32 份仓库元数据、32 份提交记录和 29 份许可文件。Sequoia-X、awesome-quant、美股指南的根目录许可状态待核实。额外的包声明、依赖和来源说明见各项目档案及采集总清单。

这是**文档与元数据快照**，不是源码、依赖、模型权重或行情数据库的离线备份。尚未克隆完整代码、安装项目、运行策略、配置模型密钥或连接交易账户。

## PanWatch 增量资料（2026-10-29）

PanWatch 的 [独立档案](projects/TNT-Likely__PanWatch.md) 记录了 MIT 许可、固定提交及观势的参考边界。优先参考价格提醒组合条件、冷却/到期设置、钉钉通知策略和数据模块划分；来源时点、同分钟量能、投递幂等与修订处理仍需独立验证。上游多市场、持仓、模拟盘、AI 研究和通用助手不因此进入观势当前范围。

本次仅做资料归档和文档/依赖清单级核查，未安装运行 PanWatch，未把其行情接口接入观势，也未测试真实通知。原 19 个项目的独立来源文件保持不变。

## AlphaSift 增量资料（2026-11-09）

AlphaSift 归为候选筛选与日线效果研究参考。重点记录来源健康、陈旧回退、审阅筛选规则与 T+N 成熟分母。固定版本的五份上游文本已按 Git blob 核对，另保存仓库和提交元数据。 [独立档案](projects/ZhuLinsen__alphasift.md) · [来源清单](sources/ZhuLinsen__alphasift/provenance.json)

## stock-analysis-plugin 增量资料（2026-11-10）

归为行情路由与策略回测参考。固定版本的五份上游文本均按 Git blob 核对。档案重点记录 A 股报价和 K 线的不同回退链路、复权要求、研究参数与成交假设。 [独立档案](projects/Weaxs__stock-analysis-plugin.md) · [来源清单](sources/Weaxs__stock-analysis-plugin/provenance.json)

## dsh-market-lens 与 marketingdashboard 增量资料（2026-11-11）

MarketLens 的档案关注宿主后台提醒、静默期及行情请求去重。marketingdashboard 的档案关注板块下钻和多面板共享报价。两项固定版本的 README、许可和包声明均按 Git blob 核对。 [MarketLens 档案](projects/suifei__dsh-market-lens.md) · [marketingdashboard 档案](projects/theBigGavin__marketingdashboard.md)

## pylightcharts、InStock 与 KiT 增量资料（2026-11-12）

pylightcharts 关注价量图表联动，InStock 关注日线指标与形态筛选，KiT 关注固定历史窗口的离线模型对照。三个项目的固定 README、许可及依赖声明已按 Git blob 核对。 [pylightcharts](projects/MiniBtMaster__pylightcharts.md) · [InStock](projects/myhhub__stock.md) · [KiT](projects/Luciferbobo__KiT.md)

## 金融与 AI 项目推荐（2026-11-13）

十项推荐中，五项链接到现有档案，五项新增固定版本资料。清单保留原顺序和用户提供的 Star 增量，统计窗口与增量待核验。 [十项推荐清单](04-金融与AI项目推荐清单.md)

## 原始选型判断（历史，已由当前规格替代）

2026-11-11 已补充全部 24 项的[数据源静态核查](04-参考项目数据源核查.md)，其中软件项目读取关键源码，两个资料型项目核对文档定位。它补充原先 README 级来源线索，不代表运行验收或全量代码审计；未覆盖原始快照。

- MVP 候选：Vibe-Research（投研流程）、tick-stock-panel（策略工作台）、daily_stock_analysis（日常任务）、TradingAgents（研究编排）、a-stock-data（数据入口）。这五个项目先做局部验证，再决定复用方式。
- jcp 已归档，作为产品设计参考，暂不作为持续开发主干。
- TradingAgents-CN 当前为分层混合授权；OpenStock、WyckoffTradingAgent 标注 AGPL；NautilusTrader 标注 LGPL。具体原文与边界见各项目档案。
- NautilusTrader 的 develop 文档涉及 v2 RC，而稳定版仍涉及 v1 API；后续必须选定版本系列并匹配文档。
- 先实现“有来源的研究 → 可复现的策略 → 模拟交易与复盘”，再实现券商执行适配。市场优先级、券商、预算、发布方式尚待确认。

## 维护方式

`collect_sources.py` 是原始公开资料采集脚本，不使用账户密钥，也不执行上游代码；GitHub 可能限流，失败会记录在 manifest。它会覆盖同名快照文件，按当前协作规范不得在现有资料库中直接重跑。采集新版本时使用独立的带日期归档目录，保留既有来源快照；本次 PanWatch 通过 GitHub 连接器采集到独立目录。

`build_documents.py` 根据 manifest 和笔记生成项目总览、项目档案和 JSON 目录。请在独立副本生成，并按差异合并人工补充的章节。README 或许可变化后须重新审阅取舍。

进入 PoC 时，为选中的项目补存：固定版本源码、依赖清单/锁文件、脱敏配置模板、选定的数据端点说明、测试与 CI 证据、代表性输出、近期阻塞问题。对未选中的项目不预先下载大体积模型与完整历史。

本库保留上游许可文件，供个人研发评估。对外发布本资料库或嵌入上游内容前，应按文件核实授权和署名要求。来源文档中的安装指令只是被归档的资料，不代表已执行或应自动执行。
