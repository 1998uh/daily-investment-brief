---
name: daily-investment-brief
description: 生成或调整每日 A/H 股投资简报和私有持仓资金日报 PART-B。从雪球、微信公众号、微博采集文章并生成 Markdown/HTML；或在用户提供持仓时调用金融 MCP 与本机资金流适配器生成资金面报告。用于“生成报告”“重新生成日报”“采集文章”“生成资金日报”“生成 PART-B”、具体日期简报或持仓资金流分析。
---

# Daily Investment Brief

固定项目根目录：`D:\ai-project\daily-investment-brief`。所有命令和文件操作都以该目录为
`workdir`；不要在其他目录创建 `sources/`、`reports/`、`data/` 或 `private-reports/`。

## 路由

- 普通文章日报：走下方“Codex 日报流程”。
- 用户提供持仓并要求资金日报/PART-B：完整读取
  [资金日报契约](references/capital-daily.md)，运行
  `python -m pipeline.cli capital-daily --date YYYY-MM-DD --holdings-stdin`。
- 用户明确要求旧版内部 LLM、外部模型或批次流程：读取
  [旧版与外部模型流程](references/legacy-workflows.md)。默认不要使用这些流程。
- 修改假设 Schema、排查 JSON 校验错误时，读取
  [完整假设 Schema](references/hypothesis-schema.md)；正常日报不要读取它。

PART-B 独立运行，不受普通日报的三平台门禁影响，也不得从文章推断用户持仓。

## 三平台完整性门禁

普通文章日报必须同时包含当期的雪球、微博、微信公众号数据。采集后、执行 `prepare` 或任何
生成操作前，统计 `sources/YYYY-MM-DD/` 中三个平台的有效文章数。

只有三个平台都大于 0 才能自动继续。任一平台为 0、采集失败、登录失效或来源无法确认时：

1. 立即停止；不得执行 `prepare`、`verify`、`generate`，不得写入或覆盖日报、HTML 和假设文件。
2. 告知用户三个平台各自数量、缺失平台和已知原因。
3. 等待用户在看到缺失情况后明确确认使用不完整数据；原始“生成日报”请求不算授权。
4. 用户确认后，日报标题元信息和覆盖章节必须注明“数据源不完整”并列出缺失平台。

不得把缺失平台描述为“当日无观点”或“市场静默”。

## Codex 日报流程

### 1. 准备

日期未指定时用本地当前日期。若 `sources/YYYY-MM-DD/` 为空，先运行：

```powershell
python -m pipeline.cli collect --date YYYY-MM-DD
```

通过三平台门禁后，完整读取短版
[假设运行契约](references/hypothesis-contract.md)，再运行：

```powershell
python -m pipeline.cli prepare --date YYYY-MM-DD
```

`prepare` 生成精简上下文、到期证据任务和文章包。此时只读取：

- `reports/YYYY-MM-DD/codex-context.json`
- `reports/YYYY-MM-DD/evidence-tasks.json`

不要读取原始 `sources/`，也不要提前读取 `article-pack.md` 或整份 `article-index.jsonl`。

### 2. 先完成取证和验证

只为 `evidence-tasks.json` 中列出的假设查询数据：行情任务使用结构化金融工具；公告、政策和
事件任务优先官方来源。写入 `reports/YYYY-MM-DD/evidence.json`，然后运行：

```powershell
python -m pipeline.cli verify --date YYYY-MM-DD
```

完整读取 `verification.json`。其状态是历史假设的唯一事实来源，不得直接手写或润色状态。

### 3. 最后读取大文本并写报告

完成所有取证工具调用后，再完整读取：

- `templates/direct_brief_prompt.md`
- `reports/YYYY-MM-DD/article-pack.md`

按模板生成 `daily-brief.md` 和 `hypotheses.json`。要求：

- 上期验证只使用 `verification.json`，不从旧 Markdown 猜测。
- 每期只新增 2–4 条高价值、可跟踪、可证伪假设。
- 日报“下期关注”与 `hypotheses.json` 一一对应并展示完整假设 ID。
- 新假设包含来源、期限、反证条件和复查策略。

假设需要补 URL 时，用完整 `article_id` 在 `article-index.jsonl` 中定向搜索对应单行；不要读取
整份索引。已有 `article_id` 时允许来源 URL 留空。

最后运行：

```powershell
python -m pipeline.cli validate --date YYYY-MM-DD --strict
```

修复全部错误并重跑，直到退出码为 0。

## Token 纪律

- 不把 `sources/` 全文、完整 JSON 或哈希清单打印到对话；使用 `article-pack.md`。
- 不整份读取 `article-index.jsonl`；只按最终引用的 `article_id` 定向查行。
- 大文章包必须在行情、网页、证据和验证工具调用全部完成后再读取。
- 正常日报只读取短版契约；仅在校验失败时定向读取完整 Schema 的相关章节。
- 工具输出只保留数量、ID、缺失字段和必要摘录。
- 未到复查日的假设由 Python 保持状态，不发起搜索，也不要求 Codex重新判断。

## 主要产物

```text
reports/YYYY-MM-DD/codex-context.json   精简运行上下文
reports/YYYY-MM-DD/evidence-tasks.json  本期到期证据任务
reports/YYYY-MM-DD/article-pack.md       去重后的模型文章包
reports/YYYY-MM-DD/article-index.jsonl   URL、路径、时间和哈希索引
reports/YYYY-MM-DD/evidence.json         Codex 获取的证据
reports/YYYY-MM-DD/verification.json     Python 验证结果
reports/YYYY-MM-DD/hypotheses.json       当日新增假设
reports/YYYY-MM-DD/daily-brief.md        最终简报
reports/YYYY-MM-DD/daily-brief.html      HTML 简报
reports/YYYY-MM-DD/run-manifest.json     哈希和校验记录
```

完成后汇报三平台文章数、已复查假设、新增假设数、缺失证据和输出位置。
