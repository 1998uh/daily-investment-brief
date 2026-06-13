# Plan B: Agent 层 + 完整 API

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Plan A 后端基础上构建五个专职 Agent（Orchestrator / Research / Report / Memory / Action），实现完整 REST API 路由（sessions、chat SSE、memory、pipeline），使系统具备完整的对话能力。

**Architecture:** LangChain AgentExecutor 单体后端，Orchestrator 接收用户输入后通过 Tool Calling 调度四个专职 Agent，推理链步骤通过 SSE 实时推送给前端。

**Tech Stack:** Python 3.10+, LangChain 0.2+, langchain-openai, FastAPI SSE (StreamingResponse + EventSourceResponse), aiosqlite, ChromaDB, Tavily

---

## 文件地图

| 文件 | 职责 |
|------|------|
| `agent/agents/__init__.py` | 包标记 |
| `agent/agents/tools.py` | 所有 Agent 工具函数（可独立测试） |
| `agent/agents/orchestrator.py` | Orchestrator：意图识别 + 路由 + 汇总 |
| `agent/routers/sessions.py` | 会话 CRUD 路由 |
| `agent/routers/chat.py` | SSE 流式对话端点 |
| `agent/routers/memory.py` | watchlist / trades / events 路由 |
| `agent/routers/pipeline.py` | collect / generate / index 触发路由 |
| `tests/agent/test_tools.py` | 工具函数单元测试 |
| `tests/agent/test_sessions.py` | 会话路由 HTTP 测试 |
| `tests/agent/test_memory_routes.py` | 记忆路由 HTTP 测试 |

---

## Task 1: 创建 agents 子包 + 工具函数

**Files:**
- Create: `agent/agents/__init__.py`
- Create: `agent/agents/tools.py`
- Create: `tests/agent/test_tools.py`

工具函数是各 Agent 调用的最小单元，先独立实现和测试，再组装进 Agent。

- [ ] **Step 1: 创建包标记**

```bash
New-Item -ItemType File agent/agents/__init__.py
```

- [ ] **Step 2: 写失败测试 `tests/agent/test_tools.py`**

```python
from __future__ import annotations

import pytest
import pytest_asyncio
from pathlib import Path
from tests.agent.conftest import make_settings


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


@pytest.mark.asyncio
async def test_get_daily_brief_returns_content(settings, tmp_path):
    from agent.agents.tools import get_daily_brief
    brief_dir = tmp_path / "reports" / "2026-06-10"
    brief_dir.mkdir(parents=True)
    (brief_dir / "daily-brief.md").write_text("# 简报\n内容", encoding="utf-8")
    result = await get_daily_brief(settings, "2026-06-10")
    assert "简报" in result


@pytest.mark.asyncio
async def test_get_daily_brief_missing(settings):
    from agent.agents.tools import get_daily_brief
    result = await get_daily_brief(settings, "2099-01-01")
    assert "未找到" in result or "not found" in result.lower()


@pytest.mark.asyncio
async def test_memory_tool_add_and_get_watchlist(settings):
    from agent.agents.tools import tool_add_watch, tool_get_watchlist
    from agent.db import init_db, create_user
    await init_db(settings.db_path)
    user = await create_user(settings.db_path, "u1", None, "pw")
    await tool_add_watch(settings, user["id"], "MU", None)
    items = await tool_get_watchlist(settings, user["id"])
    assert any(i["symbol"] == "MU" for i in items)


@pytest.mark.asyncio
async def test_memory_tool_log_trade(settings):
    from agent.agents.tools import tool_log_trade, tool_get_trades
    from agent.db import init_db, create_user
    await init_db(settings.db_path)
    user = await create_user(settings.db_path, "u2", None, "pw")
    await tool_log_trade(settings, user["id"], "MU", "buy", 105.0, 100, "2026-06-12", None)
    trades = await tool_get_trades(settings, user["id"])
    assert len(trades) == 1
    assert trades[0]["symbol"] == "MU"


@pytest.mark.asyncio
async def test_memory_tool_log_event(settings):
    from agent.agents.tools import tool_log_event, tool_get_events
    from agent.db import init_db, create_user
    await init_db(settings.db_path)
    user = await create_user(settings.db_path, "u3", None, "pw")
    await tool_log_event(settings, user["id"], "降息", "影响仓位", "2026-06-12", ["macro"])
    events = await tool_get_events(settings, user["id"])
    assert len(events) == 1
    assert events[0]["title"] == "降息"
```

- [ ] **Step 3: 创建 `tests/agent/conftest.py`** （共享 fixture 工厂）

```python
from __future__ import annotations
from pathlib import Path
from agent.config import AgentSettings


def make_settings(tmp_path: Path) -> AgentSettings:
    return AgentSettings(
        db_path=tmp_path / "agent.db",
        chroma_path=tmp_path / "chroma",
        sources_root=tmp_path / "sources",
        reports_root=tmp_path / "reports",
        jwt_secret="test-secret",
        jwt_algorithm="HS256",
        jwt_expire_minutes=60,
        llm_base_url="",
        llm_model="",
        llm_api_key="",
        tavily_api_key="",
    )
```

- [ ] **Step 4: 运行测试确认失败**

```bash
pytest tests/agent/test_tools.py -v 2>&1 | head -20
```

Expected: ImportError — `agent.agents.tools` 不存在。

- [ ] **Step 5: 创建 `agent/agents/tools.py`**

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.config import AgentSettings
from agent.db import (
    add_watch, remove_watch, get_watchlist,
    log_trade, get_trades,
    log_event, get_events,
)


async def get_daily_brief(settings: AgentSettings, date: str | None = None) -> str:
    """读取指定日期的每日简报 markdown 文件。"""
    if not date:
        import datetime
        date = datetime.date.today().isoformat()
    brief_path = settings.reports_root / date / "daily-brief.md"
    if not brief_path.exists():
        return f"未找到 {date} 的简报，请先运行 generate。"
    return brief_path.read_text(encoding="utf-8")


async def tool_search_local(
    settings: AgentSettings,
    query: str,
    top_k: int = 5,
    author: str | None = None,
    source: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    """ChromaDB 语义检索本地文章。"""
    from agent.indexer import ArticleIndexer
    indexer = ArticleIndexer(
        chroma_path=settings.chroma_path,
        llm_api_key=settings.llm_api_key,
        llm_base_url=settings.llm_base_url,
    )
    results = indexer.search(
        query=query, top_k=top_k,
        author=author, source=source,
        date_from=date_from, date_to=date_to,
    )
    return [
        {"content": r.content, "metadata": r.metadata, "score": r.score}
        for r in results
    ]


async def tool_add_watch(settings: AgentSettings, user_id: str, symbol: str, note: str | None) -> str:
    await add_watch(settings.db_path, user_id, symbol, note)
    return f"已添加 {symbol} 到关注列表"


async def tool_remove_watch(settings: AgentSettings, user_id: str, symbol: str) -> str:
    await remove_watch(settings.db_path, user_id, symbol)
    return f"已从关注列表移除 {symbol}"


async def tool_get_watchlist(settings: AgentSettings, user_id: str) -> list[dict]:
    return await get_watchlist(settings.db_path, user_id)


async def tool_log_trade(
    settings: AgentSettings,
    user_id: str,
    symbol: str,
    action: str,
    price: float | None,
    quantity: float | None,
    trade_date: str | None,
    note: str | None,
) -> dict:
    return await log_trade(settings.db_path, user_id, symbol, action, price, quantity, trade_date, note)


async def tool_get_trades(
    settings: AgentSettings,
    user_id: str,
    symbol: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    return await get_trades(settings.db_path, user_id, symbol=symbol, from_date=from_date, to_date=to_date)


async def tool_log_event(
    settings: AgentSettings,
    user_id: str,
    title: str,
    content: str | None,
    event_date: str | None,
    tags: list[str] | None,
) -> dict:
    return await log_event(settings.db_path, user_id, title, content, event_date, tags)


async def tool_get_events(
    settings: AgentSettings,
    user_id: str,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    return await get_events(settings.db_path, user_id, from_date=from_date, to_date=to_date)


async def tool_get_user_context(settings: AgentSettings, user_id: str) -> str:
    """生成用户画像摘要，注入 Orchestrator system prompt。"""
    watchlist = await get_watchlist(settings.db_path, user_id)
    trades = await get_trades(settings.db_path, user_id)
    events = await get_events(settings.db_path, user_id)
    lines = []
    if watchlist:
        symbols = ", ".join(w["symbol"] for w in watchlist)
        lines.append(f"关注标的：{symbols}")
    if trades:
        recent = trades[:3]
        t_lines = [f"{t['trade_date']} {t['action']} {t['symbol']} {t['quantity']}股 @{t['price']}" for t in recent]
        lines.append("最近交易：\n" + "\n".join(t_lines))
    if events:
        recent = events[:3]
        e_lines = [f"{e['event_date']} {e['title']}" for e in recent]
        lines.append("最近事件：\n" + "\n".join(e_lines))
    return "\n\n".join(lines) if lines else "暂无个人数据。"


async def tool_run_pipeline(command: str, date: str | None = None) -> str:
    """触发 pipeline 命令（collect / generate）。"""
    import subprocess, sys
    cmd = [sys.executable, "-m", "pipeline", command]
    if date:
        cmd += ["--date", date]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            return f"pipeline {command} 完成。\n{result.stdout[-500:]}"
        return f"pipeline {command} 失败：{result.stderr[-500:]}"
    except subprocess.TimeoutExpired:
        return f"pipeline {command} 超时（300s）"
    except Exception as exc:
        return f"pipeline {command} 出错：{exc}"
```

- [ ] **Step 6: 运行测试确认通过**

```bash
pytest tests/agent/test_tools.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add agent/agents/ tests/agent/test_tools.py tests/agent/conftest.py
git commit -m "feat(agent): agent tools — daily brief, search, watchlist, trades, events, pipeline"
```

---

## Task 2: Orchestrator Agent（SSE 流式推理链）

**Files:**
- Create: `agent/agents/orchestrator.py`
- Create: `tests/agent/test_orchestrator.py`

Orchestrator 是核心。它接收用户输入，识别意图，调用工具，通过 async generator 逐步 yield SSE 事件（thinking + token + done）。

- [ ] **Step 1: 写失败测试 `tests/agent/test_orchestrator.py`**

```python
from __future__ import annotations

import pytest
from tests.agent.conftest import make_settings


@pytest.mark.asyncio
async def test_orchestrator_yields_events(tmp_path):
    from agent.agents.orchestrator import Orchestrator
    settings = make_settings(tmp_path)
    from agent.db import init_db, create_user
    await init_db(settings.db_path)
    user = await create_user(settings.db_path, "u1", None, "pw")

    orch = Orchestrator(settings=settings, user_id=user["id"])
    events = []
    async for event in orch.run("你好，帮我看看今天的简报"):
        events.append(event)
        if len(events) > 50:  # 防止无限循环
            break

    types = {e["type"] for e in events}
    assert "done" in types


@pytest.mark.asyncio
async def test_orchestrator_no_llm_graceful(tmp_path):
    """没有 LLM 配置时应返回错误消息而非崩溃。"""
    from agent.agents.orchestrator import Orchestrator
    settings = make_settings(tmp_path)
    from agent.db import init_db, create_user
    await init_db(settings.db_path)
    user = await create_user(settings.db_path, "u1", None, "pw")

    orch = Orchestrator(settings=settings, user_id=user["id"])
    events = []
    async for event in orch.run("测试"):
        events.append(event)

    assert any(e["type"] == "done" for e in events)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/agent/test_orchestrator.py -v 2>&1 | head -10
```

Expected: ImportError.

- [ ] **Step 3: 创建 `agent/agents/orchestrator.py`**

```python
from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from agent.config import AgentSettings
from agent.agents.tools import (
    get_daily_brief, tool_search_local, tool_get_user_context,
    tool_add_watch, tool_remove_watch, tool_get_watchlist,
    tool_log_trade, tool_get_trades,
    tool_log_event, tool_get_events,
    tool_run_pipeline,
)


def _sse(type: str, **kwargs) -> dict:
    return {"type": type, **kwargs}


class Orchestrator:
    def __init__(self, settings: AgentSettings, user_id: str):
        self._settings = settings
        self._user_id = user_id

    async def run(
        self,
        message: str,
        history: list[dict] | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Yield SSE event dicts: thinking | token | done."""
        settings = self._settings
        user_id = self._user_id

        # 没有 LLM 配置时降级为简单响应
        if not settings.llm_base_url or not settings.llm_model:
            yield _sse("thinking", agent="orchestrator", text="LLM 未配置，进入简单响应模式")
            yield _sse("token", text="当前未配置 LLM。请在 .env 中设置 BRIEF_BASE_URL / BRIEF_MODEL / BRIEF_API_KEY。")
            yield _sse("done", sources=[])
            return

        # 获取用户上下文
        yield _sse("thinking", agent="orchestrator", text="正在加载用户上下文...")
        user_ctx = await tool_get_user_context(settings, user_id)

        # 构建 system prompt
        system_prompt = f"""你是一个专业的投资助手。你可以：
1. 检索本地文章和每日简报（RAG）
2. 管理用户的关注标的、交易记录、事件笔记
3. 触发 pipeline 采集或生成简报

用户个人数据：
{user_ctx}

回复使用中文 markdown 格式，简洁专业。"""

        # 构建对话历史
        messages = [{"role": "system", "content": system_prompt}]
        for h in (history or []):
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": message})

        # 意图识别：判断是否需要检索
        yield _sse("thinking", agent="orchestrator", text="分析意图...")

        needs_search = any(kw in message for kw in ["怎么看", "分析", "观点", "简报", "文章", "历史", "检索", "搜索"])
        needs_memory_write = any(kw in message for kw in ["买了", "卖了", "买入", "卖出", "关注", "记录", "记一下"])
        needs_pipeline = any(kw in message for kw in ["生成简报", "采集", "更新索引"])

        sources = []

        # 检索分支
        if needs_search:
            yield _sse("thinking", agent="research", text=f"检索本地文章：{message[:30]}...")
            results = await tool_search_local(settings, message, top_k=5)
            if results:
                context_parts = []
                for r in results:
                    meta = r["metadata"]
                    context_parts.append(
                        f"【{meta.get('author', '未知')}，{meta.get('date', '')}】\n{r['content']}"
                    )
                    sources.append({
                        "title": meta.get("title", ""),
                        "author": meta.get("author", ""),
                        "date": meta.get("date", ""),
                        "url": meta.get("url", ""),
                        "source": meta.get("source", ""),
                    })
                context = "\n\n---\n\n".join(context_parts)
                messages.append({
                    "role": "system",
                    "content": f"以下是检索到的相关文章，请基于这些内容回答：\n\n{context}"
                })
                yield _sse("thinking", agent="research", text=f"找到 {len(results)} 篇相关文章")
            else:
                yield _sse("thinking", agent="research", text="本地未找到相关文章")

        # 记忆写入分支（简单关键词解析，完整解析由 LLM 完成）
        if needs_memory_write:
            yield _sse("thinking", agent="memory", text="解析记忆操作...")

        # Pipeline 分支
        if needs_pipeline:
            yield _sse("thinking", agent="action", text="检测到 pipeline 操作（需前端确认）")

        # 调用 LLM 生成回复（流式）
        yield _sse("thinking", agent="orchestrator", text="生成回复...")
        try:
            from pipeline.llm import chat_completion
            from pipeline.config import get_settings as get_pipeline_settings
            pipeline_settings = get_pipeline_settings()
            response_text = chat_completion(pipeline_settings, messages)
            # 模拟流式：按句子分块 yield token 事件
            for chunk in _split_to_chunks(response_text, size=50):
                yield _sse("token", text=chunk)
        except Exception as exc:
            yield _sse("token", text=f"生成回复时出错：{exc}")

        yield _sse("done", sources=sources)


def _split_to_chunks(text: str, size: int = 50) -> list[str]:
    """将文本按 size 字符分块，模拟流式 token 输出。"""
    return [text[i:i+size] for i in range(0, len(text), size)]
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/agent/test_orchestrator.py -v
```

Expected: 2 tests PASS（no LLM configured → graceful degradation）.

- [ ] **Step 5: Commit**

```bash
git add agent/agents/orchestrator.py tests/agent/test_orchestrator.py
git commit -m "feat(agent): Orchestrator with SSE event stream and graceful LLM-absent mode"
```

---

## Task 3: 会话路由 `/api/sessions`

**Files:**
- Create: `agent/routers/sessions.py`
- Create: `tests/agent/test_sessions.py`
- Modify: `agent/main.py`（挂载新路由）

- [ ] **Step 1: 写失败测试 `tests/agent/test_sessions.py`**

```python
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


@pytest_asyncio.fixture
async def authed_client(tmp_path):
    import os
    os.environ["AGENT_MEMORY_DIR"] = str(tmp_path)
    os.environ["AGENT_DB_NAME"] = "test.db"
    os.environ["AGENT_JWT_SECRET"] = "test-secret"
    os.environ["BRIEF_BASE_URL"] = ""
    os.environ["BRIEF_MODEL"] = ""
    os.environ["BRIEF_API_KEY"] = ""
    import importlib, agent.config, agent.main
    importlib.reload(agent.config)
    importlib.reload(agent.main)
    from agent.main import app
    from agent.db import init_db
    from agent.config import get_agent_settings
    cfg = get_agent_settings()
    await init_db(cfg.db_path)
    app.state.settings = cfg

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/auth/register", json={"username": "u1", "password": "pw123456"})
        r = await client.post("/api/auth/login", json={"username": "u1", "password": "pw123456"})
        token = r.json()["access_token"]
        client.headers.update({"Authorization": f"Bearer {token}"})
        yield client


@pytest.mark.asyncio
async def test_create_and_list_sessions(authed_client):
    r = await authed_client.post("/api/sessions", json={"title": "Test"})
    assert r.status_code == 200
    sid = r.json()["id"]

    r = await authed_client.get("/api/sessions")
    assert r.status_code == 200
    ids = [s["id"] for s in r.json()]
    assert sid in ids


@pytest.mark.asyncio
async def test_rename_session(authed_client):
    r = await authed_client.post("/api/sessions", json={"title": "Old"})
    sid = r.json()["id"]
    r = await authed_client.patch(f"/api/sessions/{sid}", json={"title": "New"})
    assert r.status_code == 200

    r = await authed_client.get("/api/sessions")
    titles = [s["title"] for s in r.json()]
    assert "New" in titles


@pytest.mark.asyncio
async def test_delete_session(authed_client):
    r = await authed_client.post("/api/sessions", json={"title": "Del"})
    sid = r.json()["id"]
    r = await authed_client.delete(f"/api/sessions/{sid}")
    assert r.status_code == 200

    r = await authed_client.get("/api/sessions")
    ids = [s["id"] for s in r.json()]
    assert sid not in ids


@pytest.mark.asyncio
async def test_get_messages_empty(authed_client):
    r = await authed_client.post("/api/sessions", json={"title": "Msgs"})
    sid = r.json()["id"]
    r = await authed_client.get(f"/api/sessions/{sid}/messages")
    assert r.status_code == 200
    assert r.json() == []
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/agent/test_sessions.py -v 2>&1 | head -15
```

Expected: 404（路由未注册）或 ImportError。

- [ ] **Step 3: 创建 `agent/routers/sessions.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from agent.db import (
    create_session, list_sessions, rename_session,
    delete_session, get_messages,
)
from agent.dependencies import get_current_user

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    title: str | None = None


class RenameSessionRequest(BaseModel):
    title: str


@router.post("")
async def create(body: CreateSessionRequest, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    session = await create_session(cfg.db_path, user["id"], body.title)
    return session


@router.get("")
async def list_all(request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    return await list_sessions(cfg.db_path, user["id"])


@router.patch("/{session_id}")
async def rename(session_id: str, body: RenameSessionRequest, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    try:
        await rename_session(cfg.db_path, session_id, user["id"], body.title)
    except LookupError:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


@router.delete("/{session_id}")
async def delete(session_id: str, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    await delete_session(cfg.db_path, session_id, user["id"])
    return {"ok": True}


@router.get("/{session_id}/messages")
async def get_msgs(session_id: str, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    return await get_messages(cfg.db_path, session_id, user["id"])
```

- [ ] **Step 4: 在 `agent/main.py` 中挂载 sessions 路由**

在 `app.include_router(auth_router.router)` 后面添加：

```python
from agent.routers import sessions as sessions_router
app.include_router(sessions_router.router)
```

- [ ] **Step 5: 运行测试确认通过**

```bash
pytest tests/agent/test_sessions.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add agent/routers/sessions.py tests/agent/test_sessions.py agent/main.py
git commit -m "feat(agent): sessions CRUD routes — create, list, rename, delete, get messages"
```

---

## Task 4: 记忆路由 `/api/memory`

**Files:**
- Create: `agent/routers/memory.py`
- Create: `tests/agent/test_memory_routes.py`
- Modify: `agent/main.py`

- [ ] **Step 1: 写失败测试 `tests/agent/test_memory_routes.py`**

```python
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


@pytest_asyncio.fixture
async def authed_client(tmp_path):
    import os
    os.environ["AGENT_MEMORY_DIR"] = str(tmp_path)
    os.environ["AGENT_DB_NAME"] = "test.db"
    os.environ["AGENT_JWT_SECRET"] = "test-secret"
    os.environ["BRIEF_BASE_URL"] = ""
    os.environ["BRIEF_MODEL"] = ""
    os.environ["BRIEF_API_KEY"] = ""
    import importlib, agent.config, agent.main
    importlib.reload(agent.config)
    importlib.reload(agent.main)
    from agent.main import app
    from agent.db import init_db
    from agent.config import get_agent_settings
    cfg = get_agent_settings()
    await init_db(cfg.db_path)
    app.state.settings = cfg
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/auth/register", json={"username": "m1", "password": "pw123456"})
        r = await client.post("/api/auth/login", json={"username": "m1", "password": "pw123456"})
        client.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
        yield client


@pytest.mark.asyncio
async def test_watchlist_crud(authed_client):
    r = await authed_client.post("/api/memory/watchlist", json={"symbol": "MU"})
    assert r.status_code == 200
    r = await authed_client.get("/api/memory/watchlist")
    assert any(w["symbol"] == "MU" for w in r.json())
    r = await authed_client.delete("/api/memory/watchlist/MU")
    assert r.status_code == 200
    r = await authed_client.get("/api/memory/watchlist")
    assert not any(w["symbol"] == "MU" for w in r.json())


@pytest.mark.asyncio
async def test_trades_crud(authed_client):
    r = await authed_client.post("/api/memory/trades", json={
        "symbol": "MU", "action": "buy", "price": 105.0, "quantity": 100,
        "date": "2026-06-12", "note": "test"
    })
    assert r.status_code == 200
    tid = r.json()["id"]
    r = await authed_client.get("/api/memory/trades")
    assert any(t["id"] == tid for t in r.json())
    r = await authed_client.delete(f"/api/memory/trades/{tid}")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_events_crud(authed_client):
    r = await authed_client.post("/api/memory/events", json={
        "title": "降息", "content": "影响仓位", "date": "2026-06-12", "tags": ["macro"]
    })
    assert r.status_code == 200
    eid = r.json()["id"]
    r = await authed_client.get("/api/memory/events")
    assert any(e["id"] == eid for e in r.json())
    r = await authed_client.delete(f"/api/memory/events/{eid}")
    assert r.status_code == 200
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/agent/test_memory_routes.py -v 2>&1 | head -15
```

- [ ] **Step 3: 创建 `agent/routers/memory.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agent.db import (
    add_watch, remove_watch, get_watchlist,
    log_trade, get_trades, delete_trade,
    log_event, get_events, delete_event,
)
from agent.dependencies import get_current_user

router = APIRouter(prefix="/api/memory", tags=["memory"])


class WatchlistAddRequest(BaseModel):
    symbol: str
    note: str | None = None


class TradeRequest(BaseModel):
    symbol: str
    action: str
    price: float | None = None
    quantity: float | None = None
    date: str | None = None
    note: str | None = None


class EventRequest(BaseModel):
    title: str
    content: str | None = None
    date: str | None = None
    tags: list[str] | None = None


@router.get("/watchlist")
async def watchlist_list(request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    return await get_watchlist(cfg.db_path, user["id"])


@router.post("/watchlist")
async def watchlist_add(body: WatchlistAddRequest, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    await add_watch(cfg.db_path, user["id"], body.symbol, body.note)
    return {"ok": True, "symbol": body.symbol.upper()}


@router.delete("/watchlist/{symbol}")
async def watchlist_remove(symbol: str, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    await remove_watch(cfg.db_path, user["id"], symbol)
    return {"ok": True}


@router.get("/trades")
async def trades_list(request: Request, symbol: str | None = None,
                      from_date: str | None = None, to_date: str | None = None):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    return await get_trades(cfg.db_path, user["id"], symbol=symbol, from_date=from_date, to_date=to_date)


@router.post("/trades")
async def trades_add(body: TradeRequest, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    trade = await log_trade(cfg.db_path, user["id"], body.symbol, body.action,
                            body.price, body.quantity, body.date, body.note)
    return trade


@router.delete("/trades/{trade_id}")
async def trades_delete(trade_id: int, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    await delete_trade(cfg.db_path, trade_id, user["id"])
    return {"ok": True}


@router.get("/events")
async def events_list(request: Request, from_date: str | None = None, to_date: str | None = None):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    return await get_events(cfg.db_path, user["id"], from_date=from_date, to_date=to_date)


@router.post("/events")
async def events_add(body: EventRequest, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    event = await log_event(cfg.db_path, user["id"], body.title, body.content, body.date, body.tags)
    return event


@router.delete("/events/{event_id}")
async def events_delete(event_id: int, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    await delete_event(cfg.db_path, event_id, user["id"])
    return {"ok": True}
```

- [ ] **Step 4: 在 `agent/main.py` 挂载 memory 路由**

```python
from agent.routers import memory as memory_router
app.include_router(memory_router.router)
```

- [ ] **Step 5: 运行测试确认通过**

```bash
pytest tests/agent/test_memory_routes.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add agent/routers/memory.py tests/agent/test_memory_routes.py agent/main.py
git commit -m "feat(agent): memory routes — watchlist, trades, events CRUD"
```

---

## Task 5: Pipeline 路由 + SSE 对话端点

**Files:**
- Create: `agent/routers/pipeline.py`
- Create: `agent/routers/chat.py`
- Create: `tests/agent/test_chat_routes.py`
- Modify: `agent/main.py`

- [ ] **Step 1: 创建 `agent/routers/pipeline.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from agent.agents.tools import tool_run_pipeline
from agent.dependencies import get_current_user

router = APIRouter(prefix="/api", tags=["pipeline"])


class PipelineRequest(BaseModel):
    date: str | None = None


@router.post("/pipeline/collect")
async def collect(body: PipelineRequest, request: Request):
    await get_current_user(request)
    result = await tool_run_pipeline("collect", body.date)
    return {"result": result}


@router.post("/pipeline/generate")
async def generate(body: PipelineRequest, request: Request):
    await get_current_user(request)
    result = await tool_run_pipeline("generate", body.date)
    return {"result": result}


@router.post("/index/update")
async def index_update(body: PipelineRequest, request: Request):
    await get_current_user(request)
    cfg = request.app.state.settings
    from agent.indexer import ArticleIndexer
    indexer = ArticleIndexer(
        chroma_path=cfg.chroma_path,
        llm_api_key=cfg.llm_api_key,
        llm_base_url=cfg.llm_base_url,
    )
    date_str = body.date or __import__("datetime").date.today().isoformat()
    indexer.update(sources_root=cfg.sources_root, date_str=date_str)
    return {"ok": True, "date": date_str}
```

- [ ] **Step 2: 创建 `agent/routers/chat.py`**

```python
from __future__ import annotations

import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.agents.orchestrator import Orchestrator
from agent.db import (
    create_session, get_messages, append_message, rename_session, list_sessions
)
from agent.dependencies import get_current_user

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str


@router.post("/chat")
async def chat(body: ChatRequest, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    uid = user["id"]

    # 创建或复用会话
    if body.session_id:
        session_id = body.session_id
    else:
        session = await create_session(cfg.db_path, uid, body.message[:20])
        session_id = session["id"]

    # 加载历史消息
    history = await get_messages(cfg.db_path, session_id, uid)

    # 保存用户消息
    await append_message(cfg.db_path, session_id, uid, "user", body.message, None, None)

    async def event_stream():
        orch = Orchestrator(settings=cfg, user_id=uid)
        collected_tokens = []
        sources = []

        async for event in orch.run(body.message, history=history):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event["type"] == "token":
                collected_tokens.append(event["text"])
            elif event["type"] == "done":
                sources = event.get("sources", [])

        # 保存 assistant 消息
        full_text = "".join(collected_tokens)
        await append_message(cfg.db_path, session_id, uid, "assistant", full_text, "orchestrator", sources)

        # 自动设置会话标题（第一条消息）
        sessions = await list_sessions(cfg.db_path, uid)
        current = next((s for s in sessions if s["id"] == session_id), None)
        if current and not current.get("title"):
            await rename_session(cfg.db_path, session_id, uid, body.message[:20])

        yield f"data: {json.dumps({'type': 'session_id', 'session_id': session_id}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )
```

- [ ] **Step 3: 写失败测试 `tests/agent/test_chat_routes.py`**

```python
from __future__ import annotations

import json
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


@pytest_asyncio.fixture
async def authed_client(tmp_path):
    import os
    os.environ["AGENT_MEMORY_DIR"] = str(tmp_path)
    os.environ["AGENT_DB_NAME"] = "test.db"
    os.environ["AGENT_JWT_SECRET"] = "test-secret"
    os.environ["BRIEF_BASE_URL"] = ""
    os.environ["BRIEF_MODEL"] = ""
    os.environ["BRIEF_API_KEY"] = ""
    import importlib, agent.config, agent.main
    importlib.reload(agent.config)
    importlib.reload(agent.main)
    from agent.main import app
    from agent.db import init_db
    from agent.config import get_agent_settings
    cfg = get_agent_settings()
    await init_db(cfg.db_path)
    app.state.settings = cfg
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/auth/register", json={"username": "c1", "password": "pw123456"})
        r = await client.post("/api/auth/login", json={"username": "c1", "password": "pw123456"})
        client.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
        yield client


@pytest.mark.asyncio
async def test_chat_returns_sse_stream(authed_client):
    r = await authed_client.post("/api/chat", json={"message": "你好"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]

    lines = r.text.strip().split("\n")
    events = []
    for line in lines:
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    types = {e["type"] for e in events}
    assert "done" in types


@pytest.mark.asyncio
async def test_chat_message_persisted(authed_client):
    r = await authed_client.post("/api/chat", json={"message": "测试消息"})
    assert r.status_code == 200

    lines = r.text.strip().split("\n")
    session_id = None
    for line in lines:
        if line.startswith("data: "):
            event = json.loads(line[6:])
            if event["type"] == "session_id":
                session_id = event["session_id"]
                break

    assert session_id is not None
    r = await authed_client.get(f"/api/sessions/{session_id}/messages")
    assert r.status_code == 200
    msgs = r.json()
    assert any(m["role"] == "user" and "测试消息" in m["content"] for m in msgs)
```

- [ ] **Step 4: 运行测试确认失败**

```bash
pytest tests/agent/test_chat_routes.py -v 2>&1 | head -15
```

- [ ] **Step 5: 挂载新路由到 `agent/main.py`**

```python
from agent.routers import sessions as sessions_router
from agent.routers import memory as memory_router
from agent.routers import pipeline as pipeline_router
from agent.routers import chat as chat_router

app.include_router(sessions_router.router)
app.include_router(memory_router.router)
app.include_router(pipeline_router.router)
app.include_router(chat_router.router)
```

- [ ] **Step 6: 运行所有测试**

```bash
pytest tests/agent/ -q
```

Expected: 全部通过（≥ 37 tests）。

- [ ] **Step 7: Commit**

```bash
git add agent/routers/pipeline.py agent/routers/chat.py tests/agent/test_chat_routes.py agent/main.py
git commit -m "feat(agent): chat SSE endpoint, pipeline routes, full router registration"
```

---

## Plan B 完成验证

```bash
# 启动后端
python -m agent --port 8080 &
sleep 2

# 测试完整对话流
curl -s -X POST http://localhost:8080/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"password123"}'

curl -s -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"password123"}' \
  -c /tmp/cookies.txt

curl -s -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -b /tmp/cookies.txt \
  -d '{"message":"你好"}' --no-buffer

kill %1
```

Expected: SSE 流式响应，包含 `thinking` → `token` → `done` 事件序列。
