# 24 · theBigGavin/marketingdashboard

## 版本与来源

2026-11-11 按用户提供的仓库加入资料库。固定到 `main` 提交 `2d71054d76bb78b82ddb7818af4bdff49a6179a7`。根目录许可为 MIT，根包声明版本 1.4.0。前端采用 React 19、Vite、TypeScript，数据代理使用 Node.js。 [固定提交](https://github.com/theBigGavin/marketingdashboard/commit/2d71054d76bb78b82ddb7818af4bdff49a6179a7) · [许可](../sources/theBigGavin__marketingdashboard/LICENSE.txt) · [包声明](../sources/theBigGavin__marketingdashboard/package.json) · [来源及哈希](../sources/theBigGavin__marketingdashboard/provenance.json)

## 项目定位与数据来源

Market Research Cockpit 是一屏式市场研究看板，包含指数和商品走势、行业与概念排行、板块成分股、资金流及快讯。上游中文 README 列出腾讯、新浪、东方财富等行情来源及华尔街见闻等资讯来源。报价由客户端统一批量拉取并分发，服务端按接口设置缓存期限。 [固定中文 README](https://github.com/theBigGavin/marketingdashboard/blob/2d71054d76bb78b82ddb7818af4bdff49a6179a7/README_CN.md) · [本地中文快照](../sources/theBigGavin__marketingdashboard/README_CN.txt) · [本地主 README](../sources/theBigGavin__marketingdashboard/README.txt)

## 观势的参考取舍

| 对应工作 | 参考点 | 验证条件 |
|---|---|---|
| FR04、FR13 / NEXT11 | 从板块排行下钻到成分股、领涨股和资金流曲线，供观势比较概览、热点详情和时间线之间的导航 | 用已有合成切片核对热点和代表股的一致性、时点可见性、窄屏与键盘路径 |
| FR02 / NEXT03 | 同一证券在多个区域使用同批报价，接口按各自时效设置缓存期限 | 用冻结切片核对列表、详情和图表的时点对齐、陈旧标记与跨源差异 |

归为 **P1 资料参考**。本次核对固定中英文 README、许可和包声明。公开源的授权、行情语义、延迟及持续可用性待独立验证。

2026-11-11 追加[关键代码核查](../audits/2026-11-11-data-sources/dashboards-and-other.md)：除证券行情，还确认 CNBC/美国财政部美债、生意社现货、SEC/FRED 与 AI 行业指标入口；黄金页依赖作者环境的外部 JSON/SQLite，基础设施图部分为参数外推。分时点不直接等于完整分钟 OHLCV，未请求行情。
