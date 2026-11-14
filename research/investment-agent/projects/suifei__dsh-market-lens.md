# 23 · suifei/dsh-market-lens

## 版本与来源

2026-11-11 按用户提供的仓库加入资料库。固定到 `main` 提交 `9ed847797bc0eabcd3d46f3724da4df40e4fcbba`。包声明为 `@suifei/dsh-market-lens` 0.34.8，根目录许可与包声明均为 MIT。项目依赖 DeepSeek Harness 宿主及其面板和工具接口。 [固定提交](https://github.com/suifei/dsh-market-lens/commit/9ed847797bc0eabcd3d46f3724da4df40e4fcbba) · [许可](../sources/suifei__dsh-market-lens/LICENSE.txt) · [包声明](../sources/suifei__dsh-market-lens/package.json) · [来源及哈希](../sources/suifei__dsh-market-lens/provenance.json)

## 项目定位与数据来源

MarketLens 是 DSH 内的自选股、行情图表和价格提醒插件。宿主统一为面板和只读工具提供行情归一化、TTL 缓存和在途请求去重。固定 README 记录 A 股及港股优先东方财富、备选腾讯，美股优先 Yahoo chart、备选腾讯。价格提醒在宿主后台按规则评估，并为各条规则设置静默期。 [固定 README](https://github.com/suifei/dsh-market-lens/blob/9ed847797bc0eabcd3d46f3724da4df40e4fcbba/README.md) · [本地快照](../sources/suifei__dsh-market-lens/README.txt)

## 观势的参考取舍

| 对应工作 | 参考点 | 验证条件 |
|---|---|---|
| FR02 / NEXT03、FR13 / NEXT11 | 宿主统一数据请求，上一轮结束后再安排下一次刷新，页面恢复可见时刷新，并保留自选列表滚动位置 | 用隔离样本核对去重、陈旧状态、代码前导零及面板和图表的一致性。数据接入按观势的 HTTPS、来源和时点契约验收 |
| FR08 / FR09 | 后台独立评估提醒，按规则设静默期，从提醒记录跳回对应标的 | 用模拟投递核对冷却、去重与重启恢复，保留观势的扫描事务与投递状态语义 |

归为 **P1 资料参考**。本次核对固定 README、许可与包声明。供应商权限、分钟完成性及提醒运行行为待独立验证。

2026-11-11 追加[关键代码核查](../audits/2026-11-11-data-sources/dashboards-and-other.md)：确认上述市场路由；K 线仅日/周/月，快讯新浪→东财，财务/公告/股吧来自东财。未请求行情或测试提醒。
