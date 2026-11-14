# 26 · myhhub/stock（InStock）

## 固定版本与许可

2026-11-12 按用户提供的仓库入库，固定到 `master` 提交 `b6e0ca2268cfbadd02f5ed052159c187b6670231`。根目录许可为 Apache-2.0。上游以 Python、pandas、TA-Lib 计算指标，使用 MySQL 保存历史并通过 Web 展示，依赖清单包含 Tornado、SQLAlchemy 和 Bokeh。 [固定提交](https://github.com/myhhub/stock/commit/b6e0ca2268cfbadd02f5ed052159c187b6670231) · [许可](../sources/myhhub__stock/LICENSE.txt) · [依赖](../sources/myhhub__stock/requirements.txt) · [来源与哈希](../sources/myhhub__stock/provenance.json)

## 定位与参考点

InStock 的上游文档涵盖每日 A 股与 ETF 数据、技术指标、筹码分布、K 线形态、组合选股及验证回测。文档记录东方财富的数据获取路径。日线字段、指标和筛选结果可作为离线比较材料，历史可见性、复权和完成分钟权限须按观势的数据契约单独验证。 [固定 README](https://github.com/myhhub/stock/blob/b6e0ca2268cfbadd02f5ed052159c187b6670231/README.md) · [本地 README](../sources/myhhub__stock/README.txt)

归为 **P1 日线筛选与指标参考**，对应 FR02 / FR05 / FR12。优先参考日线指标、形态条件与筛选结果的展示，以及用同一数据核对选股规则。若进入验证，固定价格与复权输入，比较指标预热、涨跌停和缺失处理，并保留信号分母与结果。此次以固定文档与依赖声明为证据，回测和数据覆盖待实测。
