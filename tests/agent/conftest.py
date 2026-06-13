from __future__ import annotations
from pathlib import Path
from agent.config import AgentSettings


def make_settings(tmp_path: Path) -> AgentSettings:
    return AgentSettings(
        db_path=tmp_path / "agent.db",
        chroma_path=tmp_path / "chroma",
        sources_root=tmp_path / "sources",
        reports_root=tmp_path / "reports",
        jwt_secret="test-secret",
        jwt_algorithm="HS256",
        jwt_expire_minutes=60,
        llm_base_url="",
        llm_model="",
        llm_api_key="",
        tavily_api_key="",
    )
