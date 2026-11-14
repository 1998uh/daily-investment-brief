---
name: daily-investment-brief
description: 生成或调整每日 A/H 股投资简报和私有持仓资金日报 PART-B。从雪球、微信公众号、微博采集文章并生成 Markdown/HTML；或在用户提供持仓时调用金融 MCP 与本机资金流适配器生成资金面报告。用于“生成报告”“重新生成日报”“采集文章”“生成资金日报”“生成 PART-B”、具体日期简报或持仓资金流分析。
---

# Daily Investment Brief

固定项目根目录：`D:\project\daily-investment-brief`。所有命令和文件操作都以该目录为
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

### 1. 先生成日报

日期未指定时用本地当前日期。后台雪球/微博按自然日归档到 `sources/_raw/YYYY-MM-DD/`，
该目录只供人工检查，不是日报输入。即使 `sources/YYYY-MM-DD/` 已存在，也必须先执行：

```powershell
python -m pipeline.cli social-health
python -m pipeline.cli collect --date YYYY-MM-DD --platform wechat
python -m pipeline.cli materialize --date YYYY-MM-DD
python -m pipeline.cli market-snapshot --date YYYY-MM-DD
```

`materialize` 从 SQLite 查询 `[前一日 08:00, 当日 08:00)` 并原子重建正式输入目录。
Codex 不得自行遍历 `_raw` 或跨日期目录判断归属。任一平台为 0 或 `social-health` 非 0 时执行
三平台门禁；通过后再生成日报文章包。日报主流程不等待假设取证，也不要求先完成历史假设验证。

### 强制写作契约

普通“生成日报”必须使用 Codex 原生写作。在写任何日报正文前，完整读取项目根目录下的
`templates/direct_brief_prompt.md`；该文件是强制格式契约，不得自行简化、替换结构或改用上一期日报。
Skill 与模板属于指令来源，不受下方“日报阶段只读取”对内容来源的限制。

先生成文章包，再由 Codex 撰写日报：

```powershell
python -m pipeline.cli prepare --date YYYY-MM-DD
```

`prepare` 只负责生成文章包和可选的跟踪上下文，不负责撰写正式日报。不得调用项目内部
`generate`、fallback、外部 LLM 或批次摘要代写普通日报；只有用户明确要求旧版或外部模型流程时，
才按“路由”读取对应契约。若 `prepare` 命令不存在但当期文章包已经存在，直接继续原生写作；若必要
输入缺失，报告缺失项，不得编造。

日报阶段的内容来源只读取：

- `reports/YYYY-MM-DD/codex-context.json`
- `reports/YYYY-MM-DD/article-pack.md`

不要读取原始 `sources/`，也不要整份读取 `article-index.jsonl`。
不得读取上一期 `daily-brief.md` 作为本期内容、选题、结构或措辞参考；历史正文不进入生成上下文。

日报必须完整保留当日文章中的作者观点、原话、持仓/操作表达、观点冲突和后续观察项。把“作者观点”与“已验证事实”分层标注：证据不足时可以写“作者认为”或“待验证”，但不得因此删除观点。

按 `templates/direct_brief_prompt.md` 写入 `daily-brief.md` 后，将该 Markdown 机械渲染为
`daily-brief.html`。渲染只能转换格式，不得改写、摘要或删减正文，也不得调用项目内部 `validate`
命令生成 HTML。

交付前人工检查：

- 标题元信息、“今日三句话”、“一页速览”、“大盘量能趋势”和“今日注意事项”位于事件正文之前。
- 正文按当天真实事件动态命名；有足量表格和带作者、平台标注的 blockquote 原话。
- 持仓只来自原文明确披露，不推断；分歧具体到作者、结论和论据。
- 数据覆盖表使用 `codex-context.json` 的统计；核心矛盾图为当天专属 `graph TD` 图并附维度表，图与表只使用当天事件和数字；量能数字必须来自 `market_metrics`。
- 未要求跟踪时不创建假设；Markdown 与 HTML 内容一致。任一项不合格时先重写再交付。

### 2. 可选：假设跟踪与验证

只有用户明确要求验证假设、跟踪上期观点或补充证据时，才执行本阶段。

先运行：

```powershell
python -m pipeline.cli prepare --date YYYY-MM-DD
```

此时才读取 `evidence-tasks.json`，并只为其中列出的假设查询数据：

只为 `evidence-tasks.json` 中列出的假设查询数据：行情任务使用结构化金融工具；公告、政策和
事件任务优先官方来源。写入 `reports/YYYY-MM-DD/evidence.json`，然后运行：

```powershell
python -m pipeline.cli verify --date YYYY-MM-DD
```

完整读取 `verification.json`。其状态是历史假设的唯一事实来源，不得直接手写或润色状态。

验证完成后运行：

```powershell
python -m pipeline.cli validate --date YYYY-MM-DD --tracking
```

验证阶段要求：

- 历史验证只使用 `verification.json`，不得读取上一期 `daily-brief.md` 作为内容或结构参考。
- 每期只新增 0–4 条高价值、可跟踪、可证伪假设；宁缺毋滥，不得为凑数创建假设。
- 验证结果写入独立产物，不得重写或删减已经生成的 `daily-brief.md`。
- 假设需要补 URL 时，用完整 `article_id` 在 `article-index.jsonl` 中定向搜索对应单行；不要读取整份索引。

修复全部验证错误并重跑，直到退出码为 0。没有验证需求时，不要为了满足严格校验创建空泛假设。

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
reports/YYYY-MM-DD/evidence-tasks.json  可选：本期到期证据任务
reports/YYYY-MM-DD/hypothesis-dedup-index.json 历史假设去重索引（不得用于选题）
reports/YYYY-MM-DD/article-pack.md       去重后的模型文章包
reports/YYYY-MM-DD/article-index.jsonl   URL、路径、时间和哈希索引
reports/YYYY-MM-DD/evidence.json         可选：Codex 获取的证据
reports/YYYY-MM-DD/verification.json     可选：Python 验证结果
reports/YYYY-MM-DD/hypotheses.json       可选：当日新增假设
reports/YYYY-MM-DD/daily-brief.md        最终简报
reports/YYYY-MM-DD/daily-brief.html      HTML 简报
reports/YYYY-MM-DD/run-manifest.json     可选：假设跟踪校验的哈希和记录
```

完成后汇报三平台文章数、已复查假设、新增假设数、缺失证据和输出位置。
