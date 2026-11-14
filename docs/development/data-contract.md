# 行情与钉钉接入契约 v1

对应 FR01/02/09/12/13。当前没有已配置、已验证的行情服务商和钉钉群；所有内置样例均为合成数据。标准 HTTP 网关是待接入接口，不代表已取得供应商授权、历史成分或全市场覆盖。离线回放不发送外部通知。

## 行情接口

0.2.7另增[分钟验收工程](minute-acceptance-engineering.md)：诊断schema2显式声明阶段、证券日状态和无成交规则，整段记录独立计数，保留schema1；四阶段准备不读取凭据、不执行请求。两者仍不生成以下标准batch，不修改策略或发布门槛。

0.2.1另有[供应商原始小样本工具](next03-data-sources.md)，已取免密日线及当前元数据，但并非以下标准batch。其volume/amount单位未确认时保留null，event_time/is_complete未建立时也保留null，不以当前元数据/成分快照回填历史，不能直接输入worker。Tushare的独立探测只通过固定官方HTTPS POST体携带token，与下述标准网关Bearer认证分别处理。

0.2.2增加[离线分钟诊断](next03-minute-quality.md)。诊断计划独立schema1，强制显式时间/时区、完成性、量额单位、增量/累计、复权及相应依据；日历版本/依据未知时覆盖率为null。派生区间终点与完成性只存在于新诊断报告，不改写原始样本或历史可见时间；原始行的重复/修订保留，明确口径下才比较。准备报告及质量报告都不是以下batch，不接入worker/replay/evaluate；检查通过也不授予策略或发布资格。

0.2.3的[公开接口原始PoC](next03-public-poc.md)沿用独立采样契约，Sina JSONP不执行脚本；东方财富0价格投影为null，原值/原始字节保留，缺单位不乘100。首次接收时间不冒充历史最早可见时间，当前成员/ST/停复牌快照不证明历史资格或完整风险状态，partial不当作完整。原始同标签比较不是已对齐完成分钟；未知口径下canonical end/is_complete/coverage保持null。以上均不是下述标准batch。

0.2.4增加[Fuyao与独立连接配置](connection-settings.md)。Fuyao仅允许日线/当前资料原始采样，三板块模板12请求，上限20；缺Key/访问依据时零请求。股/元映射采用文档依据，未知历史可见性和完成性不补值，快照不伪装分钟。行情Key可从独立本地令牌文件读取，环境变量优先；页面保存不改写采样计划授权字段，也不构成以下标准batch。模型连接只作目录检查，不在evaluate或提醒路径中。

Python 3.9+ 标准库接口位于 `stockradar/providers.py`：

```python
FixtureProvider().iter_batches()                 # 合成样例，逐切片迭代
JSONLProvider("data/recording.jsonl").iter_batches()
HTTPJSONProvider(endpoint, token=None).get_slice(as_of=None)
record_batches("data/recording.jsonl", batches)  # 原子写出，保留原始时间与 null
validate_batch(batch)                           # 结构/单位/时间格式检查，不补值
```

网关只接受预先配置的 HTTPS URL。可选 Bearer 凭据只在 `Authorization` 请求头内，URL 不接受密钥查询参数；禁止重定向，防止把凭据转发到其他主机。GET 返回一个切片对象；可选查询参数 `as_of` 为 UTC ISO 时间。不接受股票池缩小参数，以免把自选扫描当成全市场。

失败抛出 `ProviderError`，字段为 `code/message/retryable/retry_after`。HTTP 429 为 `PROVIDER_LIMITED`，透传有界的秒数形式 `Retry-After`；上层必须遵守退避，适配器不自动重试。连接失败或超时不使用前值代替。每个 HTTP 响应和 JSONL 行上限为 64 MiB。JSONL 空行跳过，非法行停止并报告行号；拒绝重复 JSON 对象键及 NaN/Infinity。合法的重复行情事件保留给策略水位与修订机制处理。

## Batch schema

0.2.5的[Tushare分钟页面](tushare-minute-feed.md)复用独立采样格式，新增rt_min_daily及有界手动获取。GET/页面轮询只读本机记录；单行量额不默认为策略累计量，原始标签不默认为分钟结束，未知完成性/复权/历史可见性不补值。这些记录仍不是以下batch，不进入worker/evaluate或解除发布锁。

每行一个完整 JSON 对象，字段如下。价格推荐十进制字符串，未知为 `null`，不得填 `0`；代码必须是保留前导零的六位字符串。所有时间带 UTC 时区；交易日和连续竞价时段按中国时区解释。

| 字段 | 类型与含义 |
|---|---|
| `schema_version` | 整数 `1` |
| `snapshot_id`, `source` | 非空标识；快照 ID 必须稳定，修订用新快照或行情 revision |
| `simulated` | 必填布尔值；无真实可见时间而使用模型时也必须披露 |
| `as_of` | 本次策略截止 UTC 时间，例如 `2026-10-28T02:01:00Z` |
| `units` | 精确为 `{"volume":"shares","amount":"CNY","amount_mode":"cumulative"}` |
| `calendar` | `version`, `trading_dates:[YYYY-MM-DD]`, `sessions:[[HH:MM,HH:MM]]`；显式交易日期，不能只按工作日推断；评价目标日收盘另需`close_time:HH:MM` |
| `instruments` | 当时股票资料，含停牌/ST/退市及范围外标的供过滤；不能只给有报价者 |
| `sectors` | `[{id,name,type}]`，type 区分行业与题材 |
| `memberships` | 当时可见、有效的板块成员关系 |
| `quotes` | 当前完成或不完整分钟报价；缺少证券不得虚构条目 |
| `daily_bars` | 历史日线和对应可见时间、复权因子 |
| `minute_history` | 历史分钟累计成交和窗口价格，使用与当前报价相同 schema |
| `benchmark` | `{id,quote,daily_bars,minute_history}`；缺基准报价时 quote 为 null |
| `corporate_actions` | 可选显式公司行为数组，研究模型使用；存在时严格校验，缺省不推断股份/现金 |

`Instrument` 必需字段：`id,code,name,exchange,board,listed_on,status,valid_from,valid_to,available_at`。交易所为 SSE/SZSE/BSE；上市板块为 MAIN/CHINEXT/STAR/BSE。资格过滤由策略处理，传输层不从分母中静默删除范围内缺行情证券。

Instrument与Membership的有效区间统一按`[valid_from,valid_to)`解释，起点包含、终点不包含。边界可使用`YYYY-MM-DD`（Asia/Shanghai当天零点）或带UTC时区的ISO时间，两种格式可混用；任一边界为`null`表示该侧开放。传输层与策略层共用解析，有限起点必须早于有限终点，无效/无时区/非UTC时间或空区间直接报错。策略按批次`as_of`的UTC时点比较，午休不改变边界含义；仍须满足`available_at`及存在时的`event_time`不晚于评估时点。解析不改写原始字段或已存快照。

NEXT08已支持SSE/STAR策略资格。传输层和直接evaluate仅接受SSE/MAIN、SZSE/MAIN、SZSE/CHINEXT、SSE/STAR以及供过滤留证的BSE/BSE；错误组合报错。新配置schema2须提供STAR全部参数，历史无schema配置保持原MAIN/CHINEXT格式。新样例15个合格对象、6个排除对象，缺科创报价时为14/15；历史v1仍为12/3。配置schema2、执行规则schema2与本批次schema1是独立契约，不升级或重写历史批次。

`Membership` 必需字段：`instrument_id,sector_id,valid_from,valid_to,available_at,provider,snapshot_id`。证券/板块引用必须存在；历史回放不可用今日关系覆盖历史。

`Quote` 必需字段：`instrument_id,open,high,low,close,prev_close,volume_shares,amount_cny,interval,is_complete,event_time,available_at,ingested_at,adjustment_factor,source,quality,revision`。

- `interval=60`，`revision` 是从 1 起的整数；`is_complete` 为布尔值。
- `amount_cny` 为截至当前交易分钟累计额，不能拿一分钟增量与历史累计额相比。
- `volume_shares` 单位为股；金额人民币元；传输层不推断供应商单位。
- `quality` 由供应商显式标识（良好输入为 `good`）；完整性、过期、价格区间和时点可见性仍由策略检查。
- 三种时间分别表示市场事件、最早可见、实际接收时间。不能把历史数据下载时间当成历史可见时间。

报价可选`execution`供`study`仿真使用；存在时全部键必填、拒绝未知键：

| 字段 | 约束 |
|---|---|
| `status` | trading/suspended/delisted/unknown，unknown保留待定 |
| `can_buy,can_sell` | 布尔值或null；不从成交量或价格自行推断 |
| `available_volume_shares` | 可成交股数整数或null，全额仿真成交的显式容量假设 |
| `limit_state,limit_up,limit_down` | bounded须有效上下限；unbounded/unknown时上下限为null |
| `rule_version,available_at` | 非空规则ID、带UTC时区的最早可见时刻 |

旧报价不含execution仍可做功能回放，但研究保留pending，不默认视为可买卖。execution的未知值不能算作明确未成交；证券登记为停牌/退市也不能靠can_buy=true绕过。

`corporate_actions`项精确包含`id,instrument_id,type,effective_at,available_at,share_multiplier,cash_net_per_old_share,factor_from,factor_to,source`，证券引用须存在；type为split_dividend或unsupported。倍率、每旧股净应收及新旧因子可为null，未支持/缺失/迟到信息保持pending；同ID载荷冲突必须另用修订ID。研究不会仅凭复权因子猜测公司行为，在线策略仍保留暂停处理。完整计划、规则schema、成交/公司行为假设与数据边界见[NEXT06/07说明](next06-07-local-acceptance.md)。

科创板逐规则必须使用schema2，显式order_type及buy/sell_min_shares、buy/sell_step_shares、sell_odd_lot_full_exit；其余规则字段延续。历史v1的buy_lot格式仅保留原市场。STAR的200股最低量与1股递增、申报上限、T+1及零股退出独立验证，真实价格限制/资格/费用仍需显式证据。新旧字段与官方资料见[NEXT08说明](next08-star-acceptance.md)。

`DailyBar` 必需字段：`instrument_id,date,high,low,close,prev_close,amount_cny,adjustment_factor,available_at`。

传输层保留未来可见的输入，以便策略产生可追溯的拒绝原因；它不会把未来可见时间改写为当前时间。数据源必须提供当时已知的复权因子，不能用后见因子伪造历史可成交价格。

历史评价使用提醒时已可见的版本化交易日历。`sessions`描述连续竞价，不代替实际收盘时刻；缺`close_time`、后续交易日或目标日可见收盘报价时，5/10/20日评价保持pending，不拿更早价格充当目标日结果。

`capabilities()` 中的 `full_market_verified` 当前始终为 `false`。上线前须核验服务商授权、最大批量、限流、历史深度、成分历史、股票状态、基准口径、延迟和全市场覆盖率。此版本没有对任何免费接口作可用性承诺。

## 钉钉群机器人

代码位于 `stockradar/notifier.py`：

```python
payload = build_message(signal, event, test=False, base_url=None)
result = DingTalkNotifier(webhook_url, secret=None, timeout=10).send(payload, idempotency_key)
```

只接受 `https://oapi.dingtalk.com/robot/send?access_token=...`。构造对象不发送消息。用户在本机配置 Webhook 和可选加签密钥；不得写入仓库、日志或详情链接。安全设置为加签时必须同时配置密钥。测试消息需用户在受保护页面主动触发，带醒目的“测试通知”。fixture 消息带“模拟数据”。

加签实现使用毫秒 `timestamp`，对 `timestamp + "\n" + secret` 使用以 secret 为密钥的 HMAC-SHA256，Base64 后通过 URL 参数编码。正文采用 `msgtype:markdown`、`markdown:{title,text}`。禁止跟随重定向；TLS 验证使用系统默认配置。

返回 `status,response_code,receipt,error,retryable`：

- 仅平台 JSON 中整数 `errcode=0` 为 `accepted`；不表示已读或已成交。
- 明确的非零错误码为 `failed`；保存数值回执，避免平台错误文本回显密钥。
- 超时、连接重置、不可解析响应、缺结果码或不确定的服务器错误为 `unknown`；不得盲目重试。
- HTTP 429 和已识别的限流错误可由发件箱作有限退避重试；发送前须重新核验行情、有效期和信号 revision。
- `idempotency_key` 用于本地事务发件箱；群机器人没有在本接口中暴露端到端幂等回执查询，不能保证外部 exactly-once。

通知正文分别展示触发价格/时间和当前价格/时间、信号 ID、规则分、失效价、参与范围与来源。详情 URL 不含登录凭据；打开后重新登录。暂不开放平台卡片回调，反馈通过鉴权 API 完成。

## 事务发件箱接口

`stockradar/outbox.py`提供独立投递协调器。当前离线应用不启用真实机会投递；NEXT04已将独立模拟渠道接入worker，真实渠道仍须完成发布门槛和接线。

```python
enqueue(db, signal, event, channel="dingtalk")
dispatch_pending(store, notifier, as_of, max_messages=20)
recover_inflight(store)
```

`enqueue` 使用调用方已有事务，与 SignalEvent 一起提交，不私自 commit。同一信号、修订与渠道构成唯一键，重复相同载荷返回原 ID；不同载荷报幂等冲突。DETECTED 记录不允许进入外部发件箱。

调用方应在`BEGIN IMMEDIATE`写事务中保存信号/事件并enqueue。首次从DETECTED进入PREALERT或CONFIRMED的新机会读取已保存版本的显式`runtime.group_window_seconds`（0至59秒整数）。窗口大于0且信号含冻结的`evidence.notification_group:{id,version}`时，按策略版本、首次`trading_date`及分组ID/版本收集消息；截止时间保存在每条`outbox.payload.aggregation.ready_at`，相同窗口使用同一截止时间。窗口为0关闭聚合；旧信号缺分组证据时保持单条发送。缺窗口配置直接报错，不提供真实策略默认值。

到期时`dispatch_pending`对成员逐条复核，过时/偏离成员取消并保留原因，其余可合并为一条消息。后续入队不延长原窗口，取消首条或重启也不改变其他成员截止时间。确认、恢复、失效、过期和条件暂停/偏离更新不聚合；风险更新优先。正文保持每只股票的价格、时间、范围、规则分、ID与来源，按现有18,000字节上限拆分；单条仍过长则以MESSAGE_TOO_LARGE取消。

投递器在SQLite写锁内取得发送权并记录尝试，然后在事务外调用通知适配器。真实渠道只有frozen的live_alert版本且非模拟输入能通过（应用仍锁定live_alert）。本地模拟渠道仅允许冻结的fixture/replay/shadow及SimulationNotifier，不改变信号原模拟标记。普通机会必须仍处于PREALERT/CONFIRMED、eligible、参与价格范围内、TTL未到、无供应商暂停标志且行情符合该版本`runtime.stale_after_seconds`（样例90秒）。修订落后、价格偏离或缺数据会取消旧通知并保留原因。失效、过期、条件暂停/偏离更新优先处理，不受入场有效期或每日新机会额度影响。

明确失败按30秒、60秒退避，每条通知最多三次实际发送，每次重试前重新核验；聚合失败仅重试原批次存活成员，不混入新机会。unknown 永不自动重试。聚合请求同事务领取/回写全部成员，每个成员的开始记录含共同delivery_id、notification_ids、dispatch_snapshot及规范JSON的message_hash。一个信号有sending请求时，后续修订暂缓领取。

同数据库钉钉渠道每滚动60秒最多20次发送，跨进程调用共享该限制；按实际HTTP请求计数，聚合成员的重复尝试记录只计一次。风险更新仍遵守渠道物理限额，不受新机会每日额度限制。`max_messages`是本次请求数上限，返回列表按逐条通知列出，可能多于该值。`recover_inflight`仅在已取得唯一dispatcher所有权的进程启动时调用，将遗留sending成员全部改为unknown；不要在另一个投递进程仍活动时调用恢复。

协调器自身不sleep、不创建定时线程；NEXT04本地模拟dispatcher负责到期调度。配置窗口限制聚合收集等待，不包含调度停机、限流、网络或退避等待，不能据此宣称端到端时延达标。原模块fake验收见[NEXT05记录](next05-notification-aggregation.md)。

### 本地模拟生命周期（NEXT04）

独立的完整计划选择local_simulation及wall/simulated时钟，不能选择DingTalkNotifier。模拟渠道为dingtalk_simulation；enqueue额外要求created_at及simulation_context={plan_id,clock_mode}，真实渠道禁止覆盖入队时间。`Store.apply_batch(..., simulation_delivery={plan_id,clock_mode,enqueued_at})`核对已保存计划，将模拟队列和时钟水位与扫描/事件/内置通知原子提交；默认None不创建模拟队列，重复快照不补投历史。

`dispatch_pending`可显式指定channel/strategy_version及停止检查，`recover_inflight`可限定渠道/版本，模拟恢复才允许as_of。真实接口默认仍是dingtalk。模拟队列、聚合锚点和请求限额按渠道隔离；类型/模式/原模拟证据校验继续生效，未来模拟事件延后处理，不改写原始时间或伪装新鲜行情。

模拟dispatcher先取得数据库旁独占锁再恢复，sending改unknown不重发；持久计划/运行/水位采用独立schema1。单调模拟时钟结合已提交输入和逻辑/墙钟时间对恢复，未知schema和同策略未完成队列的时钟冲突直接报错。停止不再领取新请求，已领取请求可完成，阻塞超时保留锁。本地回执仅保存哈希和标记，不读取通知凭据或访问网络；不计真实平台时延。完整字段和限制见[NEXT04说明](next04-dispatch-lifecycle.md)。

发件箱测试覆盖排队过期、价格变化、修订抢先、断线不确定、受控重试、事务回滚、并发领取、重启恢复、风险优先和跨调用限流。这里的确定性是本地业务事件幂等，不代表钉钉外部端到端只投递一次。

## 官方资料与验证记录

2026-10-28 查阅了 [钉钉自定义机器人接入](https://open.dingtalk.com/document/robots/custom-robot-access)、[自定义机器人安全设置](https://open.dingtalk.com/document/robots/customize-robot-security-settings)。当前文档为动态页面，本次检索未取得正文，因此不能把访问页面当成真实渠道联通验证。另查阅了阿里云官方 [Webhook 安全设置](https://help.aliyun.com/zh/sls/create-a-webhook)、[签名不匹配错误诊断](https://help.aliyun.com/zh/cms/cloudmonitor-1-0/support/the-dingtalk-robot-that-sets-the-alarm-contact-reported-an-error-the-signature-sent-by-the-robot-does-not-match)、[钉钉事件通知与发送频率](https://help.aliyun.com/zh/document_detail/2342593.html)，确认安全设置与平台错误必须单独处理，且机器人有发送频率限制。

本地测试使用 mock 网络，验证签名、URL 校验、响应分类、超时不重发、日志脱敏、JSONL 原子写出及无损往返。尚未配置真实群，因此未进行真实投递或签名服务端核验；接入时需用“测试通知”完成 PoC，并记录平台受理耗时和结果。
