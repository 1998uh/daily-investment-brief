# 私有持仓资金日报 PART-B 契约

## 执行流程

1. 从用户本次对话读取持仓，不复用文章里的持仓，也不建立长期持仓档案。
2. 要求每项至少包含代码、名称、资产类型，以及 `market_value` 或 `weight_pct`。缺失权重时可以继续，但必须声明只能做数量分析。
3. 使用 `hithink-finance-meta` 搜索并转换为带市场后缀的唯一 `thscode`；有多个候选时只确认一次，不猜 `.SH`、`.SZ` 或 `.BJ`。
4. A 股调用 `hithink-finance-a-share` 补全当日涨跌；ETF 调用 `hithink-finance-fund` 补全资料、行情和披露持仓。
5. 优先使用用户提供的板块；缺失时使用 `hithink-finance-a-share-index` 的行业/板块目录与成分进行映射。无法唯一映射时写 `待映射`，不得猜测。
6. 把规范化 JSON 通过进程 stdin 交给 `capital-daily`，不要把持仓 JSON 放进命令行参数。Windows PowerShell 先把 `$OutputEncoding` 和 `[Console]::OutputEncoding` 设置为 UTF-8，避免中文名称被管道转码。
7. 读取生成的 Markdown，检查数据日期、覆盖数、窗口天数、缺失项和免责声明后再汇报路径与摘要。

## 输入 JSON

可以传数组，也可以传 `{"holdings": [...]}`。字段如下：

```json
{
  "holdings": [
    {
      "thscode": "600519.SH",
      "name": "贵州茅台",
      "asset_type": "a-share",
      "market_value": 100000,
      "sector": "食品饮料",
      "price_change_ratio_pct": -0.66
    },
    {
      "thscode": "510300.SH",
      "name": "沪深300ETF",
      "asset_type": "fund-etf",
      "weight_pct": 8.5,
      "sector": "沪深300"
    }
  ]
}
```

- `asset_type` 只支持 `a-share` 和 `fund-etf`；其他资产进入未覆盖清单。
- 同一代码只能出现一次。多账户同一标的先合并市值或权重。
- `market_value` 与 `weight_pct` 至少提供一个；同一批次优先统一使用 `market_value`。
- 代码必须保留交易所后缀。裸代码先走元数据 MCP 消歧。
- `sector` 与 `price_change_ratio_pct` 可由 MCP 补全。

## 数据与失败边界

- 同花顺 MCP 负责标的、行情、指数/板块与 ETF 数据；本机 Eastmoney 适配器负责资金流。
- 当前公开接口提供主力、超大单、大单、中单、小单；不提供可信的全市场净额时显示 `—`，不得将分档合计伪装为全市场净额。
- 5 日与 20 日累计只读取 `data/capital-flow/` 的真实每日缓存。历史不足时显示实际天数。
- 非交易日或请求日期与最新数据不一致时，报告同时显示请求日期与实际数据日期。
- 网络、限流、字段变化或空数据经有限重试仍失败时，生成带错误说明的报告并返回非零状态；不要给出顺风/逆风结论。
- 港股、美股、现金和未消歧资产只列入未覆盖，不替换成相似 A 股。

## 输出检查

确认输出位于 `private-reports/YYYY-MM-DD/capital-daily.md`，并且包含：

- 数据来源、请求日期、实际数据日期；
- 权益仓位、顺风/逆风/无法判断持仓；
- 板块当日、5 日和 20 日主力资金流；
- 实际历史窗口、缺失字段和未覆盖资产；
- “仅为数据分析，不构成投资建议”。
