# Daily Investment Brief

A/H 股投资简报生成工具：从雪球、微信公众号、微博采集观点，使用 LLM 生成每日简报。

---

## 快速启动

### 1. 安装依赖

```powershell
# Python 环境
.\scripts\setup.ps1

# 如需采集雪球专栏全文（Playwright）
.\scripts\setup.ps1 -InstallPlaywright
```

### 2. 配置环境变量

```powershell
Copy-Item .env.example .env
```

在 `.env` 中填写：  

```env
# LLM（DeepSeek、OpenAI 及绝大多数中转站）
BRIEF_LLM_PROVIDER=openai
BRIEF_BASE_URL=https://api.deepseek.com/v1
BRIEF_MODEL=deepseek-chat
BRIEF_API_KEY=sk-...

# 可选：雪球/微博/微信 Cookie
XUEQIU_COOKIE=
WEIBO_COOKIE=
WECHAT_COOKIE=
```

覆盖窗口可以直接在 `.env` 中调整（使用北京时间 `HH:MM`）：

```env
BRIEF_TIMEZONE=Asia/Shanghai
BRIEF_WINDOW_START=08:45
BRIEF_WINDOW_END=09:55
```

例如生成 `2026-08-04` 时，上面的配置会采集 `2026-08-03 08:45` 至
`2026-08-04 09:55` 的内容。未配置或格式不合法时使用 `08:00`。

### LLM 平台与中转站

`BRIEF_LLM_PROVIDER` 支持 `openai`、`openai-responses`、`anthropic`、`gemini` 和 `ollama`。如果中转站文档写着“OpenAI 兼容接口”，通常选择 `openai`；程序在模型只支持 Responses 协议时会自动切换到 `/responses`。也可显式选择 `openai-responses`，省去第一次协议探测。模型名使用中转站提供的原始模型 ID。

```env
# OpenAI 兼容中转站（推荐；BASE_URL 可写到 /v1 或完整端点）
BRIEF_LLM_PROVIDER=openai
BRIEF_BASE_URL=https://your-relay.example/v1
# 也支持：https://your-relay.example/v1/chat/completions
BRIEF_MODEL=your-relay-model-id
BRIEF_API_KEY=sk-...
```

常见平台配置：

| 平台/协议 | `BRIEF_LLM_PROVIDER` | `BRIEF_BASE_URL` |
|---|---|---|
| DeepSeek | `openai` | `https://api.deepseek.com/v1` |
| OpenAI | `openai` | `https://api.openai.com/v1` |
| 通义千问兼容模式 | `openai` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| Moonshot/Kimi | `openai` | `https://api.moonshot.cn/v1` |
| 智谱 GLM | `openai` | `https://open.bigmodel.cn/api/paas/v4` |
| OpenRouter | `openai` | `https://openrouter.ai/api/v1` |
| OpenAI Responses 协议/中转 | `openai-responses` | 服务商提供的 `/v1` 根地址 |
| Anthropic 原生协议 | `anthropic` | `https://api.anthropic.com/v1` |
| Google Gemini 原生协议 | `gemini` | `https://generativelanguage.googleapis.com/v1beta` |
| Ollama 本地模型 | `ollama` | `http://localhost:11434` |

Anthropic/Gemini 原生协议的中转站分别选择 `anthropic`/`gemini`，`BRIEF_BASE_URL` 填中转站给出的 API 根地址。Ollama 可将 `BRIEF_API_KEY` 留空；其他平台按服务商要求填写。

网络不稳定或中转站限流时，可降低并发并增加重试：

```env
BRIEF_LLM_BATCH_CONCURRENCY=1
BRIEF_MAX_CHARS_PER_ARTICLE=3000
BRIEF_BATCH_MAX_CHARS=5000
BRIEF_LLM_MAX_TOKENS=3000
BRIEF_LLM_TIMEOUT_SECONDS=180
BRIEF_LLM_RETRIES=4
BRIEF_LLM_RETRY_DELAY_SECONDS=2
```

### 3. 平台登录（一次性）

微信读书、微博、雪球的 Cookie 通过持久化浏览器 profile 自动管理，**每个平台只需登录一次**，之后 pipeline 启动时自动读取最新 Cookie，无需手动维护。

```powershell
# 微信读书（微信公众号采集）
python -m pipeline.cli auth-login --platform weread

# 微博
python -m pipeline.cli auth-login --platform weibo

# 雪球
python -m pipeline.cli auth-login --platform xueqiu
```
  
运行后会弹出浏览器窗口，完成登录、等页面完全加载后，回到终端按 Enter 保存 session。

> session 通常有效 7-30 天。过期后重新运行对应命令扫码一次即可。

**重要：重新登录必须走 `auth-login` 命令，不要手动打开浏览器登录。**
Cookie 提取带有 30 分钟文件缓存（`.browser-profiles/.cookie_cache.json`），避免每次运行命令都重新打开浏览器抢占 profile 文件锁。`auth-login` 命令登录成功后会自动清除对应平台的缓存；如果绕过这个命令手动登录，缓存不会失效，30 分钟内仍会读到登录前的旧 Cookie，表现为"浏览器里明明是登录状态，却依然采集不到数据"。

如果手动登录后想立即生效，可以直接删除缓存文件强制重新读取：

```powershell
Remove-Item .browser-profiles\.cookie_cache.json
```

缓存时长可通过环境变量调整：

```env
BROWSER_COOKIE_CACHE_TTL_SECONDS=1800
```

### 微信公众号采集排查（`-2041` / `-2010`）

微信公众号采集走微信读书 Web API，常见报错和排查顺序：

| 报错 | 含义 | 排查方式 |
|---|---|---|
| `errCode: -2010` | 未登录/会话失效 | 检查 `WEREAD_COOKIE` 是否包含 `wr_skey`/`wr_vid`/`wr_rt`（缺失说明登录态丢失，重新 `auth-login`） |
| `errCode: -2041` | 该公众号未同步到账号数据 | 1) 确认已在微信读书里关注该公众号；2) **仅关注不够**，需要在手机微信读书 App 里手动点开该公众号最近一篇文章浏览一次，触发同步后才能被 `/web/mp/articles` 接口读到 |

`-2041` 和"是否关注"没有稳定的对应关系（接口返回的 `follow` 字段不可靠），点开文章浏览一次是目前已知唯一稳定复现有效的解法。

---

## Pipeline CLI

系统提供采集、旧版内部生成、Codex 原生假设工作流、资金日报和数据源诊断命令。

### Codex 原生日报与假设验证

当前推荐工作流由 Codex 完成语义理解、金融取数和日报写作，Python 负责历史账本、确定性验证和一致性校验。

内部执行顺序：

```powershell
# 1. 采集文章
daily-brief collect --date 2026-08-07

# 2. 生成精简上下文、到期证据任务和去重文章包
daily-brief prepare --date 2026-08-07

# 3. Codex 只读取 evidence-tasks.json，先完成金融/公告取证并写 evidence.json

# 4. 程序根据证据执行确定性验证
daily-brief verify --date 2026-08-07

# 5. Codex 最后读取 article-pack.md，写入 daily-brief.md 和 hypotheses.json

# 6. 严格检查产物一致性，并生成 HTML 与运行清单
daily-brief validate --date 2026-08-07 --strict
```

普通使用时只需在项目目录中要求 Codex“生成今天的日报”。项目 Skill 会自动执行上述步骤。

新增产物：

```text
reports/<date>/codex-context.json   # 精简运行上下文和活跃假设摘要
reports/<date>/evidence-tasks.json  # 本期到复查时间的证据任务
reports/<date>/article-pack.md      # 去掉重复 front matter 的模型文章包
reports/<date>/article-index.jsonl  # 可按文章 ID 查询的 URL、路径和哈希
reports/<date>/evidence.json        # 行情、公告和政策证据
reports/<date>/verification.json    # 确定性验证结果
reports/<date>/hypotheses.json      # 当日新增结构化假设
reports/<date>/run-manifest.json    # 数据源、请求 ID 和文件哈希
```

`generate` 命令继续保留，适用于明确需要项目内部 LLM 生成器的旧工作流。

### collect — 全量采集

从所有启用的账号采集文章，存入 `sources/<date>/`。

```powershell
# 单日采集（并行）
daily-brief collect --date 2026-08-06

# 只采集指定平台
daily-brief collect --date 2026-08-08 --platform wechat   # 微信公众号
daily-brief collect --date 2026-08-03 --platform xueqiu   # 雪球
daily-brief collect --date 2026-08-03 --platform weibo    # 微博

# 日期范围采集（逐日循环，每天存到各自的 sources/<date>/）
daily-brief collect --start-date 2026-06-10 --end-date 2026-06-17

# 验证配置（不实际采集）
daily-brief collect --date 2026-06-27 --dry-run
  
# 采集后直接生成简报
daily-brief collect --date 2026-07-20 --and-generate
```

| 参数 | 说明 |
|------|------|
| `--date` | 单日采集，与 `--start-date` 互斥 |
| `--start-date` + `--end-date` | 日期范围采集（含首尾），与 `--date` 互斥 |
| `--platform` | 只采集指定平台，可选值：`xueqiu`（雪球）、`wechat`（微信公众号）、`weibo`（微博）。不指定则采集所有平台 |
| `--sequential` | 串行模式（调试用，默认并行） |
| `--limit N` | 每账号最多 N 条，默认 20 |
| `--include-undated` | 保留无法解析发布时间的条目 |
| `--dry-run` | 仅验证账号配置，不实际采集 |
| `--and-generate` | 采集完成后自动生成简报（仅单日模式） |
| `--markdown-only` | 配合 `--and-generate` 使用，跳过 HTML 输出 |
| `--out-dir` | 自定义输出目录，默认 `sources/<date>` |
| `--accounts` | 指定账号配置文件，默认 `config/accounts.json` |

### collect-one — 单博主采集

只采集指定博主的文章，用于调试或针对特定数据源采集。

```powershell
# 单日采集
daily-brief collect-one --name "睿知睿见" --date 2026-07-16 --verbose

# 日期范围采集
daily-brief collect-one --name "买股票的老木匠" --start-date 2026-06-10 --end-date 2026-06-17

# 采集到独立目录（用于后续单独生成报告）
daily-brief collect-one --name "谢佩德骨头" --start-date 2026-07-28 --end-date 2026-08-01 --out-dir sources/谢佩德骨头
```

| 参数 | 说明 |
|------|------|
| `--name` | **必填**，账号名称，需与 `accounts.json` 中一致 |
| `--date` | 单日采集，与 `--start-date` 互斥 |
| `--start-date` + `--end-date` | 日期范围采集（含首尾），与 `--date` 互斥 |
| `--limit N` | 最多 N 条，默认 20 |
| `--include-undated` | 保留无法解析发布时间的条目 |
| `--verbose` | 开启 DEBUG 日志，显示详细请求信息 |
| `--out-dir` | 自定义输出目录，默认 `sources/<date>` |
| `--accounts` | 指定账号配置文件 |

### generate — 生成简报

从 `sources/` 目录读取文章，调用 LLM 生成简报。

```powershell
# 默认全流程（批次提炼 → 合成简报）
daily-brief generate --date 2026-08-04

# 只生成 Markdown，不生成 HTML
daily-brief generate --date 2026-06-17 --markdown-only

# 从自定义目录读取文章（如单博主数据）
daily-brief generate --date 2026-06-17 --source-dir sources/买股票的老木匠
```

| 参数 | 说明 |
|------|------|
| `--date` | **必填**，简报日期（用于标题和窗口计算） |
| `--source-dir` | 指定文章来源目录，默认 `sources/<date>` |
| `--out-dir` | 指定输出目录，默认 `reports/<date>` |
| `--markdown-only` | 跳过 HTML 输出 |
| `--accounts` | 指定账号配置文件（用于覆盖统计） |

**生成模式**（四选一）：

| 模式 | 参数 | 说明 |
|------|------|------|
| 默认 | 无 | 批次提炼 + 最终合成，完整 LLM 流程 |
| 仅批次 | `--batches-only` | 只做批次提炼，保存 `batch-summaries.json`，不合成 |
| 从批次合成 | `--from-batches` | 跳过提炼，直接从已有 `batch-summaries.json` 合成 |
| 导出 prompt | `--no-batches` | 不调 LLM，打包所有文章为一个 prompt 文件，可粘贴到外部模型 |

`--batches-only` + `--from-batches` 组合可以将提炼和合成分步执行，中间手动检查或更换模型：

```powershell
# 第一步：提炼批次
daily-brief generate --date 2026-07-16 --batches-only

# （检查 reports/2026-06-17/batch-summaries.json）

# 第二步：合成简报
daily-brief generate --date 2026-07-16 --from-batches
```

### 典型工作流

```powershell
# 工作流 1：一步完成采集 + 生成
daily-brief collect --date 2026-07-20 --and-generate

# 工作流 2：分平台采集（适用于网络不稳定或调试单个平台）
daily-brief collect --date 2026-08-03 --platform wechat   # 只采集微信公众号
daily-brief collect --date 2026-08-03 --platform xueqiu   # 只采集雪球
daily-brief collect --date 2026-08-03 --platform weibo    # 只采集微博

# 工作流 3：补采某个博主
daily-brief collect-one --name "三岁小怪兽" --date 2026-08-03

# 工作流 4：针对特定博主生成专属报告
daily-brief collect-one --name "买股票的老木匠" --start-date 2026-06-10 --end-date 2026-06-17 --out-dir sources/买股票的老木匠
daily-brief generate --date 2026-06-17 --source-dir sources/买股票的老木匠

# 工作流 5：导出 prompt 给外部模型（Claude/GPT/Gemini）
daily-brief generate --date 2026-06-17 --no-batches
```

输出文件：

```text
reports/<date>/daily-brief.md        # Markdown 简报
reports/<date>/daily-brief.html      # HTML 简报
reports/<date>/batch-summaries.json  # 批次提炼结果（--batches-only 或默认模式）
reports/<date>/prompt-for-external.md # 外部模型 prompt（--no-batches）
journal/YYYY/MM/YYYY-MM-DD.md        # 个人判断模板（generate 后自动创建）
```

## 个人投研工作台

日报现在默认包含三个训练模块：

- **今日三句话**：压缩当天真正重要的变化、影响和纪律。
- **待验证假设**：每期只保留 2-4 条，把核心观点写成可观察、可证伪、可复盘的假设。
- **我的判断区**：留空给本人填写，AI 不代填。

常用脚本：

```powershell
# 单独创建某天的个人判断模板（已存在时不覆盖）
python scripts/new_journal_entry.py --date 2026-07-15

# 创建周复盘模板，并自动索引当周日报和 journal
python scripts/new_weekly_review.py --week 2026-W29

# 创建月复盘模板，并自动索引当月周复盘
python scripts/new_monthly_review.py --month 2026-07

# 初始化主题、公司、错题知识库模板
python scripts/init_knowledge_base.py
```

建议流程：

```text
每天：读日报 8 分钟 → 填 journal 5 分钟
每周：用 reviews/weekly 做一次判断复盘
每月：用 reviews/monthly 沉淀长期主题、公司和错题
```
## 账号配置

```powershell
Copy-Item config/accounts.example.json config/accounts.json
```

```json
{
  "xueqiu": [
    {"name": "诸葛孔暗", "url": "https://xueqiu.com/u/用户ID", "uid": "用户ID", "enabled": true}
  ],
  "weibo": [
    {"name": "唐史主任司马迁", "url": "https://weibo.com/u/用户ID", "uid": "用户ID", "enabled": true}
  ],
  "wechat": [
    {"name": "中金宏观", "urls": ["https://mp.weixin.qq.com/s/文章ID"], "enabled": true}
  ]
}
```

---

## 目录结构

```text
pipeline/                   简报生成流水线
  collectors/               各平台采集器（雪球、微博、微信）
  cli.py                    命令行入口
config/                     账号清单
sources/                    原始文章（按日期，不提交）
reports/                    生成结果（HTML/Markdown）
journal/                    每日个人判断记录
reviews/                    周复盘和月复盘
knowledge/                  主题、公司、错题长期知识库
scripts/                    启动脚本和调试工具
templates/                  LLM Prompt 模板
docs/                       设计文档和实现计划
```

---

## 数据说明

- `sources/` — 采集的原始文章，**不提交到 Git**
- `reports/` — 生成的简报 HTML/Markdown，已提交部分历史记录
- `journal/`、`reviews/`、`knowledge/` — 个人投研沉淀，默认可提交；如内容敏感可自行加入 `.gitignore`

---
