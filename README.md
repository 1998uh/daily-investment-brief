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

### 采集文章

```powershell
# 全量采集（并行）
daily-brief collect --date 2026-06-12

# 单博主调试
daily-brief collect-one --name "诸葛孔暗" --date 2026-06-12 --verbose

# 验证配置（不实际采集）
daily-brief collect --date 2026-06-12 --dry-run
```

| 参数 | 说明 |
|------|------|
| `--sequential` | 串行模式（调试用）|
| `--limit N` | 每账号最多 N 条，默认 20 |
| `--and-generate` | 采集后直接生成简报 |

### 生成简报

```powershell
daily-brief generate --date 2026-06-12
```

输出：`reports/2026-06-12/daily-brief.md` 和 `.html`

---

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
