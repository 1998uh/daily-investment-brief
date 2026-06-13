# 投资智能 Agent 系统 — 设计规格

**日期**：2026-06-13  
**状态**：已确认，待实现

---

## 背景与目标

在现有 `daily-investment-brief` 系统（每日采集雪球/微博/微信文章，LLM 生成投资简报）上，叠加一个多 Agent 协作的投资智能助手。现有 `pipeline/` 代码完全不改动，新系统作为独立层构建在其上。

**核心能力：**
1. 查询当日简报与历史文章（本地 RAG + 外部实时搜索）
2. 管理关注标的（watchlist）
3. 记录个人买卖操作与事件笔记（对话输入 + 表单页双入口）
4. 触发 pipeline 采集/生成（关键步骤需用户确认）
5. 透明推理链（折叠气泡，实时 SSE 流式展示）

**用户规模**：当前单用户，架构预留多用户扩展（完整账号体系）。

**部署**：本地开发优先，Docker Compose 支持将来迁移云服务器。

---

## 整体架构

```
Next.js 前端 (port 3000)
       │ REST + SSE
FastAPI 后端 (port 8080)
  └─ OrchestratorAgent (LangChain AgentExecutor)
       ├─ ResearchAgent   — ChromaDB + Tavily
       ├─ ReportAgent     — 摘要/对比/信号提取
       ├─ MemoryAgent     — SQLite CRUD
       └─ ActionAgent     — 触发 pipeline（需确认）
  └─ Auth (JWT, httpOnly cookie)
  └─ ChromaDB (本地文件)
  └─ SQLite (本地文件)
       │
现有 pipeline/（不改动）
  sources/ reports/ collect generate
```

**架构选型**：LangChain AgentExecutor 单体后端（方案 A）。理由：规模合适，Docker 化简单，LangChain 生态成熟，后期可按需拆分子服务。

---

## 五个 Agent 职责

### Orchestrator Agent（主控）
- 接收用户输入，分析意图，决定串行或并行调度子 Agent
- 通过 SSE 推送推理链事件：`{"type":"thinking","agent":"orchestrator","text":"..."}`
- 汇总子 Agent 结果，生成最终 markdown 回复

### Research Agent（研究员）
| 工具 | 说明 |
|------|------|
| `search_local(query, date_range?, author?, source?)` | ChromaDB 语义检索本地文章 |
| `get_daily_brief(date?)` | 读取 `reports/YYYY-MM-DD/daily-brief.md` |
| `search_web(query)` | Tavily 实时外部搜索（免费层 1000次/月） |

### Report Agent（报告员）
| 工具 | 说明 |
|------|------|
| `summarize(texts, focus?)` | 提炼多篇文章核心观点 |
| `compare_views(results)` | 对比不同博主观点，找共识与分歧 |
| `extract_signals(text)` | 识别看多/看空信号 |

### Memory Agent（记忆官）
| 工具 | 说明 |
|------|------|
| `add_watch / remove_watch / get_watchlist` | 关注标的管理 |
| `log_trade(symbol, action, price, quantity, date, note?)` | 买卖记录 |
| `log_event(title, content, date?, tags?)` | 事件/想法笔记 |
| `get_trades(symbol?, date_range?)` | 查询交易记录 |
| `get_events(tags?, date_range?)` | 查询事件记录 |
| `get_user_context()` | 生成用户画像摘要，注入 system prompt |

### Action Agent（执行官）
所有工具为写操作，前端必须弹出 `ConfirmDialog` 确认后才执行。

| 工具 | 说明 |
|------|------|
| `collect_articles(date?)` | 触发 `python -m pipeline collect` |
| `generate_brief(date?)` | 触发 `python -m pipeline generate` |
| `update_search_index(date?)` | 触发 ChromaDB 增量更新 |

---

## 数据模型

### SQLite（`memory/agent.db`）

```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    title TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,       -- 'user' | 'assistant' | 'thinking'
    agent TEXT,               -- 产生该消息的 agent 名称
    content TEXT NOT NULL,
    sources TEXT,             -- JSON 数组，检索来源
    created_at TEXT NOT NULL
);

CREATE TABLE watchlist (
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    note TEXT,
    added_at TEXT NOT NULL,
    PRIMARY KEY (user_id, symbol)
);

CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,     -- 'buy' | 'sell' | 'add' | 'reduce'
    price REAL,
    quantity REAL,
    trade_date TEXT,
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT,
    event_date TEXT,
    tags TEXT,                -- JSON 数组
    created_at TEXT NOT NULL
);
```

### ChromaDB（`memory/chroma/`）

单 collection `investment_docs`，metadata 字段：

```json
{
  "doc_type": "article | report",
  "source": "雪球 | 微博 | 微信公众号",
  "author": "陈达美股投资",
  "date": "2026-06-12",
  "title": "...",
  "url": "..."
}
```

检索时支持按 `date`、`author`、`source` 的 metadata filter。

---

## API 设计

```
# 认证
POST /api/auth/register
POST /api/auth/login          返回 JWT（httpOnly cookie）
POST /api/auth/refresh

# 会话管理
GET    /api/sessions
POST   /api/sessions
PATCH  /api/sessions/{id}
DELETE /api/sessions/{id}
GET    /api/sessions/{id}/messages

# 对话（SSE 流式）
POST /api/chat
  body:   { session_id, message }
  stream events:
    { type: "thinking", agent: "orchestrator", text: "..." }
    { type: "thinking", agent: "research",     text: "检索中..." }
    { type: "token",    text: "根据陈达..." }
    { type: "done",     sources: [...] }

# 记忆管理
GET    /api/memory/watchlist
POST   /api/memory/watchlist            { symbol, note? }
DELETE /api/memory/watchlist/{symbol}
GET    /api/memory/trades?symbol=&from=&to=
POST   /api/memory/trades               { symbol, action, price, quantity, date, note? }
DELETE /api/memory/trades/{id}
GET    /api/memory/events?tags=&from=&to=
POST   /api/memory/events               { title, content, date?, tags? }
DELETE /api/memory/events/{id}

# Pipeline（写操作，前端需 ConfirmDialog 确认）
POST /api/pipeline/collect    { date }
POST /api/pipeline/generate   { date }
POST /api/index/update        { date }

GET  /api/health
```

---

## 前端设计

### 路由

| 路径 | 说明 |
|------|------|
| `/login` | 登录页 |
| `/register` | 注册页 |
| `/` | 重定向到最近会话 |
| `/chat/new` | 新建会话 |
| `/chat/[sessionId]` | 具体会话页 |
| `/memory/trades` | 交易记录完整页 |
| `/memory/events` | 事件笔记完整页 |

### 三栏布局

```
┌──────────────┬─────────────────────────────┬──────────────┐
│ 左侧边栏     │ 主对话区                    │ 右侧面板     │
│ (260px固定)  │                             │ (280px可收起)│
│              │ ┌─ 🤔 思考过程（折叠）───┐  │              │
│ + 新建对话   │ │ ▶ Orchestrator 路由中  │  │ 关注标的     │
│              │ └───────────────────────┘  │ MU NVDA ...  │
│ 🔍 搜索历史  │                             │              │
│              │ [AI 回复，markdown 渲染]    │ 最近交易     │
│ 今天         │ [来源卡片]                  │ 06-12 买MU   │
│  · 美光分析  │                             │              │
│  · 科技走势  │ ─────────────────────────── │ 今日简报     │
│ 昨天         │ [输入框]         [发送]     │ ✓ 已生成     │
│  · 半导体    │                             │ [触发生成]   │
└──────────────┴─────────────────────────────┴──────────────┘
```

### 关键组件

| 组件 | 职责 |
|------|------|
| `Sidebar` | 左栏容器，会话列表 + 新建按钮 |
| `SessionList` | 按日期分组，支持搜索/重命名/删除，右键菜单 |
| `ThinkingBubble` | 推理链折叠气泡，SSE 流入时实时追加步骤 |
| `ChatWindow` | 消息滚动列表 + 输入框 |
| `MessageBubble` | 用户/AI 消息，AI 消息含 react-markdown 渲染 |
| `SourceCards` | AI 回复下方来源卡片，含标题/作者/日期/链接 |
| `WatchlistPanel` | 右栏关注标的，点击标的自动填充输入框 |
| `TradePanel` | 右栏最近交易，快速新增入口 |
| `ConfirmDialog` | Action Agent 写操作前弹出确认框 |

### 关键技术点

- **流式渲染**：`fetch` + `ReadableStream` 消费 SSE
- **JWT 存储**：`httpOnly cookie`，比 localStorage 安全
- **会话恢复**：切换会话时拉取 `/api/sessions/{id}/messages` 渲染历史
- **标题自动生成**：第一条消息发出后，截取前 20 字 `PATCH /api/sessions/{id}`
- **交易双入口**：对话中说「买了 XX」→ Memory Agent 解析；专门页面填表单

---

## 目录结构

```
daily-investment-brief/
├── pipeline/                    # 现有，完全不改动
├── agent/                       # 新增后端
│   ├── main.py                  # FastAPI app 入口
│   ├── auth.py                  # JWT 注册/登录/校验
│   ├── db.py                    # SQLite 建表 + CRUD
│   ├── indexer.py               # ChromaDB 索引构建/更新
│   ├── config.py                # 读取 .env
│   ├── agents/
│   │   ├── orchestrator.py
│   │   ├── research.py
│   │   ├── report.py
│   │   ├── memory_agent.py
│   │   └── action.py
│   └── routers/
│       ├── auth.py
│       ├── sessions.py
│       ├── chat.py              # SSE 端点
│       ├── memory.py
│       └── pipeline.py
├── frontend/                    # Next.js 14 App Router
│   ├── app/
│   │   ├── (auth)/login/page.tsx
│   │   ├── (auth)/register/page.tsx
│   │   ├── chat/new/page.tsx
│   │   ├── chat/[sessionId]/page.tsx
│   │   └── memory/trades/page.tsx
│   ├── components/
│   │   ├── Sidebar.tsx
│   │   ├── SessionList.tsx
│   │   ├── ThinkingBubble.tsx
│   │   ├── ChatWindow.tsx
│   │   ├── MessageBubble.tsx
│   │   ├── SourceCards.tsx
│   │   ├── WatchlistPanel.tsx
│   │   ├── TradePanel.tsx
│   │   └── ConfirmDialog.tsx
│   └── lib/
│       ├── api.ts
│       └── types.ts
├── memory/                      # 运行时生成，加入 .gitignore
│   ├── agent.db
│   └── chroma/
├── docker-compose.yml
├── Dockerfile.backend
├── Dockerfile.frontend
└── .env.example
```

---

## 技术栈

| 层 | 选型 |
|----|------|
| 前端框架 | Next.js 14 (App Router) + TypeScript |
| 前端样式 | Tailwind CSS，暗色 Bloomberg 风格 |
| Markdown 渲染 | react-markdown + remark-gfm |
| 后端框架 | FastAPI + uvicorn |
| Agent 框架 | LangChain AgentExecutor |
| 向量数据库 | ChromaDB（本地文件持久化） |
| 关系数据库 | SQLite + aiosqlite |
| Embeddings | langchain-openai（复用 BRIEF_BASE_URL） |
| 外部搜索 | Tavily（免费层 1000次/月） |
| 认证 | JWT + httpOnly cookie |
| 流式通信 | SSE（Server-Sent Events） |
| 容器化 | Docker Compose |

### 新增 Python 依赖（`[agent]` extra）

```toml
[project.optional-dependencies]
agent = [
    "fastapi>=0.111",
    "uvicorn>=0.30",
    "langchain>=0.2",
    "langchain-community>=0.2",
    "langchain-openai>=0.1",
    "chromadb>=0.5",
    "aiosqlite>=0.20",
    "tavily-python>=0.3",
    "python-jose[cryptography]>=3.3",  # JWT
    "passlib[bcrypt]>=1.7",            # 密码哈希
]
```

### 新增 Node.js 依赖

```json
{
  "dependencies": {
    "next": "14",
    "react": "^18",
    "react-dom": "^18",
    "react-markdown": "^9",
    "remark-gfm": "^4",
    "tailwindcss": "^3",
    "typescript": "^5"
  }
}
```

---

## 实现顺序

1. **数据层** — `agent/db.py`：建表、CRUD，所有表跑通
2. **索引层** — `agent/indexer.py`：扫描 sources/ + reports/ → ChromaDB，验证检索结果
3. **Auth** — `agent/auth.py` + `routers/auth.py`：注册/登录/JWT 校验
4. **Agent 层** — 各专职 Agent 工具单独可测试，再接入 Orchestrator
5. **API 层** — `agent/main.py` + 所有 routers，SSE 流式端点
6. **前端骨架** — Next.js 初始化，登录页，路由守卫
7. **前端核心** — Sidebar + ChatWindow + ThinkingBubble + 流式渲染
8. **前端右侧面板** — WatchlistPanel + TradePanel
9. **记录页面** — `/memory/trades` + `/memory/events`
10. **Docker** — Dockerfile.backend + Dockerfile.frontend + docker-compose.yml

---

## 验证方式

1. `pip install -e ".[agent]"` 安装依赖
2. `python -m agent.indexer --rebuild` 首次构建索引
3. `uvicorn agent.main:app --port 8080` 启动后端
4. `cd frontend && npm install && npm run dev` 启动前端
5. 浏览器访问 `http://localhost:3000`，测试：
   - 注册账号 → 登录 → 自动跳转对话页
   - 「陈达最近对美光怎么看？」→ 推理链折叠气泡实时出现，来源卡片展示
   - 「今天买了 100 股美光，105 元」→ Memory Agent 解析写入，右侧 TradePanel 更新
   - 「帮我关注 MU 和 NVDA」→ 右侧 WatchlistPanel 出现标的
   - 「帮我生成今天的简报」→ ConfirmDialog 弹出，确认后触发 pipeline
   - 切换历史会话 → 完整消息和推理链记录恢复
   - 关闭重启后，所有数据持久化保留
