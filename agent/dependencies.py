from __future__ import annotations

from fastapi import HTTPException, Request

from agent.auth import decode_token
from agent.db import get_user_by_id


async def get_current_user(request: Request) -> dict:
    cfg = request.app.state.settings
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(token)
        user_id: str = str(payload.get("sub", ""))
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing sub")
    user = await get_user_by_id(cfg.db_path, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
