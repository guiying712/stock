# NEXT03 · 可信数据来源与首批样本

2026-10-30 UTC；软件0.2.1。用户确认尚未配置账户，本轮先做免密样本和接入准备。**已得到真实原始日线，尚未得到可供分钟策略使用的完整真实批次。** 目标仍为沪深主板、创业板、科创板的单用户提醒工作台。

## 首批实际结果

后续0.2.2补充[离线分钟诊断与零请求准备](next03-minute-quality.md)，该阶段未开通账户或新增真实分钟。0.2.3另已显式执行[免费公开分钟/元数据PoC](next03-public-poc.md)，时间/单位和完整性仍待验收；本页0.2.1实际日线请求/测试证据保留原时间。

窗口为2026-10-23至2026-10-29（北京时间日期），显式选择600000.SH、000001.SZ、300750.SZ、688981.SH、689009.SH。它们用于覆盖代码/单位边界，不是推荐股票或全市场分母；689代码作为科创板相关边界样本，不据此判定CDR的正式策略资格。

| 实际检查 | 结果 | 能证明的范围 |
|---|---|---|
| TickFlow官方免密服务 | 正式CLI发出6个请求，保存5证券当前元数据及25条历史日线 | 指定窗口与标的的接口可读取，不证明分钟、实时或全市场覆盖 |
| 腾讯公开日线参考 | 另发5个只读请求，仅使用返回的未复权day序列；100个OHLC字段全部精确一致 | 两个接口的该批日线价格对齐；底层源是否独立未知 |
| 原始成交量比较 | 主板/创业板15条数值相同，科创板10条约差100倍 | 不同接口/板块的单位不能混用；未确认绝对单位 |
| 量价合理性 | 25条都只有在“成交额为元、原始量再乘100”的假设下，均价落在当日高低价内 | 只是单位诊断；不据此自动换算或确认为股/元 |
| Tushare匿名HTTPS | TLS/HTTP有响应，JSON错误码40101（GET不是合格JSON请求） | 只证明本环境可达HTTPS入口，不证明账户、POST鉴权或数据权限 |
| 两家账户模板 | 各0个请求、0条数据，显式缺凭据/授权 | 未伪造授权样本，未完成TickFlow/Tushare双源分钟比较 |
| 软件验证 | 完整220项Python通过，新增23项样本边界测试；CLI及隔离wheel另留证 | 工程行为；不替代行情/历史/投资效果验收 |

科创板例子：688981.SH在2026-10-29的TickFlow原始volume为284298，腾讯原始值为28429754；直接乘100得到28429800，仍差46。689009.SH同日为109052与10905216，也存在尾数差异。它们符合“单位不同且有舍入”的候选解释，仍须服务商确认字段单位、精度及是否含盘后交易；不能把100倍诊断写成已验证换算。

完整响应、采集时间、原始/派生文件哈希、25条逐条比较、缺配置报告和完整日志见[本轮证据](evidence/next03-sources-20261030/README.md)。初步探测和正式CLI是两次独立采集，均只读；统计中的6个请求指正式CLI，不把初探或腾讯请求混入。

## 首批 20 个参考项目的数据来源

2026-11-11 已按当前 24 项登记完成[逐项目数据源核查](../../research/investment-agent/04-参考项目数据源核查.md)，补充关键取数代码及 README/实现差异。下面保留首批研究记录；本页历史实采和测试数量不因此新增。

项目数量不等于独立源数量。以下是上游固定版本的文档/部分接口实现线索，不是本项目已集成或对上游运行稳定性的背书；全部20项的固定提交、原文和许可见[登记](../../research/investment-agent/project-registry.json)及[逐项目取舍](../requirements/03-项目借鉴与取舍.md)。

| 参考项目 | 已核对的来源线索 | 对本项目的用途与限制 |
|---|---|---|
| tick-stock-panel、WyckoffTradingAgent | TickFlow；前者另有fuyao/TdxQuant等插件 | 优先验证批量、分钟和元数据；两个项目共用一家服务，不构成双源 |
| daily_stock_analysis、TradingAgents-CN | AKShare、Tushare、BaoStock等；前者另有Pytdx/YFinance/Longbridge | 借鉴按能力选择来源；不同市场、接口和账户权限分别核验 |
| Sequoia-X | BaoStock历史/增量日线 | 日线基准和盘后增量参考，不能替代1分钟输入 |
| a-stock-data | 腾讯、东方财富、新浪、同花顺、通达信等公开接口/文件 | 借鉴原始字段与异常清单；包装器不增加底层独立性，也不保证许可/SLA |
| PanWatch | packages/marketdata内腾讯/东方财富等vendor；日线腾讯优先 | 本轮腾讯参考端点来自其固定kline实现；使用未复权序列，自行实现只读核验，未引入其运行依赖/代码 |
| TradingAgents、OpenStock、ai-financial-agent | 分别有AlphaVantage、Finnhub、Financial Datasets线索 | 不能从它们的美股/其他市场工具推定A股分钟覆盖 |
| vn.py、Qlib | 数据适配器/外部历史集；vn.py示例有RQData/迅投历史成分，Qlib快照提示数据下载状态与社区替代 | 借鉴历史状态/成员接口与研究格式；框架不是原始数据授权 |
| Vibe-Research、UZI-Skill、jcp | 外部数据工具/公开端点；UZI档案列AKShare/yfinance/公告 | 仍需逐接口核验，不把综合研究入口当作A股分钟服务 |
| NautilusTrader、Kronos、Vibe-Trading | 交易/研究适配器、训练数据或行情配置 | 框架/模型能力不等于本项目所需的分钟、历史成分及许可 |
| awesome-quant、chinese-buy-us-stock-guide | 项目/资料索引 | 不是数据服务商 |

PanWatch固定[marketdata说明](https://github.com/TNT-Likely/PanWatch/blob/1c272a825c2713e3701d8ce81622f9c49dacbef7/packages/marketdata/README.md)还明确标记部分新增字段未经真实抓取校准。[腾讯日线端点实现](https://github.com/TNT-Likely/PanWatch/blob/1c272a825c2713e3701d8ce81622f9c49dacbef7/packages/marketdata/src/marketdata/vendors/kline.py)提供了本轮参考线索；本轮没有套用其前复权选项、失败静默回退或空值补0逻辑。

### AlphaSift 增补（2026-11-09）

AlphaSift 的 A 股快照链路包含新浪、东方财富的三条入口和 Tushare。Tushare 部分读取最近交易日的 `daily` 与 `daily_basic`。这份参考补充了日线研究与来源健康的设计线索，实际完成分钟仍须用分钟端点验证。 [数据源与固定实现档案](../../research/investment-agent/projects/ZhuLinsen__alphasift.md)

### stock-analysis-plugin 增补（2026-11-10）

固定 README 记录了 A 股报价、前复权股票 K 线和原始指数点位的不同回退链路。可参考其保留行情自身时点、接收时间和复权标签的做法。观势的分钟权限、完成性和跨源一致性需用实际样本验证。 [来源与路由档案](../../research/investment-agent/projects/Weaxs__stock-analysis-plugin.md)

## 两家候选的接口与缺口

| 数据 | TickFlow | Tushare | 本轮边界 |
|---|---|---|---|
| 历史日线 | /v1/klines，period=1d，显式adjust=none；免密可取 | daily；官方说明为未复权，vol为手、amount为千元 | TickFlow单位仍未知；Tushare文档映射尚未真实取样 |
| 历史分钟 | /v1/klines，period=1m；需要相应账户权限 | stk_mins，freq=1min；“A股历史分钟”单独权限 | 未取得真实样本、分钟完成/时间标签语义未确认 |
| 当前分钟/快照 | /v1/klines/intraday及/v1/quotes | rt_min，freq=1MIN；“A股分钟RT”单独权限 | 实时快照不自动变成完成分钟；不从最近价造K线 |
| 当前证券元数据 | /v1/instruments | stock_basic | 名称/上市日期不是ST、当日停牌或历史可交易证明 |
| 交易日历 | 本轮未建立可靠接口 | trade_cal，分别请求SSE/SZSE | 不用工作日规则替代版本化交易日历 |
| 复权因子 | /v1/klines/ex-factors | adj_factor | 当前查询的因子不能无条件回填历史可见时点 |
| 概念成分 | 本轮未建立历史成分来源 | ths_member是最新成分，in_date/out_date目前暂无 | 只准备按实际观测时点保存当前快照；尚未真实采集成员 |

官方依据：[TickFlow服务模式](https://docs.tickflow.org/zh-Hans/quickstart)、[OpenAPI](https://docs.tickflow.org/zh-Hans/api-reference/openapi.json)、[套餐限制](https://tickflow.org/pricing/)；Tushare的[HTTP方式](https://tushare.pro/document/1?doc_id=130)、[日线单位](https://tushare.pro/document/2?doc_id=27)、[历史分钟](https://tushare.pro/document/2?doc_id=370)、[实时分钟](https://tushare.pro/document/2?doc_id=374)、[证券元数据](https://tushare.pro/document/2?doc_id=25)、[交易日历](https://tushare.pro/document/2?doc_id=26)、[复权因子](https://tushare.pro/document/2?doc_id=28)、[概念成分](https://tushare.pro/document/2?doc_id=261)。权限、限额和套餐按实际账户另验，不把SDK能调用写成已获权限。

本轮下载的TickFlow OpenAPI只把volume/amount描述为成交量/额，没有确立股/手、元/千元；保留下载URL/哈希，不推测SDK已经替我们统一了单位。公开参考的科创板单位差异与[a-stock-data固定档案](../../research/investment-agent/projects/simonlin1212__a-stock-data.md)所提示的异常方向一致，仍不能替代服务商确认。

## 运行与归档

无第三方运行依赖，使用Python3.9+标准库。仓库中的3份计划为源码样例，安装wheel的用户需要另存完整计划。程序不会自动加载.env；只在进程环境配置TICKFLOW_API_KEY/TUSHARE_TOKEN，不写入JSON、命令参数或聊天。

免密研究样本可直接运行；每次使用不存在的新目录，已有目录直接报错且不请求网络：

```sh
python3 -m stockradar vendor-sample --plan configs/vendor-sample-tickflow-free.json --output-dir /tmp/stockradar-free-sample-new
```

日期是本轮固定窗口，后续研究复制计划并显式修改ID/日期；最多5证券、7自然日、60个请求，预先检查预算。间隔至少6.1秒只是保守的本地请求预算，不是服务商限额已验收。超时/大小有上限，遇429停止本轮请求，保留Retry-After，不自动重试、重定向或切换来源。

账户准备好后，分别复制下列模板，填写不含凭据的访问授权依据，确认后将authorization.confirmed改为true，再显式运行。原模板故意保留false/null，即使环境有Key也不发送请求：

```sh
python3 -m stockradar vendor-sample --plan configs/vendor-sample-tickflow-template.json --output-dir /tmp/stockradar-tickflow-account-new
python3 -m stockradar vendor-sample --plan configs/vendor-sample-tushare-template.json --output-dir /tmp/stockradar-tushare-account-new
```

返回目录包含report.json、raw/原始字节、bars.jsonl及snapshots.jsonl。价格以Decimal读取并输出字符串，原始单位另存；Tushare已文档化的日线股/元转换与分钟转换分别处理，标注“文档依据、未独立实测”。TickFlow统一单位字段保持null。请求描述不含认证头/请求体；供应商错误原文不落盘，出现敏感字段或凭据回显则拒绝保存该响应。

source_time只表示供应商时间标签；event_time/is_complete在端点完成语义核实前保持null。available_at采用本次实际接收时间，source_available_at为null，不能把现在下载的历史记录伪装成当年可见。原始响应即使HTTP200也可能为空、缺标的、截断或字段非法，报告分别保留状态和原因，不由状态sample_captured推导质量通过。

当前成员快照按查询范围保存原始响应、内容哈希、observed_at与available_at；source_effective_from/to保持null，historical_eligibility_established=false。按5只股票查询到的成员关系也不是完整概念板块分母。每轮写新目录，不覆盖旧版本；将来取得明确生效/披露证据后再设计标准成员映射。

两家都得到样本后，可做未复权日线精确比较：

```sh
python3 -m stockradar compare-vendor-samples --left /tmp/stockradar-free-sample-new --right /tmp/stockradar-tushare-account-new --output /tmp/stockradar-daily-comparison-new.json
```

比较前检查报告与原始/派生文件哈希，拒绝同供应商或TickFlow免密/完整服务充当双源；保留缺日期/缺标的/未知单位，不用容差掩盖差异。无共同日线返回no_overlap；两家响应成功也不自动证明底层源独立。此命令只比较日线；0.2.2另有minute-quality独立诊断，须先核对分钟标签起止/时区、完成性、复权与累计/区间量能，不能直接按相同字符串时间拼接。

这些文件不是[标准batch](data-contract.md)，不能直接传给worker/replay/provider-poc。后者仍负责完整标准批次、股票池分母和策略质量检查。vendor-sample不写数据库、信号、通知或策略版本，所有报告strategy_input_ready/full_market_verified/release_allowed均为false。

## 接下来仍须完成

1. 先取得两家对各接口单位、金额范围、整数舍入及盘后数据的明确答复；按当前样本保留差异，不先确定最终供应商。
2. 本地配置账户，单独核验历史分钟、实时分钟、全池批量、复权、日历和ST/停复牌权限；补充ST/停牌/退市、缺数据和修订的真实案例。
3. 对齐同一完整分钟及复权基准，实测增量/累计转换与到达时间；分钟历史和完整成员不足时暂停标准批次映射，不能降为日线冒充盘中。
4. 历史概念成分需要另寻带生效/披露时间的授权来源（如进一步评估RQData/迅投）；当前ths_member快照只能从现在积累，不回填过去。
5. 才进入全市场分母/覆盖/限流/恢复和连续影子。当前既没有全市场回测结论，也未开启live_alert。

这些步骤对应[TODO NEXT03](../../TODO.md)和[验收FR01/02](acceptance.md)。本轮按用户选择只做免密读数和准备，没有购买、开通账户或发群消息。
