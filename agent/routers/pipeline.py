from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from agent.agents.tools import tool_run_pipeline
from agent.dependencies import get_current_user

router = APIRouter(prefix="/api", tags=["pipeline"])


class PipelineRequest(BaseModel):
    date: str | None = None


@router.post("/pipeline/collect")
async def collect(body: PipelineRequest, request: Request):
    await get_current_user(request)
    result = await tool_run_pipeline("collect", body.date)
    return {"result": result}


@router.post("/pipeline/generate")
async def generate(body: PipelineRequest, request: Request):
    await get_current_user(request)
    result = await tool_run_pipeline("generate", body.date)
    return {"result": result}


@router.post("/index/update")
async def index_update(body: PipelineRequest, request: Request):
    await get_current_user(request)
    cfg = request.app.state.settings
    from agent.indexer import ArticleIndexer
    indexer = ArticleIndexer(
        chroma_path=cfg.chroma_path,
        llm_api_key=cfg.llm_api_key,
        llm_base_url=cfg.llm_base_url,
    )
    import datetime
    date_str = body.date or datetime.date.today().isoformat()
    indexer.update(sources_root=cfg.sources_root, date_str=date_str)
    return {"ok": True, "date": date_str}
