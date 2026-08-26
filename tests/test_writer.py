from __future__ import annotations

from datetime import datetime, timezone

from pipeline.collectors.base import CollectedItem
from pipeline.collectors.writer import is_reply_item, write_items


def _item(*, author="九洲仙人", title="", content, published_at, url="") -> CollectedItem:
    return CollectedItem(
        source="雪球",
        author=author,
        title=title,
        url=url,
        published_at=published_at,
        content=content,
        provider="xueqiu_timeline",
    )


def test_is_reply_item_detects_reply_prefix():
    reply = _item(
        content="回复[@九洲仙人](https://xueqiu.com/n/九洲仙人): 从盘面看...",
        published_at=None,
    )
    normal = _item(content="今天大盘走势分析：科技股继续走强。", published_at=None)

    assert is_reply_item(reply) is True
    assert is_reply_item(normal) is False


def test_write_items_merges_same_author_same_day_replies(tmp_path):
    day = datetime(2026, 8, 3, tzinfo=timezone.utc)
    reply1 = _item(
        content="回复[@A](https://xueqiu.com/n/A): 第一条回复内容。",
        published_at=day.replace(hour=9),
        url="https://xueqiu.com/1/1",
    )
    reply2 = _item(
        content="回复[@B](https://xueqiu.com/n/B): 第二条回复内容。",
        published_at=day.replace(hour=10),
        url="https://xueqiu.com/1/2",
    )

    written = write_items([reply1, reply2], tmp_path)

    assert len(written) == 1
    merged_text = written[0].read_text(encoding="utf-8")
    assert "第一条回复内容" in merged_text
    assert "第二条回复内容" in merged_text
    assert "回复合集" in merged_text


def test_write_items_keeps_replies_from_different_days_separate(tmp_path):
    reply_day1 = _item(
        content="回复[@A](https://xueqiu.com/n/A): 第一天的回复。",
        published_at=datetime(2026, 8, 3, 9, tzinfo=timezone.utc),
        url="https://xueqiu.com/1/1",
    )
    reply_day2 = _item(
        content="回复[@A](https://xueqiu.com/n/A): 第二天的回复。",
        published_at=datetime(2026, 8, 4, 9, tzinfo=timezone.utc),
        url="https://xueqiu.com/1/2",
    )

    written = write_items([reply_day1, reply_day2], tmp_path)

    assert len(written) == 2


def test_write_items_keeps_replies_from_different_authors_separate(tmp_path):
    day = datetime(2026, 8, 3, 9, tzinfo=timezone.utc)
    reply_a = _item(
        author="九洲仙人",
        content="回复[@X](https://xueqiu.com/n/X): 甲的回复。",
        published_at=day,
        url="https://xueqiu.com/1/1",
    )
    reply_b = _item(
        author="润哥",
        content="回复[@X](https://xueqiu.com/n/X): 乙的回复。",
        published_at=day,
        url="https://xueqiu.com/2/1",
    )

    written = write_items([reply_a, reply_b], tmp_path)

    assert len(written) == 2


def test_write_items_does_not_merge_normal_posts(tmp_path):
    normal = _item(
        content="今天大盘走势分析：科技股继续走强，半导体板块领涨。",
        published_at=datetime(2026, 8, 3, 9, tzinfo=timezone.utc),
        url="https://xueqiu.com/1/1",
    )

    written = write_items([normal], tmp_path)

    assert len(written) == 1
    assert "回复合集" not in written[0].read_text(encoding="utf-8")


def test_write_items_reply_group_is_idempotent(tmp_path):
    day = datetime(2026, 8, 3, 9, tzinfo=timezone.utc)
    reply = _item(
        content="回复[@A](https://xueqiu.com/n/A): 重复运行测试。",
        published_at=day,
        url="https://xueqiu.com/1/1",
    )

    first = write_items([reply], tmp_path)
    second = write_items([reply], tmp_path)

    assert len(first) == 1
    assert len(second) == 0
    assert len(list(tmp_path.glob("*.md"))) == 1


def test_write_items_overwrites_when_content_becomes_ready_without_large_growth(tmp_path):
    published = datetime(2026, 8, 3, 9, tzinfo=timezone.utc)
    partial = _item(
        title="长文",
        content="摘要正文，长度已经接近详情。",
        published_at=published,
        url="https://xueqiu.com/1/99",
    )
    partial = CollectedItem(**{**partial.__dict__, "content_status": "partial"})
    ready = CollectedItem(
        **{
            **partial.__dict__,
            "content": "摘要正文，长度已经接近详情。",
            "provider": "xueqiu_full",
            "content_status": "ready",
        }
    )

    first = write_items([partial], tmp_path)
    second = write_items([ready], tmp_path)

    assert len(first) == 1
    assert second == first
    text = first[0].read_text(encoding="utf-8")
    assert "content_status: ready" in text
    assert "provider: xueqiu_full" in text
