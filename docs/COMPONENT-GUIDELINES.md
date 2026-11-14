# 组件开发、样式、依赖和无障碍规范

本项目当前使用原生ES modules，以`app.js`中的渲染函数和CSS类组合内部UI组件；没有React、Web Components注册系统、npm组件包或独立组件安装器。本文约束现有实现及后续扩展，不要求为文档结构增加新框架。

## 组件职责

| 类型 | 当前入口示例 | 边界 |
|---|---|---|
| 基础展示 | icon、tag、number/percent/price、datetime、empty | 只格式化或展示，不计算策略结论 |
| 布局 | pageHeading、modeBanner、errorBanner、drawerShell | 模式/错误可见，布局适配窄屏 |
| 待核对事项 | reviewTasks、reviewPanel、signalNextStep | 仅组织API已有事实与可用入口，不产生策略结论 |
| 业务展示 | signalTable、scoreParts、signalDetail、replayListHTML | 展示API证据，不伪造价格、分数或结果 |
| 页面 | renderMarket/Signals/Research/Settings | 组合模块与当前页面状态 |
| 连接管理 | connection-view.js、renderConnections、saveConnection | 独立行情/模型表单、凭据只写、来源/草稿/测试状态 |
| 分钟行情 | minute-view.js、renderMinutes、submitMinute | Tushare显式范围/预算、零请求准备、原始标签图表与未知项，不计算策略资格 |
| 控制 | api、loadSignals、refreshData、openSignal、action | 处理请求/状态，避免把网络操作混入纯展示辅助函数 |

同一组件只负责一类信息。新增代码优先复用已有辅助函数，不为每个页面复制状态标签、时间格式和错误语义。若需拆文件，保持ES module直接加载，并同步静态文件白名单与Python包资源。

## 数据与HTML安全

- API/用户字段进入模板前使用`escapeHTML`或`e`，不能把外部字符串作为可信HTML。SVG图标来自受控的内部映射，不加载来源未知的脚本或HTML。
- `null`显示为“—”或未知，不以0补齐；价格、收益、分数采用不同格式。所有行情时间固定Asia/Shanghai。
- 触发快照、最新状态、参与范围、投递结果分别表达。不得把DETECTED当已发机会、accepted当已读、反馈当成交。
- 长证据用details/JSON展示，保留来源、时间、版本和原因；不要用前端重新算分覆盖后端结果。

## 样式和依赖

使用[DESIGN](../DESIGN.md)中的token及已有button/panel/tag/drawer等样式。主色、风险色和模式提示保持一致；避免使用每页不同的颜色语义或重复局部样式。表格横向滚动、抽屉全宽和底部导航须在窄屏验证。

本轮共用样式将界面说明提高到12—14px、手机输入提高到16px，并加入独立控件边框与焦点token。ModeBanner展示完整行情日期/时间；SignalTable保留table语义，使用股票详情button和可聚焦的滚动区域，固定股票首列。不要把整行改成button角色覆盖表格语义。样式与静态检查的边界见[界面优化](development/ui-polish.md)。

任务化调整继续复用这些组件：概览条代替高大指标卡，reviewPanel紧邻异常提供诊断/通知/信号入口；signalNextStep按明确状态提供查看依据或记录处理的导航，不替用户交易。外部unknown/failed只读health.outbox，不能混入simulation_outbox。信号任务仅来自已加载记录，排除历史失效/过期及内部观察。完整范围与当前浏览器证据见[工作台调整](development/calm-workspace.md)。

当前没有前端构建链。新增依赖先说明具体能力、包大小、加载/离线影响和必要性；不要为简单格式化引入图表框架或整套组件库。外部资源缺失不能阻断核心机会与证据展示。

## 状态和异步交互

加载、空数据、错误、过期、暂停、模拟和成功须有可区分的表现。组件应展示API失败原因，不以空列表冒充无机会。请求期间避免重复提交，失败可恢复；反馈使用幂等键。

后台刷新不应清空参数草稿、正在输入的搜索或已展开证据。新版本保存不代表已切换运行策略；回放任务pending与评价窗口pending使用不同说明。当前轮询12秒是展示机制，不能声称真实行情延迟12秒。

未提交搜索词保存在signalQueryDraft，已应用查询保存在signalQuery；刷新不能静默应用草稿。render按稳定ID恢复股票按钮焦点和信号表横向位置。健康请求失败仍需渲染错误和缓存提示，不能仅因connected=false跳过错误展示。按钮请求期设置aria-busy，完成或失败后恢复可操作状态。

dataReady用于首次请求整组完成前的加载面，signalsLoaded区分尚未读取与成功的空列表；未知数量显示“—”。详情的data-detail-target只跳转到可聚焦的依据/反馈标题，不提交反馈；后台刷新按稳定ID恢复这些标题的焦点。新增界面校验只依赖Node内置模块和已有渲染模块。

图表/来源宽表保留容器内部横向位置，重绘后恢复图表与summary的键盘焦点；触发/最新视图使用各自不可变输入投影。报告下载使用鉴权响应的原文，不能重新序列化后冒用原报告哈希。

## 无障碍要求与现状

- 优先使用button、form、label、table、details等语义元素；图标按钮提供可读名称，装饰SVG不重复读出。
- 点击可操作的行/卡片要有键盘入口，不能只绑定鼠标。当前热点/信号行为包含相应键盘处理，后续需实测。
- 模态详情提供角色、标题关联、Esc关闭、焦点限制和关闭后焦点返回；打开时背景工作台设为inert，关闭时解除。
- 主导航提供aria-current，状态筛选提供aria-pressed；使用跳到主内容按钮，避免与Hash路由冲突。
- 仅靠红绿区分涨跌或健康不够，须有文字/符号；加载反馈使用适合的状态/错误提示。
- 可见焦点、文字对比度、放大和窄屏触控为验收目标；遵守减少动态效果偏好。

NEXT02已在内置浏览器完成桌面/手机尺寸视觉与基础键盘验收，包括后台刷新后的详情焦点返回。读屏、真机、完整对比度及WCAG验证未完成，不能声明完整无障碍支持。证据见[浏览器验收记录](development/next02-browser-acceptance.md)，补充待办在[TODO](../TODO.md)。

## 组件变更交付

记录组件用途、输入、状态、API依赖及受影响页面，验证正常/未知/错误/窄屏/键盘情景。重大交互更改补有价值的验证；纯文案或样式调整不编写镜像实现的无意义测试。更新[PAGE-STRUCTURE](PAGE-STRUCTURE.md)及必要的[REGISTRY清单](REGISTRY.md)，流程见[DEVELOPMENT](DEVELOPMENT.md)。
