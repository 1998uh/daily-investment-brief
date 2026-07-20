from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
import hashlib
import json
import sqlite3

from .collectors.base import CollectedItem
from .config import ROOT


DEFAULT_DB_PATH = ROOT / "data" / "articles.sqlite"


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                author TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                published_at TEXT,
                content TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT '',
                fetched_at TEXT NOT NULL,
                raw_json TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS source_health (
                source TEXT NOT NULL,
                author TEXT NOT NULL,
                ok INTEGER NOT NULL,
                count INTEGER NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                checked_at TEXT NOT NULL,
                PRIMARY KEY (source, author)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_window ON articles(published_at)")


def item_id(item: CollectedItem) -> str:
    if item.url.strip():
        return hashlib.sha1(item.url.strip().encode("utf-8")).hexdigest()
    digest = hashlib.sha1(item.content[:2000].encode("utf-8")).hexdigest()
    key = "|".join([item.source.strip(), item.author.strip(), item.title.strip(), digest])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def upsert_items(items: list[CollectedItem], db_path: Path = DEFAULT_DB_PATH) -> int:
    init_db(db_path)
    now = datetime.now().isoformat(timespec="seconds")
    changed = 0
    with sqlite3.connect(db_path) as conn:
        for item in items:
            published = item.published_at.isoformat() if item.published_at else ""
            existing = conn.execute(
                "SELECT length(content) FROM articles WHERE id = ?", (item_id(item),)
            ).fetchone()
            if existing and existing[0] and existing[0] >= len(item.content.strip()):
                continue
            conn.execute(
                """
                INSERT INTO articles (
                    id, source, author, title, url, published_at, content,
                    provider, fetched_at, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    source = excluded.source,
                    author = excluded.author,
                    title = excluded.title,
                    url = excluded.url,
                    published_at = excluded.published_at,
                    content = excluded.content,
                    provider = excluded.provider,
                    fetched_at = excluded.fetched_at,
                    raw_json = excluded.raw_json
                """,
                (
                    item_id(item),
                    item.source,
                    item.author,
                    item.title,
                    item.url,
                    published,
                    item.content,
                    item.provider,
                    now,
                    item.raw_json,
                ),
            )
            changed += 1
    return changed


def query_items(
    window_start: datetime,
    window_end: datetime,
    *,
    db_path: Path = DEFAULT_DB_PATH,
    source: str | None = None,
    author: str | None = None,
) -> list[CollectedItem]:
    init_db(db_path)
    clauses = ["published_at >= ?", "published_at < ?"]
    params: list[str] = [window_start.isoformat(), window_end.isoformat()]
    if source:
        clauses.append("source = ?")
        params.append(source)
    if author:
        clauses.append("author = ?")
        params.append(author)

    sql = (
        "SELECT source, author, title, url, published_at, content, provider, raw_json "
        f"FROM articles WHERE {' AND '.join(clauses)} ORDER BY published_at DESC, fetched_at DESC"
    )
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()

    items: list[CollectedItem] = []
    for row in rows:
        published_at = _parse_iso(row[4])
        items.append(
            CollectedItem(
                source=row[0],
                author=row[1],
                title=row[2],
                url=row[3],
                published_at=published_at,
                content=row[5],
                provider=row[6],
                raw_json=row[7],
            )
        )
    return items


def record_source_health(
    source: str,
    author: str,
    *,
    ok: bool,
    count: int,
    message: str = "",
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO source_health (source, author, ok, count, message, checked_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, author) DO UPDATE SET
                ok = excluded.ok,
                count = excluded.count,
                message = excluded.message,
                checked_at = excluded.checked_at
            """,
            (
                source,
                author,
                1 if ok else 0,
                count,
                message[:500],
                datetime.now().isoformat(timespec="seconds"),
            ),
        )


def load_source_health(db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, object]]:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT source, author, ok, count, message, checked_at
            FROM source_health
            ORDER BY source, author
            """
        ).fetchall()
    return [
        {
            "source": row[0],
            "author": row[1],
            "ok": bool(row[2]),
            "count": row[3],
            "message": row[4],
            "checked_at": row[5],
        }
        for row in rows
    ]


def clone_with_provider(item: CollectedItem, provider: str) -> CollectedItem:
    return replace(item, provider=item.provider or provider)


def raw_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
