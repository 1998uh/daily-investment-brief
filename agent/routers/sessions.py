from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agent.db import (
    create_session, list_sessions, rename_session,
    delete_session, get_messages,
)
from agent.dependencies import get_current_user

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    title: str | None = None


class RenameSessionRequest(BaseModel):
    title: str


@router.post("")
async def create(body: CreateSessionRequest, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    session = await create_session(cfg.db_path, user["id"], body.title)
    return session


@router.get("")
async def list_all(request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    return await list_sessions(cfg.db_path, user["id"])


@router.patch("/{session_id}")
async def rename(session_id: str, body: RenameSessionRequest, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    try:
        await rename_session(cfg.db_path, session_id, user["id"], body.title)
    except LookupError:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


@router.delete("/{session_id}")
async def delete(session_id: str, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    await delete_session(cfg.db_path, session_id, user["id"])
    return {"ok": True}


@router.get("/{session_id}/messages")
async def get_msgs(session_id: str, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    return await get_messages(cfg.db_path, session_id, user["id"])
