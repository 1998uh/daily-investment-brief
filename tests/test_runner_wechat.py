from pipeline.collectors.accounts import Account
from pipeline.collectors.base import CollectionLog
from pipeline.collectors.runner import PLATFORM_CONCURRENCY, PLATFORM_DELAY, validate_accounts


def test_validate_accounts_accepts_weread_book_id_without_urls_or_rss():
    account = Account(
        source="微信公众号",
        name="示例公众号",
        uid="MP_WXS_1234567890",
        urls=[],
        rss_url="",
    )
    log = CollectionLog()

    validate_accounts([account], log)

    assert not log.warnings


def test_wechat_collection_is_serial_and_rate_limited():
    assert PLATFORM_CONCURRENCY["微信公众号"] == 1
    assert PLATFORM_DELAY["微信公众号"][0] >= 2.0
