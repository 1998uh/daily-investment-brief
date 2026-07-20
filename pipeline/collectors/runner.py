from __future__ import annotations

import random
import threading
import time
from collections import defaultdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import date
from pathlib import Path

from .accounts import Account, load_accounts
from .base import CollectedItem, CollectionLog
from .weibo import collect_weibo
from .wechat import collect_wechat, collect_wechat_manual_urls
from .writer import write_items
from .xueqiu import collect_xueqiu
from ..cancel import PipelineCancelled, interruptible_sleep, is_cancelled, raise_if_cancelled
from ..config import ROOT, Settings
from ..datetime_utils import brief_window, format_window_cn
from ..storage import query_items, record_source_health, upsert_items

# 每个平台的最大并发数和账号间延时（秒）
PLATFORM_CONCURRENCY: dict[str, int] = {
    "雪球": 3,
    "微博": 2,
    "微信公众号": 4,
}
PLATFORM_DELAY: dict[str, tuple[float, float]] = {
    "雪球": (2.0, 5.0),
    "微博": (1.0, 3.0),
    "微信公众号": (0.5, 1.0),
}
DEFAULT_CONCURRENCY = 2
DEFAULT_DELAY = (1.0, 3.0)


class ProgressTracker:
    """线程安全的实时进度追踪器。"""

    def __init__(self, total: int, platform_totals: dict[str, int]) -> None:
        self._lock = threading.Lock()
        self._start = time.monotonic()
        self._total = total
        self._done = 0
        self._platform_totals = platform_totals
        self._platform_done: dict[str, int] = {p: 0 for p in platform_totals}

    def mark_started(self, platform: str, name: str) -> None:
        with self._lock:
            self._print(f"  ▶ {platform}/{name} ...")

    def mark_done(
        self, platform: str, name: str, count: int, *, ok: bool, error: str = ""
    ) -> None:
        with self._lock:
            self._done += 1
            self._platform_done[platform] = self._platform_done.get(platform, 0) + 1
            elapsed = time.monotonic() - self._start
            if ok:
                status = f"  ✓ {platform}/{name}  {count}条"
            else:
                status = f"  ✗ {platform}/{name}  {error[:60]}"
            self._print(f"{status}  [{self._done}/{self._total}] {elapsed:.0f}s")

    def _print(self, msg: str) -> None:
        try:
            print(msg, flush=True)
        except UnicodeEncodeError:
            # Windows GBK 终端无法输出 Unicode 符号时，替换后重试
            safe = msg.replace("▶", ">").replace("✓", "+").replace("✗", "x")
            print(safe, flush=True)


def collect_to_sources(
    *,
    accounts_path: Path,
    out_dir: Path,
    brief_date: date,
    settings: Settings,
    limit: int,
    include_undated: bool,
    dry_run: bool = False,
    parallel: bool = True,
    cache_fallback: bool = True,
) -> tuple[list[Path], CollectionLog]:
    log = CollectionLog()
    accounts = load_accounts(accounts_path)
    enabled_accounts = [account for account in accounts if account.enabled]
    window_start, window_end = brief_window(
        brief_date,
        timezone_name=settings.timezone,
        start_time=settings.window_start,
        end_time=settings.window_end,
    )

    log.add_info(f"账号配置: {accounts_path}")
    log.add_info(f"采集窗口: {format_window_cn(window_start, window_end)}（{settings.timezone}）")
    log.add_info(f"启用账号: {len(enabled_accounts)} / {len(accounts)}")

    if dry_run:
        validate_accounts(enabled_accounts, log)
        return [], log

    collect_kwargs = dict(
        window_start=window_start,
        window_end=window_end,
        settings=settings,
        limit=limit,
        include_undated=include_undated,
    )

    raise_if_cancelled()

    if parallel and len(enabled_accounts) > 1:
        items = _collect_parallel(enabled_accounts, log=log, **collect_kwargs)
    else:
        items = _collect_sequential(enabled_accounts, log=log, **collect_kwargs)

    manual_urls = ROOT / "config" / "wechat_urls" / f"{brief_date.isoformat()}.txt"
    items.extend(
        collect_wechat_manual_urls(
            manual_urls,
            window_start=window_start,
            window_end=window_end,
            settings=settings,
            include_undated=include_undated,
            log=log,
        )
    )

    raise_if_cancelled()
    changed = upsert_items(items)
    if cache_fallback:
        export_items = query_items(window_start, window_end)
        if include_undated:
            export_items.extend(item for item in items if item.published_at is None)
    else:
        export_items = items
    written = write_items(export_items, out_dir)
    log.add_info(
        f"新增/更新缓存: {changed} / 实时采集条目: {len(items)} / 导出条目: {len(export_items)}"
    )
    log.add_info(f"新增 Markdown: {len(written)} / 导出条目: {len(export_items)}")
    return written, log


def _collect_sequential(
    accounts: list[Account],
    *,
    log: CollectionLog,
    **kwargs,
) -> list[CollectedItem]:
    """原始串行采集逻辑。"""
    progress = ProgressTracker(
        total=len(accounts),
        platform_totals=_count_by_platform(accounts),
    )
    items: list[CollectedItem] = []
    for i, account in enumerate(accounts):
        raise_if_cancelled()
        progress.mark_started(account.source, account.name)
        try:
            batch = collect_account(account, log=log, **kwargs)
            items.extend(batch)
            record_source_health(account.source, account.name, ok=True, count=len(batch))
            progress.mark_done(account.source, account.name, len(batch), ok=True)
        except PipelineCancelled:
            raise
        except Exception as exc:
            log.add_error(f"{account.source} / {account.name}: {exc}")
            record_source_health(account.source, account.name, ok=False, count=0, message=str(exc))
            progress.mark_done(account.source, account.name, 0, ok=False, error=str(exc))
        if i < len(accounts) - 1:
            interruptible_sleep(random.uniform(2.0, 5.0))
    return items


def _collect_parallel(
    accounts: list[Account],
    *,
    log: CollectionLog,
    **kwargs,
) -> list[CollectedItem]:
    """按平台分组并行采集。"""
    # 按平台分组
    by_platform: dict[str, list[Account]] = defaultdict(list)
    for account in accounts:
        by_platform[account.source].append(account)

    platform_totals = {p: len(accs) for p, accs in by_platform.items()}
    progress = ProgressTracker(total=len(accounts), platform_totals=platform_totals)

    # 打印并行模式信息
    parts = [f"{p}×{PLATFORM_CONCURRENCY.get(p, DEFAULT_CONCURRENCY)}" for p in by_platform]
    print(f"[info] 并行模式: {' | '.join(parts)}", flush=True)

    # 每个平台一个 ThreadPoolExecutor，所有平台同时运行
    items: list[CollectedItem] = []
    items_lock = threading.Lock()
    # future -> account
    future_map: dict = {}
    executors: list[ThreadPoolExecutor] = []

    try:
        for platform, platform_accounts in by_platform.items():
            max_workers = PLATFORM_CONCURRENCY.get(platform, DEFAULT_CONCURRENCY)
            delay = PLATFORM_DELAY.get(platform, DEFAULT_DELAY)
            executor = ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix=f"collect-{platform}",
            )
            executors.append(executor)

            for account in platform_accounts:
                future = executor.submit(
                    _collect_one,
                    account,
                    log=log,
                    progress=progress,
                    delay=delay,
                    **kwargs,
                )
                future_map[future] = account

        # Poll futures briefly so Esc cancellation is observed.
        pending = set(future_map)
        while pending:
            raise_if_cancelled()
            done, pending = wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)
            for future in done:
                account = future_map[future]
                try:
                    batch = future.result()
                    with items_lock:
                        items.extend(batch)
                    record_source_health(account.source, account.name, ok=True, count=len(batch))
                    progress.mark_done(account.source, account.name, len(batch), ok=True)
                except PipelineCancelled:
                    raise
                except Exception as exc:
                    log.add_error(f"{account.source} / {account.name}: {exc}")
                    record_source_health(
                        account.source, account.name, ok=False, count=0, message=str(exc)
                    )
                    progress.mark_done(account.source, account.name, 0, ok=False, error=str(exc))
    except (KeyboardInterrupt, PipelineCancelled):
        for future in future_map:
            future.cancel()
        raise
    finally:
        for executor in executors:
            executor.shutdown(wait=False, cancel_futures=True)

    return items


def _collect_one(
    account: Account,
    *,
    log: CollectionLog,
    progress: ProgressTracker,
    delay: tuple[float, float],
    **kwargs,
) -> list[CollectedItem]:
    """采集单个账号，完成后 sleep 实现同平台限速。"""
    progress.mark_started(account.source, account.name)
    try:
        raise_if_cancelled()
        result = collect_account(account, log=log, **kwargs)
    finally:
        # 同平台内限速：worker 完成后 sleep，下一个任务自然延后
        if not is_cancelled():
            interruptible_sleep(random.uniform(*delay))
    return result


def collect_account(
    account: Account,
    *,
    window_start,
    window_end,
    settings: Settings,
    limit: int,
    include_undated: bool,
    log: CollectionLog,
) -> list[CollectedItem]:
    raise_if_cancelled()
    if account.source == "雪球":
        return collect_xueqiu(
            account,
            window_start=window_start,
            window_end=window_end,
            settings=settings,
            limit=limit,
            include_undated=include_undated,
            clog=log,
        )
    if account.source == "微博":
        return collect_weibo(
            account,
            window_start=window_start,
            window_end=window_end,
            settings=settings,
            limit=limit,
            include_undated=include_undated,
            log=log,
        )
    if account.source == "微信公众号":
        return collect_wechat(
            account,
            window_start=window_start,
            window_end=window_end,
            settings=settings,
            limit=limit,
            include_undated=include_undated,
            log=log,
        )
    log.add_warning(f"{account.source} / {account.name}: 不支持的平台")
    return []


def validate_accounts(accounts: list[Account], log: CollectionLog) -> None:
    for account in accounts:
        if account.source in {"雪球", "微博"} and not (account.uid or account.url):
            log.add_warning(f"{account.source} / {account.name}: 需要补 uid 或主页 url")
        if account.source == "微信公众号" and not (account.urls or account.rss_url):
            log.add_warning(f"{account.source} / {account.name}: 需要补 urls 或 rss_url")


def collect_single_account(
    *,
    name: str,
    accounts_path: Path,
    out_dir: Path,
    brief_date: date,
    settings: Settings,
    limit: int,
    include_undated: bool,
    cache_fallback: bool = True,
) -> tuple[list[Path], CollectionLog]:
    """按名称查找并采集单个博主。"""
    log = CollectionLog()
    accounts = load_accounts(accounts_path)
    matched = [a for a in accounts if a.name == name]
    if not matched:
        log.add_error(f"未找到名为 \"{name}\" 的账号")
        all_names = [a.name for a in accounts]
        log.add_info(f"可用账号: {', '.join(all_names)}")
        return [], log

    account = matched[0]
    window_start, window_end = brief_window(
        brief_date,
        timezone_name=settings.timezone,
        start_time=settings.window_start,
        end_time=settings.window_end,
    )

    log.add_info(f"单账号采集: {account.source} / {account.name}")
    log.add_info(f"采集窗口: {format_window_cn(window_start, window_end)}（{settings.timezone}）")

    try:
        raise_if_cancelled()
        items = collect_account(
            account,
            window_start=window_start,
            window_end=window_end,
            settings=settings,
            limit=limit,
            include_undated=include_undated,
            log=log,
        )
        record_source_health(account.source, account.name, ok=True, count=len(items))
    except PipelineCancelled:
        raise
    except Exception as exc:
        log.add_error(f"{account.source} / {account.name}: {exc}")
        record_source_health(account.source, account.name, ok=False, count=0, message=str(exc))
        items = []

    raise_if_cancelled()
    changed = upsert_items(items)
    if cache_fallback:
        export_items = query_items(window_start, window_end, source=account.source, author=account.name)
        if include_undated:
            export_items.extend(item for item in items if item.published_at is None)
    else:
        export_items = items
    written = write_items(export_items, out_dir)
    log.add_info(
        f"新增/更新缓存: {changed} / 实时采集条目: {len(items)} / 导出条目: {len(export_items)}"
    )
    log.add_info(f"新增 Markdown: {len(written)} / 导出条目: {len(export_items)}")
    return written, log


def _count_by_platform(accounts: list[Account]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for account in accounts:
        counts[account.source] += 1
    return dict(counts)
