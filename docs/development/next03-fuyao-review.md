# NEXT03：同花顺 Fuyao API 文档评估

核对日期：2026-11-05。对象是用户提供的 [Fuyao 在线调试站](https://fuyao.aicubes.cn/playground/)，结论只适用于该站当前文档。对应 FR01/02、NEXT03，并涉及 FR03/04/12 的数据前置条件。

后续0.2.4已完成[独立连接管理与Fuyao零请求准备](connection-settings.md)；本篇保留当轮文档评估事实，不把后续工程或模拟验证写成真实行情验收。

**结论：适合作为日线、当前板块关系及盘面资料的候选补充源；按当前公开契约，不能单独作为观势的分钟策略主行情源。** 最关键的缺口是对外 A 股完成分钟 OHLC、同期分钟历史、历史成员及完整风险状态。本次完成文档分析，没有完成账户权限或数据质量 PoC。

## 核对范围与证据

读取全站索引、全文聚合和 OpenAPI，并对照本项目 README、规格、TODO、架构、开发流程、数据契约、`providers.py`、`engine.py` 和原始采样入口。

| 范围 | 本次核对结果 |
|---|---|
| 全文聚合 | 189 个来源段落：4 个入门、72 个 REST 参考、1 个 MCP 总览、112 个 MCP 工具页；工具页中有 2 个占位页 |
| OpenAPI | 111 个路径，均为 GET；文档版本 `1.0.0`，不代表数据版本或账户权限 |
| MCP | 110 个已列工具；个股异动原因列表明确只提供 REST，所以与 111 个 REST 的数量差异有解释 |
| 去重后的文档路径 | 125 个：111 个 OpenAPI 目录路径、11 个客户端限定路径、3 个独立 dump 下载路径 |
| 本次实际数据验证 | 行情、账户和 MCP 调用均未执行；未登录、未签发或读取 API Key、未下载市场数据 |
| 项目变化 | 仅新增分析、接口索引及文档导航；版本仍为 0.2.3，未新增适配器、依赖或策略输入 |

125 个路径及各自原文入口见[完整接口索引](evidence/fuyao-doc-review-20261105/catalog.md)。下载文档的大小、SHA-256 和本地接收时间见[来源清单](evidence/fuyao-doc-review-20261105/sources.json)。清单用于标识本轮读到的版本；上游地址会更新，未把全文复制进仓库。

主要依据：[全站索引](https://fuyao.aicubes.cn/llms.txt)、[全文聚合](https://fuyao.aicubes.cn/llms-full.txt)、[OpenAPI](https://fuyao.aicubes.cn/openapi/financial-api.openapi.json)。后文“文档提供”不表示“本账户可用”或“本项目已验收”。

## 全站能力与项目用途

下表数量只统计 OpenAPI 的 111 个目录路径，客户端限定及 dump 另列，避免混算。

| 数据域 | 路径数 | 内容与观势用途 |
|---|---:|---|
| A 股 | 34 | 行情、日历、公司行为、三大财报及指标、估值、集合竞价、热榜、涨跌停、龙虎榜、异动和新股；优先评估日线与盘面辅助资料 |
| A 股指数 | 6 | 板块目录、当前成分、个股板块反查、指数快照及日线；优先评估当前板块关系与参考行情 |
| 标的元信息 | 2 | 检索和分页代码表；可作代码、名称、上市日期参考，不能据此判定完整交易资格 |
| 资讯 | 7 | 文章、快讯及刷新、公告解读、专题、日期范围异动解读、个股新闻；适合解释证据，不能替代价格或确定性评分 |
| 基金 | 33 | 基本资料、经理/公司、持仓/持有人、净值/业绩、财务、分红、诊断、募集、资讯、QDII、行情和基金回测；当前 A 股策略无需接入 |
| 期货 | 20 | 合约、品种、主力关系、持仓、基差、仓单、日程和行情；超出当前产品范围 |
| 期权 | 6 | 品种、合约、日程和行情；超出当前产品范围 |
| 港股新股 | 3 | 递表、认购/待上市日历、发行详情；不是港股全市场行情，超出当前产品范围 |
| 合计 | 111 | 目录广度不等于观势所需数据已经齐全 |

基金部分还有容易混淆的口径：快照支持 ETF/LOF，历史行情仅 ETF 日线，价格前复权但 `adjust` 返回 `null`；持仓来自定期披露。基金在线回测不是本项目 A 股分钟策略的历史验证。依据：[基金总览](https://fuyao.aicubes.cn/docs/api-reference/funds/)、[基金行情](https://fuyao.aicubes.cn/docs/api-reference/fund-market/)、[基金持仓](https://fuyao.aicubes.cn/docs/api-reference/fund-portfolio/)、[基金回测](https://fuyao.aicubes.cn/docs/api-reference/fund-backtest/)。

期货、期权虽然在参数枚举里出现分钟周期，但对外 K 线仅允许 `day_1`，分时仅当前交易日；更丰富周期和历史分时属于客户端能力。这也不能推导出 A 股分钟权限。依据：[期货行情](https://fuyao.aicubes.cn/docs/api-reference/futures-prices/)、[期权行情](https://fuyao.aicubes.cn/docs/api-reference/options-prices/)。

## 对观势最关键的能力核对

| 需求 | 文档契约 | 判断 |
|---|---|---|
| 股票历史价格 | 单只 `prices/historical` 只支持 `1d`；`historical-batch` 最多 10 个原始代码项，支持 `1d/1w/1mo`，窗口最长 10 年 | 可做日线原始样本；不提供分钟 OHLC，窗口上限也不证明每只股票都有完整十年数据 |
| 股票当前价格 | `prices/snapshot` 支持指定代码批量，或全代码表分页；默认每页 100 | 可评估行情展示和交叉核对；不是已完成的一分钟切片 |
| 基准/板块价格 | 指数支持指定代码快照、单只及最多 10 只批量日线，历史为查询日向前滚动近 5 个自然年 | 可补日线参考；没有满足策略的指数分钟历史 |
| 当前板块关系 | 目录按概念/行业/地域/特色返回；单板块成分；个股反查最多 100 个原始代码项 | 是本项目较有价值的补充；需完整采集和留存观测版本 |
| 历史板块关系 | 成分和反查均为当前关系，没有历史查询参数、生效区间或历史披露证据 | 不能用今日板块成分回填历史研究 |
| 代码表/风险状态 | 元信息有代码、名称、交易所、资产类型、上市日期等；股票基础信息页仍为占位 | 缺少可直接满足契约的完整 ST、停复牌、退市及历史状态来源 |
| 日历 | 默认近一年，可成对指定起止日期，单次闭区间最长十个自然年 | 比首页概述更丰富；仍需核实实际覆盖并冻结本地日历版本和连续竞价时段 |
| 公司行为 | REST 返回除权日、税前每股分红、送股比例等事件，调用方推导因子 | 不直接返回每日 `adjust_factor`，也没有完整历史可见性和修订链 |
| 盘面情绪/解释 | 热榜、涨跌停池、连板、异动原因、龙虎榜等 | 可提供页面依据与研究线索，不能把外部榜单或解读当成当前策略的触发条件 |
| 财务/估值 | 财报单只及批量、指标、最新估值 | 可作独立研究补充；当前策略未要求新增这些过滤条件 |

行情依据：[股票行情](https://fuyao.aicubes.cn/docs/api-reference/prices/)、[指数数据](https://fuyao.aicubes.cn/docs/api-reference/a-share-index/)。资格和日历依据：[代码表](https://fuyao.aicubes.cn/docs/api-reference/ticker-list/)、[股票基础信息](https://fuyao.aicubes.cn/docs/api-reference/stock-basics/)、[交易日历](https://fuyao.aicubes.cn/docs/api-reference/calendar/)。财务依据：[财报](https://fuyao.aicubes.cn/docs/api-reference/financials/)、[财务指标](https://fuyao.aicubes.cn/docs/api-reference/financial-indicators/)、[估值](https://fuyao.aicubes.cn/docs/api-reference/valuations/)。

板块反查还明确说明，更新失败时会继续使用最近一次成功的关系数据。因此接入时不能仅凭请求成功把关系标记为“当前已更新”；需要来源更新时间或独立新鲜度证据。当前关系适合从真实观测时点开始积累，本次没有采集这些关系。

## 两类不能直接按目录接入的能力

### 客户端限定：8 个模块、11 个路径

| 模块 | 路径数 | 当前限制与含义 |
|---|---:|---|
| [主力资金](https://fuyao.aicubes.cn/docs/api-reference/capital-flow/) | 2 | 明确未向外部开放；其中 `1m` 是资金流序列，也不是价格 OHLC |
| [高频动向](https://fuyao.aicubes.cn/docs/api-reference/high-frequency/) | 2 | 明确未向外部开放；返回高频动向/参与度指标，不是分钟价格行情 |
| [筹码形态](https://fuyao.aicubes.cn/docs/api-reference/chip-shape/) | 2 | 客户端内的可选日期和股票筛选 |
| [新增概念](https://fuyao.aicubes.cn/docs/api-reference/new-concepts/) | 1 | 客户端内的新增概念记录；不等于历史成分 |
| [市场成交额预测](https://fuyao.aicubes.cn/docs/api-reference/turnover-prediction/) | 1 | 客户端内预测值；不是已发生的分钟成交额 |
| [宽基 ETF 净流入](https://fuyao.aicubes.cn/docs/api-reference/etf-net-flow/) | 1 | 客户端内的日统计，按 T+1 更新约定提供 |
| [资讯事件库](https://fuyao.aicubes.cn/docs/api-reference/news-events/) | 1 | 客户端内的事件检索；其单实例 5 次/秒说明不能当作全站公开额度 |
| [期货 F10](https://fuyao.aicubes.cn/docs/api-reference/futures-fundamentals/) | 1 | 未开放外部接入；总览与细页对客户端内上线进度的措辞也不完全一致 |

这些路径均未进入本轮 OpenAPI 的 111 项目录。后续不能通过模拟客户端身份、复制登录 Cookie 等方式推导授权或绕过边界。

### 市场整库下载：3 个独立入口

文档另有全 A 股约十年未复权日线、最近十个交易日日线、全量公司行为事件的 Parquet 下载。适合离线备料；不包含本项目缺失的分钟历史、历史成分和完整证券状态。

[接口总览](https://fuyao.aicubes.cn/docs/api-reference/overview/)明确区分浏览器 `/dump/**` Cookie 入口和 API 客户端 `/api/dump/** + X-api-key`；[下载细页](https://fuyao.aicubes.cn/docs/api-reference/market-dumps/)主要描述登录按钮和短期签名地址，三个路径没有出现在本轮 OpenAPI。应独立验证 API Key 权限与实际文件，不能断言只能手工下载，也不能当作已经验证的普通 JSON API。签名地址可能包含临时授权参数，不应进入日志或长期证据。

本项目运行时没有 Parquet 读取器。若确需整库下载，可先在隔离的离线转换工具里处理，核心应用继续读取已校验格式；本次没有安装 `pyarrow`、引入其它依赖或下载数据。

## 为什么快照不能代替完成分钟

当前策略的 [Quote 契约](data-contract.md)要求 60 秒 OHLC、完成性、三类时间、修订、复权基准及明确量额口径。快照字段描述的是当日开盘/最高/最低和最新成交价，缺少分钟开高低收及逐条事件时间。

即使每分钟抓一次，两个最新价也无法恢复这一分钟的高低价和首笔成交；当日最高价没有变化也不表示本分钟没有波动。即使量额确认是累计值，做差仍不能补齐分钟价格、断连区间、修订和完整性。这是数据内容缺口，无法只靠转换字段名解决。

快照 `data.timestamp` 是整批最新上游有效时间，不能证明每只股票都同样新鲜。分页之间也没有文档化的固定快照游标；不能把不同页直接当作同一时刻的全市场批次。集合竞价的 `timestamp` 更明确是响应组装时间，两种含义不能统一当作行情发生时间。依据：[快照字段](https://fuyao.aicubes.cn/docs/api-reference/prices/#行情快照)、[集合竞价](https://fuyao.aicubes.cn/docs/api-reference/auction/)。

## 数据映射与实现注意点

| 项目要求/接入点 | 当前缺口或处理原则 |
|---|---|
| `event_time/available_at/ingested_at` | 按端点解释供应商时间；本地接收时间只证明本次观测，不能伪造历史最早可见时间；毫秒戳转换为带 UTC 时区时间，日期按上海解释 |
| `is_complete/interval=60` | 股票和指数公开价格接口没有完成分钟契约，禁止填 `true` 或把日线改成 60 秒 |
| `volume_shares/amount_cny` | 股票行情文档已写明股和原币金额，较未知单位源更清晰；仍需实测。集合竞价机会的数量单位另为未定义，不能跨端点套用 |
| 小数收益率 | 快照 `price_change_ratio_pct`、竞价 `auction_pct` 为百分数值；部分新接口的 `*_ratio` 为小数，财务指标则是保留精度的字符串。必须逐字段映射，价格以 Decimal 解析 |
| `daily_bars.prev_close/adjustment_factor` | 历史 OHLC 不直接给这两项；不能靠改字段名补齐。默认前复权应显式改为 `none` 才适合原始价格比对，复权推导另验 |
| 公司行为与历史时点 | REST 并不直接给计算后的因子，且缺登记日、披露/修订证据；dump 列表还有配股字段。先验证完整性和口径，不把事件日期等同披露日期，不把税前分红当作研究净现金 |
| `instruments.status` | 名称、上市日期或某个机会接口的 `exclude_st` 参数不能证明全池风险状态；未知不得默认 active |
| `memberships.valid_from/valid_to` | 当前成员关系不提供这些历史证据；保存 observed_at 和来源版本，实际生效边界未知就保持未知 |
| 部分成功/空数据 | 批量接口可 `code=0` 但省略未知/类型不符标的，合法空组为 `timestamp:null,item:[]`；必须核对请求集与返回集，不能只检查业务码 |
| 新闻和内容安全 | 资讯有 `data.items` 等不同结构；正文 HTML 需转义或严格清洗，长整数 ID/游标保留字符串，跳转 URL 不保证可反查正文 |
| 现有采样工具 | `vendor-sample` 使用固定服务商白名单，目前没有 Fuyao，不能只新增 JSON 计划就运行 |
| 现有标准网关 | `HTTPJSONProvider` 接收本项目完整 batch，认证为可选 Bearer；Fuyao 使用 `X-api-key` 和供应商信封。不能把其 URL 直接填成标准网关端点 |

公司行为依据：[除复权字段](https://fuyao.aicubes.cn/docs/api-reference/corporate-actions/)。其它差异依据：[集合竞价机会](https://fuyao.aicubes.cn/docs/api-reference/auction-opportunities/)、[资讯详情](https://fuyao.aicubes.cn/docs/api-reference/news-article-detail/)、[快讯](https://fuyao.aicubes.cn/docs/api-reference/news-flash/)、[个股新闻](https://fuyao.aicubes.cn/docs/api-reference/news-stock-timeline/)。上述实现原则是对本项目契约的评估，不是服务商承诺。

还需要保留以下历史信息边界：龙虎榜的日期零点不代表盘中已经可见；连板天梯的 `seal_nextday` 使用次日结果；财报按报告期末取数不代表当时已披露，仍要审阅 `report_date_ms` 及更正；热榜当前最多 100、历史最多 30 且限制一年，不能拿榜单作全市场分母。日期范围异动解读还允许截断，空列表可能是降级，其四个原始时间字段单位待核实。依据：[龙虎榜](https://fuyao.aicubes.cn/docs/api-reference/dragon-tiger-data/)、[连板](https://fuyao.aicubes.cn/docs/api-reference/limit-up-data/)、[财报](https://fuyao.aicubes.cn/docs/api-reference/financials/)、[热榜](https://fuyao.aicubes.cn/docs/api-reference/hot-list-data/)、[日期范围异动解读](https://fuyao.aicubes.cn/docs/api-reference/news-anomaly-analysis/)。

## 鉴权、限流与文档可靠性

接入流程是同花顺账号登录后签发 API Key，调用使用 `X-api-key`；`2001` 为认证失败，`2003` 为能力权限不足。拥有 Key 不表示所有模块都有权限。本次没有签发、查看、撤销或使用任何 Key。后续如采样，只从进程环境或本地令牌文件读取，不能放进聊天、URL、计划或报告。依据：[快速开始](https://fuyao.aicubes.cn/docs/quickstart/)。

文档表示不限制累计调用次数，同时保留动态限流；HTTP 429 或业务 `4001` 都要处理。没有找到可据此确定的全站固定 QPS、商业费用、持续运行 SLA 或本地长期保存/用途许可承诺，不能写成永久免费或可无限高并发。本次是文档范围内未找到，不推断服务商不存在其它协议。依据：[接口总览](https://fuyao.aicubes.cn/docs/api-reference/overview/)。

容量举例仅作预算推算：若假设股票池 5,000 只，使用默认每页 100，则一次扫描约 50 个请求，每分钟一轮、240 分钟约 12,000 个请求/日，尚未包括其它数据、耗时和重试。实际股票数、可用分页大小、端点限额与新鲜度均未实测；累计次数不设限不能证明这个轮询预算可行。

接口文档总体有可实施的参数、单位、错误和空值定义，也有需要人工核对的地方：

- 首页概述与细页粒度不同：单只 A 股日线、批量日/周/月必须分别处理；日历细页支持显式十年窗口，不能只按首页“近一年”判断。
- 部分页仍写 HTTP 恒为 200，总览明确可能返回 HTTP 429；应同时检查 HTTP、JSON 解析及业务码。
- OpenAPI 的 98 个响应只引用通用 `ApiResponse`，其 `data` 未细化；另外 13 个有内联细化。自动生成客户端不能替代业务数据校验。
- 部分约束只在说明文字中：例如代码批量上限、参数互斥、期货/期权端外周期。不能仅信任枚举或表单。
- 下载文档的浏览器/API Key 入口说明不在同一页；客户端限定模块也有目录，因此目录、示例、权限三者要分别核验。

MCP 是同一能力的工具包装，不增加分钟数据或授权。当前可查阅 [MCP 总览](https://fuyao.aicubes.cn/docs/mcp/overview/)，但观势的自动采集应走确定性的 REST 适配器；没有必要为行情引入 LLM、MCP 运行依赖或自动选工具。

## 推荐后续步骤与完成条件

1. **先补访问事实。** 核实账户对目标公开接口及 dump 的权限、费用、个人本地缓存和持续轮询范围；向服务方明确询问对外 A 股/指数 1 分钟 OHLC、完成语义、历史分钟、历史成分及 ST/停复牌能力。若答复仍无分钟能力，就只按补充源评估。
2. **再做独立的小样本采样器。** 沿用固定主机、显式授权依据、预算、原始响应与哈希、未知值和无自动重试规则；先实现 dry-run。本轮没有实现这个适配器，也没有可直接运行的 Fuyao 采样计划。
3. **建议首轮范围。** 主板、创业板、科创板各一只，取此前已结束交易日的短窗口未复权日线、少量当前报价、日历、公司行为、概念/行业目录及当前关系。建议本地请求上限 20、串行、间隔至少 1 秒；这是待确认的本地预算，不是平台公布的 QPS，也不是本次已经执行的计划。遇限流停止并留证，不扩大到整库或分钟探测。
4. **按原始证据验数据。** 核对单位、价格精度、三板块覆盖、缺失/空组、错误分类、时间含义、成员新鲜度和重复修订。日线可与已有独立来源比较，但响应成功不证明底层独立或策略可用；日线不送进 `minute-quality` 冒充分钟。
5. **最后才讨论标准 batch。** 只有补齐分钟、同一分钟历史量能、基准、历史/当时有效资格、完整成员分母和复权时点，才进入标准网关映射、全市场覆盖/限流及连续影子验收。缺口需要其它授权来源时，保留逐字段来源和一致性检查，不静默拼接。

本次只证明文档目录与当前项目需求的匹配程度。Fuyao 的真实权限、准确性、时效、全市场覆盖和历史可见性均未实测；`strategy_input_ready/full_market_verified/release_allowed` 不能据此变为 true，`live_alert` 继续锁定。

## 本轮验证

仅做文档及结构核对：离线解析两份文本和 OpenAPI，统计并去重路径；核对 111 个目录路径均可对应 REST 参考页，确认 11 个额外路径有客户端限定说明、3 个属于 dump；检查接口索引、来源哈希及本次新增本地链接。

没有运行 Python 软件测试、Node 或浏览器功能验收；本轮没有运行时代码变更。历史 270 项等记录不作为本轮执行结果。
