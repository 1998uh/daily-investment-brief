from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path | None = None) -> None:
    env_path = path or ROOT / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    base_url: str
    model: str
    api_key: str
    llm_timeout_seconds: int
    llm_retries: int
    llm_retry_delay_seconds: float
    timezone: str
    window_start: str
    window_end: str
    markets: str
    style: str
    max_chars_per_article: int
    batch_size: int
    batch_max_chars: int
    llm_batch_concurrency: int
    temperature: float
    llm_thinking_type: str | None = None
    llm_max_tokens: int | None = None

    @property
    def has_llm(self) -> bool:
        return bool(self.base_url and self.model and self.api_key)


def get_settings() -> Settings:
    load_env()
    return Settings(
        base_url=os.getenv("BRIEF_BASE_URL", "").rstrip("/"),
        model=os.getenv("BRIEF_MODEL", ""),
        api_key=os.getenv("BRIEF_API_KEY", ""),
        llm_timeout_seconds=_env_int("BRIEF_LLM_TIMEOUT_SECONDS", 120, min_value=1),
        llm_retries=_env_int("BRIEF_LLM_RETRIES", 2, min_value=0),
        llm_retry_delay_seconds=_env_float("BRIEF_LLM_RETRY_DELAY_SECONDS", 2.0, min_value=0),
        timezone=os.getenv("BRIEF_TIMEZONE", "Asia/Shanghai"),
        window_start=os.getenv("BRIEF_WINDOW_START", "08:00"),
        window_end=os.getenv("BRIEF_WINDOW_END", "08:00"),
        markets=os.getenv("BRIEF_MARKETS", "A股,港股"),
        style=os.getenv("BRIEF_STYLE", "strong_narrative_emoji"),
        max_chars_per_article=_env_int("BRIEF_MAX_CHARS_PER_ARTICLE", 6000, min_value=500),
        batch_size=_env_int("BRIEF_BATCH_SIZE", 8, min_value=1),
        batch_max_chars=_env_int("BRIEF_BATCH_MAX_CHARS", 15000, min_value=1000),
        llm_batch_concurrency=_env_int("BRIEF_LLM_BATCH_CONCURRENCY", 3, min_value=1),
        temperature=_env_float("BRIEF_TEMPERATURE", 0.2, min_value=0),
        llm_thinking_type=_env_choice("BRIEF_LLM_THINKING", {"disabled", "enabled"}),
        llm_max_tokens=_env_optional_int("BRIEF_LLM_MAX_TOKENS", min_value=1),
    )


def _env_int(name: str, default: int, *, min_value: int | None = None) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if min_value is not None and value < min_value:
        return default
    return value


def _env_float(name: str, default: float, *, min_value: float | None = None) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if min_value is not None and value < min_value:
        return default
    return value


def _env_optional_int(name: str, *, min_value: int | None = None) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    if min_value is not None and value < min_value:
        return None
    return value


def _env_choice(name: str, choices: set[str]) -> str | None:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return None
    if raw in choices:
        return raw
    return None
