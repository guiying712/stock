# HTTP API v1 · 当前实现

本文记录`stockradar/server.py`中已有接口，目标需求见[工程规格](../requirements/02-策略与工程规格.md)。服务默认地址`http://127.0.0.1:8765`，API前缀`/api/v1/`。当前没有远程部署、上传、下单、持仓记账或真实模式启用API。

## 鉴权与格式

所有API（包括health）要求`Authorization: Bearer <本机访问令牌>`。令牌来源和优先级见[运行手册](../DEPLOYMENT.md)。静态登录页无需API令牌，令牌不得放入URL。

POST使用`Content-Type: application/json`，正文必须为JSON对象，大小上限2,000,000字节。空操作也发送`{}`。Host仅接受localhost/127.0.0.1；如果提供Origin，须与当前HTTP服务地址一致。不开放CORS。

失败统一返回：

```json
{"error":{"code":"UNAUTHORIZED","message":"访问令牌无效或已失效"}}
```

常见HTTP状态：200成功、201创建版本、202提交回放、400输入/配置错误、401令牌无效、403Host/Origin拒绝、404不存在、409版本/幂等冲突或回放繁忙、413正文大小无效、415内容类型错误、500内部错误。

## 查询接口

0.2.4增加`GET /connections`：返回market列表、model配置、凭据是否存在/来源、修订号和当前会话测试状态，永不返回Key原文或令牌文件内容。模型当前仅管理连接，不提供推理业务API。


| GET路径 | 主要响应 |
|---|---|
| `/health` | mode、as_of、last_scan、coverage、expected_count、valid_count、missing_count、market_status、updates_paused、quality、provider、outbox、simulation_outbox、dispatcher、warnings、strategy_version |
| `/market` | 当前市场状态、广度、均线、波动及原因；暂停时显示UNKNOWN |
| `/sectors` | `{items:[...]}`：板块状态、RS/改善、广度、量能、覆盖、成分及原因 |
| `/sector-timeline?sector_id=...` | 当前策略版本的已保存切片范围、版本、阶段及质量变化、指标、代表成分和快照 ID |
| `/source-health` | 本机采样报告计数及按接口的请求状态、限流、最近完整响应和匹配分钟诊断；0.2.7兼容schema2，另给expected_records/usable_records/record_coverage，聚合或排除记录不冒充旧分钟覆盖，见[分钟验收工程](minute-acceptance-engineering.md) |
| `/signals` | `{items:[...],total,next_cursor}`，只查询当前运行策略版本 |
| `/signals/{id}` | 信号字段及events、notifications、feedback、tags；chart含触发/最近扫描视图、冻结位和原始来源表 |
| `/notifications` | `{items:[...]}`，数据库最近200条通知及投递尝试；health积压统计不受这200条限制 |
| `/strategy-versions` | `{items:[...]}`：id、status、config_hash、config、created_at、code_version |
| `/replays` | `{items:[...]}`，最近100个功能回放，包括request、result及error；先按请求类型过滤，不读取或被study结果挤占 |
| `/replays/{id}` | 单个任务状态和结果 |
| `/study-sources` | `{datasets:[id...],plans:[id...]}`，内置fixture及本地指定目录安全ID；每类最多100项 |
| `/studies` | 最近30个独立成本研究元数据，不读取完整样本 |
| `/studies/{id}` | 任务及原研究报告的计划和汇总投影，逐条样本及信号引用由完整报告提供 |
| `/studies/{id}/report` | 已完成研究的完整原报告JSON正文；未完成返回409，供鉴权原文导出 |
| `/study-cards` | 按配置哈希、对照组、模拟标记汇总已完成研究，分母和结果保留在各自报告下 |
| `/studies/{id}/cases?profile=...` | 卡片所示窗口的代表失效与待核对案例，支持四个对照组 ID |
| `/diagnostics` | config、rejections、logs、quality、release_gates、limitations、runtime |
| `/config/export` | 当前完整策略JSON，不包含环境凭据 |

`/signals`支持`status`、`q`（代码/名称包含匹配）、`sector`（主板块ID）、`limit`和`cursor`。limit默认30，限制为1—100。排序为分数降序、触发时间和信号ID；数据变化会令游标失效，返回`CURSOR_STALE`，客户端应从第一页刷新。

上述采样、热点及研究证据接口为鉴权后的本机只读查询。来源健康按目录读取有限报告，热点按最近 48 个切片投影，研究卡从最近 30 个任务取最多八份不同报告。未知覆盖、未知延迟和旧报告缺少的信号引用保持 `null`。 [读取和统计口径](history-workbench.md)

## 写接口

| POST路径 | 正文 | 行为 |
|---|---|---|
| `/signals/{id}/feedback` | `{"action":"watch","idempotency_key":"至少8字符的唯一键"}` | action可为watch/ignore/bought；同键同内容返回原记录，不创建成交 |
| `/strategy-versions` | `{"config":完整配置对象}` | 严格校验并注册版本，201；不切换运行版本 |
| `/replays` | `{"dataset_id":"fixture","strategy_version":"fixture-v1"}` | 两字段可省略，使用fixture和当前版本；202返回run_id/status |
| `/studies` | `{"dataset_id":"fixture","plan_id":"fixture"}` | 两字段必需；配对内置30日合成演练，或指定本地数据/完整计划；202返回run_id/status |
| `/demo/advance` | `{}` | fixture模式下处理下一个样例切片；结束时complete=true |
| `/demo/reset` | `{}` | 清除当前fixture版本的演示记录并加载前两个切片 |
| `/channels/dingtalk/test` | `{}` | 向已配置群发送标记为测试的消息；未配置时返回明确错误 |

反馈幂等键长度8—128字符。同键用于不同信号或不同action时返回`IDEMPOTENCY_CONFLICT`。点击或打开通知不会自动写买入反馈。

新配置须包含全部必需字段并使用新ID；同ID不同内容返回`VERSION_IMMUTABLE`。没有PUT/PATCH接口修改已保存版本。

回放数据集ID只允许字母/数字/连字符/下划线；非fixture文件须预先放到数据库旁`datasets/<id>.jsonl`。每个服务实例的回放与成本研究合计最多两个子进程。任务状态为pending/running/completed/failed；报告中5/10/20日评价窗口的pending与任务pending不同。

study文件ID长度1—80，拒绝未知请求字段、符号链接和路径穿越。计划预置于数据库旁`study-plans/<id>.json`，提交时冻结完整计划与文件/源码哈希；数据文件上限256MiB。启动前和读取后核对文件，计算前后核对代码；变化显式失败，不写实时信号、通知或持仓。详情的output_hash来自完整原报告，不能对汇总投影重新计算校验。导出直接保存服务器JSON原文，避免浏览器重新序列化0.0等数值后破坏原哈希。所有新增接口遵守相同鉴权、Host/Origin及错误响应规则。

## 信号与通知语义

信号状态为DETECTED、PREALERT、CONFIRMED、INVALIDATED、EXPIRED；参与状态独立为eligible、extended、paused、expired。DETECTED是内部记录，不应解释为已发预警。触发价格/时间与最新价格/时间分别保存。

数据过期、供应商错误或覆盖不足时，查询返回暂停状态及原因，不会仅凭缺数据把原信号写成策略失效。已保存的触发事件仍可在详情中追溯。

通知状态为pending/sending/accepted/failed/unknown/expired。inbox的accepted表示存入本地；dingtalk_simulation的accepted只表示本地模拟器已记录；钉钉的accepted表示平台受理，不表示已读或成交。真实机会投递当前未启用，钉钉测试响应及失败尝试会单独保存。

NEXT05的聚合由发件箱协调器实现，NEXT04本地模拟调度已接入worker/CLI，未新增HTTP投递入口。notifications、health.outbox和health.simulation_outbox按逐条通知计数；聚合成员的delivery_attempts共享delivery_id和notification_ids，开始记录包含发送时dispatch_snapshot及正文内容message_hash。一次调用可对应多条通知记录，不能将记录数解释为HTTP请求数。详见[聚合契约](next05-notification-aggregation.md)。

`health.outbox`排除inbox和dingtalk_simulation；`simulation_outbox`独立返回相同六种状态计数，均是数据库总量。`dispatcher`为当前策略最近一次本地演练运行（未初始化时null），包含plan_id、state、pid、heartbeat_at、clock_mode、clock_at、心跳年龄、healthy、代码/配置/计划哈希、累计计数和error_code。healthy只表示运行状态、心跳新鲜且代码匹配，不证明平台或主机存活；状态stopped/failed/interrupted保持可见。

模拟载荷含simulation_transport=local、simulation_context（plan_id/clock_mode）和wall_enqueued_at；created_at和聚合/重试边界属于计划时钟，原行情与事件时间不改写。本地回执含simulation=true/transport=local，页面显示“本地投递演练 / 模拟器已记录”，不冒充钉钉受理。计划/报告仅通过CLI使用，模拟报告不计平台P95，见[NEXT04说明](next04-dispatch-lifecycle.md)。

NEXT07新增采集worker的运行故障/恢复内置通知，payload.kind为runtime_incident，包含incident_id/code/phase/strategy_version/at及可读title/text，没有signal_id时不展示关联信号按钮。外部协调器尝试记录另含实际request_started_at/request_completed_at，旧cutoff仅作逻辑复核。运行统计和负载通过CLI导出；0.2.0显式成交研究已另接studies，原页面回放仍是功能观测。没有HTTP交易执行或发布接口。

0.2.0新增health.dingtalk_current_target_tested。连接测试回执附当前目标配置单向指纹，旧无指纹或其他配置的accepted不计当前验证；原记录不回填。诊断将当前连接受理与真实机会路径分开，后者仍待验收。图表过滤与PoC报告细节见[四项改进](four-priorities.md)。

NEXT08的health另返回`boards`数组，来自实际运行配置，侧栏以此显示范围。新配置schema_version=2包含显式STAR参数；旧无schema格式仍校验和导出原字段。保存新配置不会自动启用；fixture回放按选定配置schema选择原v1或新v2样例，不改变历史任务结果。输入批次的schema_version仍为1。

## 常见业务错误

| code | 处理方向 |
|---|---|
| CONFIG_INCOMPLETE | 补齐参数、修正类型或移除未知键 |
| VERSION_IMMUTABLE | 创建新策略ID |
| IDEMPOTENCY_CONFLICT | 不复用已有键表达不同操作 |
| MODE_FORBIDDEN / MODE_MISMATCH | 检查模式、数据模拟标记与操作范围 |
| CHANNEL_NOT_CONFIGURED | 在服务进程环境中配置钉钉 |
| REPLAY_BUSY | 等待现有任务结束 |
| STUDY_NOT_COMPLETED | 研究完成后再导出原报告 |
| CURSOR_STALE | 从第一页重新获取信号 |

`DATA_STALE`、`COVERAGE_LOW`等也会出现在成功查询响应的质量/原因字段里，不一定对应HTTP错误。`RELEASE_GATED`是应用启动时拒绝live_alert的错误，当前不存在通过API解除的操作。

## 分钟行情（0.2.5）

`GET /minute-data`返回本机最新capture、attempt及每股最近240条原始投影，不访问服务商。POST `/minute-data/prepare`执行零请求检查；POST `/minute-data/fetch`才按范围调用Tushare并保存新原始目录，不写策略数据库。

POST正文严格为`{schema_version:1,mode,symbols,start_date,end_date,access_confirmed}`：mode为latest/session/history，symbols为1—3个完整A股代码；latest/session日期须null，history显式日期最长7自然日且早于今天。账户保存的访问确认和本次确认均须满足，Token只从连接存储读取；不接受URL或内联凭据。最新批量1请求，其它每股1请求，串行6.1秒、超时15秒；60秒内重复请求或并发获取返回409（MINUTE_COOLDOWN/MINUTE_BUSY），缺配置返回400 MINUTE_NOT_READY。

原始标签/完成性/历史可见性未知仍为null，分钟记录不表示策略或发布通过。详见[分钟使用与验证](tushare-minute-feed.md)。

## 行情与模型连接管理（0.2.4）

| POST路径 | 完整请求字段 | 行为 |
|---|---|---|
| `/connections/market/{provider}` | `schema_version,revision,key_action,api_key,authorization` | 保存fuyao/tickflow/tushare独立连接；authorization含confirmed与reference |
| `/connections/model` | `schema_version,revision,key_action,api_key,base_url,model,timeout_seconds` | 保存一个自定义兼容模型连接；远程HTTPS，本机可HTTP |
| `/connections/market/{provider}/test` | `{}` | 按已保存配置发起一次固定报价/元信息请求；缺凭据或访问依据时0请求 |
| `/connections/model/test` | `{}` | 只读取`base_url + /models`，不发送生成请求 |

请求schema_version必须为整数1；revision须匹配GET返回的修订号，新配置为new。未知字段、缺项、重复JSON键、过期修订或非法URL均拒绝；配置错误返回400，未执行请求。

key_action为keep/replace/clear：keep和clear的api_key必须为空，replace必须是合法新Key。返回值只含credential.configured/source/local_key_saved/error、公开连接元数据和last_test，不包含api_key或本地令牌标识。POST体中的Key不能放入URL、模型ID或访问说明；测试接口不接受临时Key或临时地址参数。

测试返回status/message/tested_at/sent_requests，以及固定的strategy_input_ready=false、inference_tested=false；可达只证明所查接口响应，模型未列出、错误和阻塞分开展示。供应商消息、响应正文和异常原文不透传；不跟随重定向或自动重试。测试状态随配置/凭据变化失效，且不写入策略、信号或通知。文件存储和浏览器草稿规则见[连接配置说明](connection-settings.md)。

## Fuyao真实行情查看

GET `real-market`只读本机已校验记录；POST `real-market/fetch`按schema_version/mode/symbols/access_confirmed严格请求，模式latest、1至3只股票、报价与截至昨天的7自然日日线，共2请求。需要保存的Fuyao凭据及双重访问确认，独占执行、60秒冷却；错误MARKET_NOT_READY/BUSY/COOLDOWN等不触发自动重试。响应含groups/capture/attempt，逐股时间保留null，strategy_input_ready与release_allowed始终false。正文示例及实际验证见[真实行情说明](real-market-view.md)。
