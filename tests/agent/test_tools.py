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
