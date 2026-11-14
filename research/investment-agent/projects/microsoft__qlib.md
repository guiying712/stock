# 12 · microsoft/qlib

## 版本与来源

- 仓库：https://github.com/microsoft/qlib
- 固定提交：[查看源码快照](https://github.com/microsoft/qlib/tree/54355232463878d2eebb91fe0ee5fa7fa1f5976c)，`54355232463878d2eebb91fe0ee5fa7fa1f5976c`。
- 默认分支：`main`。默认分支快照不代表稳定发布版。
- 采集时间（UTC）：2026-10-28T15:36:20.530945+00:00。
- GitHub pushed_at（UTC）：2026-10-22T06:22:15Z；该字段不等于已验证的发布频率或维护质量。
- Star：49778；Fork：7861；open_issues_count：510（GitHub 该计数含 PR，非未解决 bug 数）。
- 主要语言（API）：Python；归档：否。
- [固定版本 README](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/README.md) · [本地 README](../sources/microsoft__qlib/README.txt) · [元数据与哈希](../sources/microsoft__qlib/provenance.json)。

## 项目定位与依赖（仓库文档陈述）

特征、模型、数据处理、实验与回测研究流程。

运行与数据依赖：Python；历史数据集；不同模型有不同依赖；README 提醒 artifact loading 存在未发布破坏性变更。

## 在个人投资智能体中的位置（我们的初步判断）

分类：量化研究。验证优先级：**P1**。

第三阶段引入离线因子研究和可复现实验，独立环境运行。

## 许可与复用边界

MIT。

已保存[许可原文](../sources/microsoft__qlib/LICENSE.txt)。这只覆盖取到的根目录文件；子目录、依赖、模型权重、图标和数据授权仍需逐项确认。

## 最小验证任务

时间顺序训练/验证/测试；防止财报时点泄漏、幸存者偏差；与简单基线比较并计入交易成本。

验收材料必须包含：固定 commit、依赖锁定、脱敏配置、输入数据快照、运行日志、输出产物、耗时/调用成本、失败与恢复记录。当前执行状态：**未运行，待 PoC**。

## 当前信息缺口

- 尚未核对所有源文件、依赖清单、完整测试集或近期 Issue/PR。
- 市场覆盖、行情权限、数据费用和券商可交易性需要按最终使用场景逐项实测。
- 原 README 中相对图片和文档链接以在线固定版本为准；本地仅保存文本，未镜像外链资源。
- 采集异常：本轮必需资料采集无异常。
