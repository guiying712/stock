# 四项改进：数据、真实提醒、图表证据与研究

后续0.2.1已开始[NEXT03数据来源与免密原始样本核验](next03-data-sources.md)：取得5证券25条日线及当前元数据，但量能单位/精度、真实分钟与历史成分仍待确认。该独立原始采集不是本页provider-poc所需的完整标准batch；0.2.0的四项改进证据保留原日期。

2026-10-29 用户确认优先推进。软件版本为0.2.0离线增强版；真实提醒发布门槛保持独立。当前事实、任务和证据分别由本页、[TODO](../../TODO.md)和[验证记录](verification.md)维护。

## 对照20个项目后的取舍

观势已有确定性策略、不可变事件证据、事务通知和本地恢复。与PanWatch相比，重点学习提醒设置、引导和移动使用；与tick-stock-panel相比，重点学习数据能力路由、统一口径与研究呈现。上游功能来自固定版本文档，未运行对照，不据此声明观势更快、更稳定或收益更好。

| 当前工作 | 参考项目 | 本轮工程交付 | 仍需的真实证据 |
|---|---|---|---|
| NEXT03可信数据 | tick-stock-panel、a-stock-data | 显式能力/授权/分母计划，JSONL或已授权HTTPS样本PoC报告 | 服务商、授权、分钟历史、历史成员/状态/复权、外部分母、限流与长期覆盖 |
| NEXT04真实提醒 | PanWatch、daily_stock_analysis | 独立连接测试报告；历史受理须匹配当前目标配置；unknown不自动重试 | 明确测试群、显式测试发送、消息呈现、真实恢复/聚合拆分与平台P95；机会渠道仍未接线 |
| NEXT09图表证据 | WyckoffTradingAgent、OpenStock | 触发/最近扫描分钟K线，冻结H/S、事件及来源表；1280/390/320px浏览器与键盘通过 | 真机/读屏补充验收及真实行情样本 |
| NEXT10研究呈现，关联NEXT06 | Qlib、Vibe-Research | 独立异步study、四组/分段/成本展示、鉴权原文导出；页面与CLI完整报告哈希一致 | 授权真实历史、适用规则和费用、样本外比较与正式参数冻结 |

Sequoia-X供简单规则/增量任务参考，UZI-Skill供短解释模板参考；TradingAgents、TradingAgents-CN、Vibe-Trading供日志、中文表达和任务组织参考。NautilusTrader、vn.py供事件与适配器工程参考；jcp、ai-financial-agent供工作区/来源呈现参考。Kronos延后到真实基线建立后评估，awesome-quant用于按需发现工具，美股指南仅作背景资料。完整20项来源见[资料总览](../../research/investment-agent/01-项目选型总览.md)，原始快照不改写。

## 数据PoC

`provider-poc`只读取输入并生成新的报告，不写实时数据库、不选供应商。计划必需字段与未知键严格校验；声明能力和样本中字段存在分别记录。授权确认只是提交者声明，不能取代授权原件审查。报告保留计划/配置/代码/输入哈希、覆盖、异常、重复和冲突；`full_market_verified`、`release_allowed`始终false。

先在独立临时目录演练：

```sh
python3 -m stockradar export-fixture --output /private/tmp/guanshi-poc-synthetic.jsonl
python3 -m stockradar provider-poc --input /private/tmp/guanshi-poc-synthetic.jsonl --config configs/fixture.json --plan configs/provider-poc-fixture.json --output /private/tmp/guanshi-provider-poc.json
```

完整11切片含断源故障，报告出现`incomplete`及覆盖不足是预期行为，不删除失败样本以换取通过。只检查前两个正常切片时可得到`sample_checked`，仍仅表示该样本检查完成。

真实接入先复制`configs/provider-poc-template.json`到新的计划文件，填写服务商、授权证据编号、已核实能力、外部合格股票池分母及明确UTC采样时点。另建新ID的完整`experimental shadow`策略配置，保留旧fixture配置。网关须返回[标准数据契约](data-contract.md)，供应商原始字段仍需独立映射；本轮没有内置或验证具体供应商适配器。

```sh
python3 -m stockradar provider-poc --http --config /private/tmp/guanshi-shadow.json --plan /private/tmp/guanshi-provider-plan.json --output /private/tmp/guanshi-real-provider-poc.json
```

网关从`STOCKRADAR_PROVIDER_URL`读取，令牌只从`STOCKRADAR_PROVIDER_TOKEN`读取；不得把凭据写入计划、URL查询、报告或聊天。HTTPS采样必须具有显式授权声明和非空时点；不会自动回退到免费接口或用今日成分填历史。JSONL的真实标记也不能证明数据授权、历史完整或在线路径成立。

## 钉钉连接PoC

默认只生成未发送报告，显式`--send-test`才发送一条标有“测试通知”的连接消息。应在已明确的测试群及独立数据库中执行：

```sh
python3 -m stockradar channel-poc --db /private/tmp/guanshi-channel-poc.sqlite3 --output /private/tmp/guanshi-channel-preparation.json
# 配置本机进程环境并明确测试目标后，才执行下一条。
python3 -m stockradar channel-poc --db /private/tmp/guanshi-channel-poc.sqlite3 --send-test --output /private/tmp/guanshi-channel-test.json
```

不提供真实Webhook/密钥示例。缺配置时生成`blocked_missing_configuration`，网络请求为0；报告路径已存在时在发送前拒绝执行。超时/不确定结果保持unknown，报告不会自动重新发送。

新连接测试把当前目标配置的单向指纹与回执关联；Webhook或加签配置改变后，原受理记录不再验证当前配置。旧无指纹记录保留原样，不回填、不算作当前成功。指纹不包含可恢复的凭据原文。

`accepted`只表示平台受理。报告中的`rendering_confirmed`、`opportunity_path_verified`、`release_allowed`保持false；群内呈现、真实聚合拆分、恢复、限额、风险更新和平台时延须分别实测。当前应用仍拒绝live_alert；连接测试不能解除锁定。

## 分钟K线与冻结证据

信号详情API附带`chart`，页面自动显示：

- 默认“触发时可见”读取episode最初触发对应的原始扫描快照。首次提醒晚于触发时，也不能用后来的预警快照重建旧视图；只有缺少原快照引用的旧记录才使用其保留的提醒引用。
- “截至最近扫描”单独展开，仅作后续跟踪。两个视图均限制到信号当日、完成分钟、对应截止时间内已接收且质量正常的记录。
- 冻结H/S和触发价沿用信号证据；复权基准不同的点明确排除，不换算或移动旧结构位。
- 显示UTC记录对应的北京时间、来源、修订、快照/输入哈希；OHLC未知、冲突或时间不可见时排除并保留原因。
- 每视图最多120个点，缺口不补线；横轴保留实际时间间隔。柱形是原输入的同分钟累计成交额，不称为单分钟成交量。

SVG只计算展示坐标，不计算策略分数或重新判断机会。图表可在窄屏内部横向滚动，并有数值表格供核对。浏览器未验证时，不以Node测试或API结果代替视觉/键盘验收。

## 成本研究页面

“策略与研究”新增成本与样本外研究。内置选择为30日合成演练及配套假设计划，任务在独立子进程运行；它和功能回放分开显示，共享最多两个后台任务的限制。

自备输入放在**独立数据库所在目录**的`datasets/<id>.jsonl`和`study-plans/<id>.json`，再刷新研究页面选择。ID只接受字母/数字/连字符/下划线，拒绝符号链接和路径穿越；无上传/任意URL读取入口。页面输入上限256MiB，更大的研究使用CLI。

提交时冻结完整计划及文件SHA-256，启动前/读取后校验文件，计算前后核对代码，变化导致任务显式失败；修改计划文件不会改写已提交计划。计算继续复用`run_study`和`evaluate`，不写实时信号、通知或持仓。

页面可选择研究/验证/测试段、用户反应延迟、持有窗口和固定/风险退出；同时显示个股规则基线、板块资格过滤、早期提醒、确认后提醒四组的有效/总样本、闭合/待定/未成交、净收益、基准超额和聚类区间。跨段样本单独剔除，未知收益显示“—”。样本收益均值与聚类区间权重不同，各组区间不等同组间显著性检验，不自动推荐参数。

study列表不读取完整样本，回放列表也先过滤类型再读取结果，避免后台轮询读取大体积study报告；详情只投影计划/汇总。完整导出直接保存服务端原JSON，保留0.0等数值类型与原研究报告/样本；不经浏览器解析后重新序列化。页面所示`output_hash`是完整原报告哈希，不能用详情投影重新计算核对。所有API仍需Bearer鉴权。合成或证据不充分时，正式参数冻结资格保持false。

## 当前验收状态

最终完整197项Python、2项Node、三份JS语法及Python3.9内存编译通过；CLI/页面各运行一份同输入的30日210切片合成研究，完整原报告哈希相同；全部表备份恢复、0.2.0 wheel新旧模板隔离扫描/图表通过。浏览器权限最初关闭，用户授权并开启后完成1280×800、390×844、320×780验收，图表/研究区域无页面或侧栏整体横向溢出，图表键盘横移、Esc关闭/焦点返回及后台刷新位置/焦点保留通过，控制台无警告/错误。它们不代替真机、读屏或完整无障碍验收。

具体时间、哈希、先前失败和截图见[验证记录](verification.md)及[证据索引](evidence/four-priorities/index.json)，历史173项保持原日期。当前进程仅核对到行情/钉钉环境变量均未配置，未读取或展示真实密钥，未发送真实群消息。真实行情、明确测试群、授权历史和连续影子证据尚缺，这四项的真实验收仍未完成；本地工程交付与外部依赖分别记录。
