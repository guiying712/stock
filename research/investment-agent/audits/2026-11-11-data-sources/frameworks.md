# 参考项目数据源核查：框架与海外组（6 项）

核查日期：2026-11-11（America/Los_Angeles）。范围为资料库已固定的提交，本轮通过 GitHub 连接器读取固定提交的文件树与关键源码；没有运行上游项目、没有调用行情接口、没有验证账户套餐与实时可用性。下文“代码确认”指请求目标或路由在源码中存在，不代表端点现已可用。

## 汇总

| 项目 | 真正的数据入口 | A 股相关性 | 本轮证据 |
|---|---|---|---|
| vnpy | 可插拔 datafeed：迅投研、米筐 RQData、Tushare、Wind、iFinD、掘金等；实时行情也可由券商/期货网关取得 | 有 A 股商业数据与证券网关路线，框架本身不送数据权限 | 主框架加载代码 + RQData/迅投研示例核实；供应商完整外部适配器未逐一审计 |
| Qlib | Yahoo Finance（yahooquery）、东方财富、BaoStock、中证指数；另有 CoinGecko 和用户导入数据 | 主要是研究数据处理和采集示例；A 股日线/5 分钟/财务与指数成分分开获取 | 6 类 collector 关键源码核实 |
| NautilusTrader | Databento、Tardis、CoinAPI、Interactive Brokers 和交易所直连适配器 | 已核实的主要入口面向海外交易所、加密市场、多市场券商；未发现据此可直接交付观势 A 股全市场分钟数据的证据 | Databento/Tardis 核心客户端代码 + IB 和适配器文档 |
| Kronos | 主例子读本地 CSV；微调读本地 Qlib；扩展示例经 AKShare/BaoStock/东方财富取数据 | 是消费 K 线的模型，不是行情服务 | 模型例子、微调入口、A 股下载脚本核实 |
| Vibe-Trading | 29 种注册入口，A 股默认腾讯→东方财富→BaoStock→AKShare→Tushare→恒生聚源→本地 | 数据路由可借鉴；同上游重复封装很多，不是 29 个独立供应商 | registry、腾讯、东方财富、AKShare、SEC/RSSHub 源码核实 |
| ai-financial-agent | Financial Datasets API 统一提供股价、新闻、三张财报、财务指标与筛选 | README 定位美国市场，未见 A 股接入 | 工具源码实际请求地址与 API Key 头核实 |

## vnpy/vnpy

固定提交：`c6e231caf32b7fc97e6459817fff66458cf7e7c4`。

- **历史数据不内置。** `get_datafeed()` 根据 `datafeed.name` 动态加载 `vnpy_<name>`；默认名字、用户名、密码为空，未配置只返回空基类，并提示无法查询 K 线/Tick。它提供统一抽象，不是提供免费行情。[datafeed.py L43–74](https://github.com/vnpy/vnpy/blob/c6e231caf32b7fc97e6459817fff66458cf7e7c4/vnpy/trader/datafeed.py#L43)；[setting.py L27–29](https://github.com/vnpy/vnpy/blob/c6e231caf32b7fc97e6459817fff66458cf7e7c4/vnpy/trader/setting.py#L27)
- 固定 README 列出 9 个外部历史 datafeed：**迅投研 xt、米筐 RQData、MultiCharts、Tushare、Wind、同花顺 iFinD、天勤 TQSDK、掘金 gm、Polygon**。对应包通常在独立仓库；需各自 SDK/终端/账户或数据权限，不能只装 vnpy 就获得全部服务。[README L199–217](https://github.com/vnpy/vnpy/blob/c6e231caf32b7fc97e6459817fff66458cf7e7c4/README.md#L199)
- **A 股研究例子明确两条路线。** 米筐例子调用 `rqdatac.index_components` 取历史成分，再经 datafeed 查询日线；迅投研例子调用 `xtquant.xtdata` 下载板块/成分变更、获取历史日期成分，再经 datafeed 查询 K 线，例子设置为日线。[RQData 示例 L80–147](https://github.com/vnpy/vnpy/blob/c6e231caf32b7fc97e6459817fff66458cf7e7c4/examples/alpha_research/download_data_rq.ipynb#L80)；[迅投研示例](https://github.com/vnpy/vnpy/blob/c6e231caf32b7fc97e6459817fff66458cf7e7c4/examples/alpha_research/download_data_xt.ipynb)
- **实时行情与历史服务不同。** README 还列出 CTP 等期货网关、XTP/TORA 等 A 股证券网关、IB 海外券商网关，以及 RQData/迅投研实时行情。网关依赖对应经纪商或服务商，不可将 CTP 期货权限视为 A 股权限。[README L89–133](https://github.com/vnpy/vnpy/blob/c6e231caf32b7fc97e6459817fff66458cf7e7c4/README.md#L89)
- 本轮未查各外部适配器的所有字段、最小粒度、最新收费与授权；不据此给出全市场盘中容量结论。

## microsoft/qlib

固定提交：`54355232463878d2eebb91fe0ee5fa7fa1f5976c`。

- **研究框架 + 数据采集脚本，不是自营行情 API。** 固定 README 说官方打包数据暂时停用，给出社区 `chenditc/investment_data` release 包；旧官方数据说明写来源为 Yahoo Finance，并提示质量局限。这个停用状态是固定版本文本，不是本轮实测服务状态；社区包的再上游未在本轮独立审计。[README L232–282](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/README.md#L232)
- **行情：Yahoo Finance。** `yahoo/collector.py` 用 `yahooquery.Ticker(...).history`，代码提供日线与 1 分钟采集路径；同文件的 A 股基准指数另用东方财富 `push2his.eastmoney.com/.../kline/get`。SDK 是 yahooquery，真实上游是 Yahoo；Qlib 不是独立数据源。[Yahoo collector L20–45](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/scripts/data_collector/yahoo/collector.py#L20)；[请求 L126–178](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/scripts/data_collector/yahoo/collector.py#L126)
- **A 股 5 分钟：BaoStock。** `baostock_5min` 使用无参数 `bs.login()`、`query_history_k_data_plus`，默认 HS300、5 分钟，采集 `adjustflag="3"`（代码注释/参数表明未复权），归一化另依赖日线数据。不能把这份特定采集器称为全市场一分钟实时源。[BaoStock collector L62–119](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/scripts/data_collector/baostock_5min/collector.py#L62)
- **财务：BaoStock。** PIT collector 请求业绩快报、利润、业绩预告、成长数据；可见 `pubDate` 字段处理，但归一化对缺失日期有推算补值，不能直接当作已验收的公告时点证据。[PIT collector L96–239](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/scripts/data_collector/pit/collector.py#L96)
- **基金净值：东方财富** `api.fund.eastmoney.com/f10/lsjz`；**中国指数成分/变更：中证指数官网与 BaoStock**；**加密研究数据：pycoingecko → CoinGecko**。这些是不同用途的 collector，不是一个自动主备路由。[基金 L23](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/scripts/data_collector/fund/collector.py#L23)；[指数 L24–30](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/scripts/data_collector/cn_index/collector.py#L24)；[CoinGecko L17](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/scripts/data_collector/crypto/collector.py#L17)
- 本轮确认上述代码入口；没有证明 Yahoo 目前对所有 A 股代码/分钟日期完整可用，也没有验证采样授权。

## nautechsystems/nautilus_trader

固定提交：`2b35934c0cb9e047757407d7c59f83852048502e`（资料库记录的 develop 快照；不能混用稳定版文档）。

- **是事件驱动框架与适配器集合。** 数据来自外部交易所、券商或服务商，本地 Parquet/DBN/CSV 等只是存储或重放输入，不是独立供应商。
- **Databento：历史/实时市场数据。** 核心 Rust 客户端实际构建 `databento::HistoricalClient` 并带 API Key 调用 timeseries。集成文档覆盖 L1/L2/L3、逐笔成交、秒/分钟/小时/日 K 线；需 Databento 账户/相应数据权限。未在本轮核查产品覆盖是否含目标 A 股资产。[historical.rs L89–113](https://github.com/nautechsystems/nautilus_trader/blob/2b35934c0cb9e047757407d7c59f83852048502e/crates/adapters/databento/src/historical.rs#L89)；[数据类型 L80–104](https://github.com/nautechsystems/nautilus_trader/blob/2b35934c0cb9e047757407d7c59f83852048502e/docs/integrations/databento.md#L80)
- **Tardis：加密市场历史/重放数据。** 客户端缺 API Key 会拒绝初始化；元数据走 `api.tardis.dev/v1`，Machine 服务处理历史重放/实时标准化。文档区分 Nautilus 的 `TARDIS_API_KEY` 与 Machine 的 `TM_API_KEY`。免费日期/套餐描述属于上游文档，未复核现行价格。[HTTP client L86–116](https://github.com/nautechsystems/nautilus_trader/blob/2b35934c0cb9e047757407d7c59f83852048502e/crates/adapters/tardis/src/http/client.rs#L86)；[Tardis 集成](https://github.com/nautechsystems/nautilus_trader/blob/2b35934c0cb9e047757407d7c59f83852048502e/docs/integrations/tardis.md)
- **IB：通过 TWS/IB Gateway 获取实时和历史数据。** 需运行相应终端/网关与账户权限；代码例子可设 delayed/frozen，不能因连接成功就当实时授权成功。[IB 集成 L1–64](https://github.com/nautechsystems/nautilus_trader/blob/2b35934c0cb9e047757407d7c59f83852048502e/docs/integrations/interactive_brokers.md#L1)
- README 的其他已列集成包括 **CoinAPI、Binance、Bybit、Coinbase、Kraken、OKX、Deribit、dYdX、Hyperliquid、Derive、Lighter、区块链节点、AX、Betfair、Polymarket** 等。**FinFeed、Kalshi 标记 building**，不计已接通来源。这部分为固定 README 证据，未逐一审计适配器。[集成表 L100–129](https://github.com/nautechsystems/nautilus_trader/blob/2b35934c0cb9e047757407d7c59f83852048502e/README.md#L100)

## shiyu-coder/Kronos

固定提交：`67b630e67f6a18c9e9be918d9b4337c960db1e9a`。

- **主预测示例读取本地** `./data/XSHG_5min_600977.csv`；Tokenizer/Model 从 Hugging Face 的 NeoQuasar 仓库下载。**Hugging Face 提供模型权重，不提供这些实时行情。** CSV 的原始服务商不能仅凭文件名确认。[prediction_example.py L42–49](https://github.com/shiyu-coder/Kronos/blob/67b630e67f6a18c9e9be918d9b4337c960db1e9a/examples/prediction_example.py#L42)
- **微调入口** `qlib.init(provider_uri=...)` 读取用户本地 Qlib 目录，再由 QlibDataLoader 读取 OHLCV；README 指示例为日频。上游数据究竟来自 Yahoo、商业源或用户自建，取决于用户准备的 Qlib 数据，不可一概写成 Yahoo。[qlib_data_preprocess.py L19–58](https://github.com/shiyu-coder/Kronos/blob/67b630e67f6a18c9e9be918d9b4337c960db1e9a/finetune/qlib_data_preprocess.py#L19)
- **扩展 A 股日线例子** 使用 `akshare.stock_zh_a_hist`；另一个下载脚本写明 **AKShare→BaoStock→东方财富直连**。AKShare 此接口对应东方财富体系，直连东方财富是同一上游的另一调用方式，不是完全独立备源。[A 股预测 L28–57](https://github.com/shiyu-coder/Kronos/blob/67b630e67f6a18c9e9be918d9b4337c960db1e9a/examples/prediction_cn_markets_day.py#L28)；[下载脚本 L353–381](https://github.com/shiyu-coder/Kronos/blob/67b630e67f6a18c9e9be918d9b4337c960db1e9a/examples/get_akshare_date_2024-2025_x.py#L353)
- **特别注意：该下载脚本所有真实来源失败后调用 `create_sample_data`。** 它会提示“使用示例数据”，但调用方仍会得到 DataFrame；不能拿运行成功或生成 CSV 当真实接通凭证。这是该示例脚本的行为，不推断全部 Kronos 路径都生成模拟行情。
- README 称预训练数据覆盖 45 个全球交易所；本轮未审计论文/训练原始语料提供商，所以保持“训练集底层采集供应商未确认”，不把交易所数量写成内置可访问行情源数。

## HKUDS/Vibe-Trading

固定提交：`bff6e7625fd479d78db81aa5fbf4f317f6bef416`。

- **真实 A 股默认回退顺序（源码确认）：腾讯 → 东方财富 → BaoStock → AKShare → Tushare → 恒生聚源 Gildata → local。** 环境配置可覆盖顺序。腾讯直连 `web.ifzq.gtimg.cn` 日线接口；东方财富直连 `push2his.eastmoney.com`，代码映射 1/5/15/30/60 分钟及日/周/月。**有分钟参数支持不等于历史覆盖、完结语义或账号授权已验证。**[registry.py L180–196](https://github.com/HKUDS/Vibe-Trading/blob/bff6e7625fd479d78db81aa5fbf4f317f6bef416/agent/backtest/loaders/registry.py#L180)；[腾讯 L30–34](https://github.com/HKUDS/Vibe-Trading/blob/bff6e7625fd479d78db81aa5fbf4f317f6bef416/agent/backtest/loaders/tencent_loader.py#L30)；[东方财富 L34–55](https://github.com/HKUDS/Vibe-Trading/blob/bff6e7625fd479d78db81aa5fbf4f317f6bef416/agent/backtest/loaders/eastmoney_client.py#L34)
- **AKShare 的 A 股路径再次请求 `stock_zh_a_hist`，与东方财富直连接口有共同上游。** Yahoo 直连与 yfinance 同样共用 Yahoo；CCXT 是多交易所 SDK；local 是用户文件；RSSHub 是内容聚合入口。因此“29 个 source”不能理解成 29 个彼此独立的原始供应商。[AKShare L219–238](https://github.com/HKUDS/Vibe-Trading/blob/bff6e7625fd479d78db81aa5fbf4f317f6bef416/agent/backtest/loaders/akshare_loader.py#L219)
- **mootdx/通达信仍注册，但已从默认 A 股链移除。** 固定代码注释说因上游协议失效，仅保留显式选择。这是项目维护者的判断与路由行为，本轮没有对通达信发请求验证。[registry.py L183–187](https://github.com/HKUDS/Vibe-Trading/blob/bff6e7625fd479d78db81aa5fbf4f317f6bef416/agent/backtest/loaders/registry.py#L183)
- **29 个注册数据入口完整名称**（不含 auto）：tushare、okx、nobitex、wallex、binance、yfinance、akshare、baostock、tencent、mootdx、ccxt、futu、eastmoney、sina、stooq、yahoo、finnhub、alphavantage、tiingo、fmp、gildata、qveris、india_broker、pykrx、longbridge、mt5、tickerall、b3_cotahist、local。[registry.py L36–66](https://github.com/HKUDS/Vibe-Trading/blob/bff6e7625fd479d78db81aa5fbf4f317f6bef416/agent/backtest/loaders/registry.py#L36)
- **各市场核心底层来源**：美股/港股多为 Yahoo、腾讯/东方财富、Stooq、新浪；可选 Finnhub/Alpha Vantage/Tiingo/FMP/Longbridge。加密为 OKX、Binance、CCXT 对接的交易所，另有 Nobitex/Wallex 显式入口。外汇/金属 MT5 为经纪商终端数据，TickerAll 为托管入口；印度入口接 Zerodha/Shoonya/Dhan；韩国 pykrx；巴西 B3 官方 COTAHIST 文件。此扩展列表以 README 与注册表为证，未审计每个 endpoint。
- **认证分层**：腾讯/东方财富/BaoStock/AKShare路径代码不要求个人 API Key；Tushare/Gildata/Finnhub/Alpha Vantage/Tiingo/FMP/QVeris 等需 token/key；Longbridge 需 App Key/Secret/Token；Futu 需 OpenD；MT5 需终端，India broker 需券商登录。具体收费、权限与“无 Key”服务的访问许可未复核。[数据源表 README L624–650](https://github.com/HKUDS/Vibe-Trading/blob/bff6e7625fd479d78db81aa5fbf4f317f6bef416/README.md#L624)
- **基本面与新闻不走相同链。** 本轮核实 `get_fundamentals` 工具只接受 auto/sec，底层读美国 SEC EDGAR companyfacts/submissions，不能称其为 A 股基本面统一路由；其他东方财富工具与 Tushare 财务模块另存。RSSHub 事件提供器需要配置实例和 feed，源码明确没有内置 feed catalogue；它不是默认已经接通全部财经新闻。[基本面工具 L18–20](https://github.com/HKUDS/Vibe-Trading/blob/bff6e7625fd479d78db81aa5fbf4f317f6bef416/agent/src/tools/get_fundamentals_tool.py#L18)；[SEC 客户端 L48–54](https://github.com/HKUDS/Vibe-Trading/blob/bff6e7625fd479d78db81aa5fbf4f317f6bef416/agent/backtest/loaders/sec_edgar_client.py#L48)；[RSSHub L195](https://github.com/HKUDS/Vibe-Trading/blob/bff6e7625fd479d78db81aa5fbf4f317f6bef416/agent/backtest/loaders/rsshub_events.py#L195)
- QVeris 是可选付费数据市场入口，README 明示显式启用、不会进入默认自动回退。平台宣称供应商数量未独立核验，也不把它当作无需授权的原始源。

## virattt/ai-financial-agent

固定提交：`836d30b28ff596e01d8cc287e0b83b3d3e1a1bc1`。

- **数据统一来自 Financial Datasets API**，源码没有多源自动回退。工具请求 `api.financialdatasets.ai` 的新闻、报价快照、历史价格、利润表、资产负债表、现金流量表、财务指标、财务筛选接口，均用 `X-API-Key`。[financial-tools.ts L40–102](https://github.com/virattt/ai-financial-agent/blob/836d30b28ff596e01d8cc287e0b83b3d3e1a1bc1/lib/ai/tools/financial-tools.ts#L40)；[财报与筛选 L116–304](https://github.com/virattt/ai-financial-agent/blob/836d30b28ff596e01d8cc287e0b83b3d3e1a1bc1/lib/ai/tools/financial-tools.ts#L116)
- 历史价格工具参数包含 second/minute/day/week/month/year，默认 day。这只能证明工具声明支持这些粒度，不能证明免费账户都有对应历史权限。
- README 定位美国市场；AAPL 等免费示例标的与“30 年/全市场”是固定 README 的供应商宣传，当前收费与覆盖未在本轮核实，不据此作为 A 股方案。[README L88–98](https://github.com/virattt/ai-financial-agent/blob/836d30b28ff596e01d8cc287e0b83b3d3e1a1bc1/README.md#L88)
- OpenAI 是分析模型，LangSmith 是追踪/观测服务，均不是行情数据提供商。Financial Datasets 再上游原始数据许可/交易所来源，本项目源码没有披露。

