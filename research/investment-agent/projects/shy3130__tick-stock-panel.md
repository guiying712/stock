# 04 · shy3130/tick-stock-panel

## 版本与来源

- 仓库：https://github.com/shy3130/tick-stock-panel
- 固定提交：[查看源码快照](https://github.com/shy3130/tick-stock-panel/tree/a17742c97d70e6de1af9917844a38b75d963b101)，`a17742c97d70e6de1af9917844a38b75d963b101`。
- 默认分支：`main`。默认分支快照不代表稳定发布版。
- 采集时间（UTC）：2026-10-28T15:35:57.748777+00:00。
- GitHub pushed_at（UTC）：2026-10-28T05:43:36Z；该字段不等于已验证的发布频率或维护质量。
- Star：6372；Fork：1515；open_issues_count：35（GitHub 该计数含 PR，非未解决 bug 数）。
- 主要语言（API）：Python；归档：否。
- [固定版本 README](https://github.com/shy3130/tick-stock-panel/blob/a17742c97d70e6de1af9917844a38b75d963b101/README.md) · [本地 README](../sources/shy3130__tick-stock-panel/README.txt) · [元数据与哈希](../sources/shy3130__tick-stock-panel/provenance.json)。

## 项目定位与依赖（仓库文档陈述）

自托管的 A 股策略、监控、因子研究与回测；README 明确定位本地量化研究方案。

运行与数据依赖：Python ≥3.11、FastAPI、Polars、Parquet；React 18；Docker；TickFlow / fuyao / TdxQuant 等数据插件。

## 在个人投资智能体中的位置（我们的初步判断）

分类：策略工作台。验证优先级：**P0**。

候选策略服务底座，重点参考数据能力路由、扩展契约与回测界面。

## 许可与复用边界

MIT。

已保存[许可原文](../sources/shy3130__tick-stock-panel/LICENSE.txt)。这只覆盖取到的根目录文件；子目录、依赖、模型权重、图标和数据授权仍需逐项确认。

## 最小验证任务

使用冻结行情跑一个策略，检查同一数据在信号、图表、回测中口径一致；测插件断开和历史缺口。

验收材料必须包含：固定 commit、依赖锁定、脱敏配置、输入数据快照、运行日志、输出产物、耗时/调用成本、失败与恢复记录。当前执行状态：**未运行，待 PoC**。

## 当前信息缺口

- 尚未核对所有源文件、依赖清单、完整测试集或近期 Issue/PR。
- 市场覆盖、行情权限、数据费用和券商可交易性需要按最终使用场景逐项实测。
- 原 README 中相对图片和文档链接以在线固定版本为准；本地仅保存文本，未镜像外链资源。
- 采集异常：本轮必需资料采集无异常。
