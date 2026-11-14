# 11 · vnpy/vnpy

## 版本与来源

- 仓库：https://github.com/vnpy/vnpy
- 固定提交：[查看源码快照](https://github.com/vnpy/vnpy/tree/c6e231caf32b7fc97e6459817fff66458cf7e7c4)，`c6e231caf32b7fc97e6459817fff66458cf7e7c4`。
- 默认分支：`master`。默认分支快照不代表稳定发布版。
- 采集时间（UTC）：2026-10-28T15:36:15.304704+00:00。
- GitHub pushed_at（UTC）：2026-10-27T00:54:38Z；该字段不等于已验证的发布频率或维护质量。
- Star：46122；Fork：12550；open_issues_count：11（GitHub 该计数含 PR，非未解决 bug 数）。
- 主要语言（API）：Python；归档：否。
- [固定版本 README](https://github.com/vnpy/vnpy/blob/c6e231caf32b7fc97e6459817fff66458cf7e7c4/README.md) · [本地 README](../sources/vnpy__vnpy/README.txt) · [元数据与哈希](../sources/vnpy__vnpy/provenance.json)。

## 项目定位与依赖（仓库文档陈述）

Python 量化框架，提供多市场交易网关及策略生态，README 列出独立本地仿真模块。

运行与数据依赖：Python ≥3.10（README 推荐 3.13）；具体网关和仿真组件常在独立仓库；券商账户/平台要求待核实。

## 在个人投资智能体中的位置（我们的初步判断）

分类：交易框架。验证优先级：**P1**。

第二阶段评估交易网关和模拟成交；独立进程适配，避免把 GUI 框架直接耦合进 Web 产品。

## 许可与复用边界

MIT。

已保存[许可原文](../sources/vnpy__vnpy/LICENSE.txt)。这只覆盖取到的根目录文件；子目录、依赖、模型权重、图标和数据授权仍需逐项确认。

## 最小验证任务

按目标券商验证网关、macOS/远程执行兼容性、授权、委托回报、撤单与断线对账；审查外部模块许可。

验收材料必须包含：固定 commit、依赖锁定、脱敏配置、输入数据快照、运行日志、输出产物、耗时/调用成本、失败与恢复记录。当前执行状态：**未运行，待 PoC**。

## 当前信息缺口

- 尚未核对所有源文件、依赖清单、完整测试集或近期 Issue/PR。
- 市场覆盖、行情权限、数据费用和券商可交易性需要按最终使用场景逐项实测。
- 原 README 中相对图片和文档链接以在线固定版本为准；本地仅保存文本，未镜像外链资源。
- 采集异常：本轮必需资料采集无异常。
