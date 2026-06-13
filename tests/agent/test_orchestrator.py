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
