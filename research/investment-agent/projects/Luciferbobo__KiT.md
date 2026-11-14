# 27 · Luciferbobo/KiT

## 固定版本与许可

2026-11-12 按用户提供的仓库入库，固定到 `main` 提交 `8dde755f07c54a0a9f8c3a1d5380ac378f321404`。根目录许可为 AGPL-3.0。上游要求 Python 3.10+ 与 PyTorch 2.4+，README 建议使用具备 CUDA 的 GPU 推理。 [固定提交](https://github.com/Luciferbobo/KiT/commit/8dde755f07c54a0a9f8c3a1d5380ac378f321404) · [许可](../sources/Luciferbobo__KiT/LICENSE.txt) · [依赖](../sources/Luciferbobo__KiT/requirements.txt) · [来源与哈希](../sources/Luciferbobo__KiT/provenance.json)

## 定位与参考点

KiT 将历史 OHLCV 编码为状态序列，使用流匹配生成多个预测周期的 K 线路径。固定 README 给出以历史截止时点为锚的预测、验证集推理与简单回测流程，并指向独立发布的演示数据和模型权重。该提交的训练及数据准备仍列为待完成，数据与权重的使用条件按对应发布记录核验。 [固定 README](https://github.com/Luciferbobo/KiT/blob/8dde755f07c54a0a9f8c3a1d5380ac378f321404/README.md) · [本地 README](../sources/Luciferbobo__KiT/README.txt)

归为 **P2 离线模型研究参考**，对应 FR12。可借鉴按历史锚点切窗、比较多预测周期和报告同期基准。若进入对照，先核对模型训练截止、数据授权及样本是否重叠，再以观势固定输入、现有确定性规则和明确成本比较。本次证据为固定文档、许可与依赖清单，预测和回测表现待实测。
