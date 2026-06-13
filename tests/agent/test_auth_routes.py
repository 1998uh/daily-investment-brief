from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


@pytest_asyncio.fixture
async def app(tmp_path):
    import os
    os.environ["AGENT_MEMORY_DIR"] = str(tmp_path)
    os.environ["AGENT_DB_NAME"] = "test.db"
    os.environ["AGENT_JWT_SECRET"] = "test-secret-for-routes"
    os.environ["BRIEF_BASE_URL"] = ""
    os.environ["BRIEF_MODEL"] = ""
    os.environ["BRIEF_API_KEY"] = ""
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
    # Set settings on app state directly so routes can access it
    # (lifespan doesn't run in test transport unless explicitly started)
    app.state.settings = cfg
    return app


@pytest.mark.asyncio
async def test_register_and_login(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/auth/register", json={"username": "alice", "password": "pw123456"})
        assert r.status_code == 200
        assert r.json()["username"] == "alice"

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
