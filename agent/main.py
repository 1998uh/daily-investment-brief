from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.config import get_agent_settings
from agent.db import init_db
from agent.dependencies import get_current_user  # re-export for other modules
from agent.routers import auth as auth_router
from agent.routers import sessions as sessions_router
from agent.routers import memory as memory_router
from agent.routers import pipeline as pipeline_router
from agent.routers import chat as chat_router


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
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(auth_router.router)
app.include_router(sessions_router.router)
app.include_router(memory_router.router)
app.include_router(pipeline_router.router)
app.include_router(chat_router.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
