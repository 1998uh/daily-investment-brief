"""Default capital-flow provider composition."""

from __future__ import annotations

from pathlib import Path

from .capital_flow import EastmoneyProvider, FallbackCapitalFlowProvider
from .config import load_env
from .tonghuashun_flow import TonghuashunSectorFlowProvider


def build_default_capital_flow_provider(cache_dir: Path) -> FallbackCapitalFlowProvider:
    load_env()
    cache_dir = Path(cache_dir)
    return FallbackCapitalFlowProvider(
        EastmoneyProvider(cache_dir),
        TonghuashunSectorFlowProvider(cache_dir / "tonghuashun"),
        fallback_label="同花顺公开资金流（板块净额 fallback）",
    )
