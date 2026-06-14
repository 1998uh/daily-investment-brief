from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name, str(default))
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"Environment variable {name}={raw!r} must be an integer")


@dataclass(frozen=True)
class AgentSettings:
    db_path: Path
    chroma_path: Path
    sources_root: Path
    reports_root: Path
    jwt_secret: str
    jwt_algorithm: str
    jwt_expire_minutes: int
    llm_base_url: str
    llm_model: str
    llm_api_key: str
    tavily_api_key: str
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    use_local_embeddings: bool = True
    cookie_secure: bool = False


def get_agent_settings() -> AgentSettings:
    from pipeline.config import load_env
    load_env()
    memory = ROOT / _env("AGENT_MEMORY_DIR", "memory")
    return AgentSettings(
        db_path=memory / _env("AGENT_DB_NAME", "agent.db"),
        chroma_path=memory / _env("AGENT_CHROMA_DIR", "chroma"),
        sources_root=ROOT / _env("AGENT_SOURCES_DIR", "sources"),
        reports_root=ROOT / _env("AGENT_REPORTS_DIR", "reports"),
        jwt_secret=_env("AGENT_JWT_SECRET", "change-me-in-production"),
        jwt_algorithm=_env("AGENT_JWT_ALGORITHM", "HS256"),
        jwt_expire_minutes=_env_int("AGENT_JWT_EXPIRE_MINUTES", 10080),  # 7 days
        llm_base_url=_env("BRIEF_BASE_URL"),      # optional, may be empty during tests
        llm_model=_env("BRIEF_MODEL"),            # optional, may be empty during tests
        llm_api_key=_env("BRIEF_API_KEY"),        # optional, may be empty during tests
        tavily_api_key=_env("TAVILY_API_KEY"),    # optional, may be empty during tests
        embedding_model=_env(
            "AGENT_EMBEDDING_MODEL",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        ),
        use_local_embeddings=_env("AGENT_USE_LOCAL_EMBEDDINGS", "true").lower() != "false",
    )
