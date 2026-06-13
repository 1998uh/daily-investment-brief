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
