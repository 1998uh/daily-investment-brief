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
