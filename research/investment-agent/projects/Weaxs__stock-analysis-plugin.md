# 22 · Weaxs/stock-analysis-plugin

## 版本与来源

- 2026-11-10 按用户提供的公开仓库加入资料库。取 `main` 的固定提交 `4aeb5e8993c3f51eac18ffcc6c5fd53bb86f258d`，提交记录时间为 2026-11-03 10:30:44 UTC。采集于 2026-11-11 06:36:05 UTC。 [固定提交](https://github.com/Weaxs/stock-analysis-plugin/commit/4aeb5e8993c3f51eac18ffcc6c5fd53bb86f258d) · [来源及文件哈希](../sources/Weaxs__stock-analysis-plugin/provenance.json)
- 固定提交的 Python 和 npm 包均声明版本 0.1.4，根目录许可与两份包声明均为 MIT。共享 Python 工具要求 Python 3.10+，依赖 pandas、NumPy、PyYAML、exchange-calendars 及多个行情库。 [许可原文](../sources/Weaxs__stock-analysis-plugin/LICENSE.txt) · [Python 包声明](../sources/Weaxs__stock-analysis-plugin/pyproject.toml) · [npm 包声明](../sources/Weaxs__stock-analysis-plugin/package.json) · [工具依赖](../sources/Weaxs__stock-analysis-plugin/tools-requirements.txt)

## 项目定位与数据来源

上游提供跨市场行情、筛选和策略回测。Pi、Hermes、OpenClaw 和 DeepSeek Harness 的插件入口共享 Python CLI。下表记录固定 README 中的行情链路。 [固定 README](https://github.com/Weaxs/stock-analysis-plugin/blob/4aeb5e8993c3f51eac18ffcc6c5fd53bb86f258d/README.md) · [本地快照](../sources/Weaxs__stock-analysis-plugin/README.txt)

| 用途 | 上游文档记录 |
|---|---|
| A 股普通股票报价 | 基础顺序为 AKShare、Tushare、efinance、腾讯、新浪、pytdx、BaoStock。A 股链路会优先尝试近期成功源 |
| A 股股票及 ETF K 线 | 走前复权链路，Tushare 仅用于股票。腾讯仅接受前复权结果，新浪及 pytdx 的未复权股票 K 线排除在外 |
| A 股指数 K 线 | 显式指数代码走腾讯、新浪、BaoStock，保留原始点位 |
| 港股、美股及其他市场 | 以 yfinance 为主要入口，港美股按用途另有腾讯、Finnhub、Longbridge 或 Alpha Vantage 等来源 |

行情结果保留提供方、UTC 采集时间及数据自身时点。文档要求缺少数据时点时保留空值，并在 K 线结果记录复权口径。 [固定市场路由说明](https://github.com/Weaxs/stock-analysis-plugin/blob/4aeb5e8993c3f51eac18ffcc6c5fd53bb86f258d/README.md#市场路由规则)

2026-11-11 源码补查：同一固定提交 `tools/stock_data.py` 的普通 A 股报价链实际止于 pytdx，**没有 README 所列的 BaoStock 报价回退**；BaoStock 出现在 K 线链。CLI 的 K 线周期仅 daily/weekly/monthly。上表保留 README 原陈述，实际实现以[源码核查](../audits/2026-11-11-data-sources/research-apps.md)及其中固定链接为准；未运行行情接口。

## 观势的参考取舍

| 对应工作 | 参考点 | 验证条件 |
|---|---|---|
| FR02 / NEXT03 数据质量 | 按报价、K 线和指数配置不同的回退链路。记录本次来源、行情时点、接收时间与复权标签 | 用冻结样本检查账户权限、完成分钟、延迟、单位及复权一致性。供应商切换后检查同一指标的口径 |
| FR12 / NEXT06、FR14 研究 | 用 YAML 声明信号、成交时点、成本和基准。回测文档说明了指标预热、零量阻止成交及拒绝混合复权口径的规则 | 用同一冻结输入核对研究窗口、成交资格与基准覆盖。费用和交易规则依据观势自身的验证记录 |

归为 **P1 资料参考**。本次证据为固定 README、许可和依赖声明的静态核对，数据可用性、历史可见性和回测行为待独立验证。 [固定回测说明](https://github.com/Weaxs/stock-analysis-plugin/blob/4aeb5e8993c3f51eac18ffcc6c5fd53bb86f258d/README.md#策略回测-dsl)
