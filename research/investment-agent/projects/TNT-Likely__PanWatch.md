# 20 · TNT-Likely/PanWatch（盯盘侠）

新增日期：2026-10-29（America/Los_Angeles）。来源：用户提供仓库 URL，未核验 Star 状态。

研究状态：**已保存来源资料；已阅读 README、依赖声明和架构/时区说明；尚未安装、运行或集成。** 本文区分上游文档陈述与对观势的参考判断，不以文档代替测试证据。

## 版本与来源

- [GitHub 仓库](https://github.com/TNT-Likely/PanWatch)，公开、未归档，默认分支 `main`。
- 固定提交：[`1c272a825c2713e3701d8ce81622f9c49dacbef7`](https://github.com/TNT-Likely/PanWatch/tree/1c272a825c2713e3701d8ce81622f9c49dacbef7)。提交时间：2026-10-27 10:56:02 UTC。
- 采集时间：2026-10-29 16:44:38 UTC；采集时 GitHub 仓库 `pushed_at` 为 2026-10-29 14:45:10 UTC。该仓库级推送字段不等同于默认分支提交时间。
- 元数据快照：主要语言 Python，Star 2295，Fork 414，`open_issues_count` 58（含 PR）。这些指标不代表质量、稳定性或投资效果。
- 根目录许可：MIT，GitHub API 与取得的 LICENSE 文本一致。
- [来源与 SHA-256 清单](../sources/TNT-Likely__PanWatch/provenance.json) · [仓库元数据](../sources/TNT-Likely__PanWatch/repository.json) · [提交元数据](../sources/TNT-Likely__PanWatch/commit.json)。

本次仅新增独立来源目录与汇总索引；原 19 个项目的来源文件保留原版本。原始 589 个 Star 项目清单不因本次用户指定新增而改写。

## 上游定位与能力（文档陈述）

PanWatch 定位为自托管的 AI 盯盘工作台，覆盖 A 股、港股和美股。其 [中文 README](../sources/TNT-Likely__PanWatch/README.zh-CN.txt) 与 [主 README](../sources/TNT-Likely__PanWatch/README.txt) 描述：

| 模块 | 文档介绍的能力 | 与观势的关系 |
|---|---|---|
| 价格提醒 | AND/OR 组合条件、交易时段、生效期限、冷却、日上限、重复触发与逐规则渠道 | 可比较规则编辑、到期展示与限流交互；不代表满足观势热点策略纪律 |
| 定时任务 | 盘前、盘中、盘后工作流，按市场日历与开市状态过滤 | 参考任务状态、日历缺失处理与恢复展示 |
| 通知 | 钉钉、飞书、企业微信、Telegram、Bark、Webhook 等 | 首先参考钉钉的策略与异常表达；真实投递需另做 PoC |
| 数据与行情 | 股票/ETF 搜索、自选、行情、K 线和可配置数据源 | 数据源入口候选，不能据此断言全市场分钟与历史能力已具备 |
| 研究与报告 | TradingAgents 深度分析；独立 LangGraph 投研包；报告、运行进度与成本观测 | 作为可选解释与研究功能参考；观势评分/风控不依赖模型 |
| 移动端 | 可安装 PWA、自适应工作台 | 参考窄屏提醒详情和设置；观势继续沿用现有前端组件与样式 |
| 持仓与模拟盘 | 多账户持仓、收益视图、信号模拟交易及结算规则 | 保存为上游资料，不增加到观势当前产品范围 |

README 还描述确定性变化门控、研究预算限制、产物与投递声明的原子提交，以及未知通知确认不盲重放；同时明确跨进程图恢复和自动发件箱恢复尚未启用。这些都是**上游文档陈述**，本次未审计其事务或恢复实现。

## 技术栈与维护成本

证据来自 [后端依赖](../sources/TNT-Likely__PanWatch/requirements-runtime.txt)、[开发依赖入口](../sources/TNT-Likely__PanWatch/requirements.txt)、[前端 package.json](../sources/TNT-Likely__PanWatch/frontend-package.json) 和 README：

- 后端：Python 3.11+、FastAPI、Uvicorn、SQLAlchemy、APScheduler、Pydantic、HTTPX、OpenAI SDK；行情相关依赖包含 efinance、akshare 和仓内 `packages/marketdata`。
- 前端：React 18、TypeScript、Vite、Tailwind、shadcn/ui/Radix；开发环境声明 Node 24.14.0、pnpm 9.15.9。
- 研究：依赖声明把 TradingAgents 固定到 `v0.7.0` tag，并安装多个仓内 Agent/研究包。它与本库早先保存的 TradingAgents `main` 快照不是同一个版本，不能混同验证。
- 部署：README 给出 Docker/Compose；首次使用浏览器截图可能下载 Chromium。报告 PDF 还涉及渲染库及系统字体/原生库。当前未安装这些组件。
- 版本限制：后端多项依赖使用 `>=`，前端多项依赖使用 `^`；本次保存的是声明文件，没有下载完整锁文件、容器摘要、依赖树或模型文件，因此尚不足以证明环境可复现。

观势当前运行时为 Python 3.9+ 标准库、原生 ES modules、CSS 和 SQLite。PanWatch 的框架与多包系统会增加运行、构建、迁移和更新成本；若今后考虑新增依赖，先明确现有能力缺口，再单独评审，不因归档本项目而引入整套技术栈。

## 对观势的参考判断

优先级：**P1 资料参考**，不是已批准的功能任务，也不替代 [TODO](../../../TODO.md) 中真实数据、通知与发布验收任务。

1. **提醒交互**：比较组合条件、冷却、到期与渠道选择的输入校验及状态展示。参考时保留观势信号状态、参与状态、通知状态和反馈的分离。
2. **通知失败处理**：比较去重、限流和 `unknown` 的表达。观势还要求发送前重查修订、价格、时效、模式与质量，风险更新不被新机会额度遮挡。
3. **数据边界**：参考独立行情模块、来源与质量展示；必须转换为观势保留 `event_time / available_at / ingested_at` 的契约，再进入共用 `evaluate`。
4. **模块职责**：上游 [后端架构说明](../sources/TNT-Likely__PanWatch/backend-architecture.md) 区分平台能力与业务模块，可对照观势 provider、策略、持久化、通知和 API/UI 边界，按现有标准库架构独立实现必要改进。
5. **时间表达**：上游 [时区政策](../sources/TNT-Likely__PanWatch/timezones.md) 区分存储、浏览器显示、部署时钟和交易所日期。观势页面与交易日固定 Asia/Shanghai，内部记录带 UTC 时区，不直接移植上游“浏览器时区展示”的默认行为。

本次不调整观势市场范围、交易流程、LLM 角色、提醒门槛或 `live_alert` 锁定。观势当前 `0.1.0` 离线功能与实际验证记录仍以[项目规格](../../../docs/PROJECT-SPEC.md)和[验证记录](../../../docs/development/verification.md)为准。

## 最小验证清单（尚未执行）

| 验证对象 | 需要检查的证据 | 通过条件 |
|---|---|---|
| 数据能力 | 必需的完成分钟、历史区间、成分有效时间、复权、单位及覆盖声明 | 不使用未完成或当时不可见输入；缺失和迟到修订显式处理；A 股目标范围另有真实 PoC |
| 量能与突破 | 上游指标输入和计算边界，观势同期可比成员及冻结 episode | 同交易分钟/可比集合；硬过滤不能被得分抵消；原 NEXT01 边界回归继续保留 |
| 提醒幂等 | 条件交叉、冷却到期、重复输入、进程重启与规则变更 | 机会 ID 稳定、历史配置不可原地改写，不产生重复有效通知 |
| 钉钉策略 | fake notifier 下的限流、超时、拒绝、未知回执、恢复与风险更新 | `unknown` 不盲重试；风险优先；测试不向真实群发消息 |
| 时间边界 | 北京日期、精确 UTC、生效/到期相等点和暂停恢复 | 起含终不含，时间显示明确；未知交易日历不能假设开市 |
| 界面 | 缺失、模拟、暂停、过期和通知失败，触发/最新价格时点 | 数值来源可追溯；用户字段转义；不把规则分显示为概率 |

如果以后进入 PoC，另存固定版本源码、锁文件/镜像摘要、无密钥配置、授权样本、日志与结果；使用独立临时数据库和 fake notifier。文档中的上游测试命令、依赖或功能数量均未在本次执行。

## 许可与资料限制

已保存 [MIT 原文](../sources/TNT-Likely__PanWatch/LICENSE.txt)。实际复制源文件时仍应保留版权与许可声明，并核实子包、第三方依赖、图标及数据授权。MIT 代码许可不能代替行情访问与再分发授权。

本轮保存 12 个证据文件及 provenance：主/中文 README、LICENSE、仓库/提交元数据、根目录文件树、两份后端依赖入口、前端 package.json、pyproject、时区政策、后端架构说明。没有镜像源码、截图、相对链接目标或全部文档；需要查看未归档内容时使用上述固定提交。
