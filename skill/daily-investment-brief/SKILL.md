---
name: daily-investment-brief
description: 生成或调整每日 A/H 股投资简报。从雪球、微信公众号、微博采集文章，按博主分批提炼，生成强叙事 Markdown + HTML 报告。
---

# Daily Investment Brief Skill

当用户说"生成报告"、"重新生成"、"采集今天的文章"、"调整简报"，或提到具体日期+简报时，使用此 skill。

---

## 快速操作

### 采集 + 生成（最常用）

```powershell
python -m pipeline.cli collect --date YYYY-MM-DD
python -m pipeline.cli generate --date YYYY-MM-DD
```

### 仅生成（sources 已有文章时）

```powershell
python -m pipeline.cli generate --date YYYY-MM-DD
```

### 验证账号配置（不实际采集）

```powershell
python -m pipeline.cli collect --date YYYY-MM-DD --dry-run
```

### 输出位置

```
reports/YYYY-MM-DD/daily-brief.md
reports/YYYY-MM-DD/daily-brief.html
```

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
