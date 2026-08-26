from __future__ import annotations

import argparse
from datetime import datetime
import json
from types import SimpleNamespace
from unittest.mock import patch

from pipeline.cli import source_health_command
from pipeline.collectors.accounts import Account
from pipeline.collectors.base import CollectionLog
from pipeline.collectors.browser import _cookie_header_to_browser_cookies
from pipeline.collectors.xueqiu import (
    _fetch_timeline,
    _is_reply_or_junk,
    _parse_status,
    check_xueqiu_cookie,
    is_cached_xueqiu_reply_or_retweet,
)


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


def test_cookie_health_requires_xq_a_token(monkeypatch):
    monkeypatch.setenv("XUEQIU_COOKIE", "u=123; other=value")
    client = FakeClient({"statuses": []})

    result = check_xueqiu_cookie("123", client=client)

    assert not result.ok
    assert "xq_a_token" in result.message
    assert client.calls == []


def test_cookie_health_accepts_successful_empty_first_page(monkeypatch):
    monkeypatch.setenv("XUEQIU_COOKIE", "xq_a_token=valid-token; u=123")
    client = FakeClient({"statuses": []})

    result = check_xueqiu_cookie("123", client=client)

    assert result.ok
    assert result.status_count == 0
    assert "user_id=123&page=1&count=1" in client.calls[0][0]


def test_cookie_health_rejects_api_error(monkeypatch):
    monkeypatch.setenv("XUEQIU_COOKIE", "xq_a_token=expired-token")
    client = FakeClient({"error_code": "400016", "error_description": "登录过期"})

    result = check_xueqiu_cookie("123", client=client)

    assert not result.ok
    assert "400016" in result.message


def test_source_health_warns_when_probe_fails_even_without_db_rows(tmp_path, capsys):
    accounts_path = tmp_path / "accounts.json"
    accounts_path.write_text(
        json.dumps({"xueqiu": [{"name": "作者", "uid": "123", "enabled": True}]}),
        encoding="utf-8",
    )
    args = argparse.Namespace(db=str(tmp_path / "missing.sqlite"), accounts=str(accounts_path))

    with (
        patch("pipeline.config.load_env"),
        patch("pipeline.collectors.xueqiu.check_xueqiu_cookie") as check,
    ):
        check.return_value.ok = False
        check.return_value.message = "第 1 页请求失败"
        assert source_health_command(args) == 0

    output = capsys.readouterr().out
    assert "[WARN] 雪球 Cookie 已过期，请运行 auth-login" in output
    assert "No source health records found" in output


def test_reply_detection_uses_comment_id_and_markdown_link_prefix():
    assert _is_reply_or_junk({"commentId": 123}, "回复[@用户](https://xueqiu.com/n/u)：有价值的回复内容" * 3)
    assert _is_reply_or_junk({"retweeted_status": {"id": 1}}, "带有很多文字的转发评论" * 20)


def test_browser_cookie_conversion_preserves_names_and_values():
    cookies = _cookie_header_to_browser_cookies("xq_a_token=a=b; u=42")

    assert [(cookie["name"], cookie["value"]) for cookie in cookies] == [
        ("xq_a_token", "a=b"),
        ("u", "42"),
    ]


def test_cached_reply_is_filtered_from_future_exports():
    item = type(
        "Item",
        (),
        {
            "source": "雪球",
            "content": "回复[@用户](https://xueqiu.com/n/u)：旧缓存回复",
            "title": "回复用户",
            "raw_json": "",
        },
    )()

    assert is_cached_xueqiu_reply_or_retweet(item)


def test_timeline_scans_past_reply_only_pages_to_find_original(monkeypatch):
    class PagingClient:
        def __init__(self):
            self.pages = []

        def get_json(self, url, *, headers=None):
            page = int(url.split("page=", 1)[1].split("&", 1)[0])
            self.pages.append(page)
            if page <= 10:
                return {
                    "statuses": [
                        {
                            "id": page * 100 + i,
                            "commentId": page * 100 + i,
                            "text": "回复[@某人](https://xueqiu.com/n/u)：回复内容足够长" * 3,
                            "created_at": "2026-08-26 09:00:00",
                        }
                        for i in range(20)
                    ]
                }
            if page == 11:
                return {
                    "statuses": [
                        {
                            "id": 99999,
                            "commentId": 0,
                            "text": "这是需要被发现的原创投资分析，正文长度足够通过内容过滤。" * 3,
                            "created_at": "2026-08-26 08:30:00",
                        }
                    ]
                }
            return {"statuses": []}

    monkeypatch.setattr("pipeline.collectors.xueqiu._long_sleep", lambda: None)
    client = PagingClient()
    log = CollectionLog()
    items = _fetch_timeline(
        "https://xueqiu.com/statuses/user_timeline.json",
        uid="42",
        account=Account(source="雪球", name="作者", uid="42"),
        headers={},
        client=client,
        window_start=datetime.fromisoformat("2026-08-25T08:00:00+08:00"),
        window_end=datetime.fromisoformat("2026-08-27T08:00:00+08:00"),
        settings=SimpleNamespace(timezone="Asia/Shanghai"),
        limit=300,
        include_undated=False,
        clog=log,
        seen_ids=set(),
        label="timeline",
    )

    assert [item.url for item in items] == ["https://xueqiu.com/42/99999"]
    assert 11 in client.pages


def test_truncated_long_article_is_marked_partial_when_detail_fetch_fails(monkeypatch):
    client = FakeClient(error=RuntimeError("detail unavailable"))
    log = CollectionLog()
    status = {
        "id": 406626648,
        "title": "对 OpenAI 自研芯片的解读与思考",
        "text": "这只是时间线返回的截断摘要，正文实际还有大量芯片架构、性能和投资影响分析...",
        "created_at": "2026-08-26 09:06:47",
    }
    monkeypatch.setattr("pipeline.collectors.xueqiu.HAS_PLAYWRIGHT", False)

    item = _parse_status(
        status,
        Account(source="雪球", name="作者", uid="42"),
        "42",
        datetime.fromisoformat("2026-08-27T08:00:00+08:00"),
        SimpleNamespace(timezone="Asia/Shanghai"),
        client,
        log,
    )

    assert item is not None
    assert item.content_status == "partial"
    assert item.provider == "xueqiu_summary"
