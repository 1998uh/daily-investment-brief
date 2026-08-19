from __future__ import annotations

import argparse
import json
from unittest.mock import patch

from pipeline.cli import source_health_command
from pipeline.collectors.xueqiu import check_xueqiu_cookie


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
