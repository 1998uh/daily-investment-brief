"""抖音采集器测试脚本

用于测试抖音用户视频列表采集功能。
"""
from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.collectors.accounts import Account
from pipeline.collectors.base import CollectionLog
from pipeline.collectors.douyin import collect_douyin, extract_sec_user_id
from pipeline.config import get_settings


def test_extract_sec_user_id():
    """测试 sec_user_id 提取"""
    print("=" * 60)
    print("测试 1: 提取 sec_user_id")
    print("=" * 60)

    test_cases = [
        (
            "https://www.douyin.com/user/MS4wLjABAAAAslofpLxb1ccBf6x1QC-hBZA8v4QpNg6GQjf8HQGQMiY",
            "MS4wLjABAAAAslofpLxb1ccBf6x1QC-hBZA8v4QpNg6GQjf8HQGQMiY"
        ),
        (
            "https://www.douyin.com/user/MS4wLjABAAAA123",
            "MS4wLjABAAAA123"
        ),
        ("", ""),
    ]

    for url, expected in test_cases:
        result = extract_sec_user_id(url)
        status = "[OK]" if result == expected else "[FAIL]"
        print(f"{status} URL: {url}")
        print(f"  Expected: {expected}")
        print(f"  Result: {result}")
        print()


def test_collect_douyin():
    """Test Douyin video collection"""
    print("=" * 60)
    print("Test 2: Collect Douyin user videos")
    print("=" * 60)

    # Chaojihui's sec_user_id
    account = Account(
        source="douyin",
        name="Chaojihui",
        url="https://www.douyin.com/user/MS4wLjABAAAAslofpLxb1ccBf6x1QC-hBZA8v4QpNg6GQjf8HQGQMiY",
        uid="",
        enabled=True,
    )

    # Set collection window: last 30 days
    tz = timezone(timedelta(hours=8))
    window_end = datetime.now(tz)
    window_start = window_end - timedelta(days=30)

    settings = get_settings()
    log = CollectionLog()

    print(f"Account: {account.name}")
    print(f"URL: {account.url}")
    print(f"Window: {window_start.strftime('%Y-%m-%d')} to {window_end.strftime('%Y-%m-%d')}")
    print()

    try:
        items = collect_douyin(
            account,
            window_start=window_start,
            window_end=window_end,
            settings=settings,
            limit=5,  # Only collect 5 items for testing
            include_undated=False,
            log=log,
        )

        print(f"[OK] Collection successful")
        print(f"  Items collected: {len(items)}")
        print()

        if items:
            print("Preview of first 3 items:")
            print("-" * 60)
            for i, item in enumerate(items[:3], 1):
                print(f"{i}. {item.title}")
                print(f"   URL: {item.url}")
                print(f"   Published: {item.published_at}")
                print(f"   Content: {item.content[:100]}...")
                print()

        # Print logs
        if log.warnings or log.errors:
            print("Log messages:")
            for warning in log.warnings:
                print(f"  [WARN] {warning}")
            for error in log.errors:
                print(f"  [ERROR] {error}")

    except Exception as exc:
        print(f"[FAIL] Collection failed: {exc}")
        import traceback
        traceback.print_exc()


def main():
    print("\nDouyin Collector Test\n")

    # Test 1: Extract sec_user_id
    test_extract_sec_user_id()

    # Test 2: Collect videos (requires Playwright)
    try:
        from playwright.sync_api import sync_playwright
        test_collect_douyin()
    except ImportError:
        print("=" * 60)
        print("Skipping collection test: Playwright not installed")
        print("Run these commands to install:")
        print("  pip install playwright")
        print("  playwright install chromium")
        print("=" * 60)


if __name__ == "__main__":
    main()
