# 01 · sngyai/Sequoia-X

## 版本与来源

- 仓库：https://github.com/sngyai/Sequoia-X
- 固定提交：[查看源码快照](https://github.com/sngyai/Sequoia-X/tree/444c0db69ff36b46ef2b22ab265051d60c16029d)，`444c0db69ff36b46ef2b22ab265051d60c16029d`。
- 默认分支：`master`。默认分支快照不代表稳定发布版。
- 采集时间（UTC）：2026-10-28T15:35:57.748273+00:00。
- GitHub pushed_at（UTC）：2026-07-10T23:17:43Z；该字段不等于已验证的发布频率或维护质量。
- Star：8312；Fork：1664；open_issues_count：43（GitHub 该计数含 PR，非未解决 bug 数）。
- 主要语言（API）：Python；归档：否。
- [固定版本 README](https://github.com/sngyai/Sequoia-X/blob/444c0db69ff36b46ef2b22ab265051d60c16029d/README.md) · [本地 README](../sources/sngyai__Sequoia-X/README.txt) · [元数据与哈希](../sources/sngyai__Sequoia-X/provenance.json)。

## 项目定位与依赖（仓库文档陈述）

A 股日线形态扫描，包含海龟突破、均线放量、旗形、RPS 等策略，增量更新后推送飞书。

运行与数据依赖：Python ≥3.10；BaoStock；SQLite；飞书 Webhook。

## 在个人投资智能体中的位置（我们的初步判断）

分类：规则选股。验证优先级：**P1**。

研究确定性筛选规则、策略基类、增量更新和盘后任务；许可确认前仅参考设计。

## 许可与复用边界

README 声称 MIT；API 未识别许可证，常见根目录许可文件未取到，待确认。

未取得常见根目录许可文件，不等于已证明整个仓库没有许可证。直接复制代码或文档前，检查文件树并向上游确认。

## 最小验证任务

核对复权口径、交易日增量和重复执行；用冻结行情检查每个信号是否只使用当时可见数据。

验收材料必须包含：固定 commit、依赖锁定、脱敏配置、输入数据快照、运行日志、输出产物、耗时/调用成本、失败与恢复记录。当前执行状态：**未运行，待 PoC**。

## 当前信息缺口

- 尚未核对所有源文件、依赖清单、完整测试集或近期 Issue/PR。
- 市场覆盖、行情权限、数据费用和券商可交易性需要按最终使用场景逐项实测。
- 原 README 中相对图片和文档链接以在线固定版本为准；本地仅保存文本，未镜像外链资源。
- 采集异常：LICENSE: not retrieved; HTTP Error 404: Not Found。
