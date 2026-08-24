from datetime import datetime, timezone

from pipeline.collectors.base import CollectedItem, CollectionLog
from pipeline.collectors.accounts import Account
from pipeline.collectors.weread_mobile import ArticleMetadata, WeReadCredentials
from pipeline.collectors.wechat import collect_wechat_mobile


class FakeMobileClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def fetch_recent_articles(self, book_id, *, limit):
        return [
            ArticleMetadata(
                review_id="review-1",
                book_id=book_id,
                title="移动文章",
                publish_at=datetime(2026, 8, 24, 9, tzinfo=timezone.utc),
                url="https://mp.weixin.qq.com/s/article-1",
            )
        ]


def test_collect_wechat_mobile_uses_review_id_and_keeps_full_text(monkeypatch):
    import pipeline.collectors.wechat as wechat

    monkeypatch.setattr(wechat, "WeReadMobileClient", FakeMobileClient)
    monkeypatch.setattr(
        wechat,
        "fetch_wechat_article",
        lambda account, url, *, client, settings, reference: CollectedItem(
            source="微信公众号",
            author=account.name,
            title="移动文章",
            url=url,
            published_at=reference,
            content="正文内容",
            provider="wechat_public_url",
            review_id="review-1",
        ),
    )
    account = Account(source="微信公众号", name="示例公众号", uid="MP_WXS_123")
    log = CollectionLog()

    items = collect_wechat_mobile(
        account,
        book_id=account.uid,
        credentials=WeReadCredentials(vid="vid", access_token="token"),
        window_start=datetime(2026, 8, 24, 8, tzinfo=timezone.utc),
        window_end=datetime(2026, 8, 24, 10, tzinfo=timezone.utc),
        settings=object(),
        include_undated=False,
        limit=10,
        log=log,
    )

    assert len(items) == 1
    assert items[0].review_id == "review-1"
    assert items[0].content == "正文内容"
