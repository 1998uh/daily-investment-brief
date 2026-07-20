from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pipeline.collectors.base import CollectedItem
from pipeline.storage import (
    load_source_health,
    query_items,
    record_source_health,
    upsert_items,
)


def test_upsert_items_keeps_longer_content(tmp_path):
    db_path = tmp_path / "articles.sqlite"
    published = datetime(2026, 7, 16, 9, tzinfo=timezone.utc)
    short = CollectedItem(
        source="微博",
        author="author",
        title="title",
        url="https://example.com/a",
        published_at=published,
        content="short",
        provider="weibo_mobile",
    )
    long = CollectedItem(
        source="微博",
        author="author",
        title="title",
        url="https://example.com/a",
        published_at=published,
        content="longer content",
        provider="weibo_web",
    )

    assert upsert_items([short], db_path) == 1
    assert upsert_items([short], db_path) == 0
    assert upsert_items([long], db_path) == 1

    items = query_items(published - timedelta(hours=1), published + timedelta(hours=1), db_path=db_path)
    assert len(items) == 1
    assert items[0].content == "longer content"
    assert items[0].provider == "weibo_web"


def test_source_health_roundtrip(tmp_path):
    db_path = tmp_path / "articles.sqlite"

    record_source_health("雪球", "author", ok=False, count=0, message="login expired", db_path=db_path)
    record_source_health("微博", "author2", ok=True, count=3, db_path=db_path)

    rows = load_source_health(db_path)
    assert rows == [
        {
            "source": "微博",
            "author": "author2",
            "ok": True,
            "count": 3,
            "message": "",
            "checked_at": rows[0]["checked_at"],
        },
        {
            "source": "雪球",
            "author": "author",
            "ok": False,
            "count": 0,
            "message": "login expired",
            "checked_at": rows[1]["checked_at"],
        },
    ]
