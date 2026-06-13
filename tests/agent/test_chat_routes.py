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
