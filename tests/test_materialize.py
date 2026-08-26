from __future__ import annotations

import argparse
from datetime import date, datetime
import inspect
from pathlib import Path

from pipeline.collectors.base import CollectedItem
from pipeline.config import ROOT
from pipeline.materialize import materialize_daily_sources
from pipeline.social_daemon import run_forever
from pipeline.storage import upsert_items


def _item(
    source: str,
    author: str,
    url: str,
    published_at: str,
    *,
    content: str = "这是一篇有效的投资分析正文。",
    raw_json: str = "",
    content_status: str = "ready",
) -> CollectedItem:
    return CollectedItem(
        source=source,
        author=author,
        title=f"{author}的文章",
        url=url,
        published_at=datetime.fromisoformat(published_at),
        content=content,
        provider="test",
        raw_json=raw_json,
        content_status=content_status,
    )


def test_materialize_uses_report_window_not_calendar_folder(tmp_path):
    db_path = tmp_path / "articles.sqlite"
    out_dir = tmp_path / "sources" / "2026-08-27"
    out_dir.mkdir(parents=True)
    (out_dir / "stale.md").write_text("旧的错误窗口文件", encoding="utf-8")
    upsert_items(
        [
            _item("雪球", "窗口前", "https://xueqiu.com/1/1", "2026-08-26T07:59:59+08:00"),
            _item("雪球", "窗口内雪球", "https://xueqiu.com/1/2", "2026-08-26T08:00:00+08:00"),
            _item("微博", "窗口内微博", "https://weibo.com/1/3", "2026-08-27T07:59:59+08:00"),
            _item(
                "微信公众号",
                "窗口内公众号",
                "https://mp.weixin.qq.com/s/4",
                "2026-08-26T12:00:00+08:00",
            ),
            _item("微博", "窗口后", "https://weibo.com/1/5", "2026-08-27T08:00:00+08:00"),
        ],
        db_path=db_path,
    )

    result = materialize_daily_sources(
        report_date=date(2026, 8, 27),
        db_path=db_path,
        out_dir=out_dir,
        timezone_name="Asia/Shanghai",
        window_start="08:00",
        window_end="08:00",
    )

    assert result.counts == {"雪球": 1, "微博": 1, "微信公众号": 1}
    assert result.missing_sources == []
    assert result.window_start.isoformat() == "2026-08-26T08:00:00+08:00"
    assert result.window_end.isoformat() == "2026-08-27T08:00:00+08:00"
    assert not (out_dir / "stale.md").exists()
    text = "\n".join(path.read_text(encoding="utf-8") for path in out_dir.glob("*.md"))
    assert "窗口内雪球" in text
    assert "窗口内微博" in text
    assert "窗口内公众号" in text
    assert "窗口前" not in text
    assert "窗口后" not in text


def test_materialize_filters_legacy_replies_and_incomplete_wechat(tmp_path):
    db_path = tmp_path / "articles.sqlite"
    out_dir = tmp_path / "sources" / "2026-08-27"
    upsert_items(
        [
            _item(
                "雪球",
                "旧回复",
                "https://xueqiu.com/1/10",
                "2026-08-26T09:00:00+08:00",
                content="回复[@用户](https://xueqiu.com/n/u)：旧缓存回复内容",
            ),
            _item(
                "微信公众号",
                "待补正文",
                "https://mp.weixin.qq.com/s/11",
                "2026-08-26T10:00:00+08:00",
                content="",
                content_status="pending",
            ),
        ],
        db_path=db_path,
    )

    result = materialize_daily_sources(
        report_date=date(2026, 8, 27),
        db_path=db_path,
        out_dir=out_dir,
        timezone_name="Asia/Shanghai",
        window_start="08:00",
        window_end="08:00",
    )

    assert result.counts == {"雪球": 0, "微博": 0, "微信公众号": 0}
    assert result.missing_sources == ["雪球", "微博", "微信公众号"]
    assert list(out_dir.glob("*.md")) == []


def test_social_daemon_defaults_to_raw_archive():
    default = inspect.signature(run_forever).parameters["output_root"].default

    assert default == ROOT / "sources" / "_raw"


def test_materialize_cli_parser_defaults():
    from pipeline.cli import build_parser

    args = build_parser().parse_args(["materialize", "--date", "2026-08-27"])

    assert args.command == "materialize"
    assert args.date == "2026-08-27"
    assert args.db is None
    assert args.out_dir is None
