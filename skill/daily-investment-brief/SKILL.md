---
name: daily-investment-brief
description: 生成或调整每日 A/H 股投资简报和私有持仓资金日报 PART-B。从雪球、微信公众号、微博采集文章并生成 Markdown/HTML；或在用户提供持仓时调用金融 MCP 与本机资金流适配器，生成 A 股和 ETF 的私有资金面报告。用于“生成报告”“生成资金日报”“生成 PART-B”、具体日期简报或持仓资金流分析。
---

# Daily Investment Brief Skill

当用户说"生成报告"、"重新生成"、"采集今天的文章"、"调整简报"，或提到具体日期+简报时，使用此 skill。

---

## 快速操作

### 私有持仓资金日报 PART-B

当用户要求“生成资金日报”“生成 PART-B”并提供持仓时，读取
[资金日报契约](references/capital-daily.md)，完成标的消歧、ETF/板块映射、行情补全和
确定性计算。不要从文章推断用户持仓，也不要把资金流缺失值改写成方向性结论。

内部命令：

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
python -m pipeline.cli capital-daily --date YYYY-MM-DD --holdings-stdin
```

默认输出：`private-reports/YYYY-MM-DD/capital-daily.md`。只在用户明确要求普通文章简报时走下方原有流程；PART-B 失败不得阻塞文章简报。

### 全流程（采集 + 提炼 + 合成，DeepSeek 完成所有 LLM 工作）

```powershell
python -m pipeline.cli collect --date YYYY-MM-DD
python -m pipeline.cli generate --date YYYY-MM-DD
```

### 完全不用 DeepSeek，外部模型一步到位（方案 B）

```powershell
python -m pipeline.cli generate --date YYYY-MM-DD --no-batches
```

输出：`reports/YYYY-MM-DD/prompt-for-external.md`

这个文件是**已填好所有变量的完整 prompt**，包含所有原始文章、来源统计、上期观察点、风格要求。直接复制粘贴到任意模型即可，无需任何额外处理。

- 系统提示：`你是中文每日投资简报主编。`
- 用户提示：`prompt-for-external.md` 的全部内容

今天46篇文章生成的 prompt 约 **48k 字符 / 12k tokens**，Claude、GPT-4.1、Gemini 1.5 Pro 均可直接处理。

### 只提炼不合成（先用 DeepSeek 提炼，外部模型合成）

```powershell
python -m pipeline.cli generate --date YYYY-MM-DD --batches-only
```

输出：`reports/YYYY-MM-DD/batch-summaries.json`

把 `batch-summaries.json` + `templates/final_brief_prompt.md`（手动填变量）喂给外部模型合成。适合想用 DeepSeek 做低成本提炼、高质量模型做最终写作的场景。

### 用外部模型合成后，写回并生成 HTML

```powershell
python -m pipeline.cli generate --date YYYY-MM-DD --from-batches
```

前提：已把外部模型合成的 Markdown 直接写入 `reports/YYYY-MM-DD/daily-brief.md`，
或者 `batch-summaries.json` 存在、`.env` 里配置了目标模型的 API。

### 仅生成（sources 已有文章，跳过采集）

```powershell
python -m pipeline.cli generate --date YYYY-MM-DD
```

### 验证账号配置（不实际采集）

```powershell
python -m pipeline.cli collect --date YYYY-MM-DD --dry-run
```

### 输出位置

```
reports/YYYY-MM-DD/batch-summaries.json   ← 批次提炼 JSON（中间产物）
reports/YYYY-MM-DD/daily-brief.md         ← 最终简报
reports/YYYY-MM-DD/daily-brief.html       ← HTML 版本
```

---

## 外部模型合成流程

当你想用 Claude、GPT、Gemini 或其他模型代替 DeepSeek 做最终合成时：

### 步骤一：只跑提炼，落盘批次 JSON

```powershell
python -m pipeline.cli generate --date YYYY-MM-DD --batches-only
```

这一步用 DeepSeek（快且便宜）把原始文章提炼成结构化 JSON，保存到：
`reports/YYYY-MM-DD/batch-summaries.json`

### 步骤二：把以下两份内容喂给外部模型

1. **系统提示**：`你是中文每日投资简报主编。`
2. **用户提示**：`templates/final_brief_prompt.md` 的内容，其中变量手动填入：
   - `{date_cn}` → 如 `2026年6月12日`
   - `{weekday_cn}` → 如 `周五`
   - `{session}` → `盘前` / `盘后` / `盘中`
   - `{window_label}` → 如 `2026-06-11 08:00 ~ 2026-06-12 08:00`
   - `{markets}` → `A股,港股`
   - `{coverage_json}` → 来源统计（可从 batch-summaries.json 里推算，或留空 `[]`）
   - `{batch_summaries_json}` → `batch-summaries.json` 的完整内容
   - `{prev_watch_list}` → 上一期 daily-brief.md 里「下期关注」章节的内容（可选）

### 步骤三：把外部模型输出写入文件

```powershell
# 把模型输出的 Markdown 保存到：
reports/YYYY-MM-DD/daily-brief.md
```

然后手动生成 HTML（可选）：
```powershell
python -m pipeline.cli generate --date YYYY-MM-DD --from-batches --markdown-only
# 或者直接用浏览器打开 .md 文件
```

### 用 Claude Code 直接合成（最简单）

在这个项目目录里对话，把 `batch-summaries.json` 的内容和 `final_brief_prompt.md` 一起发给 Claude，说"帮我合成今天的简报"即可。Claude Code 会直接读文件，不需要手动复制粘贴。

---

## 自动化执行流程

当用户要求生成报告时，按以下步骤执行：

1. **确认日期**：若用户未指定，使用今天的日期（`date` 命令获取）
2. **检查 sources**：确认 `sources/YYYY-MM-DD/` 目录存在且有文章
   - 若为空，先运行 collect
   - 若已有文章，直接生成
3. **运行生成**：`python -m pipeline.cli generate --date YYYY-MM-DD`
4. **检查输出**：确认 `reports/YYYY-MM-DD/daily-brief.md` 已生成，读取前 60 行确认结构正确
5. **汇报结果**：告知批次数、耗时、是否包含上期验证章节

---

## 生成流程说明

### 两阶段 LLM 流程

**第一阶段：批次提炼（并发）**
- 文章按博主分组后合并成批次（`BRIEF_BATCH_MAX_CHARS` 控制每批字数上限，默认 15000）
- 同一博主所有文章保证在同一批次，LLM 能看到完整逻辑链
- 各批次并发请求（`BRIEF_LLM_BATCH_CONCURRENCY`，默认 3）
- 每批输出结构化 JSON（主题、观点、金句、多空分歧）

**第二阶段：最终合成**
- 汇总所有批次 JSON + 覆盖统计
- 自动读取上一期 `daily-brief.md` 的「下期关注」章节，作为本期「上期观察点验证」输入
- 输出完整 Markdown 简报

### 简报固定结构

```
零、✅ 上期观察点验证      ← 对上期「下期关注」逐条验证（✅❌⚠⏳）
一、💼 博主持仓信息        ← 明确持仓/操作的博主汇总表
二、📡 博主看好方向汇总     ← 所有博主的多空方向大表
三、⚡ 今日注意事项与投资总结 ← 情绪+事件+风险+机会+操作共识
四～N、（动态章节）        ← 按当日重要事件命名，不硬套分类
📋 数据覆盖情况
🎯 核心矛盾梳理（ASCII 图）
🔭 下期关注               ← 锚定具体博主观点，带可观测验证信号
💡 金句（10条以上）
```

---

## 配置说明（.env）

### 必填（LLM）

```env
BRIEF_BASE_URL=https://api.deepseek.com
BRIEF_MODEL=deepseek-v4-pro
BRIEF_API_KEY=sk-...
```

### 分批控制

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BRIEF_BATCH_MAX_CHARS` | 15000 | 每批最大字数。按博主分组后合并，超过此值则开新批 |
| `BRIEF_MAX_CHARS_PER_ARTICLE` | 6000 | 单篇文章最大字数（超出截断） |
| `BRIEF_LLM_BATCH_CONCURRENCY` | 3 | 批次并发数 |
| `BRIEF_BATCH_SIZE` | 8 | 已废弃，不再用于分批（保留兼容） |

### 其他

```env
BRIEF_TIMEZONE=Asia/Shanghai
BRIEF_WINDOW_START=08:00
BRIEF_WINDOW_END=08:00
BRIEF_MARKETS=A股,港股
BRIEF_TEMPERATURE=0.2
```

### 采集 Cookie

```env
XUEQIU_COOKIE=
WEIBO_COOKIE=
WECHAT_COOKIE=
XUEQIU_CHROME_PATH=C:/Users/.../chrome.exe   # Playwright 本地 Chromium 路径
```

---

## 文章输入格式

`sources/YYYY-MM-DD/` 下的 `.md` 或 `.json` 文件，推荐 Markdown front matter：

```markdown
---
source: 雪球
author: 作者名
title: 文章标题
url: https://example.com/post
published_at: 2026-06-12 07:30
---

正文...
```

`source` 支持：`雪球` / `微信公众号` / `微博`

---

## 上期观察点验证机制

每次生成时，自动从 `reports/{前一天}/daily-brief.md` 提取「下期关注」章节，注入本期提示词。LLM 对每条上期关注点用当天素材逐条验证，输出状态：

- ✅ 已兑现
- ❌ 未兑现
- ⚠ 部分兑现
- ⏳ 尚无定论（今日素材无相关信息）

若上期无「下期关注」章节（如首次生成），自动跳过，不输出零章节。

---

## 模板文件

| 文件 | 作用 |
|------|------|
| `templates/batch_summary_prompt.md` | 批次提炼提示词（输出 JSON） |
| `templates/final_brief_prompt.md` | 最终合成提示词（输出 Markdown） |

调整简报风格、增减固定章节、修改金句数量等，编辑 `final_brief_prompt.md`。
调整批次提炼的信息密度、JSON 字段，编辑 `batch_summary_prompt.md`。

---

## 常见问题

**生成只有1个批次？**
`BRIEF_BATCH_MAX_CHARS` 设太大。今天文章约44k字，建议设 12000-18000。

**上期验证章节显示"无数据"？**
上一期简报没有「下期关注」章节（旧格式）。重新生成上一期后即可。

**LLM 超时或失败？**
自动切换 fallback 模式（本地结构化输出，无 LLM）。调整 `BRIEF_LLM_TIMEOUT_SECONDS`（默认120s）。

**采集不到文章？**
检查 Cookie 是否过期，或手动把文章放入 `sources/YYYY-MM-DD/`。
