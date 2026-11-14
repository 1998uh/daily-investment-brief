from pipeline.collectors.auth import (
    browser_cookies_from_header,
    cookie_header_from_items,
    platform_cookie_file,
)


def test_cookie_header_from_items_deduplicates():
    cookies = [
        {"name": "sessionid", "value": "abc"},
        {"name": "ttwid", "value": "def"},
        {"name": "sessionid", "value": "newer"},
    ]

    assert cookie_header_from_items(cookies) == "sessionid=abc; ttwid=def"


def test_browser_cookies_from_header_sets_domain_and_path():
    items = browser_cookies_from_header("sessionid=abc; ttwid=def", ".douyin.com")

    assert items[0] == {
        "name": "sessionid",
        "value": "abc",
        "domain": ".douyin.com",
        "path": "/",
    }


def test_platform_cookie_file_prefers_env(monkeypatch, tmp_path):
    target = tmp_path / "douyin_cookie.txt"
    monkeypatch.setenv("DOUYIN_COOKIE_FILE", str(target))

    assert platform_cookie_file("douyin") == target


def test_platform_cookie_file_defaults_to_secrets(monkeypatch):
    monkeypatch.delenv("DOUYIN_COOKIE_FILE", raising=False)

    path = platform_cookie_file("douyin")

    assert path.name == "douyin_cookie.txt"
    assert path.parent.name == "secrets"
