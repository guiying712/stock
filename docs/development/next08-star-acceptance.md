# NEXT08：科创板扩展与本地验收

科创板已纳入离线股票池、策略参数、研究执行规则及页面范围。软件仍为0.1.0基础上的未发布源码；真实行情/历史、交易资格与成本、全市场性能和连续影子验收继续归NEXT03/04/06/07，`live_alert`保持锁定。

## 启动与版本选择

新数据库默认使用`fixture-v2-star`，股票范围为MAIN/CHINEXT/STAR。已有数据库默认继续最后扫描的版本，不因安装新代码或保存新配置而自动切换。启用新的科创板演示时，重启服务并明确指定配置与新数据库：

```sh
python3 -m stockradar serve --config configs/fixture.json --db data/star-demo.sqlite3
```

不覆盖旧数据库；旧版继续用其已保存配置或历史样例：

```sh
python3 -m stockradar serve --config configs/fixture-v1.json --db data/legacy-demo.sqlite3
python3 -m stockradar export-fixture --fixture-version 1 --output data/legacy-fixture-new.jsonl
python3 -m stockradar export-fixture --output data/star-fixture-new.jsonl
```

`export-fixture`默认版本2；参数版本与数据版本在入口处显式选择。页面“fixture”回放任务按所选保存配置的schema选择对应样例，旧版本回放不会悄悄换成新数据。数据库无扫描且有多个已保存版本时必须用`--config`或worker的`--saved-version`明确选择。

## 配置与历史兼容

| 项目 | 历史v1 | 新v2 |
|---|---|---|
| 格式 | 原配置无schema_version字段 | schema_version必须为整数2 |
| 默认策略ID | fixture-v1 | fixture-v2-star |
| 特征版本 | features-v1 | features-v2-star |
| 股票范围 | MAIN/CHINEXT | MAIN/CHINEXT/STAR，须显式选择 |
| stock参数 | 原MAIN/CHINEXT完整键 | 三组完整键，STAR无默认回退 |
| 包内模板 | fixture-v1.json | fixture.json |

原模板完整保存在`configs/fixture-v1.json`和包内`stockradar/fixture-v1.json`，原配置哈希未变。两份当前fixture配置仍同步。没有把STAR参数补入旧对象或原地修改同ID配置；缺参数、未知键、未知schema、重复/范围外板块及超过10%的风险上限直接报错。

STAR单独声明历史窗口、区间宽度、突破/失效缓冲、距离、量能、相对强度、流动性及上市天数。当前值仅用于合成验收，不代表正式策略。合法组合为SSE/MAIN、SZSE/MAIN、SZSE/CHINEXT、SSE/STAR；BSE/BSE可在输入中保留过滤证据，但不纳入股票池。SSE/CHINEXT、SZSE/STAR等错误组合在传输层及直接evaluate均报错。

## 样例与策略行为

v2保留11个场景切片，新增三只合格科创板、科创板ST/停牌和北交所范围外对象；原科创板历史不足对象明确标记。共21个记录，其中15个合格、6个排除，四个板块；半导体/算力的可比成员由4只增为7只，包含三只STAR。

| 场景 | v2结果 |
|---|---|
| 初始观察 | 15/15覆盖，没有新突破 |
| 10:01预警 | 7条预警，其中3条科创板 |
| 持续共振 | 同episode确认，H/ATR/S及首次分组冻结 |
| 价格偏离/回归 | 更新参与状态，恢复原机会 |
| 10:05缺科创行情 | 分母仍为15，有效14，覆盖14/15；暂停，不判策略失效 |
| 10:06恢复 | 覆盖15/15，沿用原信号ID |
| 结构跌破/后续重置 | 原机会失效，后续新episode独立记录 |

没有因属于STAR而放宽10%结构风险门槛。STAR的量能/相对强度、可比成员、可见时间和冻结状态均沿用同一evaluate；不同板块不会静默借用参数。ST、停牌、退市、上市天数、日线历史和流动性仍有独立过滤原因。缺科创行情不能从覆盖分母移除。

历史v1样例、配置及全部11次策略输出按扩展前保存的golden哈希比较，完全一致：

- 配置：`dab9aba77b7032ef4eb48ddac7d239016586b8039e5df9fc4a38ceac1a44c5ce`。
- 输入：`ecc4d537b2496d94d0a7b52356a3cdc2e7777ff32b2e0b1c2107310bc16ab9da`。
- 全部evaluate输出：`0d09097ced67144c199bcd0c8e5dc74f986720e15d577923ee39b21631133151`。

哈希基准见[测试fixture](../../tests/fixtures/fixture-v1-hashes.json)。这是策略/输入兼容证明，新运行的源码哈希和记录时间仍按实际代码生成。

## 科创板执行规则v2

本轮核对[上交所2026交易规则发布通知](https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml)及[上交所科创板投教问答](https://edu.sse.com.cn/tib/qa/)。科创板最低申报200股，其上可逐股递增；限价与市价申报上限分别为10万/5万股，不能将最低数量解释成200股整数倍。实际历史仍须核验相应有效版本与执行证据。

为明确表达上述差异，新增逐规则schema2，保留原v1规则格式：

| 新字段 | 含义 |
|---|---|
| schema_version | 整数2，未知版本拒绝 |
| order_type | limit或market，区分数量上限 |
| buy_min_shares / buy_step_shares | 最低买入数量、其上递增单位，STAR为200/1 |
| sell_min_shares / sell_step_shares | 最低正常卖出数量、递增单位，STAR为200/1 |
| sell_odd_lot_full_exit | 不足最低数量时允许全部退出；不据此虚构部分成交 |

schema2移除含义不明确的buy_lot，其余规则身份、适用日期、available_at、来源、verified、最大数量、tick、卖出交易日间隔、估值时段、费用及滑点字段继续完整必填。旧v1仅适用于原主板/创业板组合；STAR缺schema2不得自动借用旧规则。STAR校验200/1、零股全额退出、对应申报上限与0.01价格单位。

仿真先扣除买入费用检查预算，再按最低数量/递增步长取数量。测试覆盖含费预算不足200股、恰好200与201股、10万/5万上限、T+1及显式合股后100股的全额退出。价格上下限、无限制或unknown仍来自可见execution证据，不将所有STAR报价机械套成统一涨跌停；缺价格限制/可成交量、规则/成本核验仍pending/null。

新的`export-study-fixture`生成15证券的显式合成研究数据，包含独立`synthetic-sse-star-v2`规则，四组配置使用新的synthetic-study-v2-star前缀。旧三组规则载荷及其ID保持原义。合成规则的verified=false，费用、短交易日历与成交容量是假设，查阅部分官方规则不等于真实执行路径验收。

## 页面与运行

health新增当前配置的boards数组，侧栏根据实际运行范围以textContent显示中文；保存新配置不会让旧运行版本显示“科创板已启用”。修复窄侧栏将“科创板”拆成两行的问题，沿用现有样式与组件。科创板详情继续同时展示触发/最新价格和时间、冻结H/ATR/S、分数非概率与反馈不下单。

本轮内置浏览器核对新旧版本桌面及390×844详情，页面宽度等于视口，无水平溢出。旧版显示主板/创业板、12/12及4个机会，新版显示三板块、15/15及7个机会。截图见[新版范围](evidence/next08/desktop-star.jpg)、[旧版范围](evidence/next08/desktop-legacy.jpg)、[390px详情](evidence/next08/mobile-star-detail.jpg)。真机与完整无障碍未重验，临时标签和服务已关闭。

当前运行计划为`synthetic-operations-v2-star`，目标15证券；原12证券计划保存在`configs/operations-fixture-v1.json`。12证券负载单元改为包含10只原样例和2只STAR，两路完整样例回放各15证券。规模与口径均显式记录，不把合成覆盖当作全市场证明。

## 本次实际验证

- 完整150项测试通过（新增科创板范围/兼容10项、执行4项）；原NEXT01时间边界及其他回归保留。
- Node检查app.js语法、CLI帮助通过。
- 30个合成交易日/210切片研究包含STAR仿真闭合样本，四组、延迟、持有窗及退出均记录；各时间分段约10日，10/20日标签会因隔离或缺窗口purged/pending，不能据此声称成熟20日样本外通过。
- 本轮负载只重测12/120合成证券，各2次扫描；两路15证券回放输入及完整结果相同。此前NEXT06/07的90日/1200证券结果属于科创板扩展前记录，本轮未重复这些规模。
- CLI新旧样例导出、守护/运行报告、只读归档、完整备份恢复及旧worker无参数重启通过。新库11次扫描、14个episode（6个STAR）、70个事件；恢复SQL dump一致，旧库重复输入后仍仅fixture-v1及11次扫描。
- 当前源码重建wheel，包内同时含新旧配置模板；Python3.9仓库外隔离导入并扫描新旧样例分别取得15/12分母。没有发布包或修改实际data数据库、令牌和来源快照。

详细时间、失败事实、哈希及证据见[验证记录](verification.md)的NEXT08追加条目和[证据索引](evidence/next08/index.json)。本轮完成NEXT08工程及合成验收，真实提醒发布条件保持原样。
