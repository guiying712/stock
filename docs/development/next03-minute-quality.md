# NEXT03 · 分钟样本诊断与采样准备

0.2.7已实现[新版阶段/状态诊断及四阶段准备](minute-acceptance-engineering.md)。以下schema1说明、旧模板和历史测试记录保留原义；schema2使用独立模板并要求显式依据。

后续方案（2026-11-12）：[来源取舍与分钟验收](source-selection-and-acceptance.md)补充按交易阶段/证券状态确定分母、单位与权限验证及分阶段预算。下文旧模板13:00—15:00是当时的简化网格，不能据此认定全程连续竞价或240条即完整；旧样本与诊断不改写。

软件0.2.2；2026-10-30 UTC。用户确认尚未开通账户，本阶段完成零请求预演、分钟诊断及采样计划。**没有新采集真实分钟，没有确认账户权限或TickFlow量能单位，也未接入策略。** 既有真实日线证据继续保留原日期和哈希。

## 先运行零请求准备

新增两份窄范围计划，显式覆盖主板、创业板、科创板各一只证券，固定示例日期为2026-10-29：

| 计划 | 数据集 | 计划请求数 |
|---|---|---|
| configs/vendor-minute-tickflow-template.json | 日线、历史分钟、最新交易日日内分钟 | 9 |
| configs/vendor-minute-tushare-template.json | 日线、历史分钟、实时分钟 | 7 |

计划中的authorization.confirmed均为false。以下命令只保存准备报告，不构造HTTP连接、不验证账户权限、不创建数据库；输出目录必须不存在：

```sh
python3 -m stockradar vendor-sample --dry-run --plan configs/vendor-minute-tickflow-template.json --output-dir /tmp/stockradar-tickflow-minute-prep-new
python3 -m stockradar vendor-sample --dry-run --plan configs/vendor-minute-tushare-template.json --output-dir /tmp/stockradar-tushare-minute-prep-new
```

无凭据及授权依据时，status为blocked_configuration、sent_requests为0，并列出缺口；即使配置齐全，也只返回prepared_not_permission_verified。credential_present只表示进程变量存在，不表示权限通过。准备报告kind=vendor_sample_preparation，不是可供诊断的原始采样报告。

本阶段没有开通、购买或试探账户接口。凭据只留在进程环境，不粘贴进计划、命令参数、文档或聊天；程序不自动读取.env。原三份日线/账户样本计划保持原样。

## 离线分钟质量报告

无样本时即可检查计划缺口：

```sh
python3 -m stockradar minute-quality --plan configs/minute-quality-template.json --output /tmp/stockradar-minute-quality-pending-new.json
```

已有实际vendor-sample采样目录后，可读取最多8份目录，同一报告不得重复计入：

```sh
python3 -m stockradar minute-quality --plan /tmp/my-minute-quality-plan.json --samples /tmp/my-tickflow-minute-sample /tmp/my-tushare-minute-sample --output /tmp/my-minute-quality-result-new.json
```

命令只读原始报告与文件，不发网、不写业务数据库，不生成标准batch，也不改变原始样本。只传日线目录时报告no_minute_samples，不能把日线价格对齐视为分钟验收。文件哈希、计划哈希、必需文件清单、请求描述或原始响应引用不一致，以及符号链接，均拒绝诊断；不覆盖既有报告。

计划默认保留四个接口口径（TickFlow历史/日内、Tushare历史/实时）。如果只验证一家或一个接口，应在复制的计划中显式保留目标profiles；缺少的预期序列会报告缺失，不静默缩小分母。未知键、缺必需字段或缺相应依据直接报错。

## 明确口径后才对齐

configs/minute-quality-template.json中的口径和依据均为unknown/null。填写值表示用户已记录审阅依据，不等于软件自动向服务商求证：

| 字段 | 允许值及约束 |
|---|---|
| timestamp_label | unknown/start/end；确认标签是分钟起点还是终点 |
| timestamp_timezone | unknown；TickFlow毫秒时间戳使用UTC，Tushare无时区标签使用Asia/Shanghai；需时间依据 |
| completion | unknown/provider_closed；需供应商闭合语义依据，并检查实际接收时刻不早于区间结束；单纯时间经过不作为闭合证明 |
| volume_unit | unknown/shares/lots_100；仅按明确依据换算，原值始终保留 |
| amount_unit | unknown/CNY/thousand_CNY；与成交量单位分别声明 |
| turnover_mode | unknown/interval/cumulative；增量和累计量能不混同比较 |
| adjustment | unknown/none；本阶段只支持明确未复权比较 |
| max_observation_delay_seconds | null或0—86400整数；历史下载通常保留null，设置时检查首次观测延迟预算 |
| evidence | timestamp/completion/units/turnover/adjustment五项引用；任何已确认口径必须提供相应非空依据 |

未知时区或起止含义时，interval_end、完成性和覆盖率保持null，不按相同字符串强行拼接。明确的起点标签加一分钟，终点标签保持原时刻，均用UTC区间终点对齐。观察到的源标签晚于接收时刻、秒数非整分钟或分钟尚未闭合，均单独标记。

calendar必须显式给出候选dates和连续竞价sessions。version和evidence同时为空时，预期分钟数、缺口列表及覆盖率均为null；提供版本和依据后才计算分母。候选日期不由工作日规则推断。示例时段为09:30—11:30、13:00—15:00，区间终点分别落在(09:30,11:30]、(13:00,15:00]，午休不算缺分钟。竞价、盘后或其他口径会标记OUTSIDE_CONTINUOUS_SESSION，应另行核验，不能补造K线消除差异。

## 报告检查什么

- observations保留样本报告哈希、原始文件/哈希、零起始行号、原始价格和量额、派生区间终点及原因。诊断重新读取原始响应，也保留采集器因重复/修订而拒绝投影的行。畸形响应/行、空结果、缺响应和疑似截断进入capture_issues。
- 同一响应的重复分钟与跨采样修订冲突分别记录；冲突保留所有版本，不自行选择最新值。不同采样中数值相同的重复观察只记为identical_reobservations，不增加覆盖分子。
- coverage按接口、证券和北京时间日期报告，区分观察到的唯一分钟、可用分钟及缺口。可用分钟还须满足完成性、价格、量能、时间及修订检查；不补价、不补0、不删除缺行情证券。
- 已知增量量能检查零量/零额冲突和量价区间；累计量能检查同日回退，包括午休后的异常重置。TickFlow的100倍合理性候选只展示诊断，不成为单位转换。
- comparisons按同一区间终点比较明确未复权且已闭合的价格；使用Decimal精确比较，不设容差掩盖差异。未知单位或不同增量/累计口径下，量额比较保留unknown。同行情商不同接口标为same_provider_endpoints；跨商也不自动证明底层源独立。
- observed_delay_seconds只是“区间结束至首次接收”的观测延迟，历史下载也会很大；不冒充当年可见时间、实时到达性能或钉钉平台时延。source_available_at保持null。

status=no_minute_samples表示没有分钟观测；issues_found表示有缺口/未知/异常；checks_passed仅表示所给样本在显式口径和日历下通过本地检查。即使checks_passed，cross_source_verified、strategy_input_ready、full_market_verified及release_allowed仍为false；证券风险状态、历史成员、复权因子、基准、原始可见性、数据许可及完整标准batch仍须独立验收。

## 账户来源开通后的采样顺序

1. 先向供应商确认量能单位、标签起止/时区、闭合/修订语义和盘后数据范围，记录可追溯依据；TickFlow现有100倍疑点保持未解决。
2. 分别核验历史分钟、实时分钟的账户权限。只有准备好权限与访问依据后，才复制采样计划并填写authorization，再去掉--dry-run进行显式采集。
3. 修改计划ID和日期为实际采样窗口，同时更新诊断日历。intraday/minute_quotes只取最新数据，不会按历史日期回放；应选择与历史分钟重叠的实际交易日，否则报告日期不匹配或缺口。
4. 用原始样本验证口径后更新复制的诊断profiles，保留依据与新报告。应保留缺数据、停牌、修订和断源案例。
5. 分钟、历史成员等完整输入齐备后再设计标准batch映射与shadow接入；本阶段不解除live_alert锁定。

2026-10-30 UTC重新查阅[TickFlow服务说明](https://docs.tickflow.org/zh-Hans/quickstart)、[Tushare历史分钟](https://tushare.pro/document/2?doc_id=370)及[实时分钟](https://tushare.pro/document/2?doc_id=374)：TickFlow免密服务不提供分钟；Tushare两类分钟分别需要权限，文档列量为股、额为元，实时分钟说明为闭合周期。文档不证明本地账户权限或已取得真实分钟，不能代替当前样本核验。TickFlow分钟页面/OpenAPI本次浏览工具未能读取，量能单位与标签终点未确认。

代码与测试证据见[本阶段验证索引](evidence/next03-minute-prep-20261030/README.md)，历史真实日线见[来源与样本](next03-data-sources.md)。对应[FR01/02验收](acceptance.md)及[TODO NEXT03](../../TODO.md)。

## 0.2.3公开来源补充

最新[公开接口PoC](next03-public-poc.md)已取得新浪/东方财富原始分钟，并支持对应intraday profile从JSONP/JSON原始响应重解析。使用configs/minute-quality-public-template.json；所有口径/单位/完成性/日历依据默认unknown或null。免费来源不用账户凭据，实际只读采样须显式记录访问依据和预算；仓库计划默认未确认，--dry-run为0请求。当前1925条观测仍为issues_found，不产生策略就绪或发布资格。本页上方0.2.2“没有真实分钟”只指原阶段，原报告和测试时间不改写。
