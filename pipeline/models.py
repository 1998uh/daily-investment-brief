from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class GenerationResult:
    markdown: str
    used_llm: bool
    model: str
