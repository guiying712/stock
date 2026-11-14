# 界面、资料与新增项目：6 项数据来源

2026-11-11（America/Los_Angeles）。固定提交与资料库登记一致，以下区分已读代码、固定文档与未知项。只读上游源码和说明，没有请求任何证券行情或读取用户凭据。

## Open-Dev-Society/OpenStock

固定提交 `b72306d39fa27dc55252ceecf858165ecf5a3fa3`。

- **行情/基本资料/新闻的后端 API 是 Finnhub**，代码请求 `finnhub.io/api/v1` 下的 quote、stock/profile2、stock/metric、company-news、news、search。需要 Finnhub API Key。[实际请求代码](https://github.com/Open-Dev-Society/OpenStock/blob/b72306d39fa27dc55252ceecf858165ecf5a3fa3/lib/actions/finnhub.actions.ts#L10)
- **图表用 TradingView 嵌入组件**，其显示覆盖、延迟与 Finnhub 后端的可查询覆盖是两回事。该版 `hasFinnhubQuotes` 只允许所选美股/加密路径，不能由“多市场图表”推断 A 股行情接入。[市场配置](https://github.com/Open-Dev-Society/OpenStock/blob/b72306d39fa27dc55252ceecf858165ecf5a3fa3/lib/markets.ts#L144)；[图表组件](https://github.com/Open-Dev-Society/OpenStock/blob/b72306d39fa27dc55252ceecf858165ecf5a3fa3/components/TradingViewWidget.tsx)
- **Adanos 是可选情绪数据源**，请求 `api.adanos.org`，使用自己的 Key；包含 Reddit、X、news、Polymarket 维度，不是直接读取这些平台的证券行情。[Adanos 客户端](https://github.com/Open-Dev-Society/OpenStock/blob/b72306d39fa27dc55252ceecf858165ecf5a3fa3/lib/actions/adanos.actions.ts#L16)；[情绪来源配置](https://github.com/Open-Dev-Society/OpenStock/blob/b72306d39fa27dc55252ceecf858165ecf5a3fa3/lib/actions/adanos.helpers.ts#L17)
- 代码含缓存与失败后旧值处理，页面更新间隔不能解释为供应商数据的新鲜度。当前套餐、延迟与许可未实测。

## wbh604/UZI-Skill

固定提交 `3dc556bdad8229fad01dc54c83d6d9402ef6218c`。

- **A 股日线实际链**：AKShare `stock_zh_a_hist`（东财）→ AKShare `stock_zh_a_daily`（新浪）→ BaoStock → 东财 push2his 直连 → 新浪 K 线直连 → 腾讯 fqkline → 通用 provider 兜底。provider 包含 AKShare、efinance、Tushare、BaoStock，按安装情况/Token/配置选择；它不是额外的独立数据商。核心日线链有多个相同底层源的不同访问方式。[日线源码](https://github.com/wbh604/UZI-Skill/blob/3dc556bdad8229fad01dc54c83d6d9402ef6218c/skills/deep-analysis/scripts/lib/data_sources.py#L895)；[provider 配置](https://github.com/wbh604/UZI-Skill/blob/3dc556bdad8229fad01dc54c83d6d9402ef6218c/skills/deep-analysis/scripts/lib/providers/__init__.py#L92)
- **A 股基础资料**有 AKShare 雪球接口，东财/腾讯/新浪与 BaoStock 补字段；可配置东方财富妙想 `MX_APIKEY`。妙想的实际请求服务为 `mkapi2.dfcfs.com`，是否有 Key 与普通公开端点是不同路径。[基础资料](https://github.com/wbh604/UZI-Skill/blob/3dc556bdad8229fad01dc54c83d6d9402ef6218c/skills/deep-analysis/scripts/lib/data_sources.py#L362)；[妙想适配器](https://github.com/wbh604/UZI-Skill/blob/3dc556bdad8229fad01dc54c83d6d9402ef6218c/skills/deep-analysis/scripts/lib/mx_api.py#L37)
- **港股 K 线**有东财/新浪、yfinance/Yahoo chart；**美股日线**为 yfinance → AKShare → Yahoo chart → Stooq。yfinance 与 Yahoo chart 是同一底层数据体系。[海外行情](https://github.com/wbh604/UZI-Skill/blob/3dc556bdad8229fad01dc54c83d6d9402ef6218c/skills/deep-analysis/scripts/lib/data_sources.py#L1063)
- **独立日常筛选器的盘中入口**：报价腾讯优先、东财备用；当日分时使用东财 trends2，不足 3 条时再试腾讯 minute，取更长结果。它与上述研究报告日线函数分开，不应统一称为一条七源分钟链。[盘中源码](https://github.com/wbh604/UZI-Skill/blob/3dc556bdad8229fad01dc54c83d6d9402ef6218c/skills/deep-analysis/scripts/lib/daily_screen/sources.py#L18)
- **已读新闻代码**直连金十、东财快讯、东财公告、同花顺今日新闻；DDGS 用于网络检索。来源注册表另列巨潮、港交所、财联社、第一财经、央行/统计局等站点；注册表存在不证明每条已实际采到。`web_search.py` 把 Tavily/Serper 写为未来 fallback，本次不列为已经接通。[新闻实现](https://github.com/wbh604/UZI-Skill/blob/3dc556bdad8229fad01dc54c83d6d9402ef6218c/skills/deep-analysis/scripts/lib/news_providers.py#L97)；[检索实现](https://github.com/wbh604/UZI-Skill/blob/3dc556bdad8229fad01dc54c83d6d9402ef6218c/skills/deep-analysis/scripts/lib/web_search.py#L1)；[来源目录](https://github.com/wbh604/UZI-Skill/blob/3dc556bdad8229fad01dc54c83d6d9402ef6218c/skills/deep-analysis/scripts/lib/data_source_registry.py#L51)
- 核查的主要是报价、K 线、新闻与来源注册，未对全部财务维度做逐字段审计。上游“零 Key”指部分基础路径，可选 Tushare、妙想仍有凭据要求。

## wilsonfreitas/awesome-quant

固定提交 `b52a1a942eda36a6539b886f26a4a391883580d6`。

这是量化工具、库和服务的人工整理索引，含 Market Data & Data Sources 分类；没有一个属于 awesome-quant 自身的统一运行行情源。每个链接都是另一个项目或服务，需要单独确认。此次“所有参考项目”指资料库登记的 24 项，没有递归扩大到该目录中的所有外部链接。[固定 README](https://github.com/wilsonfreitas/awesome-quant/blob/b52a1a942eda36a6539b886f26a4a391883580d6/README.md)

## zgwl/chinese-buy-us-stock-guide

固定提交 `c37b33b2fe294466afdbea299828910c44ae565f`。

这是一组美股开户、银行、券商、税务等文字资料，不是采集行情的软件，不应列为数据服务或券商接口。本文只确认资料类型，没有采纳其当前金融/法律建议。[固定 README](https://github.com/zgwl/chinese-buy-us-stock-guide/blob/c37b33b2fe294466afdbea299828910c44ae565f/README.md)

## suifei/dsh-market-lens（新增）

固定提交 `9ed847797bc0eabcd3d46f3724da4df40e4fcbba`。以下均核到实际实现，补充原档案的 README 级证据。

| 数据 | 实际来源/路由 | 代码依据 |
|---|---|---|
| A 股、港股报价与 K 线 | 东方财富 → 腾讯 | [service.js L29](https://github.com/suifei/dsh-market-lens/blob/9ed847797bc0eabcd3d46f3724da4df40e4fcbba/lib/service.js#L29) |
| 美股报价与 K 线 | Yahoo chart → 腾讯 | [Yahoo 适配器](https://github.com/suifei/dsh-market-lens/blob/9ed847797bc0eabcd3d46f3724da4df40e4fcbba/lib/sources/yahoo.js#L25) |
| 搜索 | 腾讯、东财、Yahoo 分源合并 | [service.js L169](https://github.com/suifei/dsh-market-lens/blob/9ed847797bc0eabcd3d46f3724da4df40e4fcbba/lib/service.js#L169) |
| 快讯 | 新浪 roll → 东财 7×24 | [news.js](https://github.com/suifei/dsh-market-lens/blob/9ed847797bc0eabcd3d46f3724da4df40e4fcbba/lib/sources/news.js#L15) |
| A 股财务指标 | 东财 F10，最近 4 期 | [financials.js L19](https://github.com/suifei/dsh-market-lens/blob/9ed847797bc0eabcd3d46f3724da4df40e4fcbba/lib/sources/financials.js#L19) |
| 公告、讨论、个股新闻 | 东财公告、东财股吧 HTML、东财统一新闻搜索 | [posts.js](https://github.com/suifei/dsh-market-lens/blob/9ed847797bc0eabcd3d46f3724da4df40e4fcbba/lib/sources/posts.js#L23) |

- 东财使用 push2 批量报价、push2his K 线；腾讯使用 qt.gtimg.cn、web.ifzq.gtimg.cn。已读公开路径不要求个人行情 API Key，代码中的网站固定参数不等于用户账户授权。
- **K 线明确只允许 day/week/month**，count 限 20–320。东财日周月请求前复权；腾讯也使用 qfq；Yahoo 返回调整方式另标为 close。没有发现该入口接分钟 K 线。[粒度限制](https://github.com/suifei/dsh-market-lens/blob/9ed847797bc0eabcd3d46f3724da4df40e4fcbba/lib/service.js#L129)；[东财 K 线](https://github.com/suifei/dsh-market-lens/blob/9ed847797bc0eabcd3d46f3724da4df40e4fcbba/lib/sources/eastmoney.js#L104)；[腾讯 K 线](https://github.com/suifei/dsh-market-lens/blob/9ed847797bc0eabcd3d46f3724da4df40e4fcbba/lib/sources/tencent.js#L109)
- DSH 宿主提供缓存、请求合并和提醒运行环境，是消费数据的系统，不是新的上游。缺源时可能读取 stale 缓存；部分东财适配调用开启 insecureFallback，后续参考代码须保留观势自己的 HTTPS 约束，不照搬传输降级。

## theBigGavin/marketingdashboard（新增）

固定提交 `2d71054d76bb78b82ddb7818af4bdff49a6179a7`。核心为 Node 代理聚合各网站，前端部分接口在代理失败时直接请求相同上游。

| 数据类别 | 已读代码确认的来源 | 固定代码证据 |
|---|---|---|
| 股票、指数报价/分时/板块榜 | 腾讯 qt.gtimg.cn、ifzq.gtimg.cn；VIX 另取新浪，离岸人民币分时可取东财 | [腾讯模块](https://github.com/theBigGavin/marketingdashboard/blob/2d71054d76bb78b82ddb7818af4bdff49a6179a7/server/sources/tencent.cjs#L60)、[端点](https://github.com/theBigGavin/marketingdashboard/blob/2d71054d76bb78b82ddb7818af4bdff49a6179a7/server/lib/tencent-urls.cjs#L7) |
| 板块/个股资金、成分 | 东财为主；按数据项回退新浪行业/概念与腾讯申万榜；有的仅部分覆盖或日频 | [资金源链](https://github.com/theBigGavin/marketingdashboard/blob/2d71054d76bb78b82ddb7818af4bdff49a6179a7/server/sources/moneyflow.cjs#L8) |
| 财务、主营、资产负债/现金流、预期 | 东财 datacenter、emweb F10 | [财务模块](https://github.com/theBigGavin/marketingdashboard/blob/2d71054d76bb78b82ddb7818af4bdff49a6179a7/server/sources/eastmoney-fin.cjs#L74) |
| 国内/国际期货报价及分时/日线 | 新浪 hq.sinajs.cn 与 stock2.finance.sina.com.cn | [期货模块](https://github.com/theBigGavin/marketingdashboard/blob/2d71054d76bb78b82ddb7818af4bdff49a6179a7/server/sources/futures.cjs#L140) |
| BTC | Binance 报价/K 线；报价失败另走 OKX，不据此声称 K 线同样双源 | [BTC 模块](https://github.com/theBigGavin/marketingdashboard/blob/2d71054d76bb78b82ddb7818af4bdff49a6179a7/server/sources/futures.cjs#L83) |
| 快讯 | 新浪直播 → 华尔街见闻 api-one-wscn.awtmt.com | [快讯路由](https://github.com/theBigGavin/marketingdashboard/blob/2d71054d76bb78b82ddb7818af4bdff49a6179a7/server/sources/sina.cjs#L42) |
| 美债收益率 | CNBC 当前值；美国财政部年度 CSV 与随包历史存档 | [美债模块](https://github.com/theBigGavin/marketingdashboard/blob/2d71054d76bb78b82ddb7818af4bdff49a6179a7/server/sources/treasuries.cjs#L8) |
| 商品现货与现期对照 | 生意社 100ppi.com，历史逐日保存 | [生意社模块](https://github.com/theBigGavin/marketingdashboard/blob/2d71054d76bb78b82ddb7818af4bdff49a6179a7/server/sources/sunsirs.cjs#L60) |
| AI 行业公司资本开支 | SEC EDGAR companyfacts | [SEC 模块](https://github.com/theBigGavin/marketingdashboard/blob/2d71054d76bb78b82ddb7818af4bdff49a6179a7/server/sources/sec-capex.cjs#L22) |
| 半导体 PPI | FRED CSV | [FRED 模块](https://github.com/theBigGavin/marketingdashboard/blob/2d71054d76bb78b82ddb7818af4bdff49a6179a7/server/sources/fred-ppi.cjs#L11) |
| 模型价格/使用排行/能力与支出指标 | OpenRouter models 与 rankings-daily；Artificial Analysis；TrakToken feed | [价格](https://github.com/theBigGavin/marketingdashboard/blob/2d71054d76bb78b82ddb7818af4bdff49a6179a7/server/sources/token-prices.cjs#L23)、[使用排行](https://github.com/theBigGavin/marketingdashboard/blob/2d71054d76bb78b82ddb7818af4bdff49a6179a7/server/sources/openrouter.cjs#L70)、[模型/支出](https://github.com/theBigGavin/marketingdashboard/blob/2d71054d76bb78b82ddb7818af4bdff49a6179a7/server/sources/ai-models.cjs#L12) |
| 问财查询 | 同花顺问财 OpenAPI，需要 Key | [问财模块](https://github.com/theBigGavin/marketingdashboard/blob/2d71054d76bb78b82ddb7818af4bdff49a6179a7/server/sources/ai.cjs#L82) |
| 黄金观察页 | 读取作者部署环境外部 gold-monitor JSON、央行购金 SQLite，不在此模块联网采集 | [本地数据入口](https://github.com/theBigGavin/marketingdashboard/blob/2d71054d76bb78b82ddb7818af4bdff49a6179a7/server/sources/gold.cjs#L1) |

边界：

- 腾讯 minute/query 返回的是分时点序列。它与完整分钟 OHLCV、任意历史区间是不同数据契约；界面有“分钟线”不自动满足观势完成分钟要求。
- 板块资金源链可能从东财分类改为新浪或申万分类；个股资金可从盘中退至日频。不能把不同分类、频率的结果无标记拼成同一历史。
- 源码支持 last-good、stale/asof 等降级；本轮不继承注释中的历史实测结论。
- AI 基础设施模块有手工锚点和参数外推，未来段不是数据 API 返回的已实现数值。[模型参数](https://github.com/theBigGavin/marketingdashboard/blob/2d71054d76bb78b82ddb7818af4bdff49a6179a7/server/sources/ai-infra.cjs#L9)
- OpenRouter 排行、Artificial Analysis、问财分别有凭据要求；不能因部分行情免个人 Key 就称整个看板无需配置。黄金 JSON/数据库的更底层采集供应商，此仓库读取代码未说明，保持未知。
- 浏览器直连腾讯或见闻仍使用相同数据方，只是绕过本站代理，不是新增独立备源。[前端回退](https://github.com/theBigGavin/marketingdashboard/blob/2d71054d76bb78b82ddb7818af4bdff49a6179a7/src/lib/api.ts#L452)
