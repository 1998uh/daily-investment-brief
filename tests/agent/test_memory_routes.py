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
