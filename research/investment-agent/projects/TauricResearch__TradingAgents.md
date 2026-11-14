# 09 · TauricResearch/TradingAgents

## 版本与来源

- 仓库：https://github.com/TauricResearch/TradingAgents
- 固定提交：[查看源码快照](https://github.com/TauricResearch/TradingAgents/tree/c4544913a14ed3df5f1ed7b9e8483270ce20682a)，`c4544913a14ed3df5f1ed7b9e8483270ce20682a`。
- 默认分支：`main`。默认分支快照不代表稳定发布版。
- 采集时间（UTC）：2026-10-28T15:36:13.630104+00:00。
- GitHub pushed_at（UTC）：2026-10-27T08:43:04Z；该字段不等于已验证的发布频率或维护质量。
- Star：117708；Fork：22523；open_issues_count：88（GitHub 该计数含 PR，非未解决 bug 数）。
- 主要语言（API）：Python；归档：否。
- [固定版本 README](https://github.com/TauricResearch/TradingAgents/blob/c4544913a14ed3df5f1ed7b9e8483270ce20682a/README.md) · [本地 README](../sources/TauricResearch__TradingAgents/README.txt) · [元数据与哈希](../sources/TauricResearch__TradingAgents/provenance.json)。

## 项目定位与依赖（仓库文档陈述）

分析师、多空研究员、交易员与组合管理角色协作；支持结构化输出、决策日志和断点恢复。

运行与数据依赖：Python、LangGraph、多种 LLM 提供商；市场数据工具。

## 在个人投资智能体中的位置（我们的初步判断）

分类：Agent 编排。验证优先级：**P0**。

优先验证研究编排与结构化决策接口；保留独立于 LLM 的计算、风控和执行服务。

## 许可与复用边界

Apache-2.0。

已保存[许可原文](../sources/TauricResearch__TradingAgents/LICENSE.txt)。这只覆盖取到的根目录文件；子目录、依赖、模型权重、图标和数据授权仍需逐项确认。

## 最小验证任务

对相同冻结数据重复运行，检查引用、输出 schema、恢复幂等、调用预算；区分交易建议和真实成交。

验收材料必须包含：固定 commit、依赖锁定、脱敏配置、输入数据快照、运行日志、输出产物、耗时/调用成本、失败与恢复记录。当前执行状态：**未运行，待 PoC**。

## 当前信息缺口

- 尚未核对所有源文件、依赖清单、完整测试集或近期 Issue/PR。
- 市场覆盖、行情权限、数据费用和券商可交易性需要按最终使用场景逐项实测。
- 原 README 中相对图片和文档链接以在线固定版本为准；本地仅保存文本，未镜像外链资源。
- 采集异常：本轮必需资料采集无异常。
