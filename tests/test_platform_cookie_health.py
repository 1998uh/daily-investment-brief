from __future__ import annotations

import argparse
import json
from types import SimpleNamespace
from unittest.mock import patch

from pipeline.cli import collect_command, collect_one_command, source_health_command
from pipeline.collectors.douyin import check_douyin_cookie
from pipeline.collectors.weibo import check_weibo_cookie


class FakeClient:
    def __init__(self, payload=None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls = []

    def get_json(self, url, *, headers=None):
        self.calls.append((url, headers))
        if self.error:
            raise self.error
        return self.payload


def test_weibo_cookie_health_requires_sub(monkeypatch):
    monkeypatch.setenv("WEIBO_COOKIE", "XSRF-TOKEN=token")
    client = FakeClient({"ok": 1, "data": {"list": []}})

    result = check_weibo_cookie("123", client=client)

    assert not result.ok
    assert "SUB" in result.message
    assert client.calls == []


def test_weibo_cookie_health_accepts_successful_empty_first_page(monkeypatch):
    monkeypatch.setenv("WEIBO_COOKIE", "SUB=valid; XSRF-TOKEN=token")
    client = FakeClient({"ok": 1, "data": {"list": []}})

    result = check_weibo_cookie("123", client=client)

    assert result.ok
    assert result.status_count == 0
    assert "uid=123&page=1&feature=0" in client.calls[0][0]


def test_weibo_cookie_health_rejects_login_error(monkeypatch):
    monkeypatch.setenv("WEIBO_COOKIE", "SUB=expired")
    client = FakeClient({"ok": -100, "msg": "请先登录"})

    result = check_weibo_cookie("123", client=client)

    assert not result.ok
    assert "-100" in result.message


def test_douyin_cookie_health_requires_session(monkeypatch):
    monkeypatch.setenv("DOUYIN_COOKIE", "passport_csrf_token=token")
    called = False

    def fetcher(_uid, _cursor):
        nonlocal called
        called = True
        return {"status_code": 0, "aweme_list": []}

    result = check_douyin_cookie("sec-user", fetcher=fetcher)

    assert not result.ok
    assert "sessionid" in result.message
    assert not called


def test_douyin_cookie_health_accepts_successful_empty_first_page(monkeypatch):
    monkeypatch.setenv("DOUYIN_COOKIE", "sessionid_ss=valid")
    calls = []

    def fetcher(uid, cursor):
        calls.append((uid, cursor))
        return {"status_code": 0, "aweme_list": []}

    result = check_douyin_cookie("sec-user", fetcher=fetcher)

    assert result.ok
    assert result.status_count == 0
    assert calls == [("sec-user", 0)]


def test_douyin_cookie_health_rejects_api_error(monkeypatch):
    monkeypatch.setenv("DOUYIN_COOKIE", "sessionid=expired")

    result = check_douyin_cookie(
        "sec-user",
        fetcher=lambda _uid, _cursor: {"status_code": 8, "status_msg": "登录失效"},
    )

    assert not result.ok
    assert "API 错误 8" in result.message


def test_source_health_prints_weibo_and_douyin_login_commands(tmp_path, capsys):
    accounts_path = tmp_path / "accounts.json"
    accounts_path.write_text(
        json.dumps(
            {
                "xueqiu": [{"name": "雪球作者", "uid": "xq-id"}],
                "weibo": [{"name": "微博作者", "uid": "wb-id"}],
                "douyin": [{"name": "抖音作者", "uid": "dy-id"}],
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(db=str(tmp_path / "health.sqlite"), accounts=str(accounts_path))
    healthy = SimpleNamespace(ok=True, message="ok", status_count=1, check_completed=True)
    expired = SimpleNamespace(ok=False, message="expired", status_count=0, check_completed=True)

    with (
        patch("pipeline.config.load_env"),
        patch("pipeline.collectors.xueqiu.check_xueqiu_cookie", return_value=healthy),
        patch("pipeline.collectors.weibo.check_weibo_cookie", return_value=expired),
        patch("pipeline.collectors.douyin.check_douyin_cookie", return_value=expired),
    ):
        assert source_health_command(args) == 0

    output = capsys.readouterr().out
    assert "[WARN] 微博 Cookie 已过期，请运行 auth-login --platform weibo" in output
    assert "[WARN] 抖音 Cookie 已过期，请运行 auth-login --platform douyin" in output


def test_collect_stops_before_fetch_when_cookie_preflight_fails(tmp_path):
    accounts_path = tmp_path / "accounts.json"
    accounts_path.write_text("{}", encoding="utf-8")
    args = argparse.Namespace(
        start_date=None,
        end_date=None,
        date="2026-08-19",
        accounts=str(accounts_path),
        out_dir=str(tmp_path / "sources"),
        limit=20,
        include_undated=False,
        dry_run=False,
        sequential=True,
        no_cache_fallback=False,
        platform="weibo",
        and_generate=False,
        markdown_only=False,
    )

    with (
        patch("pipeline.collectors.browser.inject_browser_cookies"),
        patch("pipeline.cli.get_settings"),
        patch("pipeline.cli._collection_cookie_preflight", return_value=False) as preflight,
        patch("pipeline.cli.collect_to_sources") as collect,
    ):
        assert collect_command(args) == 1

    preflight.assert_called_once_with(accounts_path, platform_filter="weibo")
    collect.assert_not_called()


def test_collect_one_stops_before_fetch_when_cookie_preflight_fails(tmp_path):
    accounts_path = tmp_path / "accounts.json"
    accounts_path.write_text("{}", encoding="utf-8")
    args = argparse.Namespace(
        verbose=False,
        start_date=None,
        end_date=None,
        date="2026-08-19",
        name="微博作者",
        accounts=str(accounts_path),
        out_dir=str(tmp_path / "sources"),
        limit=20,
        include_undated=False,
        no_cache_fallback=False,
    )

    with (
        patch("pipeline.cli.get_settings"),
        patch("pipeline.cli._collection_cookie_preflight", return_value=False) as preflight,
        patch("pipeline.cli.collect_single_account") as collect,
    ):
        assert collect_one_command(args) == 1

    preflight.assert_called_once_with(accounts_path, account_name="微博作者")
    collect.assert_not_called()
