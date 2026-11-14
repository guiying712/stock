# 21 · ZhuLinsen/alphasift（AlphaSift）

## 版本与证据

- 用户提供的公开仓库，默认分支为 `main`，GitHub 状态为未归档。归类为 P1 资料参考。 [上游仓库](https://github.com/ZhuLinsen/alphasift)
- 固定提交 `20b9a33bc051e07572fb012b07c58f5aa706dc91`，提交时间为 2026-11-04 13:29:33 UTC。采集于 2026-11-09 17:40:43 UTC。 [固定提交](https://github.com/ZhuLinsen/alphasift/commit/20b9a33bc051e07572fb012b07c58f5aa706dc91) · [来源与 SHA-256](../sources/ZhuLinsen__alphasift/provenance.json)
- 该提交声明 AlphaSift 0.2.0、Python 3.10+，运行依赖包括 pandas、PyYAML、LiteLLM、efinance、AKShare、BaoStock、Tushare、yfinance 和 requests。GitHub 许可字段、包声明及根目录许可均标识 Apache-2.0。 [依赖声明](../sources/ZhuLinsen__alphasift/pyproject.toml) · [许可原文](../sources/ZhuLinsen__alphasift/LICENSE.txt)

## 项目定位与数据来源

AlphaSift 用行情快照做候选筛选，YAML 配置保存筛选规则和因子权重。它提供行业分散约束、可选 LLM 排序和保存运行结果后的 T+N 评价。同作者的 daily_stock_analysis 可作为外部个股分析服务。 [固定版本中文 README](../sources/ZhuLinsen__alphasift/README.zh-CN.txt) · [项目与数据源说明](../sources/ZhuLinsen__alphasift/data-source-reference.txt)

| 用途 | 固定版本记录的来源 |
|---|---|
| A 股快照 | 默认依次尝试新浪、efinance、AKShare 东方财富和东方财富数据中心。有 Tushare Token 时将 Tushare 放到默认链路前面 |
| Tushare 快照 | 使用 `daily` 与 `daily_basic` 组合最近交易日的日线与指标 |
| A 股日线历史 | 自动模式按配置及健康状态选择腾讯、新浪、AKShare、BaoStock，以及有 Token 时的 Tushare |
| 其他市场 | Yahoo Finance 筛选与 yfinance 日线，范围见上游 README |

efinance、AKShare 东方财富和东方财富数据中心属于同一个底层来源组。上游快照实现记录各源结果，并为最近成功的缓存附加陈旧、年龄、回退和错误信息。 [快照实现](https://github.com/ZhuLinsen/alphasift/blob/20b9a33bc051e07572fb012b07c58f5aa706dc91/alphasift/snapshot.py) · [日线实现](https://github.com/ZhuLinsen/alphasift/blob/20b9a33bc051e07572fb012b07c58f5aa706dc91/alphasift/daily.py)

## 观势可借鉴的做法

| 对应工作 | 参考点 | 后续验证条件 |
|---|---|---|
| FR02 / NEXT03 数据质量 | 分开记录来源健康、缓存年龄、回退与字段错误。多源对账按底层提供方分组 | 用固定输入核对同周期、单位、完整性和可见时点，陈旧分钟进入暂停流程 |
| FR12 / NEXT06 效果研究 | 保存候选批次及当时价格，使用入场后第 N 根交易日线与同期基准评价。未成熟样本保留 pending 和独立分母 | 对照观势既有 5/10/20 日窗口，另核对可成交性、成本、复权、停牌与历史成员 |
| FR14 配置管理 | 筛选条件、权重和行业限制可以审阅，并随每次研究留证 | 以观势现有固定配置哈希和确定性策略路径承载，使用冻结输入核对结果 |

T+N 的静态核对覆盖保存价格、交易日线窗口、基准及 pending 分支。观势的成交与成本研究继续以自身规格验收。 [评价实现](https://github.com/ZhuLinsen/alphasift/blob/20b9a33bc051e07572fb012b07c58f5aa706dc91/alphasift/evaluate.py)

本次证据为上游固定文档与相关实现的静态核对。接口稳定性、账户权限、完成分钟、历史可见性与运行效果均待独立 PoC。
