# B 组：6 个参考项目数据源静态核查

核查日期：2026-11-11（America/Los_Angeles）。范围为资料库已经归档的固定提交，不代表当前 main 最新代码。通过 GitHub 连接器读取固定提交文件；未运行上游、未调用任何行情接口、未测试账户权限、未读取用户凭据。主备顺序为代码默认值，部署配置和健康状态可能改变顺序。“有实现”不等于数据质量或持续可用性已验收。

| 项目 | 固定提交 | 行情与日线主要来源 | 新闻、财务等补充 |
|---|---|---|---|
| TradingAgents-CN | 51060a7682cf51810b4bc3a704829438d18cd8dc | 本地导入、Tushare、AKShare、BaoStock，另有可选 QMT；AKShare 下层包括东方财富、新浪、腾讯 | A 股新闻/公告为 AKShare→东财；财务 Tushare/AKShare/BaoStock；另有 Google News、Finnhub、Yahoo/Alpha Vantage 等模块 |
| TradingAgents | c4544913a14ed3df5f1ed7b9e8483270ce20682a | 默认 Yahoo Finance（yfinance）日线；可配置 Alpha Vantage | 默认 SEC EDGAR→Yahoo 财报，Yahoo 新闻；可选 Alpha Vantage，FRED 宏观、Polymarket 事件数据；另有 Reddit RSS/Stocktwits 模块 |
| daily_stock_analysis | 4e6226430b76124e5f43b19201fc6338a62f5e1d | A 股实时默认腾讯→新浪→efinance/东财→AKShare/东财；日线默认 efinance→AKShare→通达信→BaoStock→Yahoo→腾讯，Tushare 配置成功后置前 | 可选 TickFlow、妙想、长桥、富途、Finnhub、Alpha Vantage；新闻经多搜索服务、RSS/NewsNow，社交情绪可用 Adanos |
| PanWatch | 1c272a825c2713e3701d8ce81622f9c49dacbef7 | 仓内 marketdata 直接请求腾讯、东财、新浪、Yahoo、Stooq；报价与日 K 分开路由 | 新闻雪球/东财，公告东财，快讯财联社/新浪/东财；财务腾讯/东财；资金/龙虎榜等多为东财，北向模块同花顺 |
| AlphaSift | 20b9a33bc051e07572fb012b07c58f5aa706dc91 | A 股快照新浪→efinance→AKShare 东财→东财数据中心；日线腾讯→新浪→AKShare→BaoStock；有 Tushare Token 置前；其他市场 Yahoo | 可选新闻东财、公告巨潮、资金流 AKShare、报价腾讯，行业/概念东财 |
| stock-analysis-plugin | 4aeb5e8993c3f51eac18ffcc6c5fd53bb86f258d | A 股报价 AKShare→Tushare→efinance→腾讯→新浪→pytdx；前复权日/周/月 K 线 AKShare→Tushare→efinance→腾讯→BaoStock | 港美股 Yahoo/Finnhub/长桥/Alpha Vantage；新闻/板块/资金多数 AKShare→东财，另有新浪/同花顺/巨潮/雪球；研究搜索、理杏仁和交易所接口 |

## 1. hsliuping/TradingAgents-CN

**已核到代码**：应用层 DataSourceManager 初始化 LocalAdapter、TushareAdapter、AKShareAdapter、BaoStockAdapter、QMTAdapter，按配置优先级降序；默认启用清单为 local、tushare、akshare、baostock，QMT 属可选适配。Local 是用户导入/本地存储，不是独立市场供应商。Tushare 默认优先级 3，AKShare 2，BaoStock 1；配置可覆盖，不能把这一顺序当所有分析路径的唯一默认。

- A 股报价：AKShare 适配器默认 stock_zh_a_spot_em（东方财富），可切 stock_zh_a_spot（新浪）。
- 日/周/月 K：AKShare 内部实际顺序为东方财富 stock_zh_a_hist → 新浪 stock_zh_a_daily → 腾讯 stock_zh_a_hist_tx。注释说“腾讯和新浪”，以实际列表为准。
- 分钟：AKShare 适配层代码映射 5/15/30/60m 到 stock_zh_a_minute；这一入口不是 1m 全市场历史承诺。QMT 也有 K 线适配，但需运行 QMT 与相应连接/权限。本次没有验证请求参数、完成性或覆盖。
- 财务：Tushare daily_basic 及财报 provider；AKShare 有东方财富财报接口，BaoStock 为额外路径。新闻/公告适配调用 stock_news_em、stock_announcement_em，底层都是东财。
- 其他市场/外部工具：固定目录中有 Yahoo、Finnhub、Alpha Vantage、港股 provider；外部来源目录明确 AKShare、Tushare、Google News、Finnhub。不能把这些模块存在等同于全部在默认 A 股分析流程中启用。
- 凭据：Tushare Token；QMT 环境/终端；Finnhub/Alpha Vantage 各自 API key。AKShare 本身是接口封装，不是一家行情供应商。
- **局限**：chinese_finance.py 中论坛情绪函数返回零与“数据受限”，财经新闻搜索函数是 example.com 模拟示例，不能把该文件里的“财联社”标签列为已接通真实采集。

证据：
- [应用数据源管理器 L28–42](https://github.com/hsliuping/TradingAgents-CN/blob/51060a7682cf51810b4bc3a704829438d18cd8dc/app/services/data_sources/manager.py#L28-L42)
- [默认启用及配置优先级](https://github.com/hsliuping/TradingAgents-CN/blob/51060a7682cf51810b4bc3a704829438d18cd8dc/app/core/data_source_priority.py#L12)
- [AKShare 行情与 K 线路由 L315–529](https://github.com/hsliuping/TradingAgents-CN/blob/51060a7682cf51810b4bc3a704829438d18cd8dc/app/services/data_sources/akshare_adapter.py#L315-L529)
- [外部来源目录](https://github.com/hsliuping/TradingAgents-CN/blob/51060a7682cf51810b4bc3a704829438d18cd8dc/core/tools/external/external_data_source_catalog.py)
- [模拟社交/新闻示例 L112–170](https://github.com/hsliuping/TradingAgents-CN/blob/51060a7682cf51810b4bc3a704829438d18cd8dc/tradingagents/dataflows/news/chinese_finance.py#L112-L170)

## 2. TauricResearch/TradingAgents

**已核到代码**：default_config 的 core_stock_apis、technical_indicators、news_data 默认 yfinance；fundamental_data 默认 sec_edgar,yfinance。宏观默认 fred，事件概率默认 polymarket。router 按用户配置的 vendor 列表走回退，不悄悄添加用户未选的供应商；仅 default 哨兵才采用全部可用来源。

- Yahoo Finance 是底层，yfinance 是 Python 包。行情实现 Ticker.history(start,end)，研究日线；Alpha Vantage 股票实现请求 TIME_SERIES_DAILY_ADJUSTED。不能据“stock data”名称认定有完成分钟流。
- 三张财报默认 SEC EDGAR XBRL companyfacts → Yahoo；公司概览和 insider transactions 由 Yahoo（SEC 适配不提供这两项）。
- 新闻默认 Yahoo 新闻/搜索，Alpha Vantage 新闻为可配置替代。FRED 宏观需 FRED_API_KEY；Polymarket 当前适配 keyless。
- SEC EDGAR 使用 sec.gov company_tickers 与 data.sec.gov companyfacts；支持 SEC_EDGAR_USER_AGENT 配置。Alpha Vantage 需 API key。Yahoo 这一路无需个人 API key，不等于覆盖、稳定性或许可保证。
- 固定版本还有 Reddit 搜索 RSS、Stocktwits 公共 streams 模块；本轮仅核到实现端点，未证明它们属于默认新闻路由。

证据：
- [默认供应商配置](https://github.com/TauricResearch/TradingAgents/blob/c4544913a14ed3df5f1ed7b9e8483270ce20682a/tradingagents/default_config.py#L166-L190)
- [工具与供应商路由](https://github.com/TauricResearch/TradingAgents/blob/c4544913a14ed3df5f1ed7b9e8483270ce20682a/tradingagents/dataflows/router.py#L107-L162)
- [仅按显式配置回退 L232–251](https://github.com/TauricResearch/TradingAgents/blob/c4544913a14ed3df5f1ed7b9e8483270ce20682a/tradingagents/dataflows/router.py#L232-L251)
- [Yahoo history](https://github.com/TauricResearch/TradingAgents/blob/c4544913a14ed3df5f1ed7b9e8483270ce20682a/tradingagents/dataflows/vendors/yahoo/market.py#L34)
- [Alpha Vantage 日线](https://github.com/TauricResearch/TradingAgents/blob/c4544913a14ed3df5f1ed7b9e8483270ce20682a/tradingagents/dataflows/vendors/alpha_vantage/stock.py#L40)
- [SEC 数据端点](https://github.com/TauricResearch/TradingAgents/blob/c4544913a14ed3df5f1ed7b9e8483270ce20682a/tradingagents/dataflows/vendors/sec_edgar.py#L37-L38)

## 3. ZhuLinsen/daily_stock_analysis

**已核到代码**：实时报价、日线和新闻各自有独立链，不能合成一个“数据源优先级”。

- 普通 A 股实时配置默认 tencent,akshare_sina,efinance,akshare_em。这意味着腾讯 → 新浪 → 东方财富 → 东方财富，最后两项并非独立上游。
- 日线初始化默认 efinance(P0)、AKShare(P1)、Pytdx(P2)、BaoStock(P3)、yfinance(P4)、腾讯(P5)；按市场适用性分流，美股优先 Yahoo。**Tushare 配置并初始化成功后实现优先级 -1**，排在 efinance 前；包 __init__.py 注释还写 0，已按实现纠正。
- AKShare 日线内部东财→新浪→腾讯；efinance 默认东财；pytdx 接通达信行情服务。日线下载和即时快照不等于可直接获得观势所需历史完整分钟。
- 可选注册：Tushare、TickFlow（TICKFLOW_API_KEY）、妙想（MX_APIKEY）、长桥 OAuth/legacy 凭据、富途 OpenD、Finnhub、Alpha Vantage。没有配置的可选源不实例化。不同市场与用途有专门路由，不能称全部默认调用。
- A 股基本面使用 AKShare 适配器，海外有 yfinance/Futu 基本面适配。AKShare 数据项覆盖财报、业绩预告、分红、机构/股东、资金流与板块，多个具体底层来源需按函数辨认。
- 新闻搜索：配置了 Anspire 则插入第一位；其后按已配置项为 Bocha、Tavily、Brave、SerpAPI、MiniMax、SearXNG。搜索平台返回的文章才是新闻原始发布源，LLM 供应商不算行情源。
- 独立资讯模块支持 RSS/Atom、NewsNow；内置模板含 SEC、港交所、MarketWatch RSS 及 NewsNow 的财联社热榜、雪球热门股、华尔街见闻、金十、格隆汇。模板存在不表示用户已启用。
- 可选 Adanos 社交情绪 API（Reddit/X/Polymarket 相关摘要），与证券行情分离。

证据：
- [实时默认链 src/config.py L1351](https://github.com/ZhuLinsen/daily_stock_analysis/blob/4e6226430b76124e5f43b19201fc6338a62f5e1d/src/config.py#L1351)
- [初始化/可选源 data_provider/base.py L1793–1904](https://github.com/ZhuLinsen/daily_stock_analysis/blob/4e6226430b76124e5f43b19201fc6338a62f5e1d/data_provider/base.py#L1793-L1904)
- [Tushare 实际 -1 优先级 L216–235](https://github.com/ZhuLinsen/daily_stock_analysis/blob/4e6226430b76124e5f43b19201fc6338a62f5e1d/data_provider/tushare_fetcher.py#L216-L235)
- [AKShare 三路日线](https://github.com/ZhuLinsen/daily_stock_analysis/blob/4e6226430b76124e5f43b19201fc6338a62f5e1d/data_provider/akshare_fetcher.py#L600-L602)
- [新闻搜索初始化 L2464–2506](https://github.com/ZhuLinsen/daily_stock_analysis/blob/4e6226430b76124e5f43b19201fc6338a62f5e1d/src/search_service.py#L2464-L2506)
- [RSS/NewsNow 模板](https://github.com/ZhuLinsen/daily_stock_analysis/blob/4e6226430b76124e5f43b19201fc6338a62f5e1d/src/services/intelligence_service.py#L29-L105)
- [可选 Adanos 社交服务](https://github.com/ZhuLinsen/daily_stock_analysis/blob/4e6226430b76124e5f43b19201fc6338a62f5e1d/src/services/social_sentiment_service.py)

## 4. TNT-Likely/PanWatch

**已核到代码与包文档**：当前核心为仓内 packages/marketdata。不能仅凭 requirements 中 akshare/efinance 就将它们写为主取数路径。

- 报价已注册 Tencent(CN/HK/US)、Sina(US/HK)、Eastmoney(CN)、yfinance(HK/US)。Sina 的报价适配在本版本不覆盖 CN。
- 日 K 已注册腾讯(CN/HK/US)、东财(CN/HK)、Stooq(US)、Yahoo(US/HK)。腾讯端点 web.ifzq.gtimg.cn/appstock/app/fqkline/get；东财 push2his.eastmoney.com；Stooq CSV；Yahoo chart interval=1d。
- 包 README 给出的示例顺序为报价腾讯→新浪、K 线腾讯→东财→Stooq，但宿主真正顺序由 DataSource 表/ConfigProvider 控制；本轮不把示例写成不可变应用默认。
- 新闻直接雪球 statuses/stock_timeline、东财新闻搜索、东财公告；雪球支持 cookie 配置。快讯直接财联社 cls.cn、新浪直播、东财快讯。新闻原始源与“使用模型生成分析”分开。
- 财务腾讯/东财；资金流东财/新浪，龙虎榜/两融/股东/分红多为东财，北向同花顺；热股/板块发现也是东财直连。
- 主要公共端点在代码中不要求个人 API key，雪球等访问可能依赖 cookie；没有进行网络可用性或授权测试。README 明确多种新增财务/快讯等字段尚未真实抓取校准，不能当成已运行验证。

证据：
- [包能力表与验证限制 L124–161](https://github.com/TNT-Likely/PanWatch/blob/1c272a825c2713e3701d8ce81622f9c49dacbef7/packages/marketdata/README.md#L124-L161)
- [日 K 供应商/端点](https://github.com/TNT-Likely/PanWatch/blob/1c272a825c2713e3701d8ce81622f9c49dacbef7/packages/marketdata/src/marketdata/vendors/kline.py#L15-L18)
- [Yahoo 明确 1d](https://github.com/TNT-Likely/PanWatch/blob/1c272a825c2713e3701d8ce81622f9c49dacbef7/packages/marketdata/src/marketdata/vendors/kline.py#L232-L233)
- [雪球/东财新闻代码](https://github.com/TNT-Likely/PanWatch/blob/1c272a825c2713e3701d8ce81622f9c49dacbef7/packages/marketdata/src/marketdata/vendors/news.py)
- [三路快讯代码](https://github.com/TNT-Likely/PanWatch/blob/1c272a825c2713e3701d8ce81622f9c49dacbef7/packages/marketdata/src/marketdata/vendors/flash_news.py)

## 5. ZhuLinsen/alphasift

**已核到代码**：
- A 股快照默认新浪、efinance、AKShare 东方财富、东财数据中心；有 Token 时 Tushare 置前。会按保存的健康状态重排，并允许明确标记陈旧的 last-good 缓存。
- Tushare 快照组合最近交易日 daily、daily_basic、stock_basic；代码明确不是实时快照。因此“有 Token 优先”可能改变时效口径。
- 日线 auto：有 Token 为 Tushare→腾讯→新浪→AKShare→BaoStock；没有则从腾讯起；会按健康状态重排。yfinance 仅显式路径/海外用途，不在 A 股 auto 链。
- 腾讯 fqkline 优先取 qfqday、缺失可取 day；新浪 K 线实现明确未复权；AKShare 调 stock_zh_a_hist。主备之间有复权口径差异，不能未经归一化直接喂策略。
- efinance、akshare_em、em_datacenter 属同一东财来源组。新浪快照直接 Market_Center.getHQNodeData；东财数据中心 data.eastmoney.com/dataapi/xuangu/list。
- 非 A 股由 Yahoo screener/yfinance 路径；候选上下文可调用 AKShare 东财新闻、巨潮公告、资金流，以及腾讯即时价格；行业/概念由 AKShare 东财或东财直接接口。
- Tushare 需 Token 与接口权限；其余主链是公共接口/封装，无个人 key 不代表授权或质量已验收。LLM 排序是可选处理，不是原始数据来源。

证据：
- [快照默认链 config.py L12–13](https://github.com/ZhuLinsen/alphasift/blob/20b9a33bc051e07572fb012b07c58f5aa706dc91/alphasift/config.py#L12-L13)
- [快照实现及 Tushare 日线语义](https://github.com/ZhuLinsen/alphasift/blob/20b9a33bc051e07572fb012b07c58f5aa706dc91/alphasift/snapshot.py#L775-L805)
- [日线 auto 链 L189–206](https://github.com/ZhuLinsen/alphasift/blob/20b9a33bc051e07572fb012b07c58f5aa706dc91/alphasift/daily.py#L189-L206)
- [腾讯及新浪复权差异 L569–640](https://github.com/ZhuLinsen/alphasift/blob/20b9a33bc051e07572fb012b07c58f5aa706dc91/alphasift/daily.py#L569-L640)
- [候选补充上下文 L213–275](https://github.com/ZhuLinsen/alphasift/blob/20b9a33bc051e07572fb012b07c58f5aa706dc91/alphasift/candidate_context.py#L213-L275)
- [行业映射实现](https://github.com/ZhuLinsen/alphasift/blob/20b9a33bc051e07572fb012b07c58f5aa706dc91/alphasift/industry.py)

## 6. Weaxs/stock-analysis-plugin

**已核到代码，并发现 README/实现差异**：
- 普通 A 股报价实际链：AKShare→Tushare→efinance→腾讯→新浪→pytdx。**代码没有 BaoStock 报价回退**，虽 README/本地旧档案将其列入。ETF 先额外尝试 AKShare ETF 专用 spot；带交易所前缀的代码报价直走腾讯/新浪。
- 股票/ETF K 线为前复权链：AKShare→Tushare→efinance→腾讯→BaoStock；Tushare 不服务 ETF。指数明确使用腾讯→新浪→BaoStock，保留原始点位。普通股票链不纳入新浪/pytdx 未复权 K 线。成功源会 sticky 提前。
- CLI --period 仅 daily、weekly、monthly，不能把“多行情源”当作已经提供历史分钟 API。
- 海外 K：yfinance → Finnhub/Longbridge(HK/US) → Alpha Vantage(US)；港股报价额外腾讯备源。Yahoo 是底层供应商，yfinance 是包；长桥使用 longport SDK。
- A 股 AKShare 与 efinance 常都来自东财；腾讯 qt.gtimg.cn、web.ifzq.gtimg.cn；新浪 hq.sinajs.cn、quotes.sina.cn；pytdx 为通达信行情服务。
- 资讯/财务：新闻 AKShare stock_news_em→东财；财报 AKShare/海外 Yahoo；板块、龙虎榜、资金流、涨停池、股东、ETF 等按工具调用东财/新浪/同花顺/巨潮。value_data 还直接访问 SSE/SZSE/HKEX/CNINFO，估值用 AKShare 的百度/乐咕/中证或可选理杏仁 Token。
- 搜索工具有 Tavily、Brave、SerpAPI、Bocha、SearXNG；A 股情绪取东财股吧/雪球，海外情绪可接 Adanos。
- 凭据：TUSHARE_TOKEN、FINNHUB_API_KEY、LONGBRIDGE_*、ALPHAVANTAGE_API_KEY、LIXINGER_TOKEN 与各搜索 key 仅在选中对应供应商时需要。未评估费用/额度或实际账户权限。

证据：
- [报价实际链 L1076–1101](https://github.com/Weaxs/stock-analysis-plugin/blob/4aeb5e8993c3f51eac18ffcc6c5fd53bb86f258d/tools/stock_data.py#L1076-L1101)
- [K 线链 L530–550](https://github.com/Weaxs/stock-analysis-plugin/blob/4aeb5e8993c3f51eac18ffcc6c5fd53bb86f258d/tools/stock_data.py#L530-L550)
- [海外回退 L1031–1055](https://github.com/Weaxs/stock-analysis-plugin/blob/4aeb5e8993c3f51eac18ffcc6c5fd53bb86f258d/tools/stock_data.py#L1031-L1055)
- [CLI 日周月粒度 L3381](https://github.com/Weaxs/stock-analysis-plugin/blob/4aeb5e8993c3f51eac18ffcc6c5fd53bb86f258d/tools/stock_data.py#L3381)
- [估值/股东/公告等来源](https://github.com/Weaxs/stock-analysis-plugin/blob/4aeb5e8993c3f51eac18ffcc6c5fd53bb86f258d/tools/value_data.py)
- [新闻检索与情绪来源](https://github.com/Weaxs/stock-analysis-plugin/blob/4aeb5e8993c3f51eac18ffcc6c5fd53bb86f258d/tools/search_intel.py)

## 对观势最相关的结论

1. 这 6 项没有发现可据静态代码直接认定已经解决“全 A 股完成分钟历史、历史成分有效期、复权时点、持续影子验证”的现成数据服务。很多项目核心是即时快照加日 K。
2. 多个 SDK 并不等于独立上游；efinance、AKShare 的 _em 接口、东财直连应归为同一来源组。
3. 可借鉴的是用途分路由、来源/时点留证、健康回退与显式缺失处理。真正的数据接入仍需独立权限、粒度与时点 PoC，不能从“开源项目用了”推导观势已可接通。

