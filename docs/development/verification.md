# 实际验证记录

验证时间：2026-10-29 01:11 UTC（北京时间09:11；用户所在时区2026-10-28）。环境：macOS，系统Python3.9.6；无第三方运行依赖。以下只验证功能与工程行为，不评价投资效果。

下列初始章节为该次执行的历史记录，不表示当前预览服务仍在运行。后续修复与验收独立追加在文末；最新实现边界与后续任务见[项目进度](../../TODO.md)。

最新补充：0.2.7分钟验收工程于用户时区2026-11-12（UTC 11月13日04:29—04:30）完成348项Python及零请求CLI检查，见[独立证据](evidence/minute-acceptance-20261112/README.md)。没有真实账户/行情/通知、前端或wheel验收；旧记录保留原日期。

## 自动测试

```sh
PYTHONPYCACHEPREFIX=/private/tmp/stockradar-pycache python3 -m unittest discover -s tests -v
```

实际结果：`Ran 68 tests in 8.070s — OK`。HTTP用例使用临时本地监听端口，运行时经过沙箱授权；无外部行情请求或钉钉实际投递。

| 测试文件 | 范围 |
|---|---|
| test_engine.py | 17项：契约、确定性、预警/确认、覆盖分母、广度、10%风险、偏离/恢复、失效/过期、未来可见性、基准时点、除权暂停、缺历史、重复/迟到、日历、版本、连续性、量能及坏历史 |
| test_application.py | 15项：事务注入回滚、重启、反馈幂等、快照修订拒绝、备份恢复、模式、通知原快照、完整积压统计、孤儿任务、并发版本、断源恢复、HTTP鉴权及异步回放 |
| test_integrations.py | 14项：数据契约/JSONL/网关、钉钉签名、结果分类、超时未知、脱敏和恶意URL |
| test_outbox.py | 13项：并发claim、重启不确定状态、旧修订取消、新鲜度/TTL、风险优先、退避/次数和限流 |
| test_replay.py | 9项：目标交易日与收盘缺失、可见日历、旧报价重传、null价格、延迟、复权、模拟/真实隔离 |

另通过 JavaScript `node --check stockradar/static/app.js` 和 Python `compileall`。

## 完整命令行路径

以下实际执行成功：

1. `export-fixture --output data/fixture.jsonl`：导出11个合成切片；每个切片包含12个合格样例证券、3个排除对象、4个板块（其中两个重叠）。
2. `demo --db data/first-demo.sqlite3`：依次观察UP、预警、确认、价格偏离、覆盖不足UNKNOWN、恢复、结构失效、重新检测和到期。
3. `replay --input data/fixture.jsonl --output data/replay-report.json`：四组对照完成，报告源码哈希与当前代码一致。stock_only记录8个提醒、其他三组各4个；这只是人为构造的分支结果，不能解释为样本外效果。缺失切片时最低覆盖为11/12，符合故障注入预期。
4. `worker --input data/fixture.jsonl --db data/recording-check.sqlite3`：11个切片均成功持久化。
5. `backup --db data/recording-check.sqlite3 --output data/recording-backup.sqlite3`：在线备份与完整性检查成功。
6. `restore --input data/recording-backup.sqlite3 --db data/recording-restored.sqlite3`：恢复成功，信号与源数据库一致；测试同时核对水位、事件和通知。

报告中的5/10/20交易日窗口均为pending，成本后收益为null。

## 本地服务实测

当次启动 `python3 -m stockradar serve --port 8765`，监听127.0.0.1，使用新生成的本地令牌。实际通过认证请求确认：

- `/api/v1/health`：fixture、UP、合成覆盖1.0，行情截至2026-10-28T02:01:00Z。
- `/api/v1/signals`：4个预警对象。
- `/api/v1/sectors`：4个板块对象。

这里的100%仅指12个合格合成对象，不代表真实全市场。

## 打包

离线无依赖构建wheel成功：`data/wheels/stockradar-0.1.0-py3-none-any.whl`。另安装到独立临时目录，在隔离导入路径下成功加载打包的默认参数与11个切片，确认默认配置/静态资源被包含。

## 未验证

- 浏览器工具返回 `Local browser use is disabled in Work settings`；没有绕过设置。未完成实际浏览器、手机截图、可访问性与视觉布局验收。界面目前只做代码/语法检查及API联调。
- 没有真实行情商或钉钉群配置，不声称真实接入、真实消息受理或全市场覆盖通过。
- 尚未验证交易制度/成交仿真、成本/滑点、样本外收益、连续20交易日影子运行、P95通知延迟及全市场并发负载。

真实机会推送入口仍明确锁定；剩余需求见[交付范围](acceptance.md)。

## NEXT01修复验证（追加，2026-10-29 03:03 UTC）

环境：macOS、系统Python3.9.6。当前源码基于0.1.0，修复尚未发布；原有验证时间与失败事实保留。

- 新增策略4项、传输契约2项测试，共74项。覆盖同日UTC起止边界（起含终不含）、北京时间日期跨日、午休、未来可见性、开放/混合区间、非法与倒置/空区间，以及评估不改写输入。原有确定性、重启、冻结证据与回放测试继续通过；历史数据库不做迁移。
- 首次完整测试在沙箱内执行：`Ran 71 tests in 19.710s — FAILED (errors=1)`；HTTPTests初始化因本地端口绑定被沙箱拒绝，3项HTTP测试未执行，不能算完整通过。
- 授权后以同一命令重新执行：`PYTHONPYCACHEPREFIX=/private/tmp/stockradar-pycache python3 -m unittest discover -s tests -v`，结果为`Ran 74 tests in 8.453s — OK`。使用临时数据库和本地HTTP端口，外部通知均模拟，无真实群投递。
- `PYTHONPYCACHEPREFIX=/private/tmp/stockradar-pycache python3 -m stockradar --help`退出码0。

本次未重建wheel、未重新执行历史CLI扫描/回放与隔离导入，也未进行浏览器/手机或真实行情/群路径验收。NEXT02—NEXT07仍未完成，live_alert继续锁定。

## NEXT02验收尝试（追加，2026-10-29 03:35 UTC）

- 已阅读设计、组件、页面结构与部署规范，并调用浏览器工具检查当前能力；浏览器列表为空，明确返回`Browsers: Error: Local browser use is disabled in Work settings`。没有改动或绕过该设置。
- 默认shell未找到`node`；通过工作区依赖工具取得内置Node路径后，执行`/Users/dane/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check stockradar/static/app.js`，退出码0。未安装新依赖。
- 静态代码可见viewport、移动断点、对话框角色、Esc关闭及Tab焦点限制实现；这些仅为代码存在证据，未得出交互、视觉或无障碍通过结论。
- 本次未启动服务、未创建测试数据库、未读取访问令牌、未修改应用代码；未进行真实通知测试。登录、四页、详情、反馈、回放、刷新和窄屏布局均仍待实际浏览器验收。

NEXT02保持未完成。恢复条件为Work设置允许本地浏览器使用；启用后须使用独立临时数据库执行上述检查并保存结果。

## NEXT02浏览器验收及修复（追加，2026-10-29 04:01 UTC）

用户调整浏览器权限后重试，工具可列出Chrome及内置浏览器；本次使用内置浏览器完成桌面1280×720和手机尺寸320×740、390×844检查。完整步骤、问题复现、修复与截图见[专项记录](next02-browser-acceptance.md)。这不覆盖真实手机或完整无障碍验收。

- 修复切页滚动位置、轮询刷新后的详情焦点返回、空数据库覆盖率应为null三处问题。
- 使用独立临时数据库、本机18765/18766服务及合成数据；未读取真实令牌或使用真实通知凭据。临时处理器注入500/401，四页均显示错误，401退出并清除会话。
- 完整测试命令`PYTHONPYCACHEPREFIX=/private/tmp/stockradar-pycache python3 -m unittest discover -s tests -v`在授权本地端口环境执行，实际`Ran 75 tests in 8.723s — OK`；新增1项无数据覆盖率/首切片恢复测试，应用/API共16项。
- 内置Node执行`node --check stockradar/static/app.js`通过；`PYTHONPYCACHEPREFIX=/private/tmp/stockradar-pycache python3 -m stockradar --help`退出码0。

NEXT02的限定浏览器验收完成；真实手机、读屏/完整对比度和其他浏览器留作补充。NEXT03—NEXT07仍未完成。未重建wheel，live_alert继续锁定。

## NEXT05窗口聚合验收（追加，2026-10-29 04:24 UTC）

环境：macOS、系统Python3.9.6。当前源码基于0.1.0，聚合功能尚未发布；测试使用独立临时SQLite及fake/Mock notifier，无真实行情请求、Webhook或群发送。实现和验收范围见[通知聚合说明](next05-notification-aggregation.md)。

- 新增22项测试：发件箱19项、策略2项、通知正文1项。当前定义合计97项：策略23、应用/API16、集成17、发件箱32、评价9。
- 覆盖同热点多股票合并、固定/边界窗口、取消首条后保持截止、等待中重启、链式Jaccard分组一致性与成员版本冻结、风险优先、逐条复核/旧修订取消、超长拆分、失败批次缩减重试、超时/崩溃unknown、跨进程领取与同信号顺序、领取/结果回写故障事务回滚，以及按实际请求计数的滚动限流。
- 开发中的专项28项测试曾有1项并发用例断言失败：第一调度器默认还能继续发送随后入队的风险更新，返回3条而用例预期2条；将该用例限制为只领取一次请求后通过。最终完整执行包含修正后的并发用例及后续新增用例。
- 最终执行`PYTHONPYCACHEPREFIX=/private/tmp/stockradar-pycache python3 -m unittest discover -s tests -v`，已授权临时本地HTTP端口，实际结果为`Ran 97 tests in 9.766s — OK`。
- `PYTHONPYCACHEPREFIX=/private/tmp/stockradar-pycache python3 -m stockradar --help`退出码0。两份fixture配置未修改；本次无前端文件变更，未重跑NEXT02浏览器或JavaScript验收。

NEXT05的模块/fake验收完成；常驻worker接线、调度时延和真实群消息渲染/受理仍待NEXT04。窗口参数不表示端到端P95时延达标；未重建wheel，未完成真实行情、全市场负载、样本外评价或影子运行，live_alert继续锁定。历史68/74/75项结果及失败事实保留。

## NEXT06/07本地工程与合成验收（追加，2026-10-29 06:56 UTC）

用户确认“仍无，先完成本地工程和合成验收”。本次交付范围据此限定，不将真实历史/全市场/持续影子条件改为通过。环境为macOS、系统Python3.9.6、标准库运行时；独立临时目录`/private/tmp/stockradar-next06-07-92j3kj32`。未修改实际data数据库/令牌或research来源快照，未使用真实行情/通知凭据，没有真实行情请求或钉钉发送。

最终应用源码哈希：`beb0071a5a0421a3f646e887df8f3f25c3d5f8e55951f7f07385c73da3fe3add`。最终研究、负载、运行、恢复核对及wheel记录均匹配该哈希；先前迭代报告保留在临时目录，但未当作最终证据。完整复现口径见[专项说明](next06-07-local-acceptance.md)，持久摘要及原始文件校验和见[证据索引](evidence/next06-07/index.json)。

### 自动测试与开发中失败

- 新增执行/研究20项、运行17项、负载2项；共136项（既有策略23、应用/API16、集成17、发件箱32、功能评价9项继续通过）。
- 本轮早期完整测试曾因沙箱拒绝临时HTTP端口而失败，随后授权本地端口重跑既有97项，实际`Ran 97 tests in 9.548s — OK`。受限执行不记通过，也不代表自动审批拒绝。
- 开发中的运行报告测试曾有4项NameError：筛选推导式误写为布尔表达式，已修复；执行样例的成交/成本预期也经过校正。随后专项36项与负载2项通过。
- 中间完整135项通过后，复核发现延迟入场未跟随最新参与状态：已补充暂停不买、恢复后才买、终止机会不复活的回归，并禁止登记状态已非active的证券仿真买入。
- 最终授权临时本地HTTP后执行`python3 -m unittest discover -s tests -v`，实际`Ran 136 tests in 21.616s — OK`。日志保存于[unittest.log](evidence/next06-07/unittest.log)，时间及范围见[tests.json](evidence/next06-07/tests.json)。所有外部网络/通知均fake或Mock；看门狗仅终止自身创建的临时测试子进程。
- `python3 -m stockradar --help`退出码0。无前端变更，本轮未重新执行Node或浏览器验收；此前NEXT02记录保持原时间。

### 研究CLI与结果核对

执行`export-study-fixture --days 90`与最终`study --input .../study/synthetic.jsonl --plan .../study/study-plan.json --output .../study-report-accepted.json`，均退出码0。数据为90个合成交易日、每日09:30—09:37短时段、630批次，不是实际交易日历或分钟历史；规则/费用来源显式为synthetic且verified=false。

完整计划包含0/1/3/5分钟反应、5/10/20交易日、fixed/risk退出、train/validation/test及200次固定seed聚类自举。每组1080次首次提醒，25,920个模型样本；同一提醒在多方案中重复，不是25,920笔独立交易。

| 组 | closed | not_filled | purged | pending |
|---|---:|---:|---:|---:|
| stock_only | 7,920 | 12,960 | 3,360 | 1,680 |
| sector_filter | 7,920 | 12,960 | 3,360 | 1,680 |
| early | 7,920 | 12,960 | 3,360 | 1,680 |
| confirmed | 3,960 | 19,440 | 1,680 | 840 |

这是构造样本的分支验收，不是四组策略的投资比较。已核对报告输出哈希、计划哈希及四组样本哈希；报告净收益仅为显式假设的仿真值。参数冻结资格始终false，原因包含合成数据、未核验规则/成本以及缺真实路径/影子证据。

- 数据规范化哈希：`b9aa2fb85fc1cf6404dea339e4d5c90f0dd12b62e2a51d63b7228423151f6270`。
- 计划哈希：`cfb94488732c28e102ec60d4f1cf49ed59c49b1dd27b8f8dd6212d4afe3fcb04`。
- 完整JSON报告文件SHA-256：`a4037e4da2c190801701463fecce38ba9ce39b7fc8aa15e8b8ba2964f251998d`，92,458,061字节。JSONL原始文件181,057,842字节；大文件保留临时目录，仓库保存约0.5MB精简证据，不把数据/报告打入应用包。

### 合成负载与并发

执行`benchmark --symbols 12 120 480 1200 --iterations 2 --concurrent-replays 2`，退出码0。扫描计时覆盖输入校验、evaluate及SQLite提交；每档4次，P95等于本次最大值。

| 合成证券数 | 扫描提交P95秒 | DB/WAL/SHM字节 | 本进程累计峰值RSS字节 |
|---:|---:|---:|---:|
| 12 | 0.098 | 1,650,688 | 41,418,752 |
| 120 | 1.107 | 14,192,640 | 139,165,696 |
| 480 | 3.642 | 54,509,568 | 507,985,920 |
| 1200 | 9.628 | 135,135,232 | 1,273,233,408 |

另两路并行回放各12证券/11批次，共4.713秒，输入哈希及完整结果相同；不能推导1200证券并发，更不能推导真实全市场长期容量。运行期间另有合成研究进程，本表是本机本次实际负载下的结果。平台受理P95没有样本，仍为null；无真实全市场能力证明。原始结果见[benchmark.json](evidence/next06-07/benchmark.json)。

### 守护、报告、归档与恢复

- `supervise --input .../worker.jsonl --db .../worker-accepted.sqlite3 --plan configs/operations-fixture.json`处理11批次、正常停止、重启0次；异常重启/超时由临时进程和fake测试另验。
- `ops-report`退出码0，记录11个同代码/配置扫描；真实合格切片0、连续真实影子日0，全市场/影子/P95均pending，本地存储预算pass，release_allowed=false。报告见[operations.json](evidence/next06-07/operations.json)。单元测试构造的20日证据仅验证计数逻辑，不作为真实观察记录。
- `archive-scans`只读压缩11行，输入与原结果哈希核对一致，压缩比例0.0361606；源业务数据未删除/裁剪。归档SHA-256为`2e9f72cb5abb9bb5fdd8e84f8a5877524611a1fb5fbdd3652b682dac60aa0297`。
- `backup/restore`均退出码0、完整性检查通过；源与恢复数据库的完整SQL dump逐字一致，含versions/states/scans/signals/events/tags/outbox/feedback和运行证据。核对时有11条scan、8个signal、40个event、30条内置通知、11条运行观察、1次运行、1个故障episode。结果见[CLI恢复核对](evidence/next06-07/cli-recovery.json)。
- 归档只包含输入与原结果哈希，完整状态恢复依赖SQLite备份；保留计划不执行自动删除。前台守护没有安装launchd/systemd，主机休眠、真实网络/跨日恢复及外部故障提醒仍待验收。

### 当前源码打包

在临时源码副本用已有构建工具离线执行`pip wheel --no-index --no-deps --no-build-isolation`，没有新增运行依赖或修改实际data目录。重建的0.1.0 wheel共117,695字节，SHA-256为`11f5fdd1762defdd33b067e5c6ab58e2d6c758e1f873cb60e1b2b7951983e795`。

检查包内21个Python模块、3个静态文件和fixture.json，不含数据库/令牌/JSONL；两份源码fixture配置相同。在仓库外提取wheel并用Python3.9.6隔离导入，默认配置、研究计划校验及独立数据库扫描通过，源码哈希与最终报告一致。未上传或正式发布，产物位置见[wheel核对](evidence/next06-07/wheel.json)。

NEXT06/07的本地工程和合成验收完成；真实授权历史、适用规则/执行/成本、正式参数冻结、含科创板全市场容量/覆盖、真实平台P95、主机恢复和至少20连续真实交易日影子仍未通过。live_alert保持应用入口锁定。

交付前另核对630个原始批次的规范化数据哈希、21份源码清单、持久摘要校验和及各报告代码哈希；全部一致。28份项目Markdown的221个本地链接有效，代码块闭合。审计结果保存于同目录evidence/next06-07/audit.json；本轮没有公开发布操作。

## NEXT08科创板扩展（追加，2026-10-29）

软件验证执行于08:09—08:17 UTC；证据整理于15:59 UTC。环境为macOS、系统Python3.9.6、标准库运行时，临时目录`/private/tmp/stockradar-next08-j89rpp_i`。本次不修改实际data数据库、备份、令牌或research快照，没有真实行情请求/钉钉投递。浏览器服务使用空进程环境和明确的合成令牌，仅监听本机。

最终Python源码哈希：`13891ef8cb62f9b4a41f55b8bc2b4f2f695e6e7f45e691d7b7b451f2a334dbda`；新配置规范化哈希：`3acea021596b47640687a5a6f678d5422571be25dcc7bd306cca7fdc2cb40422`。代码、配置/静态资源、研究、运行、负载及wheel核对见[证据索引](evidence/next08/index.json)，功能与启用方式见[NEXT08说明](next08-star-acceptance.md)。

### 测试及失败事实

- 新增科创板范围/兼容10项、执行4项，共150项；既有NEXT01有效区间、事务、通知、恢复等回归继续保留。原有测试的固定12/4断言和仅修改前4只报价的注入，改为新15/7分母及实际提醒成员，保留原测试目的。
- 初次完整回归在受限环境运行，实际`Ran 133 tests in 48.006s — FAILED (failures=12, errors=1)`：原样例数量/注入范围断言需适配，HTTPTests因沙箱拒绝本地端口初始化失败，3项未执行，不记完整通过。
- 新增专项首轮`Ran 76 tests in 40.831s — FAILED (failures=3)`：旧功能回放提醒数不应按全部episode计、Decimal规范化可能输出科学记数法，以及合股测试没有同步调整显式价格上下限。已修正测试口径/数据，不通过放宽执行约束解决。
- 最终授权临时本地HTTP端口执行`python3 -m unittest discover -s tests -v`，08:09:21 UTC结束，实际`Ran 150 tests in 28.667s — OK`，见[日志](evidence/next08/unittest.log)和[测试元数据](evidence/next08/tests.json)。外部网络/通知全部fake或Mock。
- 使用已有Node执行`node --check stockradar/static/app.js`退出码0，`python3 -m stockradar --help`退出码0；未安装新运行依赖。

### 配置、股票池与兼容性

新配置schema2/id=fixture-v2-star显式提供STAR参数，新样例15个合格对象（3只科创板）、6个排除对象、4个板块。科创板纳入可比成员及覆盖分母；缺SSE.688101的场景仍以15为分母、有效14，暂停后新数据恢复同信号。三只STAR均覆盖预警、确认、偏离、恢复、结构失效及冻结H/ATR/S检查，10%风险不能被评分抵消。

原无schema配置、原样例及11次全部evaluate输出与扩展前golden哈希完全一致，见[兼容结果](evidence/next08/legacy-compatibility.json)。旧库默认继续最后扫描版本，显式选择新版本才切换；同ID不同配置仍拒绝。页面fixture回放按保存配置schema选择数据，旧版early报告4个提醒、新版7个，历史任务结果不改写。

STAR逐规则schema2将最低200股和逐股递增分开，独立验证含费预算、200/201股、限价/市价10万/5万上限、T+1和显式合股后100股全额退出；旧buy_lot格式不得用来声明STAR。核对上交所官方资料的链接与适用日期记录在专项说明；合成规则仍verified=false，实际历史/费用/执行证据没有因此通过。

### 浏览器

内置浏览器、本机18768/18769、独立临时新旧库。新版桌面1102×931显示三板块范围、15/15及7个机会；旧版1280×720显示原范围、12/12及4个机会。初次发现窄侧栏把“科创板”拆字，增加keep-all并重新加载核对；[修复前](evidence/next08/desktop-star-before-wrap.jpg)、[修复后](evidence/next08/desktop-star.jpg)均保留。

390×844科创详情显示代码688101、触发/最新价及时间、冻结H=10、ATR=0.5、S=9.7，保留模拟/分数非概率/反馈不下单语义；document宽度390，无横向溢出。见[详情截图](evidence/next08/mobile-star-detail.jpg)、[旧版范围截图](evidence/next08/desktop-legacy.jpg)及[浏览器记录](evidence/next08/browser.json)。临时视口已重置，创建的标签及服务均已关闭；不代表真机或完整无障碍验收。

### 合成研究、负载与CLI

- 08:13 UTC完成`export-study-fixture --days 30`及`study`：210个切片、15证券，四组每组450次首次提醒、10,800个延迟/窗口/退出模型样本。前3组各180个STAR闭合方案、confirmed为90个，均为构造假设，不能视为独立实际交易。摘要见[研究证据](evidence/next08/study-summary.json)。
- 时间分段各约10合成日，5日存在闭合结果，10/20日仍可能跨段purged或数据未成熟pending；没有以本轮30日宣称成熟20日样本外或参数冻结通过。正式冻结资格始终false。
- 本轮`benchmark --symbols 12 120 --iterations 1 --concurrent-replays 2`，每档仅2次扫描，P95等于最大值：12证券0.094秒、120证券0.876秒。12证券单元含2只STAR；两路完整样例回放各15证券，5.940秒完成，输入及完整结果一致。见[负载报告](evidence/next08/benchmark.json)。扩展前90日/1200证券结果没有作为本轮重测。
- CLI新旧样例导出、supervise、ops-report、archive-scans、backup/restore及旧worker无config重复运行均退出码0。新库11次扫描、14个episode（6个STAR）、70个事件、51条内置通知、11条运行观察；旧库重复输入后仍仅fixture-v1和11次扫描，无静默注册/启用新版本。
- 压缩归档11个输入，SHA-256为`0a2198387a54d7e80648a1d6884a4136ed707faa0cfec6c1cf2a848bd86c13bc`；完整备份恢复SQL dump一致，未删除源业务数据。见[CLI恢复证据](evidence/next08/cli-recovery.json)。
- 当前15证券运行计划报告：真实合格切片0、影子日0、平台P95=null，全市场/影子/P95均pending，release_allowed=false。本地存储预算pass仅说明该临时库文件大小，见[运行报告](evidence/next08/operations.json)。

### 打包与交付边界

当前源码及静态资源在临时副本离线重建0.1.0 wheel，122,047字节，SHA-256为`beea3f27312be1755d98bd029b8e0ff350cacb86af8bf6a0a4a0db1c7657f8ac`。包内21份Python模块、3份静态资源及新旧配置模板均存在，无数据库/令牌/JSONL。Python3.9在仓库外隔离导入/扫描，新旧模板分别得到15/12分母；配置与包内副本逐字相同。见[wheel核对](evidence/next08/wheel.json)。未上传包索引或正式发布。

NEXT08工程与合成验收完成，旧历史证据保持原口径；真实授权历史、适用规则/执行/成本、含科创板全市场覆盖/容量、正式参数冻结、平台时延、主机恢复及连续真实影子仍归NEXT03/04/06/07。live_alert保持锁定。

16:03 UTC交付审计：30份源码/配置/静态资源及14份持久摘要校验和匹配，210个原始研究批次的规范化哈希与报告一致；29份项目Markdown的249个本地链接有效，代码块闭合，所有本轮报告代码哈希一致。结果保存为evidence/next08/audit.json；收尾只更新文档，没有把08:09的测试重记为新执行。

## NEXT04本地模拟投递生命周期（追加，2026-10-29）

本轮在macOS、Python3.9.6标准库运行时完成，仅使用临时SQLite、合成行情及fake/local通知；原始产物在`/private/tmp/stockradar-next04-zdgu5u0z`。未修改实际data数据库/备份/令牌或research来源快照，没有真实行情请求、钉钉发送或生产发布。浏览器服务以独立空凭据环境、明确的测试令牌启动，仅监听127.0.0.1；验收页和服务均已关闭。

最终Python源码哈希为`4d2d3435625aa05454eb6dc03941690410dc47cd919c0efee4f7cc73e23b361f`，计划哈希为`d06e2ef4a6316f791d67def9bb608a58e2db5d7de7199d97569b9ec8b152cac4`；策略配置未变，规范化哈希仍为`3acea021596b47640687a5a6f678d5422571be25dcc7bd306cca7fdc2cb40422`。完整字段、时钟/恢复约束及命令见[NEXT04说明](next04-dispatch-lifecycle.md)，持久摘要见[证据索引](evidence/next04/index.json)。

### 测试、边界与失败事实

- 新增23项生命周期测试，覆盖扫描/事件/内置/模拟队列/时钟水位原子回滚、重复输入不补投、4.999/5秒窗口、持久30秒退避、59.999/60秒请求限额、计划/模式/schema/时钟校验、版本与渠道隔离、unknown及永久失败终态。
- 真实临时子进程在本地模拟器阻塞时被强杀，第二进程在恢复前因flock失败；进程结束后7个sending成员恢复unknown，未重发，旧运行标记interrupted。另验后台数据库故障、发送期间扫描可提交、停止超时保留所有权、结束后不领取新请求以及无新扫描时窗口自动到期。
- 初次py_compile遇到测试文件多行with语法错误及系统字节码缓存目录拒绝写入；修正语法，测试使用PYTHONDONTWRITEBYTECODE，不把该检查记通过。首轮20项调度测试5.357秒，1失败/1错误：Decimal与浮点下界比较导致0.05秒被拒绝、测试路径未按macOS规范化为/private前缀；分别修正边界实现与断言。
- 新增专项23项于6.811秒通过，之后强化停止后不再领取的断言；最终完整回归实际执行于17:08:38—17:09:11 UTC，`Ran 173 tests in 32.677s — OK`，见[完整日志](evidence/next04/unittest.log)及[元数据](evidence/next04/tests.json)。临时本地HTTP端口经授权运行，真实外部网络均fake/mock。
- PATH未提供node（退出127），使用已安装的bundled Node执行app.js语法检查退出0；CLI帮助退出0。没有安装新运行依赖。

### CLI、时钟和恢复

17:09:38—17:09:53 UTC，在无通知/行情凭据的子进程环境实际运行export-fixture、worker、dispatcher、dispatch-report、supervise、ops-report、backup和restore；见[命令与逐表恢复记录](evidence/next04/cli-acceptance.json)。

- 明确选择simulated时钟和本地传输，前两个原始合成切片产生7条本地接受通知，固定5秒窗口后合并为1次调用。原模拟标记保持true，真实外部outbox六种状态均0；模拟回执不表述为平台受理。
- 独立dispatcher --once重启、worker重复输入后仍7条/1次请求，不补投历史；同名报告输出拒绝覆盖，缺--simulation及transport=dingtalk计划被拒绝。报告目标须新路径，真实transport不能从CLI选通。
- 全11切片当次49条模拟通知：21接受、28取消、21次调用，无pending/sending；快速输入与调度线程交错会影响具体接受/取消数量，不能当成固定策略基准或真实吞吐。报告保留取消原因和原事件时间。
- supervise实际子进程按显式计划处理前两个切片，7条本地接受/1次调用。ops-report真实请求数0、平台P95=null、真实影子门槛pending、release_allowed=false；[模拟报告](evidence/next04/first-two-report.json)的平台P95也始终null。
- 完整SQLite backup/restore的全部非系统业务/运行/调度表行数与规范化内容哈希一致，含不可变计划、运行及事务时钟水位。恢复库报告仍7条接受；源记录未删除/裁剪，unknown不自动重发。

逻辑/墙钟时间对用于跨重启恢复，停机时间不会延长原窗口或重置退避；扫描提交后但回调前中断也保留水位。模拟窗口、限流与逻辑时钟行为不证明实际平台时延，原行情时点从未改成墙钟来伪装新鲜数据。

### 页面与打包

桌面1280×720内置浏览器，临时服务8876/独立演练库。登录后通知中心明确显示“本地投递演练 / 模拟器已记录”，背景仍提示真实机会推送未启用；无横向溢出、无控制台错误。见[页面记录](evidence/next04/browser.json)和[截图](evidence/next04/desktop-simulation.jpg)。本轮只检查相关标签，未重新执行手机尺寸、真机、全页面或完整无障碍验收。

17:12:47 UTC完成临时源码副本离线构建0.1.0 wheel，131,896字节，SHA-256为`6084c7b46aebe3cab3efd5e77c3f1b605699e5317d40e501307883cd90dab85e`。22份Python模块、3份静态资源及2配置模板与源码逐字匹配，无数据库/令牌/JSONL；计划文件是源码样例，安装用户另存完整计划。

仓库外Python3.9隔离导入原v1和新v2配置/样例，分母12/15，本地接受4/7且各1次调用；源码哈希与完整测试及报告一致，见[wheel核对](evidence/next04/wheel.json)。未上传或发布，软件版本仍是未发布的0.1.0源码。

本轮未重跑NEXT06/07或NEXT08的研究、大规模负载和连续运行；历次结果保留原日期。NEXT04本地模拟生命周期完成，真实目标群PoC、真实机会渠道接线/时延及unknown人工核对继续待验收；NEXT03数据、NEXT06正式冻结、NEXT07全市场/主机恢复/至少20连续交易日真实影子等门槛不变，live_alert锁定。

17:20 UTC收尾审计：32份源码/配置/静态资源、12份持久产物校验和及6份报告输出哈希匹配；30份项目Markdown的275个本地链接有效，代码块闭合，新旧fixture模板均同步。结果见[审计记录](evidence/next04/audit.json)。收尾只更新文档与证据索引，未将17:09的完整回归记作再次执行。

## 0.2.0 四项改进（2026-10-29当地日期；2026-10-30 UTC执行）

用户确认推进可信数据、真实提醒、直观证据及真实效果四项；本轮实际交付为本地接入/连接验收工具、原快照K线和页面独立成本研究。具体范围与命令见[四项改进](four-priorities.md)，当前真实验收仍未完成。环境为macOS、Python3.9.6标准库、Node24.22.1；临时根目录`/private/tmp/stockradar-four-priorities-41vgg9c3`。未修改实际data数据库/备份/令牌、原fixture配置或research来源快照，没有真实行情请求、钉钉群发送或生产发布。

最终Python源码哈希为`048cc04bd63522c6aee522afb03eddbf9c31b3e1c2f9b4f7cbc877984841cc32`；策略及历史配置未改写。完整测试资源清单、CLI、研究、wheel及最终浏览器导出均核对当前代码，见[证据索引](evidence/four-priorities/index.json)。原NEXT04的173项和更早研究/负载保持原日期，不记作本轮重跑。

### 自动测试与先前失败

- 最终完整执行于`2026-10-30T04:19:29.280558+00:00`至`04:20:26.210007+00:00`，`Ran 197 tests in 56.785s — OK`。相较原173项新增22项数据/图表/连接/研究专项及2项HTTP检查；外部网络全部fake/mock。见[完整日志](evidence/four-priorities/unittest.log)和[元数据](evidence/four-priorities/tests.json)。
- 三个JS模块语法检查、2项Node渲染测试和全部应用/测试Python源文件的Python3.9内存编译通过；Node测试覆盖XSS转义、未知OHLC/收益及分段分母，不代替浏览器实测。见[Node记录](evidence/four-priorities/node.json)。
- 最初py_compile被系统缓存目录权限拦截，经授权使用临时缓存复查；首次完整测试在沙箱实际执行189项后因HTTPTests绑定临时端口失败，4项HTTP未执行，不能算完整通过。
- 获得本地端口授权后，先有193项43.257秒通过；修复刷新位置/焦点后193项44.074秒通过；修复导出后194项44.133秒通过。随后新增研究列表隔离及计算中代码变化两项回归，后196项51.094秒通过；最后补充原触发快照优先于延后提醒快照的边界回归，执行上述最终197项。各次时间和先前受阻事实见[迭代记录](evidence/four-priorities/earlier-checks.json)。

### 数据与连接PoC

- 独立CLI读取前两个正常合成切片，provider样本状态为`sample_checked`；读取完整11切片时保留断源失败，状态`incomplete`。声明能力和样本字段存在分别记录，未知授权/外部分母、缺历史、重复/冲突均有专项覆盖；`full_market_verified`、`release_allowed`始终false。见[正常样本](evidence/four-priorities/provider-clean-sample.json)和[含故障样本](evidence/four-priorities/provider-fault-sample.json)。
- channel-poc默认得到`not_sent`；在明确清空真实渠道环境后使用显式测试开关，得到`blocked_missing_configuration`，网络请求0；同路径报告再次执行被拒绝。单向目标指纹、旧无指纹记录不验证新目标、unknown不重试均用fake验证，没有发送真实消息。见[未发送报告](evidence/four-priorities/channel-preparation.json)、[缺配置报告](evidence/four-priorities/channel-missing-config.json)。
- 当前进程只核对环境变量是否存在，行情网关/令牌和钉钉地址/加签变量均未配置；未读取或展示任何真实密钥。尚无具体供应商字段映射、授权分钟历史或明确测试群，本轮不宣称真实数据/渠道PoC通过。

### 研究、导出及恢复

- 最终代码在CLI和页面分别独立运行30日210切片合成研究，四组各450条提醒、10800个假设样本；完整计划、数据和输出哈希相同。计划哈希`d8afc31cbb57a3438797ff2aa78c85caf3276d52ec5f3185bc7aa913ef8f083b`，数据哈希`4a71a099faccce7eb44cfaacc570e3baa748766a98939510dddaa0e230d5c68e`，完整输出哈希`adf6ae2a88ca8d5a2238d99ad7bc11ea791f7c319e3c7477c74cfda617f20de0`。这只是确定性工程复现，不是四组真实投资效果比较。
- 页面切换测试段、反应延迟、20日窗口和风险退出后，未成熟结果保持待定，收益/区间显示未知；确认组未成交单独统计，不填0。正式冻结资格始终false，包含合成数据、未核验规则/费用和缺真实路径/影子证据。
- 首次浏览器下载对解析后的对象再次JSON.stringify，部分浮点零转为整数零，原输出哈希复算失败；保留[失败记录](evidence/four-priorities/export-before-fix.json)。修复为鉴权读取服务端完整报告JSON原文；未完成任务导出409，完整导出不经过浏览器重序列化。
- 最终页面导出的21,181,101字节文件重新解析后可复算原输出哈希，且匹配独立CLI与当前代码。文件SHA-256为`ec1d696d9194d81ecb378b070f913c0a148d4866bbcb9f55675d7fffc20a42a5`，位置与结果见[下载核对](evidence/four-priorities/download.json)。详情投影不含原样本，其内容不能用于复算完整输出哈希。
- 研究不改变实时信号；同一临时库的全部非系统表backup/restore后规范内容哈希一致，包含完整study任务/报告。输入文件在提交后变化、计算中代码变化显式失败；修改计划文件不改写已提交计划；回放列表按类型先筛选，不读取或被101条study结果挤占。见[CLI/恢复证据](evidence/four-priorities/cli-acceptance.json)。

### 浏览器与图表

- 浏览器最初返回Work本地浏览器关闭及Mac锁定，未绕过设置。用户确认授权并开启后，在内置浏览器完成1280×800、390×844、320×780的新增图表与成本研究区域验收；服务仅监听本机53578端口，使用独立合成库、明确的本地测试令牌和空真实渠道环境。完成后已关闭测试页、重置视口并停止服务。
- 模拟科创1从10:01切片推进到10:02后，触发价/时间仍10.12/10:01，最新价/时间为10.30/10:02；触发图保持6点，最新图为7点，H=10.00、S=9.70未改变。来源、接收/可见时间、修订和未展示原因可核对；未补缺失K线，柱形明确为累计成交额。
- 390/320px下，图表容器分别346/276px、内部480px；研究表容器分别324/254px、内部850px。页面及侧栏无整体横向溢出；图表ArrowRight键可横移，Enter打开、Esc关闭后焦点返回原信号行。后台刷新位置保留核对跨173.784秒，79→80px为滚动动画收敛，差异≤1px且焦点仍在图表。该检查不代表完整无障碍认证。
- 最终控制台无警告/错误。见[浏览器记录](evidence/four-priorities/browser.json)、[桌面图表](evidence/four-priorities/desktop-chart.jpg)、[桌面研究](evidence/four-priorities/desktop-study.jpg)、[390px图表](evidence/four-priorities/mobile-chart-390.jpg)、[390px研究](evidence/four-priorities/mobile-study-390.jpg)及对应320px截图。真机、读屏、其他浏览器与完整对比度仍待验收。

### wheel与限制

`2026-10-30T04:21:19.568880+00:00`在临时源码副本使用已安装setuptools84.1.0离线重建`stockradar-0.2.0-py3-none-any.whl`，149,249字节，SHA-256 `1c56e7ece5c2fc1cf0bfca450a9559395d3c0e8aee653e6ded0d7df1a19727ab`。25份Python模块、5份静态资源和2份配置模板与最终197项测试资源清单逐字匹配，无数据库/令牌/JSONL。仓库外Python3.9隔离导入，新旧配置分母12/15、触发图均有6个完成分钟；两组fixture模板继续同步。见[wheel核对](evidence/four-priorities/wheel.json)。未上传或发布，未新增运行依赖。

本轮没有重跑真实/全市场负载或连续影子；30日合成研究、样本PoC、单次连接工具及浏览器视口都不替代授权历史、真实成本/执行、目标群消息呈现/恢复、平台P95或至少20个交易日的真实影子证据。具体供应商适配、真实机会渠道接线、正式参数冻结及生产发布仍未完成，live_alert保持锁定。

`2026-10-30T05:16:39.607286+00:00`收尾审计：55份项目Markdown的417个本地链接有效，代码块闭合；32份应用资源匹配最终197项测试清单，新旧fixture模板一致，CLI/页面完整报告及wheel源码哈希一致。当前进程四项行情/钉钉环境变量仍均未配置。见[审计记录](evidence/four-priorities/audit.json)。收尾只更新文档与证据索引，不把上述完整回归记作再次执行。

## NEXT11 · Impeccable界面优化（2026-10-30 UTC）

使用Impeccable 4.8.0的context、polish/Operate与craft-floor打磨现有0.2.0界面：统一字号/语义色/控件/焦点，模式条增加完整北京时间行情时点，信号表保留table语义与股票详情按钮并固定首列，保留搜索草稿/滚动/焦点，补齐健康失败重试、离线切页与模态背景隔离。完整范围见[专项记录](ui-polish.md)，持久产物见[索引](evidence/ui-polish/index.json)。

- 最终完整Python实际执行于`2026-10-30T06:14:13.504031+00:00`至`06:15:04.716855+00:00`，`Ran 220 tests in 51.122s — OK`。本轮未新增Python测试，220包含当前仓库已有供应商样本测试；不是把原197项重记为新结果。临时端口经授权，通知/外部请求使用fake/local，见[日志](evidence/ui-polish/unittest.log)及[资源清单](evidence/ui-polish/python.json)。
- 新增9项界面回归，加原2项模块渲染，共11项Node通过。三个ES module语法检查、CLI帮助退出0；初始HTML标签/静态ID与CSS括号检查通过。控制测试使用Node中的DOM桩，不构成浏览器、原生键盘或读屏证据。见[前端记录](evidence/ui-polish/frontend.json)和[日志](evidence/ui-polish/node.log)。
- 选定token的次要文本对比度在白底/页面底为5.29/4.93，状态色对最低4.78，控件边框对白底3.17；仅为源码色值计算，没有声明完整WCAG达标。
- Impeccable检测只执行一次，退出2、5条warning：三处雷达光晕、10px品牌小字、带色抽屉阴影。均修改对应声明，并以源码断言检查；未重复执行检测，不能表述为最终零告警。原始结果见[记录](evidence/ui-polish/detector.json)。
- 首轮220项于06:05:54—06:06:44 UTC、50.577秒通过；随后收尾代码检查发现离线切页可能不同步，补齐路径并新增第9项前端回归后执行上述最终回归。先前结果保留在[迭代记录](evidence/ui-polish/earlier-python.json)。一次样式补丁未匹配目标行，核对顺序后重试成功，未把失败计作验证通过。

浏览器工具返回Mac锁定、Work本地浏览器关闭；用户明确表示暂时无法开启、先完成代码。本次只参照NEXT08桌面与NEXT02手机历史截图，未产生新截图或执行当前样式的桌面/手机/缩放验收。1280/950/768/390/320px、200%缩放、原生键盘、真机与读屏仍待验证，历史结果不迁移到本次样式。

未新增运行依赖，未修改实际data数据库/备份/令牌、策略配置或research来源快照；没有真实行情请求或钉钉群发送。未重建/发布wheel，版本仍为0.2.0源码；真实路径、投资效果与live_alert发布条件保持原边界。收尾仅更新文档与证据，不再重跑或重记上述测试。

收尾[审计](evidence/ui-polish/audit.json)核对33份应用资源仍匹配最终220项回归，五份前端资源及测试文件哈希一致，两组fixture模板一致，本次修改文档的本地链接有效。初次全库检查发现范围外`next03-data-sources.md`的证据README缺失；随后核对时目标文件已存在，该链接通过。本轮未修改该资料档案，先前失败与随后状态保存在[文档检查记录](evidence/ui-polish/earlier-doc-checks.json)。

## NEXT03 · 可信来源与免密原始样本（追加，2026-10-30 UTC）

用户确认尚未配置账户，先完成免密样本和接入准备。软件升至0.2.1，同步两处版本；新增独立vendor-sample、compare-vendor-samples及3份严格计划，未修改策略、标准batch/worker、实际data数据库/令牌或research来源快照。同工作区NEXT11界面变更保留，它的Python/Node/浏览器记录不归并为本次执行。

### 实际请求与结果

- 初探在05:43 UTC向TickFlow免密接口发出6个只读请求，取得5证券当前元数据与25条日线；正式CLI另于`06:06:36.947972`至`06:07:17.848962` UTC发出6请求/保存6响应。证券为600000.SH、000001.SZ、300750.SZ、688981.SH、689009.SH，固定日期2026-10-23—29，均为北京时间标签。初探不计入正式CLI的6次统计，见[索引](evidence/next03-sources-20261030/README.md)与[正式报告](evidence/next03-sources-20261030/tickflow-free/report.json)。
- `06:06:05.410095`至`06:06:36.947925` UTC的公开参考脚本发出腾讯日线5请求、Tushare匿名HTTPS GET 1请求。腾讯只用未复权day序列，25条的100个OHLC字段精确一致，底层数据独立性未核验。Tushare返回HTTP200、JSON错误码40101，说明HTTPS有响应，不表示POST鉴权、账户权限或数据获取通过。
- 原始成交量主板/创业板15条相同，科创板10条约100倍差异；25条仅在“金额为元、量乘100”的假设下得到区间内均价。688981在10月29日284298与28429754，直接乘100仍差46；689009也有尾数差异。保持原值与统一单位null，不隐式修正，见[逐条比较](evidence/next03-sources-20261030/public-reference-comparison.json)。
- `06:07:17.849101`至`06:07:17.967866` UTC实际运行两家账户模板，均0请求/0样本、明确缺凭据/访问依据；随后日线比较为no_overlap、共同样本0，分钟未比较。缺配置不算供应商不支持，也不算双源验收通过。
- 首次读取官方文档遇沙箱DNS限制，获得网络执行授权后对相同地址读取成功。保存[文档URL/哈希](evidence/next03-sources-20261030/docs-index.json)及[字段核对](evidence/next03-sources-20261030/tickflow-field-review.json)，没有关闭TLS、绕过鉴权或安装SDK。

### 软件测试与打包

- 新增23项测试，覆盖精度/未知单位、空响应、字段/重复/截断/越界、限流/重定向/传输异常、凭据回显拒绝落盘、授权/预算/覆盖目录前置、当前成分不回填，以及比较缺样本/文件篡改。
- 完整Python于`2026-10-30T06:07:18.009364+00:00`至`06:08:09.347522+00:00`实际执行，`Ran 220 tests in 51.247s — OK`，Python3.9.6；临时本地HTTP经授权，外部发送用fake/mock。见[完整日志](evidence/next03-sources-20261030/full-tests.log)与[执行元数据](evidence/next03-sources-20261030/verification.json)。CLI帮助及新命令退出0；单独23项不另加到220总数，NEXT11的220是另一执行。
- 运行时代码哈希`75297351891738357bcae9e8a7eedb4678abcf7c8697ee6f42138bd52dd6aeb5`与正式采集、隔离包一致；全部报告strategy_input_ready/full_market_verified/release_allowed=false。
- `06:17:30.694737` UTC用已有setuptools84.1.0在临时源码副本离线构建0.2.1 wheel，160820字节，SHA-256为`87a27165b2345437cb6c91144d4b98be60464641e0427ac588db3e76c31c1cba`。26模块/5静态资源/2模板与当时工作区逐字匹配，没有数据库/令牌/原始行情/计划混入包；Python3.9仓库外新旧分母12/15、图表各6分钟及vendor-sample缺配置0请求通过，见[打包记录](evidence/next03-sources-20261030/wheel.json)。未上传/发布。

NEXT03未修改UI或执行浏览器/Node/合成负载/长期研究。0.2.1包包含同期NEXT11源码，仍缺该界面的新视觉验收；原截图不迁移。本轮无真实群消息、账户注册/购买或分钟/历史成员样本，未证明全市场、历史可见性、投资效果、连续影子或live_alert发布通过。操作与单位/分钟权限/历史成分缺口见[来源与样本](next03-data-sources.md)。

收尾[核对](evidence/next03-sources-20261030/audit.json)检查39份源码/配置/测试资源、原始/派生报告哈希、当前wheel资源、新旧fixture和维护文档链接/代码块一致。初次全库检查的4个上游快照相对链接指向未归档文件，原始结果另存，最终明确排除不可改写的来源快照；没有修改research来修复它们。收尾仅同步文档与证据，不把06:07的完整回归重记为新执行。

## NEXT03 · 分钟诊断与零请求准备（0.2.2，2026-10-30 UTC）

用户确认尚未开通账户，先完成诊断工具和采样准备。新增vendor-sample --dry-run、minute-quality、两份三板块窄范围采样计划和严格口径/日历模板。诊断只读样本并保留原始哈希与重复/修订，时间/时区和单位未知时不对齐或换算；本地检查通过也不生成标准batch或解除发布锁。版本两处同步0.2.2，无新增运行依赖。完整范围见[使用说明](next03-minute-quality.md)及[证据索引](evidence/next03-minute-prep-20261030/README.md)。

- 新增30项分钟准备/诊断测试；原23项供应商样本定向检查也通过。最终完整Python实际执行于`2026-10-30T18:06:55.677922+00:00`至`18:07:46.656119+00:00`，`Ran 250 tests in 50.718s — OK`，Python3.9.6。源码/配置/测试资源在执行期间不变，见[日志](evidence/next03-minute-prep-20261030/python-final.log)和[清单](evidence/next03-minute-prep-20261030/python-final.json)。临时本地HTTP经授权，外部传输用fake/mock，进程不带供应商或钉钉凭据。
- 首次完整回归于`17:39:42.434088`至`17:41:20.235283` UTC执行，`Ran 245 tests in 97.535s — FAILED (errors=1)`；HTTPTests的setUpClass因沙箱禁止绑定临时127.0.0.1端口失败，5项HTTP测试未执行。失败[日志](evidence/next03-minute-prep-20261030/python-sandbox.log)及[元数据](evidence/next03-minute-prep-20261030/python-sandbox.json)保留，不计为通过；获得执行授权后才进行上述最终完整回归。
- `18:10:06.413314`至`18:10:07.424584` UTC实际运行CLI帮助、两份dry-run及无样本报告；TickFlow/Tushare计划9/7请求，实际均0，明确缺凭据/授权。读取既有真实日线目录仍为no_minute_samples，忽略6个非分钟请求，原始/派生文件哈希不变。已有输出及把准备报告当原始样本均拒绝。另保存明确标为simulated的mock修订演示，不视为真实分钟。见[CLI记录](evidence/next03-minute-prep-20261030/cli.json)。
- `18:10:44.990896`至`18:10:45.889301` UTC使用已有Python3.12.14/setuptools84.1.0，在临时源码副本离线构建0.2.2 wheel。27模块/5静态资源/2模板与250项回归资源逐字一致，无数据库、令牌、原始行情或计划混入包；Python3.9仓库外新旧分母12/15、触发图各6分钟、准备0请求及无分钟报告通过。169179字节，SHA-256 `de5b05e80a8884ffa45ffc21d908dce7f936064fd4362cdbe297b673663f5ab3`，见[打包记录](evidence/next03-minute-prep-20261030/wheel.json)，未上传/发布。
- 源码哈希`02ce40964051205896adec60cb6fb4b1fe10dbf5c5281f7537df0cd6e807dc0d`在最终回归、CLI及隔离包之间一致。相关测试覆盖起点/终点与未知时区、日历分母/午休、缺分钟、原始重复及跨采样修订、累计回退、精确单位转换、未知值、哈希/引用遗漏与符号链接、禁止覆盖、代码变化和0请求准备。

本阶段只通过浏览工具阅读官方说明，没有账户开通、购买、真实分钟或群消息。TickFlow分钟页面/OpenAPI未能读取，单位疑点未解决；Tushare文档不证明账户权限。未修改UI、实际data数据库/备份/令牌、research快照或策略配置；未重跑Node/浏览器、长期研究或全市场负载。真实分钟/历史成员/复权、完整batch/shadow、参数冻结、效果及连续影子/生产发布仍待完成，所有策略/全市场/发布标记保持false。收尾文档与文件审计见[核对](evidence/next03-minute-prep-20261030/audit.json)，不把上述完整回归记作再次执行。
## NEXT11补充 · calm任务化工作台（2026-10-31 UTC）

本轮使用calm-workspace-design在0.2.2源码上调整异常/依据/下一步的阅读顺序，压缩概览并前置信号列表，补齐详情定位、未知参与状态和初始请求一致性。具体界面与预览见[说明](calm-workspace.md)，[索引](evidence/calm-workspace-20261031/index.json)独立保存本轮证据。未修改策略/API契约或实际data数据库、备份、令牌与research；没有新增运行依赖或发送真实群消息，未重建wheel。

- 完整Python实际执行于`2026-10-31T13:44:23.957433+00:00`至`13:45:15.671951+00:00`，`Ran 250 tests in 51.428s — OK`；同次运行18项Node、三个ES module语法与CLI帮助退出0。新增7项前端回归，未新增Python测试。见[清单](evidence/calm-workspace-20261031/tests.json)、[Python日志](evidence/calm-workspace-20261031/unittest.log)和[Node日志](evidence/calm-workspace-20261031/node.log)；原220/250项历史结果不重记为本轮。
- 经授权用已安装Chrome156.0.8078.76进行隔离headless自动化，独立合成服务仅监听127.0.0.1，清空真实凭据，使用临时浏览器资料并启用Chromium sandbox。最终执行时间`13:47:40.211—13:47:57.277 UTC`，15组布局与关键任务路径通过，截图14张。常态/偏离/断源来自合成切片；外部unknown=2、模拟unknown=99和503失败是响应注入，只验证展示与恢复，不视为平台回执。见[浏览器记录](evidence/calm-workspace-20261031/browser.json)。
- 概览1440/1280/950/768/390/320px、研究和诊断1440/390/320px、详情390px未见整体横向溢出。表格键盘横移、依据/反馈跳转、13秒后台刷新后的标题焦点、反馈记录、Esc返回、搜索草稿与显式查询、缓存切页和重试恢复通过。页面脚本错误0、未预期控制台警告/错误0；503注入有1条预期HTTP错误日志。
- 初次前端检查的2处旧结构断言和新增测试字符串转义错误分别修正；初始渲染捕获的部分请求混显已补加载状态与回归。浏览器两次过早断言分别改为等待原生滚动和hashchange渲染完成，先前结果保留；截图等待稳定绘制，暂停截图另补拍稳定状态。详见[迭代记录](evidence/calm-workspace-20261031/iterations.json)，没有把失败记为通过。

本轮补验当前calm样式，不倒填NEXT11初轮的浏览器限制。真机/软键盘/安全区、读屏、200%浏览器缩放、其他浏览器与完整无障碍仍待验。没有真实行情/通知、全市场或投资效果验证，live_alert继续锁定。

## NEXT03 · 免费公开接口有界PoC（0.2.3，2026-10-31 UTC）

用户明确要求开始验证免费来源。新增固定匿名HTTPS新浪分钟、东方财富当前报价/板块关联/ST/停复牌/近期分钟、腾讯未复权日线，复用vendor-sample与minute-quality。使用Python标准库，未安装AKShare/efinance或新增运行依赖；两处软件版本同步0.2.3。范围、命令和缺口见[使用说明](next03-public-poc.md)，原始/派生/脚本见[证据索引](evidence/next03-public-20261031/README.md)。

- 沙箱阶段`17:37:56.298351—17:37:56.722059 UTC`分别向三来源尝试1次，均DNS失败、无HTTP响应；在获得相同公开只读操作的网络执行授权后，正式阶段于`17:38:13.178573—17:39:23.604757 UTC`实际14次请求尝试、保存13个HTTP200响应。两阶段分开留证，不将失败记为成功；固定预算最多15次、间隔至少6.1秒、无自动重试/换源/分页/TLS降级。
- 新浪3证券各240条，共720分钟；每只10月29日尾部2条、30日238条，不能称当天240个完整分钟。东方财富取得3报价、94条当前板块关联、ST首页100/392、9条指定日期停复牌及主板5日1205条分钟；历史4日964个open=0投影null并保留原值。创业板分钟连接失败后停止，科创板该项未请求；这些缺口不假装完整或非ST。
- 腾讯15条未复权day日线；与旧TickFlow的12条重叠记录48个OHLC字段精确一致。新浪30日已有记录聚合出的12个日OHLC字段也与腾讯一致，仍不证明交易日完整。新浪/东方财富仅240个共同原始标签，753个价格字段同、205个不同、2个open未知；标签/闭合语义未知，不称合格完成分钟双源验收，不自动移位/乘100。量额单位保持null，底层源独立性未核验。
- 初次minute-quality只选29—30日，另含东方财富26—28日导致DATE_OUTSIDE_DIAGNOSTIC_WINDOW，原报告保留。随后以完整26—30日窗口另存[主报告](evidence/next03-public-20261031/minute-quality-window.json)：1925条观测、issues_found、11类原因；日历/时区/完成性/单位未知，覆盖率和canonical end为null，双源blocked_semantics。
- 新增20项公开边界测试。完整Python于`17:41:49.000030—17:42:40.239009 UTC`实际执行，`Ran 270 tests in 50.987s — OK`，Python3.9.6；69份源码/配置/测试资源在执行期间不变。测试使用fake/mock及临时本地HTTP，不向真实行情或群发送。单独定向检查不叠加到270总数，历史220/250/Node/浏览器结果不重记为本次。
- 真实采集代码哈希为`7a7585d872292b13619c5254c9fb8b563fe05dcc49fb7b15506aeb691e805c5c`；之后补齐畸形数值异常捕获。最终回归/CLI/包代码哈希为`860152e92238b65f492a1667b3c108430aaf3ca69da0bf1a4d6ada1954163dbd`。最终解析器从原始字节与原接收时间逐条重建1940条分钟/日线，全部与原投影相同；原采集报告不改哈希。
- `17:49:51.720511—17:49:52.824321 UTC`实际执行CLI帮助、3份默认公开计划dry-run及已有目录拒绝。预算3/9/3，实际全部0请求；缺访问确认明确blocked_configuration，已有文件哈希不变，见[CLI记录](evidence/next03-public-20261031/cli.json)。
- `17:49:51.733875—17:49:52.772552 UTC`使用已有Python3.12.14/setuptools84.1.0在临时源码副本离线构建0.2.3 wheel，175985字节，SHA-256为`241042a29a8a5642a12c92e436e48e9f92e25c676c81394ae35003e1ed6c95c1`。28模块/5静态/2fixture匹配270项回归资源；Python3.9仓库外新旧分母12/15、触发图各6分钟、公开准备0请求及1925条原始重解析通过，见[打包记录](evidence/next03-public-20261031/wheel.json)，未上传/发布。

本次未修改界面源码/运行策略、实际data数据库/备份/令牌或research快照；页面继续原模拟数据，未重跑Node、浏览器、长期研究/全市场负载，也无真实群消息、账户注册或购买。分钟语义/单位、完整风险和成员分母、历史有效性/复权/基准及标准batch仍待核验，所有策略输入/双源/全市场/发布就绪标记为false，live_alert锁定。

收尾[审计](evidence/next03-public-20261031/audit.json)核对回归/包资源、样本原始哈希、fixture、文档链接和修改范围。初次检查因audit.json尚未写出而有1个自引用链接缺失，[初次结果](evidence/next03-public-20261031/audit-initial.json)保留，文件写出后的最终文档核对另存；纯证据与文档收尾没有重跑或重记上述完整测试。



## 2026-11-05 · 0.2.4 连接配置与Fuyao零请求准备

按用户确认，尚未取得Fuyao Key，先完成适配器与零请求准备；同时新增独立行情API与模型配置页。模型只查目录，不接评分/风险/通知。

- 最终完整304项Python（新增34项）于17:01:26—17:02:20 UTC通过；22项Node（新增4项）、两份JS语法及CLI帮助随后通过。源码哈希在执行前后保持一致，记录见[本轮自动检查](evidence/connection-settings-20261105/verification.json)。此前270/301项和环境PATH缺Node的检查不冒充这次最终执行。
- Fuyao三板块模板实际12个计划请求、0次发送，缺Key/访问依据；[准备报告](evidence/connection-settings-20261105/fuyao-preparation.json)保留false发布标记。
- 独立临时合成数据库及内置浏览器验证两页320/390/768/1280宽度、保存后Key不回显、未确认访问不测试、清除本地Key、未保存输入刷新保留和错误恢复。本机假模型目录可达仅验证目录路径，无真实模型生成。参见[页面记录](evidence/connection-settings-20261105/browser.json)与[桌面视图](evidence/connection-settings-20261105/desktop-views.json)；未做真机、读屏或其他浏览器检查。
- 临时源码副本离线构建wheel，30个Python模块、6个静态文件和两份fixture逐字核对；仓库外Python3.9新旧分母12/15、只读连接及Fuyao CLI零请求通过，见[包核对](evidence/connection-settings-20261105/wheel.json)。未上传或发布，未修改实际data/research。

使用说明见[连接配置](connection-settings.md)。真实Fuyao权限/数据质量、模型推理和AI解释、全市场/连续影子与真实机会通知继续待验，live_alert锁定。

## 2026-11-08 UTC · Fuyao首轮12请求采样（0.2.4）

用户已自行创建并在本机配置Key，页面单次报价连接检查成功；之后在会话中独立确认三只证券、11月2—4日日线及当前资料的12请求计划。确认前[零请求准备](evidence/fuyao-preparation-20261108/report.json)实际0发送，仅缺计划确认；[连接观察](evidence/fuyao-preparation-20261108/connection-state.json)只保存脱敏状态，未重发页面的1次报价检查。

- 实采于`2026-11-08T07:45:00.599364+00:00`至`07:46:08.948202+00:00`执行；12请求、9成功，取得9条未复权日线、3条报价、3日历日期、3证券资料、710条概念/行业目录和76条当前关系。三只公司行为均HTTP200/业务码3002，整体`incomplete`，无自动重试或换源。见[报告](evidence/fuyao-poc-20261108/report.json)与[范围/限制](next03-fuyao-poc.md)。
- 离线分析验证原报告/计划及11份原始、派生文件哈希。9条日线无请求组合缺失/外来/重复，OHLC正值与区间关系通过，文档单位假设下的均价处于高低区间。此检查不证明单位独立核验、历史可见性、逐股报价时间或历史关系；已有参考日期无重叠。脚本与结果见[证据目录](evidence/fuyao-poc-20261108/README.md)，离线分析0网络请求。
- 运行时代码未修改，采集代码哈希为`b019476a8284ae1f95d521de9165ec461cb80258a0ae7d5a7d6a4e430d902d32`。本轮未重跑Python单元测试、Node、浏览器或wheel，11月5日304/22项结果不重记；仅新增计划、实际样本、离线分析及维护文档。

观势仍为fixture，原始样本未写入运行行情。公司行为3002、同日期跨源、完成分钟、历史风险/成员、全市场与连续影子仍待验；所有策略/双源/发布标记保持false，未发送真实群消息。

## 2026-11-08 UTC · Tushare分钟获取与查看（0.2.5）

用户选择Tushare并自行开通分钟权限。本轮新增rt_min_daily和独立分钟页面，复用rt_min/stk_mins、连接存储及原始采样器；显式1—3股请求、0请求准备、独占文件锁/60秒间隔、原始哈希与只读投影，未送入运行策略。见[使用与限制](tushare-minute-feed.md)。

- 完整321项Python于`08:20:02.693444—08:20:59.819919 UTC`通过（321 tests in 57.010s）；29项Node和CLI随后通过。新增17项Python、7项前端检查；执行期间资源/源码不变，见[执行清单](evidence/tushare-minute-20261108/verification.json)。首轮12项定向检查有1项错误，涉及敏感响应被抑制后仍继续请求；修复为整轮停止，并分开权限/回显边界后13项定向及上述完整回归通过。
- `08:21:31.225—08:21:46.156 UTC`使用独立临时数据库、合成Token、fake Tushare和本机Chrome检查配置清空Key、3股模拟图表、历史模式重置确认、0请求预算、12秒草稿保留和503恢复。320/390/768/1280宽度无页面整体横向溢出，页面错误0；真实外网请求0。后补稳定顶部/记录截图，见[浏览器记录](evidence/tushare-minute-20261108/browser.json)及[证据索引](evidence/tushare-minute-20261108/README.md)。
- 临时源码离线构建0.2.5 wheel，31模块、7静态、2fixture逐字匹配；Python3.9仓库外加载新旧配置、缺凭据0请求及无分钟记录通过，未上传/发布，见[包核对](evidence/tushare-minute-20261108/wheel.json)。
- [本机准备报告](evidence/tushare-minute-20261108/preparation.json)计划最新分钟批量1次、实际0次，缺Tushare Token及访问确认。本轮所有服务商、模型、通知请求均为0，模拟页面不作为账户权限/分钟语义验收。

真实账户实采、代码列/标签起止、量额累计、历史可见性与标准batch继续待验。Fuyao先前12次真实请求及历史304/22项记录保留原日期，不重记为这次执行；策略仍fixture，live_alert锁定。

## 2026-11-10 · 工作台证据回看（0.2.6）

新增数据源健康、热点阶段时间线、研究策略卡和案例。326 项 Python、31 项 Node、CLI、四档 Chrome 视口及 0.2.6 wheel 仓库外核对通过。Chrome 使用隔离的合成行情、模拟采样和显式假设成本。另在临时目录读取 5 份旧实采报告、16 个接口，本次服务商请求为 0。真实分钟权限、标准行情批次及发布待验收。 [实际执行与截图](evidence/history-workbench-20261110/README.md)

## 2026-11-13真实行情小目标

本轮352项Python、33项Node通过；Fuyao两轮共4请求成功，第二轮从浏览器获取目标3股报价与15条日线。1280/390/320 Chrome实测及最终只读复核通过，详见[本轮独立证据](evidence/real-market-20261113/README.md)。逐股行情时间未知，未进入策略、未发通知、未构建wheel。
