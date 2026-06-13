from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agent.db import (
    add_watch, remove_watch, get_watchlist,
    log_trade, get_trades, delete_trade,
    log_event, get_events, delete_event,
)
from agent.dependencies import get_current_user

router = APIRouter(prefix="/api/memory", tags=["memory"])


class WatchlistAddRequest(BaseModel):
    symbol: str
    note: str | None = None


class TradeRequest(BaseModel):
    symbol: str
    action: str
    price: float | None = None
    quantity: float | None = None
    date: str | None = None
    note: str | None = None


class EventRequest(BaseModel):
    title: str
    content: str | None = None
    date: str | None = None
    tags: list[str] | None = None


@router.get("/watchlist")
async def watchlist_list(request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    return await get_watchlist(cfg.db_path, user["id"])


@router.post("/watchlist")
async def watchlist_add(body: WatchlistAddRequest, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    await add_watch(cfg.db_path, user["id"], body.symbol, body.note)
    return {"ok": True, "symbol": body.symbol.upper()}


@router.delete("/watchlist/{symbol}")
async def watchlist_remove(symbol: str, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    await remove_watch(cfg.db_path, user["id"], symbol)
    return {"ok": True}


@router.get("/trades")
async def trades_list(request: Request, symbol: str | None = None,
                      from_date: str | None = None, to_date: str | None = None):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    return await get_trades(cfg.db_path, user["id"], symbol=symbol, from_date=from_date, to_date=to_date)


@router.post("/trades")
async def trades_add(body: TradeRequest, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    trade = await log_trade(cfg.db_path, user["id"], body.symbol, body.action,
                            body.price, body.quantity, body.date, body.note)
    return trade


@router.delete("/trades/{trade_id}")
async def trades_delete(trade_id: int, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    await delete_trade(cfg.db_path, trade_id, user["id"])
    return {"ok": True}


@router.get("/events")
async def events_list(request: Request, from_date: str | None = None, to_date: str | None = None):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    return await get_events(cfg.db_path, user["id"], from_date=from_date, to_date=to_date)


@router.post("/events")
async def events_add(body: EventRequest, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    event = await log_event(cfg.db_path, user["id"], body.title, body.content, body.date, body.tags)
    return event


@router.delete("/events/{event_id}")
async def events_delete(event_id: int, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    await delete_event(cfg.db_path, event_id, user["id"])
    return {"ok": True}
