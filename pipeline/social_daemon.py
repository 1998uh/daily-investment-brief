from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import os
from pathlib import Path
import random
import time
from zoneinfo import ZoneInfo

from .collectors.accounts import load_accounts
from .collectors.auth import (
    inject_platform_cookie_files,
    load_platform_cookie,
    platform_cookie_is_usable,
    redact_secret_text,
)
from .collectors.base import CollectionLog, CollectedItem
from .collectors.runner import collect_account
from .collectors.writer import write_items
from .config import ROOT, get_settings
from .storage import record_source_health, upsert_items

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SocialRunResult:
    accounts: int
    items: int
    changed: int
    written: int
    errors: int


def _now(timezone_name: str) -> datetime:
    return datetime.now(ZoneInfo(timezone_name))


def export_collected_items(
    items: list[CollectedItem], output_root: Path, *, timezone_name: str | None = None
) -> list[Path]:
    """Export items to the existing date-partitioned source format."""
    grouped: dict[str, list[CollectedItem]] = {}
    today = datetime.now().date().isoformat()
    for item in items:
        published_at = item.published_at
        if published_at and timezone_name:
            published_at = published_at.astimezone(ZoneInfo(timezone_name))
        date_key = published_at.date().isoformat() if published_at else today
        grouped.setdefault(date_key, []).append(item)
    written: list[Path] = []
    for date_key, group in grouped.items():
        written.extend(write_items(group, output_root / date_key))
    return written


def run_once(
    *,
    accounts_path: Path,
    output_root: Path,
    db_path: Path,
    limit: int = 1000,
    lookback_hours: int = 48,
    settings=None,
) -> SocialRunResult:
    """Run one bounded collection pass for enabled Xueqiu/Weibo accounts."""
    inject_platform_cookie_files(prefer_file=True)
    settings = settings or get_settings()
    end = _now(settings.timezone)
    start = end - timedelta(hours=max(1, lookback_hours))
    accounts = [
        account
        for account in load_accounts(accounts_path)
        if account.enabled and account.source in {"雪球", "微博"}
    ]
    all_items: list[CollectedItem] = []
    errors = 0
    for index, account in enumerate(accounts):
        platform = "xueqiu" if account.source == "雪球" else "weibo"
        cookie = load_platform_cookie(platform)
        if not platform_cookie_is_usable(platform, cookie):
            message = f"{account.source} Cookie 缺少有效登录令牌"
            record_source_health(account.source, account.name, ok=False, count=0, message=message, db_path=db_path)
            errors += 1
            continue
        clog = CollectionLog()
        try:
            items = collect_account(
                account,
                window_start=start,
                window_end=end,
                settings=settings,
                limit=limit,
                include_undated=False,
                log=clog,
            )
            fatal_warning = next(
                (
                    warning
                    for warning in clog.warnings
                    if "第 1 页请求失败" in warning or "API 返回错误" in warning
                ),
                "",
            )
            if not items and (clog.errors or fatal_warning):
                errors += 1
                message = redact_secret_text(clog.errors[0] if clog.errors else fatal_warning)
                record_source_health(
                    account.source,
                    account.name,
                    ok=False,
                    count=0,
                    message=message,
                    db_path=db_path,
                )
                continue
            all_items.extend(items)
            partial_count = sum(item.content_status != "ready" for item in items)
            message = f"partial={partial_count}" if partial_count else ""
            record_source_health(
                account.source,
                account.name,
                ok=True,
                count=len(items),
                message=message,
                db_path=db_path,
            )
        except Exception as exc:  # noqa: BLE001 - isolate one account from the pass
            errors += 1
            safe_error = redact_secret_text(exc)
            record_source_health(account.source, account.name, ok=False, count=0, message=safe_error, db_path=db_path)
            log.warning("social collection failed for %s/%s: %s", account.source, account.name, safe_error)
        if index < len(accounts) - 1:
            time.sleep(random.uniform(1.0, 3.0))
    changed = upsert_items(all_items, db_path=db_path)
    written = export_collected_items(all_items, output_root, timezone_name=settings.timezone)
    return SocialRunResult(len(accounts), len(all_items), changed, len(written), errors)


def run_forever(
    *,
    accounts_path: Path = ROOT / "config" / "accounts.json",
    output_root: Path = ROOT / "sources" / "_raw",
    db_path: Path = ROOT / "data" / "articles.sqlite",
    interval_seconds: int | None = None,
    limit: int = 1000,
    lookback_hours: int | None = None,
) -> None:
    settings = get_settings()
    interval = interval_seconds or int(os.getenv("SOCIAL_COLLECTOR_INTERVAL_SECONDS", "1800"))
    lookback = lookback_hours or int(os.getenv("SOCIAL_COLLECTOR_LOOKBACK_HOURS", "48"))
    while True:
        try:
            result = run_once(
                accounts_path=accounts_path,
                output_root=output_root,
                db_path=db_path,
                limit=limit,
                lookback_hours=lookback,
                settings=settings,
            )
            log.info(
                "social pass: accounts=%d items=%d changed=%d written=%d errors=%d",
                result.accounts, result.items, result.changed, result.written, result.errors,
            )
        except Exception as exc:  # noqa: BLE001 - keep the daemon alive across pass failures
            log.error("social pass failed: %s", redact_secret_text(exc))
        time.sleep(max(10, interval))


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run_forever()
