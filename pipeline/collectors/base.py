from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class CollectedItem:
    source: str
    author: str
    title: str
    url: str
    published_at: datetime | None
    content: str


@dataclass
class CollectionLog:
    info: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add_info(self, message: str) -> None:
        with self._lock:
            self.info.append(message)

    def add_warning(self, message: str) -> None:
        with self._lock:
            self.warnings.append(message)

    def add_error(self, message: str) -> None:
        with self._lock:
            self.errors.append(message)
