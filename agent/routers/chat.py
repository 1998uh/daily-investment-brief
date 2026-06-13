from __future__ import annotations

import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.agents.orchestrator import Orchestrator
from agent.db import (
    create_session, get_messages, append_message, rename_session, list_sessions
)
from agent.dependencies import get_current_user

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str


@router.post("/chat")
async def chat(body: ChatRequest, request: Request):
    user = await get_current_user(request)
    cfg = request.app.state.settings
    uid = user["id"]

    # 创建或复用会话
    if body.session_id:
        session_id = body.session_id
    else:
        session = await create_session(cfg.db_path, uid, body.message[:20])
        session_id = session["id"]

    # 加载历史消息
    history = await get_messages(cfg.db_path, session_id, uid)

    # 保存用户消息
    await append_message(cfg.db_path, session_id, uid, "user", body.message, None, None)

    async def event_stream():
        orch = Orchestrator(settings=cfg, user_id=uid)
        collected_tokens = []
        sources = []

        async for event in orch.run(body.message, history=history):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event["type"] == "token":
                collected_tokens.append(event["text"])
            elif event["type"] == "done":
                sources = event.get("sources", [])

        # 保存 assistant 消息
        full_text = "".join(collected_tokens)
        await append_message(cfg.db_path, session_id, uid, "assistant", full_text, "orchestrator", sources)

        # 自动设置会话标题（第一条消息）
        sessions = await list_sessions(cfg.db_path, uid)
        current = next((s for s in sessions if s["id"] == session_id), None)
        if current and not current.get("title"):
            await rename_session(cfg.db_path, session_id, uid, body.message[:20])

        yield f"data: {json.dumps({'type': 'session_id', 'session_id': session_id}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )
