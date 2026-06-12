from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Article:
    path: Path
    source: str
    author: str
    title: str
    url: str
    published_at: str
    content: str

    @property
    def display_author(self) -> str:
        return self.author or "未知作者"

    @property
    def display_title(self) -> str:
        return self.title or self.path.stem


@dataclass(frozen=True)
class CoverageRow:
    source: str
    authors_total: int
    articles_total: int
    authors: list[str]
    # 该来源在 accounts.json 中配置且 enabled 的账号数（未提供配置时为 0）。
    expected_authors: int = 0
    # 配置了但当天没有产出文章的账号名（静默账号）。
    missing_authors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GenerationResult:
    markdown: str
    used_llm: bool
    model: str
