# 项目构建与部署说明

本手册对应当前CLI和服务实现。默认离线模拟，完整数据契约见[接入说明](development/data-contract.md)，功能边界见[当前进度](../TODO.md)。

## 部署范围

当前已验证源码直接运行、本地wheel及前台有界worker守护，不含Docker、云部署、OS开机自启或CI自动发布配置。服务仅绑定127.0.0.1，Host/Origin校验也按本机地址设计；直接加远程代理或假设存在--host参数不是已支持的部署方式。

页面服务与数据worker需分别运行。下面的shadow命令只说明代码接口，真实服务商、授权和连续运行尚未验证。受控提醒仍锁定，软件构建成功不表示满足真实发布条件。

## 本地启动与登录

Python3.9+，从项目根目录直接运行，无需安装第三方运行依赖：

```sh
python3 -m stockradar serve --port 8765
```

访问 <http://127.0.0.1:8765>，粘贴启动终端显示的令牌。服务只绑定本机，不支持通过`--host`对外监听。停止使用Ctrl+C。

未设置`STOCKRADAR_TOKEN`时，在数据库所在目录生成`.api-token`，默认是`data/.api-token`，文件权限0600。若已设置环境变量，则以变量为准，不会另生成令牌。浏览器只在sessionStorage保存当前令牌，链接不带令牌。

首次启动默认加载前两个合成切片，已有记录时恢复原状态。使用`--empty`可禁止自动加载，后续手动推进。页面“推进一分钟”每次处理下一个样例切片；“重置演示”删除当前fixture版本的信号、通知、反馈、水位及扫描记录，保留策略版本和研究任务。

新库默认fixture-v2-star，包含科创板的15个合格样例。已有库默认继续最后扫描的配置，即使已保存新版本也不自动切换；没有扫描且有多个配置时须明确选择。使用新库启用科创板：

```sh
python3 -m stockradar serve --config configs/fixture.json --db data/star-demo.sqlite3
```

原v1配置保存在configs/fixture-v1.json，`export-fixture --fixture-version 1`可导出原样例。不要把新参数写回旧ID，也不要用重置演示来迁移真实数据；新旧格式与验证见[NEXT08说明](development/next08-star-acceptance.md)。

## 模式和进程

| 模式 | 当前行为 |
|---|---|
| `fixture` | 默认合成演示；拒绝未标记模拟的真实输入 |
| `replay` | 独立研究任务使用同一策略；模拟与真实数据不能混入同一次回放 |
| `shadow` | experimental配置下计算并保存真实输入，不向外部投递机会；接口具备，实际数据路径未验收 |
| `live_alert` | 应用明确拒绝启动；不是通过修改JSON就可使用的功能 |

`serve`负责页面/API，`worker`负责采集或录制扫描。两个进程使用同一数据库和相同配置版本才能看到同一运行结果。关闭浏览器不影响worker；仅启动serve不会开始真实采集。不同模式/实验建议使用不同数据库。

## 环境变量

变量名示例见[.env.example](../.env.example)。程序不自动加载`.env`，须在启动进程的环境中设置。

| 变量 | 当前用途 |
|---|---|
| `STOCKRADAR_TOKEN` | 可选固定访问令牌，至少24字符；优先于本地令牌文件 |
| `DINGTALK_WEBHOOK` | 可选钉钉群机器人官方HTTPS地址；未设置时测试返回未配置 |
| `DINGTALK_SECRET` | 可选加签密钥；机器人启用加签时必须匹配 |
| `STOCKRADAR_PROVIDER_URL` | `worker --http`及`provider-poc --http`使用的标准HTTPS网关，不是内置行情服务商 |
| `STOCKRADAR_PROVIDER_TOKEN` | 网关Bearer凭据，不放在URL或策略JSON中 |
| `TICKFLOW_API_KEY` | 仅vendor-sample的TickFlow完整服务；只入x-api-key请求头，免密服务不读取 |
| `TUSHARE_TOKEN` | 仅vendor-sample；只入固定官方HTTPS POST体，不写入计划/URL/报告 |
| `STOCKRADAR_PUBLIC_URL` | 预留变量；当前应用没有读取或接线，不会自动生成通知详情链接 |

设置钉钉环境变量后重启serve，在“设置与诊断”显式发送测试消息。只配置变量不会自动投递机会。`accepted`只代表平台受理；`unknown`可能已经被平台收到，须先核对群消息，不能将超时当作明确失败重发。

0.2.0另提供`provider-poc`样本报告和`channel-poc`显式连接报告；默认不发送，真实测试须明确测试目标。当前钉钉配置变化后，旧受理不再验证新配置。页面成本研究、自备文件目录、完整计划及报告导出见[四项改进操作](development/four-priorities.md)，研究不会切换运行策略或解除发布锁。

## 行情与模型连接界面

登录后打开“设置与诊断 → 行情 API”或“大模型”，分别管理行情Key/访问依据和兼容模型地址/模型ID/Key。凭据只保存到数据库旁的`.connections`令牌文件，环境变量优先；不进入策略导出或SQLite备份。保存不会切换运行行情，模型检查只取目录，不生成内容。操作、环境变量名称和边界见[连接配置](development/connection-settings.md)。

Fuyao新增固定三板块日线/当前资料计划；尚未取得Key时只执行`vendor-sample --dry-run`，实际0请求。CLI默认读取`data/.connections`；自定义数据库需显式传`--connections-dir`。完整计划、访问依据和请求预算仍独立于页面保存状态。

## 录制与后台扫描

0.2.5增加“设置与诊断 → 分钟行情”：先在行情API选择Tushare保存Token与访问依据，另行开通“A股分钟RT”或“A股历史分钟”，再按1—3只证券检查预算并手动获取。页面轮询只读本机文件，默认不启动自动采集；记录在数据库旁minute-data中，与SQLite/策略分离，备份时需另行保存。步骤、固定接口及未验条件见[分钟接入说明](development/tushare-minute-feed.md)。

0.2.1提供独立`vendor-sample`和`compare-vendor-samples`，免密与账户模板/操作见[可信数据来源](development/next03-data-sources.md)。原始响应和派生诊断保存在显式的新目录，不读写应用数据库，也不能直接交给worker。日期窗口、权限与单位须逐项确认；设置上述两个变量不会自动接入serve或worker。

0.2.2增加`vendor-sample --dry-run`，只保存请求计划、预算和缺配置原因，实际0请求；配置齐全也不表示权限已验收。`minute-quality --plan ... --samples ... --output ...`只读原始样本并输出独立分钟质量报告，省略--samples可查看准备缺口。两份窄范围采样计划、口径/日历模板和后续实采顺序见[分钟诊断与准备](development/next03-minute-quality.md)。0.2.2阶段用户尚无账户，未采真实分钟；这些命令均不会启动shadow或解除live_alert。

```sh
python3 -m stockradar export-fixture --output data/fixture.jsonl
python3 -m stockradar worker --input data/fixture.jsonl --db data/worker-fixture.sqlite3
```

JSONL按记录顺序处理；相同版本、相同快照及内容幂等，重复运行不会重复创建业务事件。同一快照ID内容冲突会报`DATA_CORRECTION`，修订须使用新的快照ID。

真实网关接入的命令形式如下，需事先准备完整experimental shadow配置、环境变量和通过审查的数据路径；这不是当前已完成接入的示例：

```sh
python3 -m stockradar worker --http --once --config data/shadow.json --db data/shadow.sqlite3
python3 -m stockradar worker --http --interval 60 --config data/shadow.json --db data/shadow.sqlite3
python3 -m stockradar serve --config data/shadow.json --db data/shadow.sqlite3
```

`--once`用于只处理一次。轮询间隔至少1秒，429的`Retry-After`会与配置间隔取较大值；实际间隔仍须满足供应商限制。网关故障会写日志和暂停标志，新的成功扫描才会解除；重复旧快照不能假装恢复。

worker在macOS/Linux对数据库旁`.worker.lock`取独占锁，并保存运行心跳、扫描事实及故障/恢复内置通知。前台有界守护和报告示例：

```sh
python3 -m stockradar supervise --input data/fixture.jsonl --db data/worker-fixture.sqlite3 --plan configs/operations-fixture.json
python3 -m stockradar ops-report --db data/worker-fixture.sqlite3 --plan configs/operations-fixture.json --output data/operations-new.json
```

当前运行计划适用于fixture-v2-star的15证券样例；旧12证券计划为configs/operations-fixture-v1.json。目标、版本和退避均须匹配，不能直接把样例当真实计划。HTTP守护另需experimental shadow配置及新计划。守护仅监控自己的子进程，达到失败上限退出，Ctrl+C停止；长退避续写心跳。无真实投递时P95为null，模拟输入不能积累真实影子日，任何报告都不会启用live_alert。完整口径见[运行说明](development/next06-07-local-acceptance.md)。

## 本地模拟投递调度

显式计划可让worker同时启动本地调度线程；无需钉钉环境变量，也不会访问通知网络。使用独立的新演练数据库：

```sh
python3 -m stockradar export-fixture --output data/dispatch-input-new.jsonl
head -n 2 data/dispatch-input-new.jsonl > data/dispatch-first-two-new.jsonl
python3 -m stockradar worker --input data/dispatch-first-two-new.jsonl --db data/dispatch-demo-new.sqlite3 --simulation-dispatch-plan configs/dispatcher-fixture.json
python3 -m stockradar dispatch-report --db data/dispatch-demo-new.sqlite3 --plan configs/dispatcher-fixture.json --output data/dispatch-report-new.json
```

前两个切片产生7条模拟预警，5秒固定窗口后合并为1次本地调用；JSONL结束前最多等待计划指定的6秒，未完成队列保留。页面服务另用同一数据库启动，通知中心显示“本地投递演练 / 模拟器已记录”。完整11个切片快速推进会取消过时修订，调用数量也可能随线程调度而变，不能把它当实时平台时延测试。

重启消费已保存的模拟队列，无需再次导入历史：

```sh
python3 -m stockradar dispatcher --simulation --db data/dispatch-demo-new.sqlite3 --plan configs/dispatcher-fixture.json
python3 -m stockradar dispatcher --simulation --once --db data/dispatch-demo-new.sqlite3 --plan configs/dispatcher-fixture.json
python3 -m stockradar supervise --input data/dispatch-first-two-new.jsonl --db data/dispatch-demo-new.sqlite3 --plan configs/operations-fixture.json --simulation-dispatch-plan configs/dispatcher-fixture.json
```

独立dispatcher按Ctrl+C停止；`--once`只执行一轮，不等待未来窗口。一个数据库只允许一个模拟投递所有者，不能同时启动集成worker与独立dispatcher。相同输入不补投历史，计划同ID内容不可变；修改时另建新ID。源码样例计划不随wheel打包，安装包用户须另存完整计划。

计划明确选择`simulated`时钟用于录制的合成输入，原行情时间不变，重启包含停机经过时间。`wall`计划须另建ID且simulation_start=null，按当前UTC复核；同策略未完成队列不能混用时钟域。只支持本地模拟传输，模拟回执与真实outbox/P95分开；真实机会渠道仍未接线，live_alert锁定。字段、故障处理与证据见[NEXT04说明](development/next04-dispatch-lifecycle.md)。

## 参数版本与回放

默认新配置来自包内stockradar/fixture.json，与configs/fixture.json同步，schema_version=2/id=fixture-v2-star，STAR参数完整必填；历史无schema格式使用包内fixture-v1.json模板，原配置/哈希不变。修改模板或保存新配置不自动切换运行版本。新参数使用新ID，未知键/缺项拒绝，同ID不同内容报VERSION_IMMUTABLE。批次schema_version仍为1，不与配置或逐规则schema混用。

页面创建版本只注册实验，不切换正在运行的版本。真实shadow需`purpose=experimental`且保留板块过滤；不得把fixture阈值直接视为正式策略。

```sh
python3 -m stockradar replay --input data/fixture.jsonl --output data/replay-report.json
```

省略--input时按所选配置schema使用对应内置样例；页面fixture回放也按选定保存版本选择，旧任务不会换成新样例。页面任务用独立进程，CLI直接写JSON报告。其他数据集通过将`<id>.jsonl`放到数据库旁datasets目录供API选择，当前页面没有上传入口。

四组输出、配置/数据/代码/结果哈希和局限均保存在报告中。延迟价格观测、未成熟窗口和成本未配置字段的含义见[验收说明](development/acceptance.md)。

## 显式成本研究与合成负载

`study`提供独立于页面功能回放的四组受控研究，完整计划包括执行/费用/滑点、反应延迟、持有窗、退出、时间分段和自举参数。先在新目录生成合成样例：

```sh
python3 -m stockradar export-study-fixture --output-dir data/study-new --days 90
python3 -m stockradar study --input data/study-new/synthetic.jsonl --plan data/study-new/study-plan.json --output data/study-report-new.json
python3 -m stockradar benchmark --symbols 12 120 480 1200 --iterations 2 --concurrent-replays 2 --output data/load-report-new.json
```

目录和报告必须是新路径；不覆盖既有实验，命令不默认创建业务数据库。90日样例是每日7分钟的构造交易日历，可能运行数分钟且报告较大；其中价格、费用/规则和参数均是合成假设。真实研究必须另建experimental计划，缺可成交性/成本/规则核验时结果pending/null。真实样本外、正式参数冻结及连续影子门槛仍待验收。

benchmark使用临时数据库，记录本机扫描耗时、存储与RSS，最多6000证券是输入上限。NEXT06/07曾测1200证券；本轮含STAR仅重测12/120，12证券负载单元含2只STAR，两路完整样例回放各15证券，不能证明最大规模并发或平台P95。当前结果见[NEXT08说明](development/next08-star-acceptance.md)，原模型见[NEXT06/07](development/next06-07-local-acceptance.md)。

## 备份与恢复

```sh
python3 -m stockradar backup --db data/radar.sqlite3 --output data/radar-backup.sqlite3
python3 -m stockradar restore --input data/radar-backup.sqlite3 --db data/restored.sqlite3
python3 -m stockradar serve --db data/restored.sqlite3
```

备份使用SQLite backup API并检查完整性，目标须不存在。恢复也要求新目标文件；不要覆盖运行中的数据库，也不要仅复制WAL模式下的主文件代替一致性备份。备份包含反馈、快照与通知，但不包括环境变量或`.api-token`，这些需另行保护。

原始输入可按策略版本和UTC截止时点只读压缩归档：

```sh
python3 -m stockradar archive-scans --db data/worker-fixture.sqlite3 --strategy-version fixture-v2-star --before 2027-01-01T00:00:00Z --output data/inputs-new.jsonl.gz
```

同时生成`.manifest.json`，含SHA-256、配置/输入/原结果哈希、行数与压缩比例。目标必须不存在，源业务数据不裁剪或删除；保留天数仅用于运行报告的归档建议。gzip只包含输入与原结果哈希，完整事件/状态恢复仍使用SQLite备份，运行证据表也在该备份内。

恢复的数据库仍保存原通知状态；`unknown`不会自动重发。本地模拟dispatcher取得独占锁后，仅把所选策略/模拟渠道的遗留sending恢复为unknown；不触碰真实渠道。锁文件不包含业务状态，不删除锁文件抢占运行中的进程。真实渠道的独占恢复与人工核对仍待后续接线/验收。

NEXT05的固定窗口、拆分、发送前复核和按请求限流已接入显式模拟调度；普通serve和未指定模拟计划的worker不创建模拟投递队列，修改窗口参数不能启用真实提醒。unknown不自动重发；真实群中需人工核对，模拟unknown仅说明本地结果不确定，不表示平台收到了消息。见[聚合说明](development/next05-notification-aggregation.md)。

## 常见情况

| 情况 | 处理 |
|---|---|
| 端口被占用 | 停止原服务，或用`--port 8766`启动并访问对应地址 |
| 登录401 | 使用当前服务环境中的令牌；检查环境变量是否覆盖本地文件 |
| 覆盖不足/UNKNOWN | 查看诊断原因、缺失对象和最新行情时点；不要用前值或0填充伪装恢复 |
| 策略版本冲突 | 保留旧版本，为新配置使用新ID；必要时使用独立数据库 |
| 钉钉未配置 | 在serve的环境中设置变量并重启，再显式测试 |
| 投递unknown | 先检查群消息与尝试记录，避免不确定投递被重复发送 |
| CURSOR_STALE | 列表已变化，丢弃旧游标，从第一页刷新 |
| 回放pending/failed | pending可能是未成熟评价窗口；任务failed则查任务error，二者含义不同 |

执行测试：`python3 -m unittest discover -s tests -v`。测试需要创建临时本地HTTP端口，使用模拟外部网络，不向真实群发消息。受限环境如需改变字节码缓存，可设置`PYTHONPYCACHEPREFIX=/private/tmp/stockradar-pycache`。过去执行结果保存在[验证记录](development/verification.md)，不表示当前服务一定仍在运行。

0.2.3另提供新浪/东方财富/腾讯的固定公开接口研究计划，默认authorization.confirmed=false，先用--dry-run查看3/9/3请求预算，实际均0请求。公开来源无需账户凭据；显式采样仍须记录访问依据、使用新目录并核对返回窗口、partial及未知单位。计划和minute-quality-public-template.json须从源码另存，不随wheel分发。命令、实际样本与未通过条件见[免费公开PoC](development/next03-public-poc.md)；这些工具不会给页面换成真实行情、启动worker或解除发布锁。

## 构建wheel

构建元数据在`pyproject.toml`，构建后端为setuptools>=61；“无第三方运行依赖”不等于构建后端无需准备。正常构建可由pip创建隔离构建环境：

```sh
python3 -m pip wheel --no-deps --wheel-dir data/wheels .
```

已准备好构建工具的离线环境可使用：

```sh
python3 -m pip wheel --no-index --no-deps --no-build-isolation --wheel-dir data/wheels .
```

当前产物名为`stockradar-0.2.4-py3-none-any.whl`；版本变化时相应改变。常规产物可保存在data/wheels中，不纳入源码。本轮在独立临时目录重建当前源码并用Python3.9隔离导入/扫描/图表，代码与wheel哈希见[验证记录](development/verification.md)；未上传或发布。资源要求见[REGISTRY](REGISTRY.md)。

## 安装和分发

可在隔离Python环境中安装本地wheel：

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install --no-deps data/wheels/stockradar-0.2.4-py3-none-any.whl
python3 -m stockradar serve --port 8765
```

安装后也可使用`stockradar serve`入口。在可写工作目录启动，默认数据保存在该目录data/下；默认配置与静态资源来自安装包，不要求仓库当前目录。若需要修改配置，另存完整JSON并用--config显式传入，不改安装包内模板。

当前没有向PyPI、npm、Sites或公共组件registry发布的执行记录，也没有自动更新服务。分发源码或wheel时同时说明版本、运行模式、验证证据与未完成项；环境凭据、数据库、令牌和研究记录不随安装包分发。

## 运行环境迁移

迁移服务前停止相关写入流程或使用一致性备份，分别保存数据库、所用完整配置和必要的受保护环境配置。环境变量与.api-token不在数据库备份内。新主机首次检查登录、版本/水位、当前模式、数据质量与通知不确定状态，不因迁移而自动开启外部机会发送。

前台守护、合成负载及只读归档已完成本地验收；OS自启、主机休眠与真实网络恢复、目标硬件全市场负载/长期容量和故障外部通知仍在[TODO](../TODO.md)。迁移后的真实影子证据须匹配当前配置、代码、模式及日历，不沿用合成/旧录制作为运行通过证明。
