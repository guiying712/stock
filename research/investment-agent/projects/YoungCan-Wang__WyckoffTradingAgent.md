# 02 · YoungCan-Wang/WyckoffTradingAgent

## 版本与来源

- 仓库：https://github.com/YoungCan-Wang/WyckoffTradingAgent
- 固定提交：[查看源码快照](https://github.com/YoungCan-Wang/WyckoffTradingAgent/tree/30aa5da6c42061ef79683930df89fbd6bc746cc7)，`30aa5da6c42061ef79683930df89fbd6bc746cc7`。
- 默认分支：`main`。默认分支快照不代表稳定发布版。
- 采集时间（UTC）：2026-10-28T15:35:57.748548+00:00。
- GitHub pushed_at（UTC）：2026-10-28T05:43:52Z；该字段不等于已验证的发布频率或维护质量。
- Star：759；Fork：217；open_issues_count：40（GitHub 该计数含 PR，非未解决 bug 数）。
- 主要语言（API）：Python；归档：否。
- [固定版本 README](https://github.com/YoungCan-Wang/WyckoffTradingAgent/blob/30aa5da6c42061ef79683930df89fbd6bc746cc7/README.md) · [本地 README](../sources/YoungCan-Wang__WyckoffTradingAgent/README.txt) · [元数据与哈希](../sources/YoungCan-Wang__WyckoffTradingAgent/provenance.json)。

## 项目定位与依赖（仓库文档陈述）

威科夫量价分析、A 股筛选，提供 CLI、MCP、React Web 与桌面形态。

运行与数据依赖：Python ≥3.11；TickFlow；云端涉及 Supabase、Cloudflare 等服务。

## 在个人投资智能体中的位置（我们的初步判断）

分类：量价分析。验证优先级：**P1**。

借鉴形态证据、持仓诊断、信号复盘；是否复用代码先评估 AGPL 及具体部署方式。

## 许可与复用边界

AGPL-3.0。

已保存[许可原文](../sources/YoungCan-Wang__WyckoffTradingAgent/LICENSE.txt)。这只覆盖取到的根目录文件；子目录、依赖、模型权重、图标和数据授权仍需逐项确认。

## 最小验证任务

用相同 K 线复现形态；区分本地可用功能与云端会员功能，测数据 Key 缺失时的降级。

验收材料必须包含：固定 commit、依赖锁定、脱敏配置、输入数据快照、运行日志、输出产物、耗时/调用成本、失败与恢复记录。当前执行状态：**未运行，待 PoC**。

## 当前信息缺口

- 尚未核对所有源文件、依赖清单、完整测试集或近期 Issue/PR。
- 市场覆盖、行情权限、数据费用和券商可交易性需要按最终使用场景逐项实测。
- 原 README 中相对图片和文档链接以在线固定版本为准；本地仅保存文本，未镜像外链资源。
- 采集异常：本轮必需资料采集无异常。
