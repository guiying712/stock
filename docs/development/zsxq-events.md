# 知识星球事件接入：首次真实读取、独立事件库与使用

日期：2026-11-14（America/Los_Angeles）。映射 FR17 / NEXT12，目标见[专项需求](../requirements/05-知识星球事件选股.md)与[持续采集方案](../requirements/06-持续事件采集与买入提醒方案.md)。

## 已完成

用户已在官方 OAuth 页面完成授权，指定群 `51128424448184` 的主题读取成功。独立工具 `stockradar.zsxq_events` 使用 Python 标准库调用官方 CLI，只允许该群、每次 1—20 条，不翻页、不启动后台调度、不写运行策略数据库。

在此基础上新增独立事件库 `stockradar.zsxq_store`：使用与策略库完全隔离的 SQLite 数据库（WAL、权限 `0600`、群 ID 锁定和独占文件锁 `.collect.lock`），实现跨次采集的主题去重、修订版本追加、倒序分页连续覆盖水位与缺口（gap）记录，以及按北京时间（`Asia/Shanghai`）自然日预先记账的每日请求预算（发网前落库，进程崩溃或请求失败不回退已消耗预算）。

本轮先直接调用官方 CLI，再通过新采集器验证；合计两次主题列表请求，各返回 20 条，同一组 20 个主题的内容版本哈希一致。采样覆盖的帖子发布时间为北京时间 2026-11-14 12:36:12—21:07:56（UTC `2026-11-14T04:36:12.577000+00:00` 至 `2026-11-14T13:07:56.259000+00:00`）。14 条有文本，6 条仅图片占位，8 条带图片或附件；附件未解析，列表文本未逐条请求详情核验，不代表全天或历史全量。两次真实快照导入独立事件库后核对：首批 20 条入库为 `initial` 覆盖段，第二批 20 条全部识别为 `unchanged` 且覆盖判定为 `contiguous`，开放缺口 `0`，再次重复导入同快照按 `source_sha256` 幂等跳过（`duplicate=true`）。

原始响应只在临时文件中处理，规范化后删除该临时响应。持久记录按白名单保存文本、主题/图片/附件 ID、发布时间、修订哈希和本地观察时间；去除头像、账户资料和签名图片 URL。`event_time`、历史 `available_at` 未核实时保留 null。导入快照的观察时点是本轮处理时点，不伪称系统在帖子发布时已获知。

## 本机使用

官方 CLI `0.5.1` 已按 npm 公布的 SHA-512 校验，在项目私有 `.local/zsxq/0.5.1/` 保留原生二进制。该目录已加入忽略规则，不随源码包交付；不用 Node 运行时。它是有版本的外部采集工具，由上游维护，升级须重新核对认证和返回结构。

```sh
# 用户需要重新授权时，官方 CLI 自行管理系统 Keychain 凭据。
.local/zsxq/0.5.1/zsxq-cli auth login

# 手动读一页快照目录，输出目录必须为新目录；已有目录在请求前拒绝。
python3 -m stockradar.zsxq_events \
  --cli .local/zsxq/0.5.1/zsxq-cli \
  --limit 20 \
  --output .local/zsxq/captures/manual-next

# 已取得的官方 CLI JSON 可离线导入为快照目录；该命令不发网。
python3 -m stockradar.zsxq_events \
  --input /absolute/path/topics.json \
  --output .local/zsxq/captures/import-next

# 将已保存的快照目录导入独立事件数据库（校验 manifest SHA-256，不发网）。
python3 -m stockradar.zsxq_store \
  --db .local/zsxq/events.sqlite3 \
  import .local/zsxq/captures/20261114-first .local/zsxq/captures/20261114-adapter-check

# 手动带预算读取最新一页并直接入库（发网前预先扣除北京时间当日预算）。
python3 -m stockradar.zsxq_store \
  --db .local/zsxq/events.sqlite3 \
  fetch --cli .local/zsxq/0.5.1/zsxq-cli --limit 20 --daily-budget 10

# 只读查看独立事件库汇总（主题数、修订数、覆盖段、开放缺口、当日预算与边界标志）。
python3 -m stockradar.zsxq_store \
  --db .local/zsxq/events.sqlite3 \
  status --daily-budget 10
```

输出 `topics.json` 与 `manifest.json`，以及独立事件库 `.local/zsxq/events.sqlite3`。本轮保存位置：

- `.local/zsxq/captures/20261114-first/`：首次 CLI 返回的离线规范化导入。
- `.local/zsxq/captures/20261114-adapter-check/`：采集器真实读取。
- `.local/zsxq/events.sqlite3`：导入上述两份真实快照后的独立事件库（20 个主题、20 个版本、0 个开放缺口）。
- `.local/zsxq/reports/20261114-事件候选研究.md`：本轮人工核实、归并及三只候选的研究记录。

输出为研究数据，须通过鉴权页面和统一转义后才能用于未来 UI；不能把外部帖子当 HTML 插入页面。首次读取不把用户拥有群权限推导为公共转载授权；私有文本仅保存在本机忽略目录。

## 本轮验证与限制

`python3 -m unittest tests.test_zsxq_events -v`：16 项通过（含 `ZsxqTests` 11 项与 `ZsxqStoreTests` 5 项）。首轮发现 Python 3.9 不接受服务商 `+0800` 紧凑时区，修复为兼容转换后重跑通过。测试覆盖指定群、单页与自然日预算预先记账、中断恢复、失败响应、图片缺口、脱敏、时间、页内与跨次去重、稳定修订哈希、乱序离线导入、覆盖水位与未重叠缺口（`gap_recorded` / `complete_to_start`）、独占锁与符号链接拒绝、输出不可覆盖及哈希核对。两个模块 CLI 帮助均通过，实际采集器完成一页真实读取并经 `zsxq_store` 验证 20 个版本跨次连续一致。

本轮在当前沙箱环境还运行了全量 `python3 -m unittest discover -s tests -v`（共 369 项：352 项非网络/非本地端口测试通过，17 项需要绑定本地 `127.0.0.1` 临时 HTTP 端口的测试因沙箱 socket 权限限制报错，未在沙箱外重跑或伪称全量 HTTP/Node/浏览器/wheel 验收通过）。没有修改原有策略评估、运行配置、真实策略数据库和通知通路；没有新增自动分析、行情请求或定时任务。软件版本沿用现有源码 `0.2.8`。

目前的代码实现是手动主题采集、证据快照及独立事件库（去重、修订、覆盖段与缺口、每日请求预算），事件语义归并、公开事实检索及候选研究由本轮人工分析完成。尚缺：图片/附件提取、历史分页续采游标、自动公司关联、当前行情与估值筛选、工作台事件页面。

三只研究候选没有完成当前行情、估值、流动性及风险过滤，不能称为已通过的买入信号。`automatic_collection=false`、`strategy_input_ready=false`、`release_allowed=false`，原 `live_alert` 锁定保持不变。

上游依据：[官方工具](https://github.com/unnoo/zsxq-skill)、[OAuth](https://github.com/unnoo/zsxq-skill/blob/main/skills/zsxq/references/auth-errors.md)、[主题列表](https://github.com/unnoo/zsxq-skill/blob/main/skills/zsxq/references/group-topics.md)。
