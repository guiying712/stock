# NEXT03 · 免费公开接口小样本PoC

2026-10-31；软件0.2.3。用户明确要求开始验证新浪分钟、东方财富配套数据及腾讯日线。新增固定HTTPS公开接口支持，复用vendor-sample/minute-quality；未安装AKShare、efinance或其他运行依赖。**取得真实原始分钟，不等于已得到合格策略输入；应用仍使用原模式，live_alert锁定。**

## 实际采集结果

样本为600000.SH、300750.SZ、688981.SH，分别覆盖主板、创业板、科创板的代码边界，不作为推荐或全市场分母。计划窗口为北京时间2026-10-26—30。三份计划最多3/9/3个请求，间隔至少6.1秒，不自动重试、换源、分页、改用HTTP或降低TLS校验。

| 来源 | 本次实际结果 | 仍有的缺口 |
|---|---|---|
| 新浪 | 3请求/3个HTTP200响应，每只240条，共720条原始分钟 | 每只含10月29日尾部2条、10月30日238条；不是当天240个完整分钟。标签起止、闭合、量额单位及修订语义未确认 |
| 东方财富报价 | 1请求，取得3只样本当前报价 | 快照不自动成为完成分钟，证券资格仍待独立核验 |
| 东方财富当前板块关联 | 3请求，分别30/40/24条，共94条关系 | 仅这三只股票的当前关联，不是全部板块成员分母，也不是历史成分 |
| 东方财富ST列表 | 首页100条，服务端总数392，明确partial | 没有继续分页；缺席于第一页不能证明非ST |
| 东方财富停复牌 | 指定日期9条，响应声明1页 | 这是首次接收的公开记录，不证明当年最早披露时间或完整风险状态 |
| 东方财富分钟 | 主板取得5日1205条，日均241条 | 历史4日共964条开盘价为0，投影保留原值并将价格设null；创业板请求连接失败后本轮停止，科创板该项未请求 |
| 腾讯日线 | 3请求/3响应，取得15条明确未复权day记录 | 原始量额单位仍未独立确认；缺成交额不从当前快照补历史 |

正式网络阶段实际14个请求尝试、保存13个HTTP200响应（其中ST页为partial，不计入完整captured_responses）；得到1925条原始分钟、15条日线及6个元数据快照。此前沙箱内另有3次DNS失败尝试，无HTTP响应，单独保留，不混入正式请求统计。采集时间、原始字节/哈希、计划、首次接收及CLI记录见[证据索引](evidence/next03-public-20261031/README.md)。

## 已做的比较与限制

- 腾讯与此前TickFlow免密日线在3只股票、2026-10-26—29共12条重叠记录上，48个OHLC字段精确一致；成交量/额未知保持unknown，底层源独立性未确认，不能据此证明全部分钟可信。
- 每只股票10月30日现有238条新浪记录聚合出的日开高低收，与腾讯当日日线一致，共12个字段；这只是已有记录的汇总合理性检查，仍未确认完整交易日或分钟闭合。
- 新浪与东方财富主板样本有240个相同原始时间标签。958个可比较OHLC字段中753个相同、205个不同，另2个开盘价未知。这个检查只是raw_label_diagnostic：标签起止和闭合尚未核实，不能称为同一完成分钟的合格双源比较，也不以容差抹平差异。
- 新浪量价合理性主要出现量乘1候选，东方财富主要出现乘100候选；同原始标签量的比例也并非总为100。全部保留原值、单位null及诊断候选，不把合理性推断当作服务商单位确认。
- 官方日历和完成语义未知时，minute-quality的区间终点、完成性及覆盖率保持null。按完整采样窗口执行的[诊断](evidence/next03-public-20261031/minute-quality-window.json)有1925条观测、status=issues_found；初次只选择29—30日的报告另存，未覆盖或改写。

所有样本/诊断的strategy_input_ready、cross_source_verified、full_market_verified和release_allowed仍为false。股票风险状态、完整成员分母、复权因子、基准、来源最早可见时间、数据使用依据和完整标准batch尚未齐备；没有写入应用、worker、信号或通知。

## 操作方式

仓库模板中的访问确认均为false。普通查看先使用--dry-run：

```sh
python3 -m stockradar vendor-sample --dry-run --plan configs/vendor-sample-sina-public.json --output-dir /tmp/stockradar-sina-prepare-new
python3 -m stockradar vendor-sample --dry-run --plan configs/vendor-sample-eastmoney-public.json --output-dir /tmp/stockradar-eastmoney-prepare-new
python3 -m stockradar vendor-sample --dry-run --plan configs/vendor-sample-tencent-public.json --output-dir /tmp/stockradar-tencent-prepare-new
```

明确决定做一次公开只读研究采样时，复制完整计划，修改ID/日期，填入非凭据的访问依据与authorization.confirmed=true，再显式运行；目录必须不存在。该确认只表示研究访问依据已记录，不授予市场数据许可或发布资格。公开接口不读取任何行情账号凭据；账户型TickFlow/Tushare依旧要求各自权限/环境凭据。

```sh
python3 -m stockradar vendor-sample --plan /tmp/my-public-sample-plan.json --output-dir /tmp/my-public-sample-new
python3 -m stockradar minute-quality --plan configs/minute-quality-public-template.json --samples /tmp/my-sina-sample /tmp/my-eastmoney-sample --output /tmp/my-public-minute-quality-new.json
```

新浪固定取最近240条，东方财富固定取近5日，查询参数不提供任意历史窗口回放。start_date/end_date只是显式研究窗口，实际返回范围必须核对；不能把“最近240条”视为一天，或把“近5日”解释成长期分钟历史。当前模板日期固定于本轮窗口，后续须显式更新，不自动猜交易日。

新浪JSONP只解析已知外壳中的JSON字面量，不执行脚本；保留原始字节。东方财富的0价格标记为未知，同时保留raw_price_values及原始响应；合法0成交量/额保持原样。腾讯仅读取day，不回退qfqday/hfqday、不用最新报价重写历史close。分页总数/页数若显示还有数据，保留partial并停止，不假装拿到全量。

## 来源与工程验证

接口依据为AKShare官方文档及固定提交[f8dc2d6c…](https://github.com/akfamily/akshare/tree/f8dc2d6c6c3456f5cab037523459f9b5bd0ecbc7)：[新浪分钟](https://github.com/akfamily/akshare/blob/f8dc2d6c6c3456f5cab037523459f9b5bd0ecbc7/akshare/stock/quote/stock_zh_a_sina.py)、[ST列表](https://github.com/akfamily/akshare/blob/f8dc2d6c6c3456f5cab037523459f9b5bd0ecbc7/akshare/stock/quote/stock_zh_a_special.py)、[停复牌](https://github.com/akfamily/akshare/blob/f8dc2d6c6c3456f5cab037523459f9b5bd0ecbc7/akshare/stock/issue/stock_tfp_em.py)。当前板块/报价/分钟的请求形状也核对了[efinance实现](https://github.com/Micro-sheep/efinance/blob/main/efinance/stock/getter.py)和[通用行情实现](https://github.com/Micro-sheep/efinance/blob/main/efinance/common/getter.py)。腾讯使用此前已留证的公开未复权端点。源码、字段和可读响应不等于数据授权或SLA，不引入上游自动换源、静默补值、最新价改历史值或关闭TLS的行为。

新增20项公开接口测试；完整270项Python于2026-10-31 17:41:49—17:42:40 UTC通过，50.987秒。常规测试为fake/mock，真实采集另行显式执行，没有真实群消息。采集后补齐畸形数值异常捕获，因此保留采集代码哈希与最终代码哈希两份记录；用最终解析器逐条重建全部1940条已采集分钟/日线，结果与原投影一致，未改旧报告。CLI、包核对和收尾审计见[本轮证据](evidence/next03-public-20261031/README.md)及[验证记录](verification.md)。

## 接下来

1. 优先确认新浪与东方财富的分钟起止、收盘集合竞价、修订和量额单位，解释现有205个字段差异；保持原值，不用简单移位或乘100消除差异。
2. 对东方财富连接失败、未请求证券及ST剩余分页另建有预算的新计划，核验稳定性和完整性；本次缺口不伪装成已通过。
3. 为股票状态/成分保存首次观测与明确生效依据，再核验复权、日历和基准；当前成分不回填历史。
4. 只有必需数据齐备后才进入标准batch映射、shadow及真实研究。真实提醒、正式参数冻结、全市场与连续影子门槛继续保持。
