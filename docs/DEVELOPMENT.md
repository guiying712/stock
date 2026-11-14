# 项目开发和组件发布流程

主协作规范见[AGENTS](../AGENTS.md)，产品边界见[PROJECT-SPEC](PROJECT-SPEC.md)，当前任务统一在[TODO](../TODO.md)维护。

## 开发环境

Python3.9+，源代码运行不要求第三方依赖。前端是静态ES modules，无npm/pnpm安装或开发构建步骤。Node仅可用于可选JavaScript语法检查。系统需要可用的Asia/Shanghai时区数据。

```sh
python3 -m stockradar --help
python3 -m stockradar serve --port 8765
```

浏览器访问本地地址并使用终端令牌；操作细节、环境变量与运行模式见[DEPLOYMENT](DEPLOYMENT.md)。静态资源修改后刷新页面，Python服务代码修改后重启服务；当前没有热更新构建器。

## 实现流程

0.2.7新增[分钟验收工具](development/minute-acceptance-engineering.md)：`minute-acceptance-plan`只生成未授权计划；`minute-quality`兼容schema1/2。相关修改需检查历史语义、阶段/状态分母、无成交规则、整段区间比较和零请求/零凭据准备。

1. 核对需求编号和TODO任务，明确当前实现、目标行为及不在本次范围的内容。
2. 定义或核对输入/输出、未知值和失败语义。数据变更遵守[数据契约](development/data-contract.md)，HTTP变更遵守[API参考](development/api.md)。
3. 在所属模块实现；策略与回放共用路径，保持事务和不可变证据，避免界面推断业务状态。
4. 使用独立临时数据库/合成数据验证，不通过修改用户数据库、令牌或外部群状态完成常规测试。
5. 运行受影响检查，记录实际结果，更新对应文档/任务/验收映射。

## 后端与策略变更

先覆盖关键边界：时间可见性、缺失/乱序/重复、非交易时段、风险硬门槛、冻结参考、版本变化、断源暂停/恢复。交易规则或真实评价新增时，核验适用交易所的官方规则和生效时点，不能从示例推断真实可成交。

事务、通知或鉴权变更关注回滚、重启、并发领取、迟到发送、不确定投递和反馈幂等。完整配置必需字段与未知键规则保持一致，不能静默新增隐藏默认值。

## UI组件变更

沿用现有渲染函数、样式token和Hash路由。增加或调整组件前明确它的输入、状态、API依赖、可访问名称和窄屏表现；流程不是发布独立React组件。

开发后检查数据转义、未知数值、北京时间、加载/失败/暂停/模拟状态和键盘行为。若拆分ES module或增加资源，同步server静态白名单及package-data，并检查wheel确实包含资源。组件登记和分发见[REGISTRY](REGISTRY.md)。

## 验证命令

```sh
python3 -m unittest discover -s tests -v
python3 -m stockradar export-fixture --output data/fixture.jsonl
python3 -m stockradar replay --input data/fixture.jsonl --output data/replay-report.json
```

Node可用时：

```sh
node --check stockradar/static/app.js
```

此前四项改进完整执行197项；NEXT03新增23项供应商样本测试、完整执行220项，NEXT11也对当前220项另作完整执行。两个任务的时间见[验证记录](development/verification.md)，不要合并执行或将历史结果记作新执行。测试需要临时本地HTTP端口，外部网络使用fake/mock。受限环境下可调整PYTHONPYCACHEPREFIX，不能把沙箱拒绝当测试通过。

新增ES module须分别语法检查；Node可用时运行`node --test tests/ui_modules.test.mjs tests/ui_workbench.test.mjs tests/ui_minute.test.mjs`。0.2.5当前共29项；NEXT11初轮原11项与后续18/22项均保留原日期。DOM桩验证转义、未知值、草稿、路由及请求行为，不代表真实浏览器、布局或读屏验收。

2026-10-31的calm工作台调整另新增7项前端回归，当时共18项；包含任务排序/范围、真实与模拟投递计数隔离、原因转义、未知参与状态、信息顺序及初始加载一致性。完整250项Python和多尺寸Chrome验收另作该轮执行，见[记录](development/calm-workspace.md)。历史11项和220项不改写为新执行。

涉及股票池/配置格式时保留历史格式模板与golden回归；不能将新字段补进旧配置。NEXT08的新旧配置、样例、执行规则schema及显式启用流程见[科创板说明](development/next08-star-acceptance.md)。

研究/运行改动还需核对`study`、`supervise`、`ops-report`、`archive-scans`的显式计划和输出证据。合成复现命令与分母/未知值约束见[NEXT06/07专项说明](development/next06-07-local-acceptance.md)；普通开发不修改实际data数据库，也不运行真实通知测试。

本地投递调度使用独立显式计划、SimulationNotifier和`dingtalk_simulation`渠道，见[NEXT04说明](development/next04-dispatch-lifecycle.md)。测试覆盖独占恢复前置、进程强杀、固定窗口/退避水位、扫描回滚和阻塞发送的停止边界；模拟回执不能进入真实平台P95。源码与包外隔离验收须同时保留原配置/样例兼容。

只改文档时，检查文件结构、相对链接、CLI与代码事实；不用为文档重复全部软件测试。若未实际运行，不在验收记录中写“本次通过”。页面浏览器/手机检查仍是独立任务，不能由API或截图缺席推断完成。

四项改进另需验证provider-poc的样本范围、外部分母未知和异常保留，channel-poc缺配置/禁止覆盖时不发网，触发图表不可被后续行情覆盖，以及study输入/计划/代码冻结、任务隔离和完整导出。操作及外部条件见[专项说明](development/four-priorities.md)。

## 版本与交付

0.2.1的NEXT03新增23项供应商样本测试，独立完整执行220项的时间另见[验证记录](development/verification.md)，不要与NEXT11的完整执行合并记作一次。覆盖HTTPS/凭据不落盘、请求与响应边界、Decimal/单位未知、当前成分不回填历史、文件哈希和比较缺样本；真实采集是显式操作，单元测试只使用mock。NEXT03没有改动UI或复跑浏览器；Node与NEXT11的记录各保留原时间。

0.2.2新增30项分钟诊断/准备测试，完整250项于2026-10-30 18:06:55—18:07:46 UTC通过；此前沙箱端口拒绝的失败执行单独保留。仅用mock分钟与临时本地HTTP，未取得真实分钟；没有UI改动或新的Node/浏览器执行。`vendor-sample --dry-run`和`minute-quality`的CLI/包外检查见[分钟准备](development/next03-minute-quality.md)与[本阶段证据](development/evidence/next03-minute-prep-20261030/README.md)。

功能改动按影响决定软件版本，并同步`stockradar/__init__.py`和`pyproject.toml`；纯文档重组不自动提升软件版本。更新CHANGELOG、TODO及受影响的主文档。完整需求/策略公式和执行证据保留在现有辅助目录，不覆盖来源快照。

内部组件随Python应用wheel一起交付。发布前先完成相关验证、资源打包与隔离安装检查，再按[构建与部署](DEPLOYMENT.md)分发。当前仅验证本地wheel，没有公共包索引或组件registry发布流程的执行记录。

离线工程包与真实提醒发布分开：只有完成行情/群路径、冻结参数、研究、负载与影子运行等门槛后才进入真实提醒工作。不得为“发布组件”而顺便移除live_alert保护或外发真实消息。

0.2.3新增20项公开接口测试，覆盖固定HTTPS/预算、匿名来源不读凭据、JSONP字面量/畸形数值、0价格和未知单位、前导零/符号不匹配、分页partial、近期窗口、错误/重定向停止及离线原始重解析。2026-10-31 17:41:49—17:42:40 UTC独立完整270项Python通过，外部传输为fake/mock。实际公开采样与测试分开留证；本次无UI改动、Node/浏览器重跑或真实群消息，见[使用与结果](development/next03-public-poc.md)和[证据索引](development/evidence/next03-public-20261031/README.md)。
