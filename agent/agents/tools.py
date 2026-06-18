from __future__ import annotations

import asyncio
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
    from agent.indexer import make_indexer
    indexer = make_indexer(settings)
    results = indexer.search(
        query=query, top_k=top_k,
        author=author, source=source,
        date_from=date_from, date_to=date_to,
    )
    return [
        {"content": r.content, "metadata": r.metadata, "score": r.score}
        for r in results
    ]


async def tool_search_web(
    settings: AgentSettings,
    query: str,
    max_results: int = 5,
) -> list[dict[str, Any]]:
    """联网实时搜索（Tavily API），返回结构与 tool_search_local 对齐。"""
    if not settings.tavily_api_key:
        raise RuntimeError("TAVILY_API_KEY 未配置，无法执行联网搜索")

    from tavily import TavilyClient
    client = TavilyClient(api_key=settings.tavily_api_key)
    response = await asyncio.to_thread(
        client.search,
        query=query,
        search_depth="basic",
        max_results=max_results,
        include_answer=False,
    )
    results = []
    for r in response.get("results", []):
        results.append({
            "content": r.get("content", ""),
            "metadata": {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "source": "tavily",
                "kind": "web",
                "date": r.get("published_date", ""),
                "author": "",
            },
            "score": r.get("score", 0),
        })
    return results


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
