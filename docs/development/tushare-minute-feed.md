# Tushare分钟接入与查看（0.2.5）

用户选择Tushare并自行开通分钟权限。本版完成分钟适配器、页面和有界手动获取，对应NEXT03、FR01/02/13。独立分钟记录尚未送入策略，真实提醒仍锁定。

## 开通与使用

1. 在Tushare开通“A股分钟RT”（最新/当日分钟）及需要的“A股历史分钟”。两项权限分别开通，依据：[实时分钟](https://tushare.pro/document/2?doc_id=374)、[当日分钟](https://tushare.pro/document/2?doc_id=457)、[历史分钟](https://tushare.pro/document/2?doc_id=370)。
2. 在“设置与诊断 → 行情API”选择Tushare，保存Token和不含Token的个人研究访问依据。环境变量`TUSHARE_TOKEN`优先于本地令牌文件；凭据不要发到聊天。
3. 打开“分钟行情”（`#minute-data`），选择接口范围和1—3只A股。历史模式显式选择早于今天的日期，最多7个自然日；其它模式不接受历史日期。
4. 勾选已开通所选接口及本次个人研究用途，点击“检查请求 · 零请求”。准备通过不证明服务端分钟权限。
5. 点击“获取分钟数据”才发起本次请求。两次获取至少间隔60秒，单次超时15秒，串行间隔6.1秒；不自动采集、重试、分页或换源。休市时核对返回日期和空记录。

| 范围 | 固定接口/频度 | 请求数 |
|---|---|---|
| 最新闭合分钟 | `rt_min` / `1MIN`，批量显式代码 | 1 |
| 当日分钟 | `rt_min_daily` / `1MIN`，每只单独请求 | 1—3 |
| 历史分钟 | `stk_mins` / `1min`，显式日期09:00—15:30 | 1—3 |

原行情API页的Tushare连接测试检查股票基础信息，不证明分钟权限；本页按实际目标接口另验。

## 记录与限制

原始字节、哈希、接收时间和派生记录在数据库旁`minute-data/<记录ID>/`。目录0700、文件0600，状态文件原子写入，拒绝符号链接；独占文件锁防止重复采集。重启后未完成记录明确显示，不自动续传。此目录不进入SQLite、数据库备份、策略导出或wheel。

Token只从连接存储读取，向固定HTTPS地址POST，不进入URL、报告、日志或页面。权限错误、429、传输失败和敏感响应停止相关请求；错误正文不存档。旧目录保留，失败不把旧价格拼成新结果。GET与12秒页面轮询只读本机记录。

每股展示最近240条，图表最近120条，表格最近60条；完整采样仍保留。价格用Decimal，股/元映射保留文档依据，单位未独立核验。单行量额没有转成策略累计口径；历史最早可见时间、标签起止、完成性和复权未知时保留null，不补0或当前时间。

当日接口字段表写`ts_code`，示例表头写`code`，当前严格按字段表校验`ts_code`及`freq=1MIN`，不符则保留原始字节并失败。官方示例还含09:30点，集合竞价和闭合标签须实测。完成分钟、同期历史量能、基准、历史成员/风险状态和复权链未齐备前，不伪装标准batch输入evaluate；策略/发布就绪为false。

## 接口与验证

`GET /api/v1/minute-data`只读本机记录；POST同路径下`/prepare`为零请求检查，`/fetch`为显式获取。请求必须仅含`schema_version,mode,symbols,start_date,end_date,access_confirmed`，见[样例](../../configs/minute-feed-tushare-template.json)。`latest/session`日期为null，`history`必须提供日期；此格式不同于vendor-sample完整计划。

新增`minute_feed.py`和`minute-view.js`，复用现有采样器/连接存储，静态白名单与包资源同步，无第三方运行依赖。独占文件锁能力要求沿用worker/dispatcher；不支持的平台仍可查看记录，获取明确报错。

本轮2026-11-08 UTC实际验证：

- 完整321项Python、29项Node与CLI帮助通过，新增17项Python、7项前端检查。首次定向检查发现敏感响应后仍继续请求，修为整轮停止后通过；见[自动记录](evidence/tushare-minute-20261108/verification.json)。
- 临时独立库、合成Token和fake Tushare通过配置/清空Key、3股图表、历史范围/零请求预算、12秒草稿保留及503恢复，320/390/768/1280px无页面横向溢出；见[浏览器记录](evidence/tushare-minute-20261108/browser.json)。
- 离线wheel的31模块/7静态/2fixture逐字匹配，Python3.9仓库外新旧配置和缺凭据0请求准备通过，未发布；见[包记录](evidence/tushare-minute-20261108/wheel.json)。
- 本机Tushare仍未配置，[准备报告](evidence/tushare-minute-20261108/preparation.json)计划1次、实际0次，缺Token和访问确认。本轮真实Tushare、模型和通知请求均0，历史304/22项不重记，没有账户数据质量验收或策略切换。

截图：[桌面](evidence/tushare-minute-20261108/minute-desktop-clean.png)、[手机顶部](evidence/tushare-minute-20261108/minute-mobile-top.png)、[手机记录](evidence/tushare-minute-20261108/minute-mobile-records.png)，均为模拟验收样本。真机、读屏、其它浏览器和200%缩放仍待验。
