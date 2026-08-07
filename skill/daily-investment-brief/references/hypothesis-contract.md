# 假设运行契约

用于每日 Codex 流程。完整字段示例只在校验失败或修改 Schema 时读取
`hypothesis-schema.md`。

## 顺序

1. `prepare` 后只读 `codex-context.json` 和 `evidence-tasks.json`。
2. 按任务取证并写 `evidence.json`。
3. 运行 `verify`，以 `verification.json` 为唯一历史状态来源。
4. 完成所有工具调用后才读 `article-pack.md` 和日报模板。
5. 写 `daily-brief.md`、`hypotheses.json`，运行严格校验。

## 证据

`evidence.json` 顶层固定为：

```json
{"schema_version":"1.0","report_date":"YYYY-MM-DD","items":[]}
```

行情证据必填：`evidence_id`、`hypothesis_id`、`evidence_type=market_metric`、`metric`、
`entity{name,thscode}`、`observed_date`、数值型 `value`、`unit`、`provider`、`fetched_at`。

事件证据必填：`evidence_type=event`、`event_type`、`title`、`published_at`、
`source_level`、`publisher`、`url`、`quote`、布尔型 `supports`、`fetched_at`。
`source_level` 只用 `official/authoritative/media/social`；媒体和社交内容不能独立触发正式结论。

只有用户明确判断时才能写 `manual_resolution`；不得替用户创建人工确认。

禁止用股价代替订单、库存、产量、行业价格、政策或公告事实；不得把缺失值改写成方向结论。

## 新假设

`hypotheses.json` 顶层固定为：

```json
{"schema_version":"1.0","report_date":"YYYY-MM-DD","hypotheses":[]}
```

每期 2–4 条。每条必填：

- `id`：`H-YYYYMMDD-NNN`，日期与 `created_date` 一致。
- `claim`、`subject{type,name,thscode}`。
- 非空 `sources`；每个来源包含 `author`、`quote`，以及 `article_id` 或 `url` 至少一项。
- `deadline`、`verification_mode`、`conditions`、`falsification_conditions`。
- `review_policy`：`daily/weekly/event_triggered/deadline_only`。
- `status=pending`。

`event_triggered` 还必须提供非空 `trigger_terms`；需要指定首次复查日时使用
`next_review_date`，且必须位于创建日和截止日之间。

默认复查策略：量化 `daily`，事件与混合 `weekly`，人工 `deadline_only`。只有确有明确触发词时
使用 `event_triggered`。未到复查日的假设不进入证据任务。

量化规则只允许 `price_threshold`、`relative_return`、`turnover_threshold`、`capital_flow`。
量化假设必须同时有支持和强反证条件；其他判断使用 `event/hybrid/manual`，不得自创规则名。

## 一致性

- 日报必须展示所有本期 `verification.json` 结果和所有新假设完整 ID。
- 新假设表与 `hypotheses.json` 一一对应，不重复仍活跃的同义假设。
- `confirmed/falsified` 必须引用真实证据 ID。
- 不得直接修改 `verification.json`，不得把 `pending` 润色成方向性结论。

状态映射：`pending` 待验证，`partially_confirmed` 部分兑现，`confirmed` 已兑现，
`falsified` 已证伪，`inconclusive` 尚无定论，`unavailable` 数据不可用，`expired` 已过期。
