# 13 · nautechsystems/nautilus_trader

## 版本与来源

- 仓库：https://github.com/nautechsystems/nautilus_trader
- 固定提交：[查看源码快照](https://github.com/nautechsystems/nautilus_trader/tree/2b35934c0cb9e047757407d7c59f83852048502e)，`2b35934c0cb9e047757407d7c59f83852048502e`。
- 默认分支：`develop`。默认分支快照不代表稳定发布版。
- 采集时间（UTC）：2026-10-28T15:36:21.332452+00:00。
- GitHub pushed_at（UTC）：2026-10-28T11:01:43Z；该字段不等于已验证的发布频率或维护质量。
- Star：30994；Fork：4173；open_issues_count：151（GitHub 该计数含 PR，非未解决 bug 数）。
- 主要语言（API）：Rust；归档：否。
- [固定版本 README](https://github.com/nautechsystems/nautilus_trader/blob/2b35934c0cb9e047757407d7c59f83852048502e/README.md) · [本地 README](../sources/nautechsystems__nautilus_trader/README.txt) · [元数据与哈希](../sources/nautechsystems__nautilus_trader/provenance.json)。

## 项目定位与依赖（仓库文档陈述）

Rust 交易运行时与 Python 策略控制，面向事件驱动研究和执行。

运行与数据依赖：Rust / Python / PyO3；具体交易适配器；默认 develop 分支包含 v2 RC 说明。

## 在个人投资智能体中的位置（我们的初步判断）

分类：事件驱动交易。验证优先级：**P2**。

作为后续执行/仿真引擎备选，与 vnpy 按券商覆盖、运行平台和事件一致性比较。

## 许可与复用边界

LGPL-3.0。

已保存[许可原文](../sources/nautechsystems__nautilus_trader/LICENSE.txt)。这只覆盖取到的根目录文件；子目录、依赖、模型权重、图标和数据授权仍需逐项确认。

## 最小验证任务

固定 v1 稳定版或 v2 RC 之一并匹配文档；验证订单生命周期、恢复重放和市场适配；勿混用两代 API。

验收材料必须包含：固定 commit、依赖锁定、脱敏配置、输入数据快照、运行日志、输出产物、耗时/调用成本、失败与恢复记录。当前执行状态：**未运行，待 PoC**。

## 当前信息缺口

- 尚未核对所有源文件、依赖清单、完整测试集或近期 Issue/PR。
- 市场覆盖、行情权限、数据费用和券商可交易性需要按最终使用场景逐项实测。
- 原 README 中相对图片和文档链接以在线固定版本为准；本地仅保存文本，未镜像外链资源。
- 采集异常：本轮必需资料采集无异常。
