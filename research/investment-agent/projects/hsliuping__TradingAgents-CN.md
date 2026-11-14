# 08 · hsliuping/TradingAgents-CN

## 版本与来源

- 仓库：https://github.com/hsliuping/TradingAgents-CN
- 固定提交：[查看源码快照](https://github.com/hsliuping/TradingAgents-CN/tree/51060a7682cf51810b4bc3a704829438d18cd8dc)，`51060a7682cf51810b4bc3a704829438d18cd8dc`。
- 默认分支：`v3.0`。默认分支快照不代表稳定发布版。
- 采集时间（UTC）：2026-10-28T15:36:11.351866+00:00。
- GitHub pushed_at（UTC）：2026-09-22T12:11:05Z；该字段不等于已验证的发布频率或维护质量。
- Star：32671；Fork：6811；open_issues_count：296（GitHub 该计数含 PR，非未解决 bug 数）。
- 主要语言（API）：Python；归档：否。
- [固定版本 README](https://github.com/hsliuping/TradingAgents-CN/blob/51060a7682cf51810b4bc3a704829438d18cd8dc/README.md) · [本地 README](../sources/hsliuping__TradingAgents-CN/README.txt) · [元数据与哈希](../sources/hsliuping__TradingAgents-CN/provenance.json)。

## 项目定位与依赖（仓库文档陈述）

中文分析与自然语言选股，v3.0 采用社区版/Pro 版及分层授权。

运行与数据依赖：Python 3.11、FastAPI、Vue 3、MongoDB、Redis；Tushare / AKShare / BaoStock；模型凭据。

## 在个人投资智能体中的位置（我们的初步判断）

分类：中文 Agent 应用。验证优先级：**P2**。

参考中文场景；只在明确目录许可边界后评估核心组件，应用层不得默认按 Apache 复制。

## 许可与复用边界

混合授权：指定目录 Apache-2.0；app/、frontend/、core/ 为专有许可。

已保存[许可原文](../sources/hsliuping__TradingAgents-CN/LICENSE.txt)。这只覆盖取到的根目录文件；子目录、依赖、模型权重、图标和数据授权仍需逐项确认。

## 最小验证任务

逐目录建立许可清单；检查核心引擎能否独立运行，避免把专有 app/frontend/core 带入可分发产品。

验收材料必须包含：固定 commit、依赖锁定、脱敏配置、输入数据快照、运行日志、输出产物、耗时/调用成本、失败与恢复记录。当前执行状态：**未运行，待 PoC**。

## 当前信息缺口

- 尚未核对所有源文件、依赖清单、完整测试集或近期 Issue/PR。
- 市场覆盖、行情权限、数据费用和券商可交易性需要按最终使用场景逐项实测。
- 原 README 中相对图片和文档链接以在线固定版本为准；本地仅保存文本，未镜像外链资源。
- 采集异常：本轮必需资料采集无异常。
