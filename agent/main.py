from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from agent.auth import decode_token
from agent.config import get_agent_settings
from agent.db import get_user_by_id, init_db
from agent.routers import auth as auth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_agent_settings()
    await init_db(cfg.db_path)
    app.state.settings = cfg
    yield


app = FastAPI(title="Investment Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)


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
        user_id: str = payload.get("sub")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await get_user_by_id(cfg.db_path, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@app.get("/api/health")
async def health():
    return {"status": "ok"}
