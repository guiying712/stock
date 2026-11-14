# 05 · Open-Dev-Society/OpenStock

## 版本与来源

- 仓库：https://github.com/Open-Dev-Society/OpenStock
- 固定提交：[查看源码快照](https://github.com/Open-Dev-Society/OpenStock/tree/b72306d39fa27dc55252ceecf858165ecf5a3fa3)，`b72306d39fa27dc55252ceecf858165ecf5a3fa3`。
- 默认分支：`main`。默认分支快照不代表稳定发布版。
- 采集时间（UTC）：2026-10-28T15:36:05.511822+00:00。
- GitHub pushed_at（UTC）：2026-10-25T15:14:11Z；该字段不等于已验证的发布频率或维护质量。
- Star：20910；Fork：2574；open_issues_count：6（GitHub 该计数含 PR，非未解决 bug 数）。
- 主要语言（API）：TypeScript；归档：否。
- [固定版本 README](https://github.com/Open-Dev-Society/OpenStock/blob/b72306d39fa27dc55252ceecf858165ecf5a3fa3/README.md) · [本地 README](../sources/Open-Dev-Society__OpenStock/README.txt) · [元数据与哈希](../sources/Open-Dev-Society__OpenStock/provenance.json)。

## 项目定位与依赖（仓库文档陈述）

行情展示、股票关注与提醒、公司信息；README 明确其不是券商平台。

运行与数据依赖：Next.js 15、React 19、Node 22、MongoDB、Finnhub Key；部分通知与 AI 功能需要其他服务。

## 在个人投资智能体中的位置（我们的初步判断）

分类：行情界面。验证优先级：**P2**。

参考自选列表、公司详情和提醒交互；代码接入先评估 AGPL。

## 许可与复用边界

AGPL-3.0。

已保存[许可原文](../sources/Open-Dev-Society__OpenStock/LICENSE.txt)。这只覆盖取到的根目录文件；子目录、依赖、模型权重、图标和数据授权仍需逐项确认。

## 最小验证任务

核对目标市场覆盖、行情延迟、限流和提醒是否真实发送；不能据此推断具备下单能力。

验收材料必须包含：固定 commit、依赖锁定、脱敏配置、输入数据快照、运行日志、输出产物、耗时/调用成本、失败与恢复记录。当前执行状态：**未运行，待 PoC**。

## 当前信息缺口

- 尚未核对所有源文件、依赖清单、完整测试集或近期 Issue/PR。
- 市场覆盖、行情权限、数据费用和券商可交易性需要按最终使用场景逐项实测。
- 原 README 中相对图片和文档链接以在线固定版本为准；本地仅保存文本，未镜像外链资源。
- 采集异常：本轮必需资料采集无异常。
