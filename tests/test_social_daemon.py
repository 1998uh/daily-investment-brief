from __future__ import annotations

from datetime import datetime, timezone
import json

from pipeline.collectors.auth import (
    inject_platform_cookie_files,
    load_platform_cookie,
    platform_cookie_is_usable,
    redact_secret_text,
)
from pipeline.social_daemon import export_collected_items, run_once
from pipeline.collectors.base import CollectedItem, CollectionLog


def test_load_platform_cookie_reads_file_when_environment_is_empty(tmp_path, monkeypatch):
    cookie_path = tmp_path / "xueqiu_cookie.txt"
    cookie_path.write_text("xq_a_token=from-file; u=42\n", encoding="utf-8")
    monkeypatch.delenv("XUEQIU_COOKIE", raising=False)
    monkeypatch.setenv("XUEQIU_COOKIE_FILE", str(cookie_path))

    assert load_platform_cookie("xueqiu") == "xq_a_token=from-file; u=42"


def test_load_platform_cookie_prefers_explicit_environment(monkeypatch, tmp_path):
    cookie_path = tmp_path / "cookie.txt"
    cookie_path.write_text("xq_a_token=file", encoding="utf-8")
    monkeypatch.setenv("XUEQIU_COOKIE", "xq_a_token=environment")
    monkeypatch.setenv("XUEQIU_COOKIE_FILE", str(cookie_path))

    assert load_platform_cookie("xueqiu") == "xq_a_token=environment"


def test_cookie_file_can_refresh_a_running_process(monkeypatch, tmp_path):
    cookie_path = tmp_path / "cookie.txt"
    cookie_path.write_text("xq_a_token=first", encoding="utf-8")
    monkeypatch.setenv("XUEQIU_COOKIE", "xq_a_token=stale")
    monkeypatch.setenv("XUEQIU_COOKIE_FILE", str(cookie_path))

    inject_platform_cookie_files(prefer_file=True)
    assert load_platform_cookie("xueqiu") == "xq_a_token=first"

    cookie_path.write_text("xq_a_token=second", encoding="utf-8")
    inject_platform_cookie_files(prefer_file=True)
    assert load_platform_cookie("xueqiu") == "xq_a_token=second"

    cookie_path.write_text("", encoding="utf-8")
    inject_platform_cookie_files(prefer_file=True)
    assert load_platform_cookie("xueqiu") == ""


def test_load_platform_cookie_reads_douyin_file(tmp_path, monkeypatch):
    cookie_path = tmp_path / "douyin_cookie.txt"
    cookie_path.write_text("sessionid=abc; sessionid_ss=def", encoding="utf-8")
    monkeypatch.delenv("DOUYIN_COOKIE", raising=False)
    monkeypatch.setenv("DOUYIN_COOKIE_FILE", str(cookie_path))

    assert load_platform_cookie("douyin") == "sessionid=abc; sessionid_ss=def"


def test_platform_cookie_is_usable_accepts_douyin_session_tokens():
    assert platform_cookie_is_usable("douyin", "sessionid=abc") is True
    assert platform_cookie_is_usable("douyin", "sessionid_ss=abc") is True
    assert platform_cookie_is_usable("douyin", "ttwid=abc") is False


def test_redact_secret_text_removes_douyin_and_weread_tokens():
    message = "Cookie: sessionid=douyin-secret; wr_skey=weread-secret"

    safe = redact_secret_text(message)

    assert "douyin-secret" not in safe
    assert "weread-secret" not in safe


def test_redact_secret_text_removes_cookie_values():
    message = "Cookie: xq_a_token=secret; SUB=private"

    safe = redact_secret_text(message)

    assert "secret" not in safe
    assert "private" not in safe
    assert "<redacted>" in safe


def test_platform_cookie_requires_platform_login_token():
    assert not platform_cookie_is_usable("xueqiu", "smidV2=anonymous")
    assert platform_cookie_is_usable("xueqiu", "xq_a_token=token; u=42")
    assert not platform_cookie_is_usable("weibo", "XSRF-TOKEN=anonymous")
    assert platform_cookie_is_usable("weibo", "SUB=token; XSRF-TOKEN=value")


def test_export_uses_configured_timezone_for_partition(tmp_path):
    from datetime import timedelta

    item = CollectedItem(
        source="微博",
        author="作者",
        title="标题",
        url="https://weibo.com/1/2",
        published_at=datetime(2026, 8, 24, 23, 30, tzinfo=timezone.utc),
        content="一段正文。",
        provider="weibo_web",
    )

    written = export_collected_items([item], tmp_path, timezone_name="Asia/Shanghai")

    assert written[0].parent.name == "2026-08-25"


def test_export_collected_items_writes_each_item_to_publish_date(tmp_path):
    item = CollectedItem(
        source="雪球",
        author="作者",
        title="标题",
        url="https://xueqiu.com/42/100",
        published_at=datetime(2026, 8, 25, 9, 30, tzinfo=timezone.utc),
        content="一段足够长的正文。",
        provider="xueqiu_timeline",
        raw_json=json.dumps({"id": 100}),
    )

    written = export_collected_items([item], tmp_path)

    assert len(written) == 1
    assert written[0].parent.name == "2026-08-25"
    assert "标题" in written[0].read_text(encoding="utf-8")


def test_run_once_collects_only_social_accounts(monkeypatch, tmp_path):
    from pipeline import social_daemon
    from pipeline.collectors.accounts import Account

    accounts = [
        Account(source="雪球", name="雪作者", uid="42", enabled=True),
        Account(source="微博", name="微博作者", uid="43", enabled=True),
        Account(source="微信公众号", name="公众号", uid="44", enabled=True),
    ]
    monkeypatch.setattr(social_daemon, "load_accounts", lambda _path: accounts)
    monkeypatch.setattr(
        social_daemon,
        "load_platform_cookie",
        lambda platform: "xq_a_token=token" if platform == "xueqiu" else "SUB=token",
    )
    calls = []

    def fake_collect(account, **kwargs):
        calls.append(account.source)
        return []

    monkeypatch.setattr(social_daemon, "collect_account", fake_collect)
    monkeypatch.setattr(social_daemon, "upsert_items", lambda items, **kwargs: 0)
    monkeypatch.setattr(social_daemon, "record_source_health", lambda *args, **kwargs: None)

    result = run_once(
        accounts_path=tmp_path / "accounts.json",
        output_root=tmp_path / "sources",
        db_path=tmp_path / "articles.sqlite",
        limit=20,
    )

    assert result.accounts == 2
    assert calls == ["雪球", "微博"]


def test_run_once_reports_partial_xueqiu_content(monkeypatch, tmp_path):
    from pipeline import social_daemon
    from pipeline.collectors.accounts import Account

    monkeypatch.setattr(
        social_daemon,
        "load_accounts",
        lambda _path: [Account(source="雪球", name="作者", uid="42", enabled=True)],
    )
    monkeypatch.setattr(
        social_daemon, "load_platform_cookie", lambda _platform: "xq_a_token=token"
    )
    monkeypatch.setattr(
        social_daemon,
        "collect_account",
        lambda *args, **kwargs: [
            CollectedItem(
                source="雪球",
                author="作者",
                title="长文",
                url="https://xueqiu.com/42/1",
                published_at=datetime.now(timezone.utc),
                content="摘要",
                provider="xueqiu_summary",
                content_status="partial",
            )
        ],
    )
    monkeypatch.setattr(social_daemon, "upsert_items", lambda items, **kwargs: 1)
    monkeypatch.setattr(social_daemon, "export_collected_items", lambda *args, **kwargs: [])
    health = []
    monkeypatch.setattr(
        social_daemon,
        "record_source_health",
        lambda *args, **kwargs: health.append(kwargs),
    )

    run_once(
        accounts_path=tmp_path / "accounts.json",
        output_root=tmp_path / "sources",
        db_path=tmp_path / "articles.sqlite",
        settings=type("Settings", (), {"timezone": "Asia/Shanghai"})(),
    )

    assert health[0]["ok"] is True
    assert health[0]["message"] == "partial=1"


def test_run_once_marks_empty_first_page_failure_unhealthy(monkeypatch, tmp_path):
    from pipeline import social_daemon
    from pipeline.collectors.accounts import Account

    monkeypatch.setattr(
        social_daemon,
        "load_accounts",
        lambda _path: [Account(source="雪球", name="作者", uid="42", enabled=True)],
    )
    monkeypatch.setattr(
        social_daemon, "load_platform_cookie", lambda _platform: "xq_a_token=token"
    )

    def failed_collect(*args, **kwargs):
        kwargs["log"].add_warning("雪球 / 作者: timeline 第 1 页请求失败: HTTP 403")
        return []

    monkeypatch.setattr(social_daemon, "collect_account", failed_collect)
    monkeypatch.setattr(social_daemon, "upsert_items", lambda items, **kwargs: 0)
    monkeypatch.setattr(social_daemon, "export_collected_items", lambda *args, **kwargs: [])
    health = []
    monkeypatch.setattr(
        social_daemon,
        "record_source_health",
        lambda *args, **kwargs: health.append(kwargs),
    )

    result = run_once(
        accounts_path=tmp_path / "accounts.json",
        output_root=tmp_path / "sources",
        db_path=tmp_path / "articles.sqlite",
        settings=type("Settings", (), {"timezone": "Asia/Shanghai"})(),
    )

    assert result.errors == 1
    assert health[0]["ok"] is False
    assert "第 1 页请求失败" in health[0]["message"]


def test_cli_parser_exposes_social_daemon_and_health():
    from pipeline.cli import build_parser

    parser = build_parser()
    daemon = parser.parse_args(["social-daemon", "--interval-seconds", "60"])
    health = parser.parse_args(["social-health"])

    assert daemon.command == "social-daemon"
    assert daemon.interval_seconds == 60
    assert daemon.limit == 1000
    assert health.command == "social-health"


def test_social_health_is_unhealthy_without_records(tmp_path, capsys):
    import argparse
    from pipeline.cli import social_health_command

    result = social_health_command(argparse.Namespace(db=str(tmp_path / "empty.sqlite")))

    assert result == 1
    assert "No social collector health records" in capsys.readouterr().out


def test_social_health_is_unhealthy_when_records_are_stale(tmp_path, capsys, monkeypatch):
    import argparse
    import sqlite3
    from pipeline.cli import social_health_command
    from pipeline.storage import record_source_health

    db_path = tmp_path / "health.sqlite"
    record_source_health("雪球", "作者", ok=True, count=1, db_path=db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE source_health SET checked_at = '2020-01-01T00:00:00' WHERE source = '雪球'"
        )
    monkeypatch.setenv("SOCIAL_COLLECTOR_STALE_SECONDS", "60")

    result = social_health_command(argparse.Namespace(db=str(db_path)))

    assert result == 1
    assert "stale" in capsys.readouterr().out
