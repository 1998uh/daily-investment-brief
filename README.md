# Daily Investment Brief

A/H 股投资智能助手系统：从雪球、微信公众号、微博采集观点，生成每日简报，并提供 AI 对话界面。

---

## 系统架构

```
前端 (Next.js 14)  ←→  Agent 后端 (FastAPI)  ←→  Pipeline (简报生成)
  :3000                   :8080                      CLI 工具
```

- **前端**：对话界面、会话管理、自选股面板、交易/事件记录
- **Agent 后端**：JWT 认证、SSE 流式对话、记忆系统（SQLite + ChromaDB）
- **Pipeline**：从社交平台采集文章，调用 LLM 生成 Markdown/HTML 简报

---

## 快速启动（本地开发）

### 1. 安装依赖

```powershell
# Python 环境
.\scripts\setup.ps1

# 如需采集雪球专栏全文（Playwright）
.\scripts\setup.ps1 -InstallPlaywright

# 前端依赖
cd frontend && npm install && cd ..
```

### 2. 配置环境变量

```powershell
Copy-Item .env.example .env
```

在 `.env` 中填写：

```env
# LLM（OpenAI 兼容接口）
BRIEF_BASE_URL=https://api.deepseek.com/v1
BRIEF_MODEL=deepseek-chat
BRIEF_API_KEY=sk-...

# Agent 认证密钥（必填，用于 JWT 签名）
AGENT_JWT_SECRET=your-secret-key-here

# 可选：雪球/微博/微信 Cookie
XUEQIU_COOKIE=
WEIBO_COOKIE=
WECHAT_COOKIE=

# 可选：Tavily 搜索
TAVILY_API_KEY=
```

生成随机 JWT 密钥：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. 启动服务

```powershell
# 终端 1：后端（端口 8080）
.\.venv\Scripts\Activate.ps1
python -m agent --port 8080

# 终端 2：前端（端口 3000）
cd frontend && npm run dev
```

打开 http://localhost:3000，注册账号后即可使用。

---

## Docker 一键启动

```bash
# 1. 准备 .env
cp .env.example .env
# 编辑 .env，填写 BRIEF_API_KEY 和 AGENT_JWT_SECRET

# 2. 启动
bash scripts/docker-start.sh

# 3. 等待健康检查
bash scripts/health_check.sh
```

服务启动后：
- 前端：http://localhost:3000
- 后端 API：http://localhost:8080

停止：`docker compose down`

---

## Pipeline CLI

系统提供三个子命令：`collect`（全量采集）、`collect-one`（单博主采集）、`generate`（生成简报）。

### collect — 全量采集

从所有启用的账号采集文章，存入 `sources/<date>/`。

```powershell
# 单日采集（并行）
daily-brief collect --date 2026-06-22

# 日期范围采集（逐日循环，每天存到各自的 sources/<date>/）
daily-brief collect --start-date 2026-06-10 --end-date 2026-06-17

# 验证配置（不实际采集）
daily-brief collect --date 2026-06-17 --dry-run

# 采集后直接生成简报
daily-brief collect --date 2026-06-22 --and-generate
```

| 参数 | 说明 |
|------|------|
| `--date` | 单日采集，与 `--start-date` 互斥 |
| `--start-date` + `--end-date` | 日期范围采集（含首尾），与 `--date` 互斥 |
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
daily-brief collect-one --name "睿知睿见" --date 2026-06-17 --verbose

# 日期范围采集
daily-brief collect-one --name "买股票的老木匠" --start-date 2026-06-10 --end-date 2026-06-17

# 采集到独立目录（用于后续单独生成报告）
daily-brief collect-one --name "买股票的老木匠" --start-date 2026-06-10 --end-date 2026-06-17 --out-dir sources/买股票的老木匠
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
daily-brief generate --date 2026-06-17

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
daily-brief generate --date 2026-06-17 --batches-only

# （检查 reports/2026-06-17/batch-summaries.json）

# 第二步：合成简报
daily-brief generate --date 2026-06-17 --from-batches
```

### 典型工作流

```powershell
# 工作流 1：一步完成采集 + 生成
daily-brief collect --date 2026-06-17 --and-generate

# 工作流 2：补采某个博主
daily-brief collect-one --name "谢佩德骨头" --date 2026-06-17

# 工作流 3：针对特定博主生成专属报告
daily-brief collect-one --name "买股票的老木匠" --start-date 2026-06-10 --end-date 2026-06-17 --out-dir sources/买股票的老木匠
daily-brief generate --date 2026-06-17 --source-dir sources/买股票的老木匠

# 工作流 4：导出 prompt 给外部模型（Claude/GPT/Gemini）
daily-brief generate --date 2026-06-17 --no-batches
```

输出文件：

```text
reports/<date>/daily-brief.md        # Markdown 简报
reports/<date>/daily-brief.html      # HTML 简报
reports/<date>/batch-summaries.json  # 批次提炼结果（--batches-only 或默认模式）
reports/<date>/prompt-for-external.md # 外部模型 prompt（--no-batches）
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
agent/                      FastAPI 后端
  routers/                  路由（auth, sessions, memory, chat, pipeline）
  main.py                   应用入口
frontend/                   Next.js 14 前端
  app/                      页面（login, chat, memory, profile）
  components/               组件（Sidebar, WatchlistPanel, ChatInput...）
pipeline/                   简报生成流水线
  collectors/               各平台采集器（雪球、微博、微信）
  cli.py                    命令行入口
config/                     账号清单
sources/                    原始文章（按日期，不提交）
reports/                    生成结果（HTML/Markdown）
memory/                     Agent 运行时数据（不提交）
scripts/                    启动脚本和调试工具
templates/                  LLM Prompt 模板
docs/superpowers/           设计文档和实现计划
```

---

## 数据说明

- `memory/` — Agent 运行时数据（SQLite + ChromaDB），**不提交到 Git**，各环境独立
- `sources/` — 采集的原始文章，**不提交到 Git**
- `reports/` — 生成的简报 HTML/Markdown，已提交部分历史记录

---

## Docker 数据备份

```bash
# 备份 memory 数据
docker compose exec backend tar czf /tmp/backup.tar.gz /data/memory
docker cp investment-backend:/tmp/backup.tar.gz ./backup-$(date +%Y%m%d).tar.gz
```
