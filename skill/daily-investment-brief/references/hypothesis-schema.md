# 完整假设 Schema

仅用于修改 Schema 或定位严格校验错误。正常日报使用 `hypothesis-contract.md`。

## Hypothesis

```json
{
  "id": "H-20260807-001",
  "created_date": "2026-08-07",
  "claim": "半导体板块未来5个交易日跑赢沪深300至少2个百分点",
  "subject": {"type": "index", "name": "半导体板块", "thscode": "唯一代码"},
  "sources": [
    {
      "author": "作者名",
      "article_id": "A-文章ID",
      "url": "原文URL",
      "quote": "直接相关的作者原话"
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
  "review_policy": "daily",
  "next_review_date": "2026-08-08",
  "status": "pending"
}
```

人工、事件或混合假设可以使用空条件，但必须提供 `manual_reason`。显式使用
`review_policy=event_triggered` 时必须提供 `trigger_terms` 字符串数组。

## Market evidence

```json
{
  "evidence_id": "E-20260807-001",
  "hypothesis_id": "H-20260806-001",
  "evidence_type": "market_metric",
  "metric": "index.close",
  "entity": {"name": "创业板指", "thscode": "399006.SZ"},
  "observed_date": "2026-08-07",
  "value": 3522.18,
  "unit": "point",
  "provider": "hithink-finance",
  "request_id": "",
  "source_url": "",
  "fetched_at": "2026-08-07T09:05:00+08:00"
}
```

## Event evidence

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
  "quote": "直接相关原文",
  "supports": true,
  "fetched_at": "2026-08-07T09:10:00+08:00"
}
```

## Manual resolution

```json
{
  "evidence_id": "E-20260807-003",
  "hypothesis_id": "H-20260806-005",
  "evidence_type": "manual_resolution",
  "resolved_status": "inconclusive",
  "note": "用户确认本轮证据冲突，暂不判断。",
  "resolved_by": "user",
  "fetched_at": "2026-08-07T09:15:00+08:00"
}
```

状态只能由 `verify` 生成。支持的量化规则、状态枚举和字段级错误以
`pipeline/hypothesis_models.py` 为最终定义。
