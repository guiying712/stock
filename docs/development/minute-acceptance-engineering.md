# 分钟验收工程（0.2.7）

2026-11-12。对应 NEXT03、FR01/02/13，实现[验收方案](source-selection-and-acceptance.md)的第一批离线工具：交易阶段与证券状态分母、同区间比较、四阶段零请求计划。没有发起真实行情请求、读取真实密钥、修改用户数据库或接入策略。

## 零请求准备

```sh
python3 -m stockradar minute-acceptance-plan --plan configs/minute-acceptance-template.json --output-dir /tmp/stockradar-acceptance-new
```

目录必须不存在。输出 `latest.json`、`session.json`、`history.json`、`daily.json` 和 `report.json`；目录0700、文件0600。三只股票分别对应1、3、3、3个请求，合计10次。总预算不足、字段缺失/未知、非交易日或日期安排冲突会在写文件前失败。

本命令不访问凭据、供应商、业务数据库，也不等待或执行日程。所有输出采样计划的 `authorization` 固定为未确认；`account_permissions=not_tested`，策略/发布就绪为false。交易日与采集时点未知时仍可输出准备缺口，不能把输出文件存在看作已完成实采。

复制模板后填写：

| 字段 | 含义 |
|---|---|
| `symbols` | 1—3只显式证券，保留前导零与板块；模板为三个板块各一只 |
| `trade_date` | 四阶段共同核对的数据交易日D，模板日期仅为示例 |
| `calendar` | 日历版本、依据和 `is_trading_day`；未知保留null，确认必须有依据 |
| `capture_times.latest/session` | 带UTC时区的采集时间，换算北京时间必须同属D；session晚于latest |
| `capture_times.history/daily` | 本方案安排在D之后的日期回查，数据参数仍为D |
| `max_requests` | 四阶段合计预算，三股至少10次；不会自动放宽单阶段限额 |

只校验日期和顺序，不自动确认交易所时段、供应商发布时间、账户权限或当前时刻；报告明确 `schedule_enforced=false`。最新和当日接口不接收历史回放日期，实际执行前仍需按阶段核对当时日期、访问依据及可用性，另行明确确认。模板未生成自动采集器，不自动重试、补采或换源。原7请求Tushare模板保持原样。

## schema2离线分钟诊断

```sh
python3 -m stockradar minute-quality --plan configs/minute-quality-phases-template.json --output /tmp/stockradar-phase-pending-new.json
```

准备好口径后，可在复制的计划中提供依据，并以 `--samples` 传入已保存的vendor-sample目录。仍最多8份目录、5只股票、7个自然日、100000条观测；不会发网或创建标准策略批次。读取原始哈希并重解析，原始报告及样本不修改。

schema1计划、历史诊断、旧模板继续保留原有行为。schema2额外要求如下；不从系统当前日期、工作日、最新状态或返回行情推断这些信息。

| 层级 | 新增声明 |
|---|---|
| `calendar.phases` | 1—8个按序且不重叠的同日阶段，各有 `id/kind/start/end`；类型为连续竞价、开盘竞价、收盘竞价或盘后 |
| `profiles[].phase_rules` | 每个接口必须完整列出所有阶段；`minutes` 为逐分钟，`aggregate` 为整阶段记录，`excluded` 为有据排除，`unknown` 保持未知 |
| `profiles[].no_trade_policy` | `emit/omit/unknown`及依据；分别表示已确认无成交区间仍返回零量记录、可以省略记录、规则未知 |
| `security_days` | 必须覆盖全部证券×日期，状态为 `trading/suspended/not_listed/unknown`，附依据及日内区间清单 |

模板阶段只是待核对的示例，日历、证券状态、接口口径及单位均未确认。不同市场、日期若需要不同阶段，应分开明确计划，当前不会自动选择交易所规则。

**证券日 `evidence` 应支持该日状态及完整异常区间清单。** `intervals=[]` 且状态已确认为trading，表示有依据确认没有需要排除的日内停牌/无成交区间，不能仅因接口没返回异常就这样填写。每个区间还须有 `start/end/kind/evidence`，kind仅为halt或no_trade。缺必要依据应把状态保持unknown。

时间区间按 `[start,end)` 描述实际覆盖。`minutes`使用接口已有 `timestamp_label=start/end`；`aggregate`必须另填 `label_at`，允许明确映射“09:30标签代表09:15—09:25竞价”。输出的 `interval_start/end` 记录真实声明区间，不按标签硬加一分钟。不同阶段若映射到同一原始标签直接拒绝，不猜归属。

停牌区间完全覆盖的记录从有效分母中排除；若只覆盖聚合记录的一部分，报告 `PARTIAL_BAR_EXCEPTION`，分母保持未知。整日停牌/未上市为零分母，覆盖率为null，不制造100%。无成交规则为omit时，仅排除有证据的无成交区间；emit时仍要求记录，若增量量额为正则报告矛盾。累计量额无法据单行证明区间零成交时，明确待核验。不会补价或补零。

## 输出与工作台兼容

schema2按接口、证券和日期输出：

- `expected_records`、`observed_unique_records`、`usable_unique_records`、观测覆盖率和可用覆盖率。
- 各阶段记录数、缺失区间终点、按原因排除的记录数、状态和未知原因。缺行情证券仍保留在报告中。
- 每条观测的真实声明区间、阶段及长度。重复观察不增加覆盖，冲突版本全部保留。
- 比较键包含证券、区间起止和阶段类型；同结束时间、不同长度或不同阶段的记录不比较。`common_records`与真正一分钟的`common_minutes`分别统计。

覆盖率表示已声明阶段与有据排除规则下的**记录覆盖**，不是完整策略输入覆盖。包含整阶段汇总或日内排除时，旧版 `expected_minutes/usable_unique_minutes` 不填数值。来源健康API接受schema2并提供独立记录计数；现有界面的分钟覆盖保持未知，避免把一条竞价汇总显示成一分钟完整。纯一分钟且无日内排除时仍兼容原分钟显示。本轮未改前端界面。

口径、状态、日历未知会阻止覆盖率和相应比较；完成性仍需供应商依据及接收时点共同约束。文档依据的非空校验不是自动验证文档真实性，首次接收时间仍不等于历史最早可见时间。即使本地 `checks_passed`，双源、策略、全市场及发布就绪仍为false。

## 验证与剩余工作

测试使用模拟供应商响应、合成状态依据和临时目录；账户/行情权限未测试。覆盖旧schema回归、集合竞价区间、标签碰撞、停牌、零成交、未知分母、重复/修订、精确比较、三类Tushare解析、四阶段预算及零凭据/零网络/不覆盖文件。完整执行记录见[本轮证据](evidence/minute-acceptance-20261112/README.md)。

下一批仍需：跨日分层样本矩阵及预算汇总、分钟与日线量额对账报告、按固定时刻重复观察的有界采集、全市场容量测量、历史时点资料与标准批次桥接。工程通过不代表已有供应商分钟合格，也不改变原真实影子、研究及发布条件。
