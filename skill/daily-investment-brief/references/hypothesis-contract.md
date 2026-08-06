# 结构化假设与自动验证契约

本契约用于 Codex 原生日报工作流。Codex 负责阅读、取数和写作；项目命令负责历史账本、确定性验证和一致性校验。

## 默认执行顺序

```powershell
python -m pipeline.cli prepare --date YYYY-MM-DD
```

然后：

1. 完整读取 `reports/YYYY-MM-DD/codex-context.json`。
2. 读取其中列出的当日文章。
3. 对 `required_evidence` 中的行情任务调用结构化金融 MCP。
4. 名称不唯一时先搜索并消歧为唯一 `thscode`。
5. 对公告、政策和事件任务优先搜索官方来源。
6. 写入 `reports/YYYY-MM-DD/evidence.json`。
7. 运行：

```powershell
python -m pipeline.cli verify --date YYYY-MM-DD
```

8. 完整读取 `verification.json`，以其中状态为历史假设的唯一事实来源。
9. 生成 `daily-brief.md`，每条历史验证和新假设都必须展示完整假设 ID。
10. 写入 `hypotheses.json`。
11. 运行：

```powershell
python -m pipeline.cli validate --date YYYY-MM-DD --strict
```

12. 根据校验错误修改产物并重跑，直到退出码为 0。

## 禁止事项

- 不得直接手写或修改 `verification.json` 的状态。
- 不得把行情缺失值改写成涨跌、多空或资金方向。
- 不得用股票涨跌代替订单、产量、库存、行业价格或政策事实。
- 不得把媒体或社交平台内容当成正式公告。
- 不得根据作者观点反推作者未披露的持仓。
- 不得生成没有原文来源、期限或反证条件的新假设。
- 不得把 `pending` 润色成「基本兑现」或其他方向性结论。

## `evidence.json`

文件必须使用 UTF-8 JSON：

```json
{
  "schema_version": "1.0",
  "report_date": "2026-08-07",
  "items": []
}
```

### 行情证据

```json
{
  "evidence_id": "E-20260807-001",
  "hypothesis_id": "H-20260806-001",
  "evidence_type": "market_metric",
  "metric": "index.close",
  "entity": {
    "name": "创业板指",
    "thscode": "399006.SZ"
  },
  "observed_date": "2026-08-07",
  "value": 3522.18,
  "unit": "point",
  "provider": "hithink-finance",
  "request_id": "上游请求ID；服务未返回时可为空字符串",
  "source_url": "",
  "fetched_at": "2026-08-07T09:05:00+08:00"
}
```

要求：

- `value` 必须是数值，不得写带单位字符串。
- 单位必须与假设条件一致。
- 收盘价使用 `close` 或以 `.close` 结尾的 metric。
- 成交额使用 `turnover` 或以 `.turnover` 结尾的 metric。
- 主力资金净流入使用 `main_net_inflow` 或以其结尾的 metric。
- 相对收益必须提供标的和基准的对齐收盘价，由 Python 计算，不要直接填写结论。
- 同一日期、实体和指标重复查询时，只保留最新、口径一致的一条证据。

### 事件证据

```json
{
  "evidence_id": "E-20260807-002",
  "hypothesis_id": "H-20260806-002",
  "evidence_type": "event",
  "event_type": "policy_release",
  "title": "正式政策标题",
  "published_at": "2026-08-07",
  "source_level": "official",
  "publisher": "发布机构",
  "url": "官方URL",
  "quote": "与假设直接相关的原文",
  "supports": true,
  "fetched_at": "2026-08-07T09:10:00+08:00"
}
```

证据等级：

- `official`：监管文件、交易所公告、公司公告。
- `authoritative`：官方发布会、权威统计和一手公开数据。
- `media`：主流媒体或行业媒体。
- `social`：雪球、微博、公众号等观点材料。

媒体和社交证据只用于描述进展，不能独立触发正式的事件结论。

### 人工解决记录

只有用户明确作出人工判断时使用：

```json
{
  "evidence_id": "E-20260807-003",
  "hypothesis_id": "H-20260806-005",
  "evidence_type": "manual_resolution",
  "resolved_status": "inconclusive",
  "note": "用户确认本轮财报季证据冲突，暂不判断。",
  "resolved_by": "user",
  "fetched_at": "2026-08-07T09:15:00+08:00"
}
```

不得代替用户创建人工确认记录。

## `hypotheses.json`

```json
{
  "schema_version": "1.0",
  "report_date": "2026-08-07",
  "hypotheses": []
}
```

每期提取 3-5 条最有价值、可跟踪的假设。不要为了凑数收录泛泛判断。

### 量化假设

```json
{
  "id": "H-20260807-001",
  "created_date": "2026-08-07",
  "claim": "半导体板块未来5个交易日跑赢沪深300至少2个百分点",
  "subject": {
    "type": "index",
    "name": "半导体板块",
    "thscode": "唯一板块代码"
  },
  "sources": [
    {
      "author": "作者名",
      "article_id": "codex-context.json 中的 article_id",
      "url": "原文URL",
      "quote": "与假设直接相关的作者原话"
    }
  ],
  "deadline": "2026-08-14",
  "verification_mode": "quantitative",
  "conditions": [
    {
      "type": "relative_return",
      "entity": "板块代码",
      "benchmark": "000300.SH",
      "operator": ">=",
      "value": 2.0,
      "unit": "percentage_point",
      "window_trading_days": 5
    }
  ],
  "falsification_conditions": [
    {
      "type": "relative_return",
      "entity": "板块代码",
      "benchmark": "000300.SH",
      "operator": "<=",
      "value": -3.0,
      "unit": "percentage_point",
      "window_trading_days": 5
    }
  ],
  "status": "pending"
}
```

### 人工或混合假设

```json
{
  "id": "H-20260807-002",
  "created_date": "2026-08-07",
  "claim": "正式政策不会在一个月内造成产业订单取消",
  "subject": {
    "type": "theme",
    "name": "光模块政策风险",
    "thscode": ""
  },
  "sources": [],
  "deadline": "2026-09-07",
  "verification_mode": "hybrid",
  "conditions": [],
  "falsification_conditions": [],
  "manual_reason": "需要正式政策文件、公司公告或客户订单披露，不能用股价代替。",
  "status": "pending"
}
```

实际文件中的 `sources` 不得为空；示例为空仅用于突出其他字段。

## 支持的确定性规则

第一版只允许：

- `price_threshold`
- `relative_return`
- `turnover_threshold`
- `capital_flow`

不属于这四类的内容使用 `manual` 或 `hybrid`，不得自创规则名。

### 状态含义

- `pending`：尚未满足证实或证伪条件。
- `partially_confirmed`：部分支持条件满足，但完整规则未满足。
- `confirmed`：所有必要支持条件满足。
- `falsified`：至少一个预定义强证伪条件满足。
- `inconclusive`：到期时证据冲突或不足。
- `unavailable`：到期时所需数据不可用。
- `expired`：到期且不再继续跟踪。

最终状态只能以 `verification.json` 为准。

## 日报一致性

日报必须：

- 在历史验证表中展示完整假设 ID，例如 `H-20260806-001`。
- 对状态使用 `verification.json` 原值对应的中文表达。
- 列出关键观测值和证据来源。
- 在「下期关注」中展示当日每个新假设的完整 ID。
- 保证日报中的新假设与 `hypotheses.json` 一一对应。
- 不重复创建与仍处于活跃状态的历史假设语义相同的新 ID。

推荐状态映射：

```text
pending                 待验证
partially_confirmed     部分兑现
confirmed               已兑现
falsified               已证伪
inconclusive            尚无定论
unavailable             数据不可用
expired                 已过期
```
