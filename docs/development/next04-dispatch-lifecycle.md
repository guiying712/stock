# NEXT04 · 本地模拟投递生命周期

2026-10-29完成本地工程与模拟验收，仍是0.1.0基础上的未发布源码。真实目标群PoC、真实机会渠道接线、平台时延及unknown人工核对未验收，live_alert继续在应用入口锁定。

## 已实现范围

- `SimulationDispatcher`提供独占启动/停止、独立线程调度、心跳、故障状态、所选版本的恢复及只读报告。worker/supervise通过完整计划显式启用，普通扫描/页面演示不创建模拟投递队列。
- `dingtalk_simulation`复用现有发件箱的固定窗口、风险优先、逐条复核、拆分、同信号顺序、30/60秒退避、最多三次尝试及每滚动60秒20次请求限制。模拟与真实渠道的聚合锚点、恢复和请求计数隔离。
- 模拟outbox、原SignalEvent、内置通知、扫描状态和逻辑/墙钟水位同事务提交。重复输入不补投历史，不改写原信号、模式、触发快照或数据模拟标记。
- 内置SimulationNotifier只产生本地回执，不读取钉钉凭据、不访问网络。标题含“本地投递演练”，通知中心显示“模拟器已记录”；真实通知统计与平台P95排除模拟记录。

本轮没有接通真实通知适配器，也没有增加主机开机自启、故障外部提醒或页面启动调度按钮。已有explicit钉钉测试仍须作为用户明确的测试操作执行，常规开发使用fake。

## 显式计划与命令

完整样例为[configs/dispatcher-fixture.json](../../configs/dispatcher-fixture.json)，独立于策略配置；全部字段必填，未知键报错，同ID不同内容拒绝。计划文件不随wheel默认打包，安装包用户须另存完整JSON。

| 字段 | 约束与样例含义 |
|---|---|
| schema_version / id | 整数1、不可变非空计划ID |
| strategy_version | 数据库已保存的冻结fixture/replay/shadow配置；集成worker须等于当前策略ID |
| transport | 只允许local_simulation |
| clock_mode | wall或simulated，必须显式选择 |
| simulation_start | simulated必须为UTC起点；wall必须显式null |
| poll_interval_seconds | 0.05—10秒，样例0.25秒 |
| heartbeat_timeout_seconds | 1—3600秒且至少为轮询间隔三倍，样例10秒 |
| max_messages_per_tick | 1—20个请求，样例20；返回的通知条数可更多 |
| shutdown_timeout_seconds | 0.05—30秒，样例5秒 |
| drain_timeout_seconds | 0—60秒，样例6秒；有限JSONL/once在退出前有界等待 |

使用新路径演练前两个切片：

```sh
python3 -m stockradar export-fixture --output data/dispatch-input-new.jsonl
head -n 2 data/dispatch-input-new.jsonl > data/dispatch-first-two-new.jsonl
python3 -m stockradar worker --input data/dispatch-first-two-new.jsonl --db data/dispatch-demo-new.sqlite3 --simulation-dispatch-plan configs/dispatcher-fixture.json
python3 -m stockradar dispatch-report --db data/dispatch-demo-new.sqlite3 --plan configs/dispatcher-fixture.json --output data/dispatch-report-new.json
```

默认新配置产生7条预警，5秒窗口后为1次本地调用。可另用serve打开同库查看通知。有限输入结束且排空等待到期后停止，不代表未到期队列已完成；需要继续消费时显式运行：

```sh
python3 -m stockradar dispatcher --simulation --db data/dispatch-demo-new.sqlite3 --plan configs/dispatcher-fixture.json
python3 -m stockradar dispatcher --simulation --once --db data/dispatch-demo-new.sqlite3 --plan configs/dispatcher-fixture.json
```

Ctrl+C停止常驻命令，--once仅执行一轮。源数据库必须存在，报告目标必须是新路径，报告不初始化调度表。supervise接受相同--simulation-dispatch-plan并传给子worker，完整操作见[部署手册](../DEPLOYMENT.md)。

## 时钟与证据

`wall`使用当前UTC复核过期/行情新鲜度；老录制数据不会自动成为当前机会。`simulated`用于明确的本地记录演练：起点来自计划，成功提交新输入后前进到其as_of，之后按单调经过时间推进；发送前每次刷新复核时点。

扫描事务保存逻辑时间与墙钟时间对。启动时结合历史运行心跳、已提交水位、入队和请求开始时间对恢复，包含非负停机经过时间，始终不倒退；进程即使在扫描提交后、回调/心跳前崩溃，也不丢失该水位。未来模拟事件暂缓，重复旧输入不推进水位。同策略未完成队列不允许混时钟域；模拟时钟快进会使旧修订或不再满足条件的机会被取消。

模拟outbox.created_at、聚合截止、退避和尝试逻辑at属于计划时钟；wall_enqueued_at、request_started_at/request_completed_at及运行心跳属于实际UTC墙钟。原行情event_time/available_at/ingested_at与SignalEvent.at保持原值。模拟回执中的accepted仅为本地记录，不能用于实际平台耗时、吞吐或投资表现。

`dispatch-report`含计划/配置/代码/输出哈希、所选策略队列总量、去重后的模拟请求次数及最新运行状态；始终simulation=true、transport=local、release_allowed=false、platform_acceptance_p95_seconds=null。`ops-report`继续仅统计真实钉钉渠道。health/API字段见[API参考](api.md)。

## 独占、恢复与停止

macOS/Linux使用数据库旁`.dispatcher-simulation.lock`的flock，覆盖整个模拟渠道；第二个所有者在恢复前失败。不要删除锁文件或并行运行集成worker与独立dispatcher。获取所有权后，只有所选版本/模拟渠道的遗留sending变为unknown，其他版本和真实渠道不改动。

恢复不延长窗口、不重置尝试次数或next_attempt_at，unknown不自动重试。新修订可在旧请求结束后接受复核，但旧通知不会因此重发。本地模拟unknown只说明模拟结果不确定；真实群的人工核对流程仍须PoC，当前无“强制重发unknown”接口。

适配器调用在SQLite事务外，等待模拟回执时采集仍可提交。停止先禁止新领取，让已领取请求完成；若测试用自定义模拟器阻塞，停止在计划超时后报DISPATCHER_STOP_TIMEOUT并保留锁，直到线程退出或进程结束。强杀后已领取请求以unknown恢复，不能假定请求一定没发生。内置模拟器没有网络等待，这项阻塞边界由测试替身验证。

生命周期元数据在首次启动时创建：dispatcher_meta（schema1）、dispatcher_plans、dispatcher_runs和dispatcher_watermarks。未知schema、计划不可变冲突、时钟域冲突直接报错；后台错误以failed及脱敏error_code记录，未完成队列保留。心跳healthy仅是当前代码/状态/新鲜度观测，不能替代锁或真实平台健康检查。完整SQLite备份包含这些表，归档输入文件不替代完整备份。

## 本轮验收

临时目录`/private/tmp/stockradar-next04-zdgu5u0z`，Python3.9.6、标准库运行；未修改实际data数据库/令牌和research快照，未配置真实群。持久摘要见[证据索引](evidence/next04/index.json)，原始数据库与wheel保留临时目录。

- 完整173项测试通过，新增23项覆盖事务回滚、互斥/进程强杀、窗口/退避/限流边界、版本/渠道隔离、unknown终态、发送期间扫描、阻塞停止、后台失败及worker/守护接线。
- CLI前两个切片：7条本地接受、1次调用；独立重启和重复输入后仍7/1。真实通知计数0、平台P95=null。全11切片当次为49条模拟通知，其中21接受、28取消、21次调用，无pending/sending；线程与快速时钟推进会影响具体结果，不把它作为固定策略基准。
- supervise子进程实际启用相同计划；完整备份恢复全部业务/运行/调度表逐表行数及内容哈希一致。报告重复路径和真实transport计划被拒绝。
- 桌面1280×720通知中心标签、无横向溢出/控制台错误检查通过，见[截图](evidence/next04/desktop-simulation.jpg)。未重测手机尺寸、真机或完整无障碍。
- Node语法与CLI帮助通过；离线重建0.1.0 wheel，22模块、3静态资源及2配置模板逐字匹配。仓库外Python3.9新旧配置分母15/12、本地接受7/4且各1次调用，未上传或发布。

本轮未重新执行研究、大规模负载或真实路径验收。真实行情/目标群、正式参数冻结、含STAR全市场容量和覆盖、平台P95、主机恢复及连续真实影子观察继续待NEXT03/04/06/07。
