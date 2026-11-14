# 行情 API 与大模型连接配置（0.2.4）

后续0.2.5新增[Tushare分钟获取与查看](tushare-minute-feed.md)，沿用本页Tushare Token和访问依据；股票基础信息连接检查不证明分钟权限，需在独立分钟页按目标接口另验。

本次完成 Fuyao 独立原始采样适配器、零请求准备，以及两张独立配置页面。对应 NEXT03、FR01/02/13；模型连接管理不代表 P1 AI 解释业务已经实现。

## 页面入口与操作

启动工作台并登录，在“设置与诊断”顶部选择：

- **行情 API**：`#market-api`，分别管理同花顺 Fuyao、TickFlow、Tushare 的 Key/Token 与个人研究访问依据。
- **大模型**：`#models`，填写兼容 API 基础地址、模型 ID、超时和可选本地 Key。

两个页面独立于策略参数。保存连接不会切换策略、启动采集或解锁 `live_alert`。

行情页面先选择服务商、填写 Key 并保存。Key 留空表示保留；勾选“清除已保存的本地 Key”后保存才删除本地凭据。尚未确认权限时可以先保存 Key，但“测试接口连接”保持禁用。确认目标接口与个人研究用途、填写不含凭据的依据后，再显式测试。

模型页面接受服务商提供的兼容 API 基础地址或本机 `http://127.0.0.1:11434/v1`，不要填 `/models` 或生成端点，也不要在 URL 中放 Key。模型 ID 使用服务商实际提供的值。远程服务需要 HTTPS 和 Key；本机兼容服务可以不填 Key。

“检查模型目录”只访问保存地址下的 `GET /models`，核对所选模型是否列出，不提交生成请求、行情、信号或聊天记录。“接口可达”不表示推理或额度验证通过；兼容服务若不提供模型目录，应按实际协议另验。依据：[OpenAI 模型目录](https://developers.openai.com/api/reference/resources/models/methods/list)、[Ollama 兼容接口](https://docs.ollama.com/api/openai-compatibility)。

普通字段草稿在当前浏览器会话保留。Key 只留在当前输入框，后台刷新不清空它；提交时立即清空，保存失败需重新输入。离开页面或退出会清除输入框；页面不从服务端回填 Key，也不把它写入浏览器存储。需要丢弃草稿时点“恢复已保存配置”。

## 本地存储与环境变量

连接目录位于数据库旁的 `.connections`，默认 `data/.connections`。目录权限 0700，元数据与令牌文件权限 0600；拒绝令牌符号链接、过宽权限或非当前用户拥有的文件。元数据只引用随机命名的 `.token` 文件，Key 与元数据分开保存。

替换时先写新令牌，再原子发布元数据，成功后移除旧令牌；元数据发布失败保留原连接。文件没有额外加密，依靠本机文件权限保护。它们不进入 SQLite、数据库备份、策略配置导出、原始样本或静态资源；迁移设备时须另行安全处理本地连接文件。

| 连接 | 进程环境优先项 | 无环境变量时 |
|---|---|---|
| Fuyao | `FUYAO_API_KEY` | 对应本地令牌文件 |
| TickFlow | `TICKFLOW_API_KEY` | 对应本地令牌文件 |
| Tushare | `TUSHARE_TOKEN` | 对应本地令牌文件 |
| 模型 | `STOCKRADAR_LLM_API_KEY` | 模型本地令牌文件；本机服务可无 Key |

页面显示当前凭据来源。清除本地 Key 不修改进程环境；环境变量存在时仍优先使用。服务不自动加载 `.env`。真实 Key 不应发到聊天、写入访问依据、JSON 计划或命令行参数。

每次保存生成新修订号，旧页面覆盖新配置会被拒绝。测试状态仅在当前服务进程保留，并绑定当时参数与凭据；保存、轮换环境凭据或重启后，旧测试不再证明当前连接有效。

## Fuyao 零请求准备

源码模板：[vendor-sample-fuyao-template.json](../../configs/vendor-sample-fuyao-template.json)。3 只证券分别来自主板、创业板、科创板；日期固定为 2026-11-02—2026-11-04。后续使用应复制新计划、修改 ID 和明确的已结束日期，不自动滚动历史窗口。

| 数据集 | 固定请求方式 | 请求数 |
|---|---|---:|
| `instruments` | 每只精确代码检索 | 3 |
| `daily_bars` | 三只批量 `1d`、显式 `adjust=none` | 1 |
| `quotes` | 三只当前报价 | 1 |
| `calendar` | 显式日期闭区间 | 1 |
| `adjustment_factors` | 每只公司行为事件 | 3 |
| `sector_catalog` | 概念、行业目录各一次 | 2 |
| `memberships` | 三只个股的当前板块反查 | 1 |
| 合计 | 预先固定完整计划 | 12 |

本地预算上限 20 次、串行间隔 6.1 秒、超时 15 秒，不是平台的 QPS 承诺。保持 1—5 只证券、最多 7 个自然日；拒绝分钟数据集、自定义端点和超预算计划。

无账户时执行：

```sh
python3 -m stockradar vendor-sample \
  --plan configs/vendor-sample-fuyao-template.json \
  --connections-dir /tmp/stockradar-fuyao-unconfigured \
  --output-dir /tmp/stockradar-fuyao-preparation-new \
  --dry-run
```

输出目录须不存在。该命令不构造网络连接；没有 Key 和访问依据时报告 `blocked_configuration`、12 个计划请求、实际 0 请求。模板保持 `authorization.confirmed=false`，准备报告不证明已取得权限。

页面保存的 Key 可由 CLI 读取，默认连接目录 `data/.connections`；自定义 `serve --db` 时，用 `--connections-dir` 指向该数据库旁的连接目录。真实采样仍需另存有明确访问依据的计划；页面的确认不会改写计划里的 false。具备权限并显式运行不带 `--dry-run` 的命令时，才可能请求接口。

采样器保存原始字节、哈希与本次接收时间，派生日线保留 Decimal 精度；股/元映射标记为 `fuyao_documented_not_independently_verified`。完成性和历史发布时间未知时保留 null，快照和当前关系不变成标准分钟 batch。

HTTP 429 或业务 `4001` 停止本轮，不自动重试；认证失败停止，能力权限不足仅阻断相应数据集。省略标的和合法空组分别记录；默认前复权、重复日期、外来标的、未结束日线窗口和敏感信息回显均有显式处理。没有实现 dump 下载、分钟行情或历史成员。

## 本轮证据与剩余条件

完整测试、CLI、包核对和浏览器记录见[证据目录](evidence/connection-settings-20261105/README.md)。[零请求报告](evidence/connection-settings-20261105/fuyao-preparation.json)实际为 12 个计划请求、0 次发送，缺 Key 与访问依据。

浏览器使用独立临时数据库、合成 Key 和本机假模型目录，检查保存后 Key 不回显、权限未确认时不测试、草稿刷新保留、错误恢复、目录检查及响应式布局。假目录可达不证明真实模型可用。

上述11月5日阶段没有真实 Fuyao 权限、费用、样本质量或供应商时效实测；模型推理与 AI 解释业务未实现。完成分钟、同期历史量能、历史成员/风险状态、全市场与连续影子等发布条件继续有效，详见[Fuyao 文档评估](next03-fuyao-review.md)及[数据契约](data-contract.md)。

## 后续真实接口验证（2026-11-08 UTC）

用户已在本机保存Fuyao Key并完成单次报价连接检查，随后独立确认12次个人研究采样计划。本轮取得9条日线、3条报价、710条概念/行业目录和76条当前关系；三只公司行为接口均返回3002，整体incomplete。9份原始成功响应和11份原始/派生文件的哈希、离线质量检查及实际时间见[首轮采样记录](next03-fuyao-poc.md)。

观势仍为fixture，真实样本未送入分钟策略。Key可用和部分接口成功不证明公司行为、单位独立核验、逐股报价时间、历史成员或完成分钟已齐备；没有真实模型推理或真实提醒发布。
