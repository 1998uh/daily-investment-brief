from datetime import datetime, timezone

import pytest
from io import BytesIO
from urllib.error import HTTPError

from pipeline.collectors.weread_mobile import (
    AuthExpiredError,
    RiskControlError,
    WeReadCredentialStore,
    WeReadCredentials,
    WeReadMobileClient,
    parse_articles_payload,
)


def test_http_499_json_body_is_classified_by_business_error_code():
    from pipeline.collectors.weread_mobile import classify_http_error

    error = HTTPError(
        "https://i.weread.qq.com/mp/chapters",
        499,
        "ERR",
        {},
        BytesIO(b'{"errcode":-2041,"errmsg":"-2041"}'),
    )

    with pytest.raises(RiskControlError, match="-2041"):
        classify_http_error(error)


def test_credential_store_roundtrip_uses_camel_case_wire_fields(tmp_path):
    path = tmp_path / "weread_credentials.json"
    store = WeReadCredentialStore(path)
    store.save(
        WeReadCredentials(
            vid="vid-1",
            access_token="access-1",
            refresh_token="refresh-1",
            device_id="device-1",
        )
    )

    loaded = store.load()

    assert loaded is not None
    assert loaded.vid == "vid-1"
    assert loaded.access_token == "access-1"
    assert loaded.refresh_token == "refresh-1"
    assert loaded.device_id == "device-1"
    assert loaded.updated_at


def test_parse_current_chapters_payload_preserves_review_id_and_metadata():
    payload = {
        "data": [
            {
                "reviewId": "review-1",
                "title": "标题",
                "createTime": 1720000000,
                "summary": "摘要",
                "mpInfo": {"doc_url": "https://mp.weixin.qq.com/s/article-1"},
            }
        ]
    }

    articles = parse_articles_payload(payload, "MP_WXS_123")

    assert len(articles) == 1
    assert articles[0].review_id == "review-1"
    assert articles[0].book_id == "MP_WXS_123"
    assert articles[0].title == "标题"
    assert articles[0].url == "https://mp.weixin.qq.com/s/article-1"
    assert articles[0].publish_at == datetime.fromtimestamp(1720000000, tz=timezone.utc)


def test_parse_legacy_chapters_payload_supports_nested_review():
    payload = {
        "reviews": [
            {
                "subReviews": [
                    {
                        "reviewId": "legacy-1",
                        "review": {
                            "reviewId": "legacy-1",
                            "mpInfo": {"title": "旧标题", "url": "https://example.test/old"},
                            "createTime": 1720000001,
                        },
                    }
                ]
            }
        ]
    }

    articles = parse_articles_payload(payload, "MP_WXS_123")

    assert [(item.review_id, item.title, item.url) for item in articles] == [
        ("legacy-1", "旧标题", "https://example.test/old")
    ]


def test_get_articles_uses_synckey_only_for_first_request():
    class FakeTransport:
        def __init__(self):
            self.calls = []

        def get_json(self, path, *, params, headers):
            self.calls.append((path, params, headers))
            return {"data": []}

    transport = FakeTransport()
    client = WeReadMobileClient(
        vid="vid-1",
        access_token="token-1",
        transport=transport,
        min_interval=0,
    )

    client.get_articles("MP_WXS_123", count=20, synckey=0)
    client.get_articles("MP_WXS_123", count=20, offset=20)

    assert transport.calls[0][1] == {"bookId": "MP_WXS_123", "count": 20, "synckey": 0}
    assert transport.calls[1][1] == {"bookId": "MP_WXS_123", "count": 20, "offset": 20}


def test_fetch_recent_articles_starts_with_positive_synckey():
    """synckey=0 is rejected as -2041; the first page must use a positive cursor."""

    class FakeTransport:
        def __init__(self):
            self.calls = []

        def get_json(self, path, *, params, headers):
            self.calls.append((path, params, headers))
            return {"data": [{"reviewId": "r1", "createTime": 1720000000, "mpInfo": {"title": "t"}}]}

    transport = FakeTransport()
    client = WeReadMobileClient(
        vid="vid-1",
        access_token="token-1",
        transport=transport,
        min_interval=0,
    )

    client.fetch_recent_articles("MP_WXS_123", limit=1)

    assert transport.calls[0][1]["synckey"] == 1


def test_resolve_article_url_reads_doc_url_from_review_single():
    class FakeTransport:
        def __init__(self):
            self.calls = []

        def get_json(self, path, *, params, headers):
            self.calls.append((path, params))
            return {"review": {"mpInfo": {"doc_url": "https://mp.weixin.qq.com/s/a"}}}

    transport = FakeTransport()
    client = WeReadMobileClient(
        vid="vid-1",
        access_token="token-1",
        transport=transport,
        min_interval=0,
    )

    assert client.resolve_article_url("review-1") == "https://mp.weixin.qq.com/s/a"
    assert transport.calls == [("/review/single", {"reviewId": "review-1"})]


def test_refresh_updates_access_token_once_from_login_response():
    class FakeTransport:
        def __init__(self):
            self.calls = []

        def post_json(self, path, *, body, headers):
            self.calls.append((path, body, headers))
            return {
                "vid": "vid-1",
                "accessToken": "access-2",
                "refreshToken": "refresh-2",
                "deviceId": "device-1",
            }

    from pipeline.collectors.weread_mobile import WeReadCredentials

    transport = FakeTransport()
    client = WeReadMobileClient(
        credentials=WeReadCredentials(
            vid="vid-1",
            access_token="access-1",
            refresh_token="refresh-1",
            device_id="device-1",
        ),
        transport=transport,
        min_interval=0,
    )

    refreshed = client.refresh()

    assert refreshed.access_token == "access-2"
    assert client.access_token == "access-2"
    assert transport.calls[0][0] == "/login"


@pytest.mark.parametrize(
    ("status", "payload", "expected"),
    [
        (401, {}, AuthExpiredError),
        (200, {"errCode": -2012}, AuthExpiredError),
        (429, {}, RiskControlError),
        (200, {"errCode": -2041}, RiskControlError),
    ],
)
def test_get_articles_maps_auth_and_risk_errors(status, payload, expected):
    class FakeTransport:
        def get_json(self, path, *, params, headers):
            if status != 200:
                raise RuntimeError(f"HTTP {status}")
            return payload

    client = WeReadMobileClient(
        vid="vid-1",
        access_token="token-1",
        transport=FakeTransport(),
        min_interval=0,
    )

    with pytest.raises(expected):
        client.get_articles("MP_WXS_123")
