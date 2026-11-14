# NEXT06/07：本地工程与合成验收

本页保存科创板扩展前的当次验收口径与证据。后续NEXT08已增加科创板、新旧配置格式和执行规则schema2，见[NEXT08记录](next08-star-acceptance.md)；之后[NEXT04记录](next04-dispatch-lifecycle.md)完成本地模拟调度及完整173项测试。不要将本页原有90日/1200证券结果当作后续重测。

本轮用户确认“仍无，先完成本地工程和合成验收”。按此范围交付研究模型、运行守护、证据报告、负载与归档恢复；真实历史/样本外、正式参数冻结、全市场容量/平台时延及连续真实影子观察仍待外部数据。`live_alert`应用入口继续锁定。

当次软件为0.1.0基础上的未发布源码，wheel按源码哈希区分，没有上传包索引；当次只支持原主板/创业板执行组合。后续NEXT08已扩展，以下命令与数据规模保留当次口径，当前默认生成器/计划见NEXT08记录。

## 本次验收证据

2026-10-29 UTC，macOS、系统Python3.9.6；临时数据库与合成数据，通知均为fake/Mock，没有真实行情请求或群发送。

- 完整136项测试通过，新增执行/研究20项、运行17项、负载2项；既有97项全部保留。
- 90个合成交易日、每日7个完成分钟，覆盖四组配置、0/1/3/5分钟反应、5/10/20交易日及固定/风险退出。短时段、日期、价格、成交量与费用均为构造假设。
- 12/120/480/1200合成证券各两轮、每轮两个扫描；最大档扫描提交P95为9.63秒，进程峰值RSS约1.27GB。每档只有4个计时样本，P95在此样本量下等于最大值。两路并发回放各12证券、11切片，输入和完整结果一致。
- `supervise`处理11个切片，运行报告明确给出真实全市场/影子日数/平台P95待验收；只读压缩归档后输入及原结果哈希一致，SQLite备份恢复的完整SQL dump一致。
- 当前源码wheel包含21份Python模块、3份静态资源与默认配置；在仓库外用Python3.9隔离导入并扫描通过，两份fixture配置一致。

持久保存的精简结果见[证据索引](evidence/next06-07/index.json)、[研究摘要](evidence/next06-07/study-summary.json)、[负载报告](evidence/next06-07/benchmark.json)、[运行报告](evidence/next06-07/operations.json)、[CLI/恢复核对](evidence/next06-07/cli-recovery.json)和[wheel核对](evidence/next06-07/wheel.json)。原始大文件的位置、文件哈希与复现命令记录在索引，临时目录不保证长期保存。实际执行和开发中失败记录见[验证记录](verification.md)。

## 研究命令与显式计划

从源码根目录执行，输出使用全新路径：

```sh
study_root="$(mktemp -d /tmp/guanshi-study-XXXXXX)"
python3 -m stockradar export-study-fixture --output-dir "$study_root/input" --days 90
python3 -m stockradar study --input "$study_root/input/synthetic.jsonl" --plan "$study_root/input/study-plan.json" --output "$study_root/report.json"
```

90日样例报告较大，研究需数分钟。`study`不创建业务数据库，也不写实时信号/持仓/通知。页面与`replay`命令仍是已有功能观测，不包含本模型，界面研究任务未新增接线。

计划schema为1，全部字段必填，未知键、重复JSON键、NaN/Infinity、无效日期、重叠规则/分段、错误容器或枚举均拒绝。完整字段：

| 类别 | 字段 |
|---|---|
| 身份 | `schema_version,id,purpose,benchmark_id` |
| 执行 | `capital_per_signal,delivery_delay_seconds,reaction_delays_minutes,holding_windows_days,exit_modes,price_model,dividend_accounting,max_loss_fraction,rules` |
| 研究 | `profiles,splits,bootstrap_samples,min_clusters,seed` |

`purpose=fixture`只接受全部显式模拟输入，`experimental`只接受全部非模拟输入；两类不能混用。生成器提供完整样例计划，不能把其费用、短日历或阈值直接用于真实策略。研究报告保存完整计划及计划、配置、输入、代码、样本和输出哈希；报告以新文件独占创建，禁止覆盖旧实验。

四组均调用同一个`evaluate`，保持原到达顺序、可见性、市场/数据/风险硬过滤，冻结首次提醒快照：

| 组 | 板块资格门槛 | 板块评分 | 提醒阶段 |
|---|---|---|---|
| stock_only | 关闭 | 关闭，权重转给个股 | early |
| sector_filter | 保留 | 关闭，权重转给个股 | early |
| early | 保留 | 保留 | early |
| confirmed | 保留 | 保留 | confirmed |

配置须显式给出全部参数。校验约束四组除上述分支与ID外参数一致，避免将其他阈值变化混作板块价值。stock_only仍保留市场环境等共同条件，不能解释为无任何过滤的裸突破策略。

## 仿真成交与未知值

每条信号使用独立预算，不建组合净值。每种延迟/窗口/退出分别计算，不能累加为可同时投入的实盘资金或实际交易。

1. 反应时点为首次提醒时间＋显式投递延迟＋用户反应分钟。入场采用严格晚于该时点、早于TTL的下一可执行完成分钟收盘；报价须满足`event_time ≤ available_at ≤ ingested_at ≤ cutoff`。同时检查当时最新SignalEvent的参与状态，暂停期间不买入，失效/过期机会不因价格回到区间而复活。不能使用触发价或停牌前旧价填单。
2. 价格使用Decimal，滑点向不利方向按tick取整；买入股数按显式单位向下取整，并计入买入费用后检查预算。佣金最低额、双边过户费、卖出税费分别按分计价；全额成交假设依赖显式可成交量，不做隐含排队或部分成交。
3. 执行资格、停牌/退市、涨跌停上下限、可成交量、规则版本和最早可见时间须显式提供。unknown或缺证据为pending；已知停牌、涨跌停阻挡、预算不足且入场窗口完整时为not_filled。涨跌停不硬编码为统一百分比。
4. 卖出按版本化交易日历满足T+1或更长间隔。固定模式只使用目标交易日精确收盘，缺收盘不拿次日价格替代。风险模式在完成分钟观察到冻结结构位或相对含费买入成本的风险边界后，于下一可卖分钟退出；跳空可能损失超过10%，不伪造止损价成交。
5. 复权因子变化不能自行推导股份与现金。研究仅支持当时已知的显式拆股/净现金分红，将股份、冻结失效位和净应收同步转换；实际分红到账与个人税务账本不模拟。迟到、缺字段、非整数股份或未支持公司行为为pending。在线策略遇复权变化仍暂停。
6. 真实研究的`rules[].verified`必须为true且成本完整，才计算该规则下的结果；未核验时为pending、净收益null。fixture允许显式假设费用得到模型数值，报告始终标记simulated，正式参数冻结资格始终为false。

报价的可选`execution`和批次的可选`corporate_actions`契约见[数据契约](data-contract.md)。不含新字段的旧fixture/录制仍可做功能回放，但不能凭空取得仿真成交证据。

规则结构包含`id,exchange,board,valid_from,valid_to,available_at,source_urls,verified,buy_lot,max_order_shares,tick_size,sell_delay_sessions,valuation_sessions,fees,slippage_buy_fraction,slippage_sell_fraction`。日期有效区间起含终不含，同交易所/板块不允许重叠；当前只接受SSE/MAIN、SZSE/MAIN、SZSE/CHINEXT。规则须按真实适用时期独立核验，合成规则不冒用官方版本。

本轮查阅[上交所2026修订发布通知](https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml)及其附件、[深交所2026交易规则](https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf)，用来确认交收/回转、申报单位、价格单位及生效时点必须分项建模。仅有规则资料不能证明服务商执行资格、券商费率或历史成交能力；合成规则的`verified=false`保持不变。

## 时间隔离、指标与分母

`train/validation/test`为有序、不重叠的UTC起含终不含区间。提醒归属按首次提醒时点；入场窗口或计划目标收盘跨分段时整条样本purged，即使风险模型可能提前退出也不能绕过边界。测试段仅报告，不自动挑选/上线参数。

| 字段/指标 | 口径 |
|---|---|
| closed | 具有仿真买卖及完整成本，可报告成本后/毛收益与人民币损益 |
| pending | 缺数据、缺执行/成本/规则/公司行为证据或窗口未成熟；未知值null |
| not_filled | 已知入场约束阻挡，或反应后已过期；单列原因 |
| purged | 跨时间分段标签，不进入可参与分母 |
| 可参与率 | 有entry样本数 ÷（有entry样本＋明确not_filled）；无entry的pending单列，不当作失败 |
| 未成交率 | not_filled ÷ 非purged总数；同时报告所有状态数及可参与分母，避免掩盖pending |
| 收益失败 | 成本后损益<0，分母仅closed |
| 结构失败 | 观察到冻结结构失效即true；完整分钟窗无失效才false，缺窗且未观察到失效为null |
| 超额收益 | 对齐入场/退出的精确基准报价及复权因子；缺任一基准时为null |
| MFE/MAE | 实际仿真持有期间最高/最低价值的毛变动，含显式公司行为；分钟窗不完整则null |

净收益、超额、MFE/MAE与结构/收益失败各自保留有效分母。报告按分段、反应、持有窗及退出分组。相同首次交易日＋热点的closed样本先求簇均值，再用固定seed对簇均值自举95%区间；不足最小簇数不生成区间。该方法仍依赖簇间独立假设，不能处理所有跨日/热点相关性，更不能把合成区间当作投资有效性证明。

## worker守护与运行报告

```sh
ops_root="$(mktemp -d /tmp/guanshi-ops-XXXXXX)"
python3 -m stockradar export-fixture --output "$ops_root/input.jsonl"
python3 -m stockradar supervise --input "$ops_root/input.jsonl" --db "$ops_root/worker.sqlite3" --plan configs/operations-fixture.json
python3 -m stockradar ops-report --db "$ops_root/worker.sqlite3" --plan configs/operations-fixture.json --output "$ops_root/operations.json"
```

`worker`自身取得数据库旁0600的`.worker.lock`，macOS/Linux用flock保证一个采集worker。运行表schema单独版本化，未知schema拒绝；心跳、进程退出/中断和故障episode持久化。新的成功扫描才恢复故障，重复旧快照不清暂停、不新增观察证据。扫描业务数据仍使用原事务；附加运行观察在其后保存，崩溃缺失的观察不靠重传补造成实时证据。

`supervise`在前台守护自己创建的子进程，按显式计划限制重启次数/指数退避，并监控持久心跳；只终止自己的超时子进程。长Retry-After等待分片续写心跳，避免把退避误判为进程挂死。HTTP只允许experimental shadow，读取现有环境凭据；JSONL合成验收不访问这些凭据。没有安装launchd/systemd、开机自启或休眠恢复配置。

完整运行计划样例为[operations-fixture.json](../../configs/operations-fixture.json)，字段全必填、无隐藏目标默认值：目标股票池/日历版本、全市场及板块覆盖、P95、至少20交易日、每日切片比例、新鲜度、心跳超时、重启/退避、磁盘预算与归档周期。真实计划另存新ID，不能直接把12证券样例改名为全市场证明。

运行报告的门槛口径：

- 只纳入同策略配置哈希、同代码哈希、同模式及报告截止前的证据；模拟输入不能计入真实门槛。
- 真实影子还须当日实时接收、质量良好、精确目标分母、服务商完整市场能力声明及相同日历版本。旧录制、超龄切片及少量日采样不计完整日；按已完成交易日的完整分钟比例计算连续日数，中间缺一天重新累计。
- 全市场≥98%、单板块≥90%和每日切片≥98%分别检查。当前provider的`full_market_verified`始终为false，真实验收仍需NEXT03的独立PoC。
- 平台P95只使用非模拟通知的实际`request_completed_at`相对来源`slice_end`，聚合成员按共同delivery_id去重并取最长等待。旧cutoff、扫描耗时或inbox接受记录不能替代；本轮无真实投递样本，P95为null。未来接线能力不解除当前live_alert保护。
- 本轮报告真实合格切片0、连续真实影子日0，覆盖/日数/P95均pending；本地磁盘预算通过仅表示当前文件大小。`release_allowed`始终false。

故障与恢复当前进入内置通知中心和日志，真实外部故障提醒仍待NEXT04接线。UI可读取这些通知，运行统计报告通过CLI导出，没有新增HTTP研究/发布接口。

## 负载、归档与恢复

```sh
python3 -m stockradar benchmark --symbols 12 120 480 1200 --iterations 2 --concurrent-replays 2 --output "$ops_root/load.json"
python3 -m stockradar archive-scans --db "$ops_root/worker.sqlite3" --strategy-version fixture-v1 --before 2027-01-01T00:00:00Z --output "$ops_root/inputs.jsonl.gz"
python3 -m stockradar backup --db "$ops_root/worker.sqlite3" --output "$ops_root/backup.sqlite3"
python3 -m stockradar restore --input "$ops_root/backup.sqlite3" --db "$ops_root/restored.sqlite3"
```

benchmark最多6种规模、每种12的整数倍且不超过6000，迭代1至10、并发回放0至2；能力上限不是已测结论。本次最大实际测到1200。计量包括扫描提交时间、DB/WAL/SHM大小及本进程截至该点的RSS峰值；并发回放固定12证券，不能推导1200或全市场并发能力。数据库随临时压测目录清理，报告持久保留。全市场长期负载仍需目标机器实测，当前完整切片结构在最大样本已占用明显内存。

`archive-scans`按指定策略版本及UTC截止时点只读导出原输入、原结果哈希、配置和配置哈希；gzip固定mtime、SHA-256与清单，目标必须不存在，文件0600。保留期仅用于报告可归档行数，不会自动删除、裁剪、VACUUM或修改任何历史证据。归档不是完整业务状态备份，恢复仍用SQLite backup API。

本轮压缩11个原始切片，压缩后约为原JSONL的3.62%；已核对输入、原结果哈希及归档SHA。完整数据库恢复包含业务状态、水位、追加事件、通知和运行证据；SQL dump逐字一致。进程崩溃后锁释放/重启、旧快照幂等及看门狗由临时子进程与fake测试覆盖，不等于真实主机休眠或跨日网络演练通过。

后续真实验收仍需授权历史和当时成分/复权/执行信息、正式交易/成本规则、真实行情/钉钉路径、目标硬件全市场容量与P95、至少20连续交易日影子及主机恢复证据。原发布门槛不因本轮工程通过而降低。
