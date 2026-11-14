# 06 · wbh604/UZI-Skill

## 版本与来源

- 仓库：https://github.com/wbh604/UZI-Skill
- 固定提交：[查看源码快照](https://github.com/wbh604/UZI-Skill/tree/3dc556bdad8229fad01dc54c83d6d9402ef6218c)，`3dc556bdad8229fad01dc54c83d6d9402ef6218c`。
- 默认分支：`main`。默认分支快照不代表稳定发布版。
- 采集时间（UTC）：2026-10-28T15:36:05.751206+00:00。
- GitHub pushed_at（UTC）：2026-10-18T02:56:06Z；该字段不等于已验证的发布频率或维护质量。
- Star：7444；Fork：1036；open_issues_count：2（GitHub 该计数含 PR，非未解决 bug 数）。
- 主要语言（API）：Python；归档：否。
- [固定版本 README](https://github.com/wbh604/UZI-Skill/blob/3dc556bdad8229fad01dc54c83d6d9402ef6218c/README.md) · [本地 README](../sources/wbh604__UZI-Skill/README.txt) · [元数据与哈希](../sources/wbh604__UZI-Skill/provenance.json)。

## 项目定位与依赖（仓库文档陈述）

A 股、港股、美股分析 Skills，包含多视角评审、估值及结构化报告。

运行与数据依赖：Python ≥3.10；Agent 宿主；akshare、yfinance、公告与公开网站；部分源需要登录或 Key。

## 在个人投资智能体中的位置（我们的初步判断）

分类：分析方法与报告。验证优先级：**P1**。

选择少量可解释分析维度和报告模板，独立封装为受控工具。

## 许可与复用边界

MIT。

已保存[许可原文](../sources/wbh604__UZI-Skill/LICENSE.txt)。这只覆盖取到的根目录文件；子目录、依赖、模型权重、图标和数据授权仍需逐项确认。

## 最小验证任务

检查缺数据时是否保持缺失而非生成估值；复核数值计算、来源链接、时点与评分校准。

验收材料必须包含：固定 commit、依赖锁定、脱敏配置、输入数据快照、运行日志、输出产物、耗时/调用成本、失败与恢复记录。当前执行状态：**未运行，待 PoC**。

## 当前信息缺口

- 尚未核对所有源文件、依赖清单、完整测试集或近期 Issue/PR。
- 市场覆盖、行情权限、数据费用和券商可交易性需要按最终使用场景逐项实测。
- 原 README 中相对图片和文档链接以在线固定版本为准；本地仅保存文本，未镜像外链资源。
- 采集异常：本轮必需资料采集无异常。
