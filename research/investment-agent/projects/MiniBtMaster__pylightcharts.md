# 25 · MiniBtMaster/pylightcharts

## 固定版本与许可

2026-11-12 按用户提供的仓库入库，固定到 `master` 提交 `a4238198e7e1919fe9786d55f3dc73031cbc9438`。Python 包声明为 0.2.1，要求 Python 3.9+，依赖 pandas、NumPy 和 pywebview。根目录 Python 封装采用 MIT，内嵌 TradingView Lightweight Charts 采用 Apache-2.0，原项目保留了署名与 NOTICE。 [固定提交](https://github.com/MiniBtMaster/pylightcharts/commit/a4238198e7e1919fe9786d55f3dc73031cbc9438) · [许可](../sources/MiniBtMaster__pylightcharts/LICENSE.txt) · [NOTICE](../sources/MiniBtMaster__pylightcharts/NOTICE.txt) · [依赖](../sources/MiniBtMaster__pylightcharts/pyproject.toml) · [来源与哈希](../sources/MiniBtMaster__pylightcharts/provenance.json)

## 定位与参考点

Python 通过桥接驱动 WebView 内的 Lightweight Charts 渲染器。上游展示了 K 线、价格线、事件标记、十字线同步、独立窗格和增量更新。图表接收调用方提供的数据，行情供应与图表交互分别验证。 [固定中文 README](https://github.com/MiniBtMaster/pylightcharts/blob/a4238198e7e1919fe9786d55f3dc73031cbc9438/README.zh-CN.md) · [本地 README](../sources/MiniBtMaster__pylightcharts/README.txt)

归为 **P1 图表交互参考**，对应 FR08 / FR13。可借鉴价格与量能同轴定位、触发事件标记和局部更新。若进入原型验证，使用观势现有合成切片核对冻结突破位、失效位、触发与最新时点、窄屏和键盘操作。本次为固定文档与依赖声明核对，图表兼容性和性能待实测。
