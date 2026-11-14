# 15 · HKUDS/Vibe-Trading

## 版本与来源

- 仓库：https://github.com/HKUDS/Vibe-Trading
- 固定提交：[查看源码快照](https://github.com/HKUDS/Vibe-Trading/tree/bff6e7625fd479d78db81aa5fbf4f317f6bef416)，`bff6e7625fd479d78db81aa5fbf4f317f6bef416`。
- 默认分支：`main`。默认分支快照不代表稳定发布版。
- 采集时间（UTC）：2026-10-28T15:36:22.930829+00:00。
- GitHub pushed_at（UTC）：2026-10-28T03:24:14Z；该字段不等于已验证的发布频率或维护质量。
- Star：37005；Fork：5973；open_issues_count：18（GitHub 该计数含 PR，非未解决 bug 数）。
- 主要语言（API）：Python；归档：否。
- [固定版本 README](https://github.com/HKUDS/Vibe-Trading/blob/bff6e7625fd479d78db81aa5fbf4f317f6bef416/README.md) · [本地 README](../sources/HKUDS__Vibe-Trading/README.txt) · [元数据与哈希](../sources/HKUDS__Vibe-Trading/provenance.json)。

## 项目定位与依赖（仓库文档陈述）

个人交易 Agent 平台；README 涵盖研究、因子、回测与交易执行场景。

运行与数据依赖：Python ≥3.11、FastAPI、React 19；模型、行情与目标 broker 的配置。

## 在个人投资智能体中的位置（我们的初步判断）

分类：综合交易 Agent。验证优先级：**P1**。

参考跨研究/回测/执行的产品组织与失败处理；先验证局部功能，避免整库引入过大范围。

## 许可与复用边界

MIT。

已保存[许可原文](../sources/HKUDS__Vibe-Trading/LICENSE.txt)。这只覆盖取到的根目录文件；子目录、依赖、模型权重、图标和数据授权仍需逐项确认。

## 最小验证任务

复核缺失行情、复权标记、订单异常和重启恢复；仅在模拟环境验证 README 声称的执行能力。

验收材料必须包含：固定 commit、依赖锁定、脱敏配置、输入数据快照、运行日志、输出产物、耗时/调用成本、失败与恢复记录。当前执行状态：**未运行，待 PoC**。

## 当前信息缺口

- 尚未核对所有源文件、依赖清单、完整测试集或近期 Issue/PR。
- 市场覆盖、行情权限、数据费用和券商可交易性需要按最终使用场景逐项实测。
- 原 README 中相对图片和文档链接以在线固定版本为准；本地仅保存文本，未镜像外链资源。
- 采集异常：本轮必需资料采集无异常。
