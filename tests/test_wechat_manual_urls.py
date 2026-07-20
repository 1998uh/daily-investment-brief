from __future__ import annotations

from pipeline.collectors.wechat import parse_manual_url_pool


def test_parse_manual_url_pool_supports_comments_plain_and_named_urls(tmp_path):
    path = tmp_path / "2026-07-16.txt"
    path.write_text(
        "\n".join(
            [
                "# comment",
                "",
                "https://mp.weixin.qq.com/s/plain",
                "猫笔刀|https://mp.weixin.qq.com/s/cat",
                "ETF领航员 https://mp.weixin.qq.com/s/etf",
            ]
        ),
        encoding="utf-8",
    )

    assert parse_manual_url_pool(path) == [
        ("手工公众号", "https://mp.weixin.qq.com/s/plain"),
        ("猫笔刀", "https://mp.weixin.qq.com/s/cat"),
        ("ETF领航员", "https://mp.weixin.qq.com/s/etf"),
    ]
