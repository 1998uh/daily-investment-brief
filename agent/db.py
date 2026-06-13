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
        await db.execute("PRAGMA foreign_keys=ON")
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
