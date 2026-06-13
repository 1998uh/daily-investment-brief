# Investment Agent — Plan A: Backend Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend foundation: SQLite data layer, ChromaDB vector index, and JWT authentication — everything Plan B (Agent layer) depends on.

**Architecture:** Single FastAPI app in `agent/` directory, completely independent of existing `pipeline/`. SQLite via `aiosqlite` for relational data (users, sessions, messages, watchlist, trades, events). ChromaDB local file store for semantic search over `sources/` articles and `reports/` briefs. JWT in httpOnly cookies for auth.

**Tech Stack:** Python 3.10+, FastAPI, aiosqlite, chromadb, langchain-openai (embeddings), passlib[bcrypt], python-jose[cryptography], pytest, pytest-asyncio

---

## File Map

| File | Role |
|------|------|
| `agent/__init__.py` | Package marker |
| `agent/config.py` | Settings from `.env` — db path, chroma path, JWT secret, LLM config |
| `agent/db.py` | SQLite init + all CRUD functions |
| `agent/auth.py` | Password hashing, JWT encode/decode, `get_current_user` dependency |
| `agent/indexer.py` | Scan `sources/` + `reports/`, chunk, embed, upsert to ChromaDB |
| `agent/main.py` | FastAPI app, mounts routers, lifespan startup |
| `agent/routers/__init__.py` | Package marker |
| `agent/routers/auth.py` | `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/refresh` |
| `tests/agent/__init__.py` | Package marker |
| `tests/agent/test_db.py` | Unit tests for all CRUD functions |
| `tests/agent/test_auth.py` | Unit tests for password hashing + JWT |
| `tests/agent/test_indexer.py` | Integration test for indexer with fixture articles |
| `tests/agent/test_auth_routes.py` | HTTP-level tests for auth endpoints |

---

## Task 1: Project scaffold + config

**Files:**
- Create: `agent/__init__.py`
- Create: `agent/config.py`
- Create: `agent/routers/__init__.py`
- Create: `tests/agent/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add `[agent]` optional dependencies to `pyproject.toml`**

Open `pyproject.toml` and add after the existing `[project.optional-dependencies]` section:

```toml
[project.optional-dependencies]
collect = [
    "playwright>=1.40",
]
agent = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.30",
    "langchain>=0.2",
    "langchain-community>=0.2",
    "langchain-openai>=0.1",
    "chromadb>=0.5",
    "aiosqlite>=0.20",
    "tavily-python>=0.3",
    "python-jose[cryptography]>=3.3",
    "passlib[bcrypt]>=1.7",
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
]
```

- [ ] **Step 2: Install dependencies**

```bash
pip install -e ".[agent]"
```

Expected: installs without errors. Verify with `python -c "import fastapi, chromadb, aiosqlite; print('ok')"`.

- [ ] **Step 3: Create package markers**

Create `agent/__init__.py` — empty file.  
Create `agent/routers/__init__.py` — empty file.  
Create `tests/agent/__init__.py` — empty file.

- [ ] **Step 4: Write `agent/config.py`**

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class AgentSettings:
    db_path: Path
    chroma_path: Path
    sources_root: Path
    reports_root: Path
    jwt_secret: str
    jwt_algorithm: str
    jwt_expire_minutes: int
    llm_base_url: str
    llm_model: str
    llm_api_key: str
    tavily_api_key: str


def get_agent_settings() -> AgentSettings:
    from pipeline.config import load_env
    load_env()
    memory = ROOT / _env("AGENT_MEMORY_DIR", "memory")
    return AgentSettings(
        db_path=memory / _env("AGENT_DB_NAME", "agent.db"),
        chroma_path=memory / _env("AGENT_CHROMA_DIR", "chroma"),
        sources_root=ROOT / _env("AGENT_SOURCES_DIR", "sources"),
        reports_root=ROOT / _env("AGENT_REPORTS_DIR", "reports"),
        jwt_secret=_env("AGENT_JWT_SECRET", "change-me-in-production"),
        jwt_algorithm=_env("AGENT_JWT_ALGORITHM", "HS256"),
        jwt_expire_minutes=int(_env("AGENT_JWT_EXPIRE_MINUTES", "10080")),  # 7 days
        llm_base_url=_env("BRIEF_BASE_URL"),
        llm_model=_env("BRIEF_MODEL"),
        llm_api_key=_env("BRIEF_API_KEY"),
        tavily_api_key=_env("TAVILY_API_KEY"),
    )
```

- [ ] **Step 5: Add new env vars to `.env.example`**

Append to the existing `.env.example`:

```bash
# Agent system
AGENT_MEMORY_DIR=memory
AGENT_DB_NAME=agent.db
AGENT_CHROMA_DIR=chroma
AGENT_SOURCES_DIR=sources
AGENT_REPORTS_DIR=reports
AGENT_JWT_SECRET=change-me-in-production
AGENT_JWT_ALGORITHM=HS256
AGENT_JWT_EXPIRE_MINUTES=10080
TAVILY_API_KEY=tvly-...
```

- [ ] **Step 6: Commit**

```bash
git add agent/ tests/agent/ pyproject.toml .env.example
git commit -m "feat(agent): scaffold package, config, dependencies"
```

---

## Task 2: SQLite data layer

**Files:**
- Create: `agent/db.py`
- Create: `tests/agent/test_db.py`

- [ ] **Step 1: Write failing tests for `db.py`**

Create `tests/agent/test_db.py`:

```python
from __future__ import annotations

import json
import pytest
import pytest_asyncio
from pathlib import Path
import aiosqlite

from agent.db import init_db, create_user, get_user_by_username, create_session, \
    list_sessions, append_message, get_messages, delete_session, \
    add_watch, remove_watch, get_watchlist, \
    log_trade, get_trades, log_event, get_events


@pytest_asyncio.fixture
async def db_path(tmp_path):
    path = tmp_path / "test.db"
    await init_db(path)
    return path


@pytest.mark.asyncio
async def test_create_and_get_user(db_path):
    user = await create_user(db_path, "alice", "alice@example.com", "hashed_pw")
    assert user["username"] == "alice"
    fetched = await get_user_by_username(db_path, "alice")
    assert fetched["id"] == user["id"]


@pytest.mark.asyncio
async def test_create_and_list_sessions(db_path):
    user = await create_user(db_path, "bob", None, "pw")
    session = await create_session(db_path, user["id"], "Test Session")
    sessions = await list_sessions(db_path, user["id"])
    assert len(sessions) == 1
    assert sessions[0]["title"] == "Test Session"


@pytest.mark.asyncio
async def test_append_and_get_messages(db_path):
    user = await create_user(db_path, "carol", None, "pw")
    session = await create_session(db_path, user["id"])
    await append_message(db_path, session["id"], "user", "hello", agent=None, sources=None)
    await append_message(db_path, session["id"], "assistant", "world", agent="orchestrator", sources=[{"title": "t"}])
    msgs = await get_messages(db_path, session["id"])
    assert len(msgs) == 2
    assert msgs[1]["sources"] == [{"title": "t"}]


@pytest.mark.asyncio
async def test_delete_session_cascades_messages(db_path):
    user = await create_user(db_path, "dave", None, "pw")
    session = await create_session(db_path, user["id"])
    await append_message(db_path, session["id"], "user", "hi", None, None)
    await delete_session(db_path, session["id"], user["id"])
    msgs = await get_messages(db_path, session["id"])
    assert msgs == []


@pytest.mark.asyncio
async def test_watchlist_crud(db_path):
    user = await create_user(db_path, "eve", None, "pw")
    await add_watch(db_path, user["id"], "MU", "美光科技")
    await add_watch(db_path, user["id"], "NVDA", None)
    items = await get_watchlist(db_path, user["id"])
    assert {i["symbol"] for i in items} == {"MU", "NVDA"}
    await remove_watch(db_path, user["id"], "MU")
    items = await get_watchlist(db_path, user["id"])
    assert len(items) == 1


@pytest.mark.asyncio
async def test_log_and_get_trades(db_path):
    user = await create_user(db_path, "frank", None, "pw")
    await log_trade(db_path, user["id"], "MU", "buy", 105.0, 100, "2026-06-12", "first buy")
    trades = await get_trades(db_path, user["id"])
    assert len(trades) == 1
    assert trades[0]["symbol"] == "MU"
    assert trades[0]["price"] == 105.0
    # filter by symbol
    trades2 = await get_trades(db_path, user["id"], symbol="NVDA")
    assert trades2 == []


@pytest.mark.asyncio
async def test_log_and_get_events(db_path):
    user = await create_user(db_path, "grace", None, "pw")
    await log_event(db_path, user["id"], "降息预期改变", "重新评估仓位", "2026-06-12", ["macro", "fed"])
    events = await get_events(db_path, user["id"])
    assert len(events) == 1
    assert events[0]["tags"] == ["macro", "fed"]
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/agent/test_db.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `agent.db` doesn't exist yet.

- [ ] **Step 3: Write `agent/db.py`**

```python
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;

        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            agent TEXT,
            content TEXT NOT NULL,
            sources TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS watchlist (
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            symbol TEXT NOT NULL,
            note TEXT,
            added_at TEXT NOT NULL,
            PRIMARY KEY (user_id, symbol)
        );

        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            symbol TEXT NOT NULL,
            action TEXT NOT NULL,
            price REAL,
            quantity REAL,
            trade_date TEXT,
            note TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            content TEXT,
            event_date TEXT,
            tags TEXT,
            created_at TEXT NOT NULL
        );
        """)
        await db.commit()


def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
    return dict(row)


async def create_user(db_path: Path, username: str, email: str | None, password_hash: str) -> dict:
    uid = str(uuid.uuid4())
    now = _now()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT INTO users (id, username, email, password_hash, created_at) VALUES (?,?,?,?,?)",
            (uid, username, email, password_hash, now),
        )
        await db.commit()
        async with db.execute("SELECT * FROM users WHERE id=?", (uid,)) as cur:
            return _row_to_dict(await cur.fetchone())


async def get_user_by_username(db_path: Path, username: str) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE username=?", (username,)) as cur:
            row = await cur.fetchone()
            return _row_to_dict(row) if row else None


async def get_user_by_id(db_path: Path, user_id: str) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            return _row_to_dict(row) if row else None


async def create_session(db_path: Path, user_id: str, title: str | None = None) -> dict:
    sid = str(uuid.uuid4())
    now = _now()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT INTO sessions (id, user_id, title, created_at, updated_at) VALUES (?,?,?,?,?)",
            (sid, user_id, title, now, now),
        )
        await db.commit()
        async with db.execute("SELECT * FROM sessions WHERE id=?", (sid,)) as cur:
            return _row_to_dict(await cur.fetchone())


async def list_sessions(db_path: Path, user_id: str) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM sessions WHERE user_id=? ORDER BY updated_at DESC",
            (user_id,),
        ) as cur:
            return [_row_to_dict(r) for r in await cur.fetchall()]


async def rename_session(db_path: Path, session_id: str, user_id: str, title: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE sessions SET title=?, updated_at=? WHERE id=? AND user_id=?",
            (title, _now(), session_id, user_id),
        )
        await db.commit()


async def delete_session(db_path: Path, session_id: str, user_id: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "DELETE FROM sessions WHERE id=? AND user_id=?",
            (session_id, user_id),
        )
        await db.commit()


async def append_message(
    db_path: Path,
    session_id: str,
    role: str,
    content: str,
    agent: str | None,
    sources: list | None,
) -> dict:
    now = _now()
    sources_json = json.dumps(sources, ensure_ascii=False) if sources is not None else None
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "INSERT INTO messages (session_id, role, agent, content, sources, created_at) VALUES (?,?,?,?,?,?)",
            (session_id, role, agent, content, sources_json, now),
        )
        await db.execute(
            "UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id)
        )
        await db.commit()
        async with db.execute("SELECT * FROM messages WHERE id=?", (cur.lastrowid,)) as c:
            row = _row_to_dict(await c.fetchone())
    row["sources"] = json.loads(row["sources"]) if row["sources"] else None
    return row


async def get_messages(db_path: Path, session_id: str) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM messages WHERE session_id=? ORDER BY id ASC", (session_id,)
        ) as cur:
            rows = [_row_to_dict(r) for r in await cur.fetchall()]
    for r in rows:
        r["sources"] = json.loads(r["sources"]) if r["sources"] else None
    return rows


async def add_watch(db_path: Path, user_id: str, symbol: str, note: str | None) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO watchlist (user_id, symbol, note, added_at) VALUES (?,?,?,?)",
            (user_id, symbol.upper(), note, _now()),
        )
        await db.commit()


async def remove_watch(db_path: Path, user_id: str, symbol: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "DELETE FROM watchlist WHERE user_id=? AND symbol=?",
            (user_id, symbol.upper()),
        )
        await db.commit()


async def get_watchlist(db_path: Path, user_id: str) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM watchlist WHERE user_id=? ORDER BY added_at DESC", (user_id,)
        ) as cur:
            return [_row_to_dict(r) for r in await cur.fetchall()]


async def log_trade(
    db_path: Path,
    user_id: str,
    symbol: str,
    action: str,
    price: float | None,
    quantity: float | None,
    trade_date: str | None,
    note: str | None,
) -> dict:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "INSERT INTO trades (user_id, symbol, action, price, quantity, trade_date, note, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (user_id, symbol.upper(), action, price, quantity, trade_date, note, _now()),
        )
        await db.commit()
        async with db.execute("SELECT * FROM trades WHERE id=?", (cur.lastrowid,)) as c:
            return _row_to_dict(await c.fetchone())


async def get_trades(
    db_path: Path,
    user_id: str,
    symbol: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    query = "SELECT * FROM trades WHERE user_id=?"
    params: list = [user_id]
    if symbol:
        query += " AND symbol=?"
        params.append(symbol.upper())
    if from_date:
        query += " AND trade_date>=?"
        params.append(from_date)
    if to_date:
        query += " AND trade_date<=?"
        params.append(to_date)
    query += " ORDER BY trade_date DESC, id DESC"
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cur:
            return [_row_to_dict(r) for r in await cur.fetchall()]


async def delete_trade(db_path: Path, trade_id: int, user_id: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM trades WHERE id=? AND user_id=?", (trade_id, user_id))
        await db.commit()


async def log_event(
    db_path: Path,
    user_id: str,
    title: str,
    content: str | None,
    event_date: str | None,
    tags: list[str] | None,
) -> dict:
    tags_json = json.dumps(tags, ensure_ascii=False) if tags else None
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "INSERT INTO events (user_id, title, content, event_date, tags, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, title, content, event_date, tags_json, _now()),
        )
        await db.commit()
        async with db.execute("SELECT * FROM events WHERE id=?", (cur.lastrowid,)) as c:
            row = _row_to_dict(await c.fetchone())
    row["tags"] = json.loads(row["tags"]) if row["tags"] else []
    return row


async def get_events(
    db_path: Path,
    user_id: str,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    query = "SELECT * FROM events WHERE user_id=?"
    params: list = [user_id]
    if from_date:
        query += " AND event_date>=?"
        params.append(from_date)
    if to_date:
        query += " AND event_date<=?"
        params.append(to_date)
    query += " ORDER BY event_date DESC, id DESC"
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cur:
            rows = [_row_to_dict(r) for r in await cur.fetchall()]
    for r in rows:
        r["tags"] = json.loads(r["tags"]) if r["tags"] else []
    return rows


async def delete_event(db_path: Path, event_id: int, user_id: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM events WHERE id=? AND user_id=?", (event_id, user_id))
        await db.commit()
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/agent/test_db.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/db.py tests/agent/test_db.py
git commit -m "feat(agent): SQLite data layer with full CRUD"
```

---

## Task 3: Auth — password hashing + JWT

**Files:**
- Create: `agent/auth.py`
- Create: `tests/agent/test_auth.py`

- [ ] **Step 1: Write failing tests**

Create `tests/agent/test_auth.py`:

```python
from __future__ import annotations

import pytest
from agent.auth import hash_password, verify_password, create_token, decode_token


def test_hash_and_verify():
    pw = "s3cret!"
    hashed = hash_password(pw)
    assert hashed != pw
    assert verify_password(pw, hashed)
    assert not verify_password("wrong", hashed)


def test_create_and_decode_token():
    token = create_token({"sub": "user-123"}, expire_minutes=60, secret="test-secret", algorithm="HS256")
    payload = decode_token(token, secret="test-secret", algorithm="HS256")
    assert payload["sub"] == "user-123"


def test_decode_token_wrong_secret():
    token = create_token({"sub": "user-123"}, expire_minutes=60, secret="real", algorithm="HS256")
    with pytest.raises(Exception):
        decode_token(token, secret="wrong", algorithm="HS256")


def test_decode_expired_token():
    token = create_token({"sub": "user-123"}, expire_minutes=-1, secret="s", algorithm="HS256")
    with pytest.raises(Exception):
        decode_token(token, secret="s", algorithm="HS256")
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/agent/test_auth.py -v
```

Expected: `ImportError` — `agent.auth` doesn't exist yet.

- [ ] **Step 3: Write `agent/auth.py`**

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


def create_token(
    data: dict[str, Any],
    expire_minutes: int,
    secret: str,
    algorithm: str,
) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_token(token: str, secret: str, algorithm: str) -> dict[str, Any]:
    # Raises JWTError on invalid/expired tokens
    return jwt.decode(token, secret, algorithms=[algorithm])
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/agent/test_auth.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/auth.py tests/agent/test_auth.py
git commit -m "feat(agent): password hashing and JWT encode/decode"
```

---

## Task 4: FastAPI app + auth routes

**Files:**
- Create: `agent/main.py`
- Create: `agent/routers/auth.py`
- Create: `tests/agent/test_auth_routes.py`

- [ ] **Step 1: Write failing tests**

Create `tests/agent/test_auth_routes.py`:

```python
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from pathlib import Path


@pytest_asyncio.fixture
async def app(tmp_path):
    import os
    os.environ["AGENT_MEMORY_DIR"] = str(tmp_path)
    os.environ["AGENT_DB_NAME"] = "test.db"
    os.environ["AGENT_JWT_SECRET"] = "test-secret"
    os.environ["BRIEF_BASE_URL"] = ""
    os.environ["BRIEF_MODEL"] = ""
    os.environ["BRIEF_API_KEY"] = ""
    # Re-import after env vars set
    import importlib
    import agent.config
    importlib.reload(agent.config)
    import agent.main
    importlib.reload(agent.main)
    from agent.main import app
    from agent.db import init_db
    from agent.config import get_agent_settings
    cfg = get_agent_settings()
    await init_db(cfg.db_path)
    return app


@pytest.mark.asyncio
async def test_register_and_login(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # register
        r = await client.post("/api/auth/register", json={"username": "alice", "password": "pw123456"})
        assert r.status_code == 200
        assert r.json()["username"] == "alice"

        # login
        r = await client.post("/api/auth/login", json={"username": "alice", "password": "pw123456"})
        assert r.status_code == 200
        assert "access_token" in r.json()


@pytest.mark.asyncio
async def test_login_wrong_password(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/auth/register", json={"username": "bob", "password": "correct"})
        r = await client.post("/api/auth/login", json={"username": "bob", "password": "wrong"})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_username(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/auth/register", json={"username": "carol", "password": "pw"})
        r = await client.post("/api/auth/register", json={"username": "carol", "password": "pw"})
        assert r.status_code == 409


@pytest.mark.asyncio
async def test_health(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/agent/test_auth_routes.py -v
```

Expected: `ImportError` — `agent.main` doesn't exist yet.

- [ ] **Step 3: Write `agent/routers/auth.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from agent.auth import create_token, hash_password, verify_password
from agent.config import AgentSettings
from agent.db import create_user, get_user_by_username

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _settings(request: Request) -> AgentSettings:
    return request.app.state.settings


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/register")
async def register(body: RegisterRequest, request: Request):
    cfg = _settings(request)
    existing = await get_user_by_username(cfg.db_path, body.username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")
    if len(body.password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters")
    user = await create_user(cfg.db_path, body.username, body.email, hash_password(body.password))
    return {"id": user["id"], "username": user["username"]}


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response):
    cfg = _settings(request)
    user = await get_user_by_username(cfg.db_path, body.username)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(
        {"sub": user["id"]},
        expire_minutes=cfg.jwt_expire_minutes,
        secret=cfg.jwt_secret,
        algorithm=cfg.jwt_algorithm,
    )
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=cfg.jwt_expire_minutes * 60,
    )
    return {"access_token": token, "token_type": "bearer"}


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    from agent.main import get_current_user
    user = await get_current_user(request)
    cfg = _settings(request)
    token = create_token(
        {"sub": user["id"]},
        expire_minutes=cfg.jwt_expire_minutes,
        secret=cfg.jwt_secret,
        algorithm=cfg.jwt_algorithm,
    )
    response.set_cookie("access_token", token, httponly=True, samesite="lax",
                        max_age=cfg.jwt_expire_minutes * 60)
    return {"access_token": token, "token_type": "bearer"}
```

- [ ] **Step 4: Write `agent/main.py`**

```python
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError

from agent.auth import decode_token
from agent.config import get_agent_settings
from agent.db import get_user_by_id, init_db
from agent.routers import auth as auth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_agent_settings()
    await init_db(cfg.db_path)
    app.state.settings = cfg
    yield


app = FastAPI(title="Investment Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)


async def get_current_user(request: Request) -> dict:
    cfg = request.app.state.settings
    token = request.cookies.get("access_token")
    if not token:
        # Also accept Bearer header for API clients
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(token, secret=cfg.jwt_secret, algorithm=cfg.jwt_algorithm)
        user_id: str = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await get_user_by_id(cfg.db_path, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
pytest tests/agent/test_auth_routes.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add agent/main.py agent/routers/auth.py tests/agent/test_auth_routes.py
git commit -m "feat(agent): FastAPI app with register/login/JWT auth"
```

---

## Task 5: ChromaDB indexer

**Files:**
- Create: `agent/indexer.py`
- Create: `tests/agent/test_indexer.py`

- [ ] **Step 1: Create fixture articles for tests**

Create `tests/agent/fixtures/` directory and two sample markdown files:

`tests/agent/fixtures/xueqiu-test-author-test-article-aabbccdd.md`:
```markdown
---
source: 雪球
author: 测试作者
title: 测试文章关于美光
url: https://xueqiu.com/test/1
published_at: 2026-06-10 09:00:00
collected_at: 2026-06-10 10:00:00
---

美光科技（MU）最新财报超出预期，HBM 需求强劲，目标价 120 美元。存储行业进入上行周期。
```

`tests/agent/fixtures/reports/2026-06-10/daily-brief.md`:
```markdown
# 每日投资简报 — 2026年6月10日

## 半导体板块

今日半导体板块整体上涨，美光带动存储股走强。
```

- [ ] **Step 2: Write failing tests**

Create `tests/agent/test_indexer.py`:

```python
from __future__ import annotations

import pytest
from pathlib import Path
from agent.indexer import ArticleIndexer, SearchResult


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def indexer(tmp_path):
    # Use a tiny local embedding model to avoid real API calls in tests
    return ArticleIndexer(
        chroma_path=tmp_path / "chroma",
        embedding_model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        use_local_embeddings=True,
    )


def test_build_index_finds_articles(indexer):
    indexer.build(
        sources_root=FIXTURES,
        reports_root=FIXTURES / "reports",
    )
    stats = indexer.stats()
    assert stats["total_docs"] > 0


def test_search_returns_results(indexer):
    indexer.build(sources_root=FIXTURES, reports_root=FIXTURES / "reports")
    results = indexer.search("美光 HBM 存储", top_k=3)
    assert len(results) >= 1
    assert isinstance(results[0], SearchResult)
    assert results[0].content
    assert results[0].metadata["author"]


def test_search_with_author_filter(indexer):
    indexer.build(sources_root=FIXTURES, reports_root=FIXTURES / "reports")
    results = indexer.search("美光", top_k=5, author="测试作者")
    assert all(r.metadata["author"] == "测试作者" for r in results)


def test_incremental_update(indexer, tmp_path):
    # Build initial index
    indexer.build(sources_root=FIXTURES, reports_root=FIXTURES / "reports")
    before = indexer.stats()["total_docs"]

    # Add a new article
    new_dir = tmp_path / "sources" / "2026-06-13"
    new_dir.mkdir(parents=True)
    (new_dir / "xueqiu-new-article-12345678.md").write_text(
        "---\nsource: 雪球\nauthor: 新作者\ntitle: 新文章\nurl: https://x.com/2\npublished_at: 2026-06-13 09:00:00\ncollected_at: 2026-06-13 10:00:00\n---\n\nNVDA 最新动态。",
        encoding="utf-8",
    )

    indexer.update(sources_root=tmp_path / "sources", date_str="2026-06-13")
    after = indexer.stats()["total_docs"]
    assert after > before
```

- [ ] **Step 3: Run tests — verify they fail**

```bash
pytest tests/agent/test_indexer.py -v
```

Expected: `ImportError` — `agent.indexer` doesn't exist yet.

- [ ] **Step 4: Write `agent/indexer.py`**

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

from pipeline.ingest import load_markdown


COLLECTION_NAME = "investment_docs"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


@dataclass
class SearchResult:
    content: str
    metadata: dict[str, Any]
    score: float


def _doc_id(path: Path) -> str:
    return hashlib.sha1(str(path).encode()).hexdigest()


def _get_embedder(embedding_model: str, use_local: bool, api_key: str = "", base_url: str = ""):
    if use_local:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        return SentenceTransformerEmbeddingFunction(model_name=embedding_model)
    from langchain_openai import OpenAIEmbeddings
    from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
    return OpenAIEmbeddingFunction(
        api_key=api_key,
        model_name=embedding_model,
        api_base=base_url or None,
    )


class ArticleIndexer:
    def __init__(
        self,
        chroma_path: Path,
        embedding_model: str = "text-embedding-3-small",
        use_local_embeddings: bool = False,
        llm_api_key: str = "",
        llm_base_url: str = "",
    ):
        chroma_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(chroma_path))
        ef = _get_embedder(embedding_model, use_local_embeddings, llm_api_key, llm_base_url)
        self._col = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", "。", "，", " ", ""],
        )

    def _index_file(self, path: Path, doc_type: str) -> None:
        try:
            article = load_markdown(path)
        except Exception:
            return
        if not article.content.strip():
            return

        chunks = self._splitter.split_text(article.content)
        ids, docs, metas = [], [], []
        base_id = _doc_id(path)
        for i, chunk in enumerate(chunks):
            ids.append(f"{base_id}_{i}")
            docs.append(chunk)
            metas.append({
                "doc_type": doc_type,
                "source": article.source,
                "author": article.author,
                "title": article.title,
                "url": article.url,
                "date": article.published_at[:10] if article.published_at else "",
                "file_path": str(path),
            })
        if ids:
            self._col.upsert(ids=ids, documents=docs, metadatas=metas)

    def build(self, sources_root: Path, reports_root: Path) -> None:
        for path in sorted(sources_root.rglob("*.md")):
            self._index_file(path, "article")
        for path in sorted(reports_root.rglob("daily-brief*.md")):
            self._index_file(path, "report")

    def update(self, sources_root: Path, date_str: str) -> None:
        date_dir = sources_root / date_str
        if date_dir.exists():
            for path in sorted(date_dir.glob("*.md")):
                self._index_file(path, "article")

    def search(
        self,
        query: str,
        top_k: int = 5,
        author: str | None = None,
        source: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        doc_type: str | None = None,
    ) -> list[SearchResult]:
        where: dict = {}
        conditions = []
        if author:
            conditions.append({"author": {"$eq": author}})
        if source:
            conditions.append({"source": {"$eq": source}})
        if doc_type:
            conditions.append({"doc_type": {"$eq": doc_type}})
        if date_from:
            conditions.append({"date": {"$gte": date_from}})
        if date_to:
            conditions.append({"date": {"$lte": date_to}})
        if len(conditions) == 1:
            where = conditions[0]
        elif len(conditions) > 1:
            where = {"$and": conditions}

        kwargs: dict = {"query_texts": [query], "n_results": top_k}
        if where:
            kwargs["where"] = where

        try:
            results = self._col.query(**kwargs)
        except Exception:
            return []

        out = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            out.append(SearchResult(content=doc, metadata=meta, score=1 - dist))
        return out

    def stats(self) -> dict:
        return {"total_docs": self._col.count()}
```

- [ ] **Step 5: Install sentence-transformers for local test embeddings**

```bash
pip install sentence-transformers
```

- [ ] **Step 6: Create fixture directories**

```bash
mkdir -p tests/agent/fixtures/reports/2026-06-10
```

Then create the two fixture files as described in Step 1.

- [ ] **Step 7: Run tests — verify they pass**

```bash
pytest tests/agent/test_indexer.py -v
```

Expected: all 4 tests PASS. First run may be slow (downloads embedding model ~120MB).

- [ ] **Step 8: Commit**

```bash
git add agent/indexer.py tests/agent/test_indexer.py tests/agent/fixtures/
git commit -m "feat(agent): ChromaDB indexer with semantic search and metadata filters"
```

---

## Task 6: Indexer CLI entry point + run full index

**Files:**
- Create: `agent/__main__.py`

- [ ] **Step 1: Write `agent/__main__.py`**

```python
"""python -m agent [--rebuild-index] [--port 8080]"""
from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Investment Agent backend")
    parser.add_argument("--rebuild-index", action="store_true", help="Rebuild ChromaDB index from scratch")
    parser.add_argument("--update-index", metavar="DATE", help="Incremental index update for DATE (YYYY-MM-DD)")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    from agent.config import get_agent_settings
    cfg = get_agent_settings()

    if args.rebuild_index:
        print("[info] Building ChromaDB index from scratch...")
        from agent.indexer import ArticleIndexer
        indexer = ArticleIndexer(
            chroma_path=cfg.chroma_path,
            llm_api_key=cfg.llm_api_key,
            llm_base_url=cfg.llm_base_url,
        )
        indexer.build(sources_root=cfg.sources_root, reports_root=cfg.reports_root)
        stats = indexer.stats()
        print(f"[info] Index built: {stats['total_docs']} chunks")
        sys.exit(0)

    if args.update_index:
        from agent.indexer import ArticleIndexer
        indexer = ArticleIndexer(
            chroma_path=cfg.chroma_path,
            llm_api_key=cfg.llm_api_key,
            llm_base_url=cfg.llm_base_url,
        )
        indexer.update(sources_root=cfg.sources_root, date_str=args.update_index)
        print(f"[info] Index updated for {args.update_index}")
        sys.exit(0)

    import uvicorn
    uvicorn.run("agent.main:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Build the real index**

```bash
python -m agent --rebuild-index
```

Expected output:
```
[info] Building ChromaDB index from scratch...
[info] Index built: NNNN chunks
```

Where NNNN is the number of chunks from your actual `sources/` and `reports/` directories.

- [ ] **Step 3: Smoke-test the server starts**

```bash
python -m agent --port 8080 &
sleep 3
curl http://localhost:8080/api/health
# Expected: {"status":"ok"}
kill %1
```

- [ ] **Step 4: Commit**

```bash
git add agent/__main__.py
git commit -m "feat(agent): CLI entry point for index build and server start"
```

---

## Task 7: Add memory/ to .gitignore

- [ ] **Step 1: Update `.gitignore`**

Append to `.gitignore`:

```
# Agent runtime data
memory/
.env
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore memory/ directory (SQLite + ChromaDB runtime data)"
```

---

## Plan A Complete — Verification

Run the full test suite:

```bash
pytest tests/agent/ -v
```

Expected: all tests PASS.

Start the server and verify auth works end-to-end:

```bash
python -m agent --port 8080 &
sleep 2

# Register
curl -s -X POST http://localhost:8080/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"password123"}' | python -m json.tool

# Login
curl -s -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"password123"}' | python -m json.tool

# Health
curl -s http://localhost:8080/api/health | python -m json.tool

kill %1
```

Expected: register returns `{"id":"...","username":"testuser"}`, login returns `{"access_token":"...","token_type":"bearer"}`, health returns `{"status":"ok"}`.

**Plan B (Agent layer + full API) can now begin.**
