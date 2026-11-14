# 17 · simonlin1212/a-stock-data

## 版本与来源

- 仓库：https://github.com/simonlin1212/a-stock-data
- 固定提交：[查看源码快照](https://github.com/simonlin1212/a-stock-data/tree/cb57c7aba720380b48a11dd065c6db57a2c39db9)，`cb57c7aba720380b48a11dd065c6db57a2c39db9`。
- 默认分支：`main`。默认分支快照不代表稳定发布版。
- 采集时间（UTC）：2026-10-28T15:36:29.049186+00:00。
- GitHub pushed_at（UTC）：2026-10-28T01:33:32Z；该字段不等于已验证的发布频率或维护质量。
- Star：11214；Fork：2026；open_issues_count：0（GitHub 该计数含 PR，非未解决 bug 数）。
- 主要语言（API）：Python；归档：否。
- [固定版本 README](https://github.com/simonlin1212/a-stock-data/blob/cb57c7aba720380b48a11dd065c6db57a2c39db9/README.md) · [本地 README](../sources/simonlin1212__a-stock-data/README.txt) · [元数据与哈希](../sources/simonlin1212__a-stock-data/provenance.json)。

## 项目定位与依赖（仓库文档陈述）

以结构化 Markdown 与内嵌 Python 组织 A 股及相关市场数据入口；涵盖行情、财务、公告、研报等。

运行与数据依赖：Python ≥3.9；多外部数据源；iwencai 需 Key；部分 TCP 数据源有地域网络限制。

## 在个人投资智能体中的位置（我们的初步判断）

分类：数据工具。验证优先级：**P0**。

优先梳理数据字典并封装成普通代码适配器，避免运行时直接执行任意 Skill 片段。

## 许可与复用边界

Apache-2.0。

已保存[许可原文](../sources/simonlin1212__a-stock-data/LICENSE.txt)。这只覆盖取到的根目录文件；子目录、依赖、模型权重、图标和数据授权仍需逐项确认。

## 最小验证任务

逐个核实 MVP 必需端点的可用性、单位、复权、公告时间、限流和错误值；免费访问不等于数据可再分发。

验收材料必须包含：固定 commit、依赖锁定、脱敏配置、输入数据快照、运行日志、输出产物、耗时/调用成本、失败与恢复记录。当前执行状态：**未运行，待 PoC**。

## 当前信息缺口

- 尚未核对所有源文件、依赖清单、完整测试集或近期 Issue/PR。
- 市场覆盖、行情权限、数据费用和券商可交易性需要按最终使用场景逐项实测。
- 原 README 中相对图片和文档链接以在线固定版本为准；本地仅保存文本，未镜像外链资源。
- 采集异常：本轮必需资料采集无异常。
