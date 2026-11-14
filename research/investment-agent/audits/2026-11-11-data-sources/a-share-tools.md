# 参考项目数据源审计 A 组（6 项）

审阅日期：2026-11-11（America/Los_Angeles）。范围是资料库已经固定的提交，并非宣称上游最新 main。通过 GitHub 连接器读取固定提交源码，没有安装运行上游、调用行情服务或读取任何本地密钥。代码可见 ≠ 当前接口可用、账户权限、数据许可或分钟语义已通过实测。

证据标记：**代码** = 已读取具体实现；**目录/文档** = 上游自述或端点清单；**未知** = 本轮没有独立核实。以下源码 URL 均钉在固定提交。

## 总表

| 项目 / 固定 SHA | 行情与 K 线 | 基本面、新闻、其他 | 账户与主要边界 |
|---|---|---|---|
| Sequoia-X / 444c0db69ff36b46ef2b22ab265051d60c16029d | **代码**：BaoStock；历史与增量日线，后复权 adjustflag=1。股票清单也来自 BaoStock | 本轮数据引擎未见新闻、独立财务或分钟实现 | bs.login() 无用户参数；README 称免注册。没有查到替代源；不能据 README “无限流”承诺服务能力 |
| WyckoffTradingAgent / 30aa5da6c42061ef79683930df89fbd6bc746cc7 | **代码**：股票历史统一入口按 TickFlow → Tushare → AKShare → BaoStock → efinance 尝试；另有 TickFlow 全市场报价、日线/分钟和盘口客户端；AKShare 东方财富快照辅助入口 | **代码**：TickFlow 财务指标历史；东方财富个股新闻；可选 RSS + GDELT 主题新闻 | TickFlow API Key；Tushare token。不同 workflow 可能直接走 TickFlow 批量路径，不能把五源链当成所有功能统一回退 |
| Vibe-Research / db3a7c60afcb643abdf36933294765d1cbfc2b9c | **代码**：A 股报价与主日线直连腾讯；港美股 Yahoo 日线；**目录**：BaoStock、通达信 HTTP 盘后包、腾讯分钟与逐笔、北交所官方备源 | 新浪财务、BaoStock 估值、东财资金/事件/财务、同花顺预期、巨潮/交易所公告；Yahoo、SEC、港交所；财联社、RSS、华尔街见闻、央视、Exa 搜索等 | 168 个端点为该提交生成目录数量，不是 168 个独立供应商。问财需 key，SEC 需联系标识；其余是否免费及当前许可不由代码证明 |
| tick-stock-panel / a17742c97d70e6de1af9917844a38b75d963b101 | **代码**：TickFlow SDK 为默认；Fuyao 和 TdxQuant 插件可按数据集路由；TdxQuant 支持 1m，Fuyao 此插件**不提供分钟** | TickFlow 财务；Fuyao 财报、指标、龙虎榜、盘前风向标和交易日历等 | TickFlow 免费/付费端点分开；Fuyao、TdxQuant 各需 key。插件声明和套餐门槛分别控制能力，非所有源有同等覆盖 |
| jcp / 44af274e0bfa2cef1364527eda1c8e64dfd00a64 | **代码**：通达信行情为主（github.com/injoyai/tdx Go 客户端），新浪行情为备；实时/盘口、1m/日/周/月 K 线 | **代码**：东财板块/个股/指数资金流和公告；财联社电报网页；节假日使用 holiday-cn GitHub 数据经 jsDelivr | 已查路径未见行情用户 key；公开/协议接口当前可用性未实测。股票与指数的服务使用相同主备机制 |
| a-stock-data / cb57c7aba720380b48a11dd065c6db57a2c39db9 | **代码**：腾讯报价、日周月及 1/5/15/30/60 分钟 K；通达信官网全市场日线压缩包；BaoStock；mootdx 只保留财务/F10 用途 | **代码与目录**：新浪、东财、同花顺、百度、巨潮、财联社、华尔街见闻、央视、交易所、指数公司、央行/统计局/中债/中国货币网、期货交易所等 | 问财需要 key；其他已列代码路径不要求个人 key。34 个来源为上游分类口径，包含同一东财站点的多个 API 族。无统一行情服务 SLA |

## 1. Sequoia-X

- 单一行情供应商是 BaoStock，SQLite 是存储，不是数据供应商。
- `sequoia_x/data/engine.py` 的批量 worker（33–49 行）直接调用 `query_history_k_data_plus`，字段为 date/open/high/low/close/volume/amount，`frequency="d"`、`adjustflag="1"`；回填路径也是同样口径。
- 股票清单用 `query_stock_basic`，保留上市且股票类型的记录。只从这段实现不能证明北交所或完整历史退市股票覆盖。
- 本轮未见分钟、实时盘口、新闻接入；没有备用行情源。README 的“不限流”“全市场耗时”属于项目自述，本轮未验证。
- 证据：[数据引擎](https://github.com/sngyai/Sequoia-X/blob/444c0db69ff36b46ef2b22ab265051d60c16029d/sequoia_x/data/engine.py#L33)、[固定 README](https://github.com/sngyai/Sequoia-X/blob/444c0db69ff36b46ef2b22ab265051d60c16029d/README.md)。

## 2. WyckoffTradingAgent

- README 强调 TickFlow 日线，但统一历史入口实际保留五源链，顺序见 `integrations/data_source.py:51–77`：TickFlow → Tushare → AKShare → BaoStock → efinance。不能只记一个源。
- TickFlow 是直接服务方：`https://api.tickflow.org`；客户端有 `/v1/klines`、`/v1/klines/intraday`、批量接口、depth、financial metrics 与 quotes。历史适配器调用默认日线，分钟由专门方法获取，不能把“按日线策略实时拉取”说成“分钟策略”。
- Tushare 调用 `ts.pro_bar(... adj="qfq")`，读取 `TUSHARE_TOKEN`；权限失败的诊断会尝试 `pro.daily`。
- AKShare 调用 `stock_zh_a_hist(period="daily")`；辅助快照调用 `stock_zh_a_spot_em`。efinance 调用 `stock.get_quote_history(klt=101,fqt=1)`。它们是库/适配器名称，并不应计作与东方财富完全独立的原始行情。AKShare 历史与 efinance 的已安装依赖版本、精确底层服务本轮未沿 lockfile 穿透核实；东财映射应注明库 API 层，不能宣称独立供应商容灾。
- `integrations/fundamental_history.py` 直接取 TickFlow `get_financial_metrics(latest=False)`；并非 Supabase 提供财务。Supabase 存用户和业务状态，README 已明确无行情缓存。
- 个股新闻 `integrations/stock_news_events.py:12` 直连 `search-api-web.eastmoney.com/search/jsonp`。
- 主题新闻 `integrations/theme_news.py` 读取自配 RSS 与 `api.gdeltproject.org/api/v2/doc/doc`；可配置禁用 GDELT。
- 未核实各工作流是否全部经过五源门面、港美股是否同等回退、账户当前套餐或 TickFlow 更底层供应链。
- 证据：[五源历史入口](https://github.com/YoungCan-Wang/WyckoffTradingAgent/blob/30aa5da6c42061ef79683930df89fbd6bc746cc7/integrations/data_source.py#L51)、[TickFlow 客户端](https://github.com/YoungCan-Wang/WyckoffTradingAgent/blob/30aa5da6c42061ef79683930df89fbd6bc746cc7/integrations/tickflow_client.py#L350)、[AKShare 适配](https://github.com/YoungCan-Wang/WyckoffTradingAgent/blob/30aa5da6c42061ef79683930df89fbd6bc746cc7/integrations/data_source_akshare.py#L31)、[财务历史](https://github.com/YoungCan-Wang/WyckoffTradingAgent/blob/30aa5da6c42061ef79683930df89fbd6bc746cc7/integrations/fundamental_history.py#L30)、[个股新闻](https://github.com/YoungCan-Wang/WyckoffTradingAgent/blob/30aa5da6c42061ef79683930df89fbd6bc746cc7/integrations/stock_news_events.py#L12)、[主题新闻](https://github.com/YoungCan-Wang/WyckoffTradingAgent/blob/30aa5da6c42061ef79683930df89fbd6bc746cc7/integrations/theme_news.py#L26)。

## 3. Vibe-Research

该版本自己的 `datasources/CATALOG.md` 有 168 个端点。数据层在 `.agents/skills/data-access/scripts/`，多数是直接 HTTP，而非统一买某个行情包。

| 数据类别 | 已核实来源与层级 |
|---|---|
| A 股快照/主日线 | **代码** `fetch_quote.py:46` → `qt.gtimg.cn/q=`；`fetch_kline.py:60` → `web.ifzq.gtimg.cn/appstock/app/fqkline/get`，前复权日线 |
| 扩展行情 | **目录** 腾讯日周月/分钟/当日逐笔；BaoStock 前复权日线与日历；通达信官网 HTTP 盘后包（不是 TCP 盘口）；北交所官网快照备源 |
| A 股财务和估值 | **目录** 新浪财报摘要/三表；BaoStock PE/PB/PS/PCF 与 ST/停牌；东财个股资料、主营、股东；通达信 mootdx 财务/F10；同花顺 EPS 预期 |
| 公告与资金事件 | **目录** 巨潮、深交所、东财公告；东财资金流/龙虎榜/解禁/机构调研/回购等；沪深交易所备源。新浪板块资金流是不同口径备源，不能拼接成同一序列 |
| 港美股 | **代码** Yahoo chart、财务 timeseries、options、新闻；SEC EDGAR submissions/companyfacts/全文检索。**目录** 腾讯报价、东财港美公司/财报、港交所公告、百度 PE 历史 |
| 新闻与检索 | **目录** 财联社、东财、RSS（源清单移自 investment-news）、华尔街见闻、央视、Yahoo、Techmeme；**代码** Exa MCP `https://mcp.exa.ai/mcp`，是线索检索而非行情供给 |
| 宏观/其他 | **目录** 央行、统计局、中债、中国货币网、申万、中证/国证；FRED CSV、美国财政部、CFTC、FINRA、CBOE、Nasdaq、FinMind；Kalshi/Polymarket 等预测市场和公开产业数据 |

- `datasources/UPSTREAM.md` 解释了代码来历：部分移植 a-stock-data v3.7.0/v3.10.1、global-stock-data v2.0.3；investment-news 仅使用源清单，RSS 抓取器是产品自有实现。这是上游工具代码来源，不能混同为金融数据原始供应商。
- 问财需 `IWENCAI_API_KEY`；SEC 使用 `VRA_SEC_CONTACT` 联系信息，不是收费 key；Exa 代码走公开 MCP，目录标示免 key，但本轮未验证额度/商业许可。
- 已核实主要行情/海外代码，其余 168 端点未逐个请求或全量审计，应标为“目录证据”。各源发布时间、历史修订、数据许可仍需专项验证。
- 证据：[完整端点目录](https://github.com/simonlin1212/Vibe-Research/blob/db3a7c60afcb643abdf36933294765d1cbfc2b9c/datasources/CATALOG.md)、[代码来历](https://github.com/simonlin1212/Vibe-Research/blob/db3a7c60afcb643abdf36933294765d1cbfc2b9c/datasources/UPSTREAM.md)、[腾讯报价](https://github.com/simonlin1212/Vibe-Research/blob/db3a7c60afcb643abdf36933294765d1cbfc2b9c/.agents/skills/data-access/scripts/fetch_quote.py#L46)、[腾讯日线](https://github.com/simonlin1212/Vibe-Research/blob/db3a7c60afcb643abdf36933294765d1cbfc2b9c/.agents/skills/data-access/scripts/fetch_kline.py#L60)、[Yahoo](https://github.com/simonlin1212/Vibe-Research/blob/db3a7c60afcb643abdf36933294765d1cbfc2b9c/.agents/skills/data-access/scripts/sources/yahoo.py#L29)、[SEC](https://github.com/simonlin1212/Vibe-Research/blob/db3a7c60afcb643abdf36933294765d1cbfc2b9c/.agents/skills/data-access/scripts/sources/sec.py#L39)。

## 4. tick-stock-panel

- 三类内置来源不是统一相同主备链，而是数据集能力路由；默认是 TickFlow。代码另允许 YAML 自定义 HTTP 来源，实际接谁由配置决定，不能列为固定第四家供应商。
- TickFlow 官方 Python SDK：无 key/免费档走 `TickFlow.free()` 和 `https://free-api.tickflow.org`；付费 key 走 `TickFlow(api_key=...)`、`https://api.tickflow.org`，可设 base_url。**这是固定版本运行政策，不是 2026-11-11 供应商套餐承诺。**
- 固定代码的路由门槛：日 K none，复权与实时 starter，分钟与五档 pro，财务与全量分钟 expert。
- Fuyao：`https://fuyao.aicubes.cn` + `X-api-key`；代码/README称同花顺金融数据服务，但请求打向 Fuyao，不能写成用户直接使用同花顺官方账户。提供 realtime/daily/adj_factor/financial；**未声明 minute**，缺失能力返回 TickFlow 路径。日线锁 `interval=1d, adjust=none`，复权因子由事件和前收盘价派生；还取龙虎榜、盘前风向标、交易日历。准确更底层授权关系未核实。
- TdxQuant：`tdxaidata` 原生库/私有 TCP，代码注释写 `aihs/aids.tdx.com.cn`；需自己的 key。提供 realtime/depth5/daily/adj_factor/minute/full_minute，不提供 financial。分钟路由仅 1m，个股原始价；并不等于传统 mootdx 免费 TCP，二者必须分开。
- 证据：[TickFlow 端点与免费/付费分流](https://github.com/shy3130/tick-stock-panel/blob/a17742c97d70e6de1af9917844a38b75d963b101/backend/app/tickflow/client.py#L1)、[能力注册表](https://github.com/shy3130/tick-stock-panel/blob/a17742c97d70e6de1af9917844a38b75d963b101/backend/app/data_providers/capabilities.py#L28)、[Fuyao 能力](https://github.com/shy3130/tick-stock-panel/blob/a17742c97d70e6de1af9917844a38b75d963b101/backend/app/plugins/fuyao/provider.py#L1)、[Fuyao 请求](https://github.com/shy3130/tick-stock-panel/blob/a17742c97d70e6de1af9917844a38b75d963b101/backend/app/plugins/fuyao/client.py#L20)、[TdxQuant 能力](https://github.com/shy3130/tick-stock-panel/blob/a17742c97d70e6de1af9917844a38b75d963b101/backend/app/plugins/tdxquant/provider.py#L1)、[TdxQuant 原生客户端](https://github.com/shy3130/tick-stock-panel/blob/a17742c97d70e6de1af9917844a38b75d963b101/backend/app/plugins/tdxquant/client.py#L1)。

## 5. jcp

- `internal/services/market_service.go:117–118` 明确 primary = TDX，fallback = Sina；实时报价、K 线、指数与股票搜索都通过对应主备 facade。
- TDX 层使用 Go 库 `github.com/injoyai/tdx`，`DialDefault` 连接通达信协议服务器；不是 Tushare、AkShare 或 TdxQuant 付费 SDK。
- `market_provider_tdx.go:137–145` 对应 1m/日/周/月；1m 路径会过滤今天，不能从这个入口声称完整长期分钟历史。
- 新浪备源：`hq.sinajs.cn` 实时报价；`quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData` K 线。
- 东财：`push2.eastmoney.com/api/qt/clist/get` 板块与资金流、`push2.eastmoney.com/api/qt/stock/fflow/kline/get` 资金流序列、`np-anotice-stock.eastmoney.com/api/security/ann` 公告。
- 新闻：`news_service.go:52` 请求 `www.cls.cn/telegraph` 网页并解析，不是财联社付费授权 API。
- 节假日：`cdn.jsdelivr.net/gh/NateScarlet/holiday-cn@master/{year}.json`，是第三方 GitHub 节假日表，不是交易所权威交易日历。是否完全适合证券开市日未经本轮验证。
- 已查看路径没有行情个人 key；模型 key 与行情权限分开。上游已归档记录来自原档案，本轮不重新断言最新仓库状态。
- 证据：[服务初始化及端点](https://github.com/run-bigpig/jcp/blob/44af274e0bfa2cef1364527eda1c8e64dfd00a64/internal/services/market_service.go#L36)、[TDX 主备设置](https://github.com/run-bigpig/jcp/blob/44af274e0bfa2cef1364527eda1c8e64dfd00a64/internal/services/market_service.go#L115)、[通达信客户端](https://github.com/run-bigpig/jcp/blob/44af274e0bfa2cef1364527eda1c8e64dfd00a64/internal/services/market_provider_tdx.go#L42)、[K 线粒度](https://github.com/run-bigpig/jcp/blob/44af274e0bfa2cef1364527eda1c8e64dfd00a64/internal/services/market_provider_tdx.go#L130)、[财联社新闻](https://github.com/run-bigpig/jcp/blob/44af274e0bfa2cef1364527eda1c8e64dfd00a64/internal/services/news_service.go#L40)。

## 6. a-stock-data

固定版本自述 15 层、87 端点、34 来源。项目主体是含可运行取数代码的 SKILL.md，而非已经托管好的行情平台。此处读取其代码作为研究对象，未执行其中命令。

- **腾讯财经**：`qt.gtimg.cn` 报价/估值/五档；K 线在 `web.ifzq.gtimg.cn`、`proxy.finance.qq.com/ifzqgtimg`、`ifzq.gtimg.cn` 三入口轮换；它们仍是同一腾讯源，并不构成三个独立数据供应商。日/周/月前后复权，分钟 m1/m5/m15/m30/m60 只有不复权、最近最多 320 根；当日逐笔来自 `stock.gtimg.cn/data/index.php`。
- **通达信官网**：`www.tdx.com.cn/products/data/data/g4day/{ymd}.zip` 全市场单日盘后包，覆盖沪深北日线。**mootdx TCP** 是另一访问方式：上游称 2026-09 起行情命令失效，因此其固定版主要用财务/F10；本轮没有重测故障。
- **BaoStock**：历史估值、换手、停牌、ST、上市/退市日；代码限制不支持北交所。
- **新浪**：三张财报、复权因子、研报列表、ETF 期权、期货实时与日 K、A50。
- **东财 API 族**：datacenter（龙虎榜/解禁/两融/大宗/股东/分红/事件/可转债/LPR）、push2/push2his（板块/资金流/资料/ST）、reportapi/PDF（研报）、search/np-weblist（新闻）；统一 `em_get()` 限流，不能将同源不同 API 当独立容灾。
- **同花顺**：热点/涨停归因/hsgt 北向/basic 一致预期；**问财 OpenAPI**自然语言研报/数据查询需 `IWENCAI_API_KEY`。百度股市通提供带均线 K 线。
- **公告和新闻**：巨潮公告/互动易，上证 e 互动；财联社、华尔街见闻、央视。
- **官方机构**：沪深北交易所；中证/国证成分权重估值；申万行业变迁；央行社融、统计局 PMI、中债收益率曲线、中国货币网 FR/FDR。
- **期货与商品**：上期所、上期能源、郑商所、中金所、广期所日行情/期权/部分会员排名；上金所现货。大商所官方日行情未接，相关品种历史走新浪。不能因为“交易所集合”就认为覆盖所有交易所全部字段。
- 固定版代码除 mootdx/BaoStock 客户端外主要直接 HTTP；已移除 AKShare 依赖。README 的“不封 IP/免费”是上游观察，不构成服务保证或商业许可证明。
- 证据：[固定 SKILL 源码与目录](https://github.com/simonlin1212/a-stock-data/blob/cb57c7aba720380b48a11dd065c6db57a2c39db9/SKILL.md)、[腾讯分钟代码](https://github.com/simonlin1212/a-stock-data/blob/cb57c7aba720380b48a11dd065c6db57a2c39db9/SKILL.md#L1199)、[通达信盘后包](https://github.com/simonlin1212/a-stock-data/blob/cb57c7aba720380b48a11dd065c6db57a2c39db9/SKILL.md#L1412)、[新浪复权接口](https://github.com/simonlin1212/a-stock-data/blob/cb57c7aba720380b48a11dd065c6db57a2c39db9/SKILL.md#L1740)、[来源总表](https://github.com/simonlin1212/a-stock-data/blob/cb57c7aba720380b48a11dd065c6db57a2c39db9/README.md)。

## 给观势的直接启示（判断，不是集成结论）

1. A 股基础免费路径高度集中：腾讯、东财、新浪、BaoStock 与通达信。换 AKShare/efinance/mootdx 只是换客户端，不必然得到独立源。
2. 分钟数据需要单独比较：a-stock-data 腾讯只有有限近期窗口；jcp 的 1m 路径只取当日；tick-stock-panel 的 Fuyao 插件根本未接分钟。README 同时出现“实时”和“日线”不证明长期分钟历史可用。
3. TickFlow、Fuyao、TdxQuant 应作为不同商业/账户服务评估；固定开源代码展示能力，不代替账户权限、历史覆盖和许可验收。
4. 本轮只研究，不修改观势策略、数据源设置或 live_alert 发布锁。

## 来源元数据

本轮已读取源码的连接器元数据见 [provenance-a.json](provenance-a.json)。主要事实依据为上文固定提交 URL；临时缓存不视为完整源码备份。
