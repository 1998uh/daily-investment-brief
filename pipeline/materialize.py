from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import shutil
import uuid

from .collectors.base import CollectedItem
from .collectors.writer import write_items
from .collectors.xueqiu import is_cached_xueqiu_reply_or_retweet
from .datetime_utils import brief_window
from .storage import query_items


REQUIRED_SOURCES = ("雪球", "微博", "微信公众号")


@dataclass(frozen=True)
class MaterializeResult:
    report_date: date
    window_start: datetime
    window_end: datetime
    output_dir: Path
    counts: dict[str, int]
    missing_sources: list[str]
    written: list[Path]


def _valid_daily_item(item: CollectedItem) -> bool:
    if is_cached_xueqiu_reply_or_retweet(item):
        return False
    if item.source == "微信公众号" and (
        not item.content.strip() or item.content_status != "ready"
    ):
        return False
    return bool(item.content.strip())


def materialize_daily_sources(
    *,
    report_date: date,
    db_path: Path,
    out_dir: Path,
    timezone_name: str,
    window_start: str,
    window_end: str,
) -> MaterializeResult:
    """Build an exact report-date source directory from timestamped SQLite rows."""
    start, end = brief_window(
        report_date,
        timezone_name=timezone_name,
        start_time=window_start,
        end_time=window_end,
    )
    items = [
        item
        for item in query_items(start, end, db_path=db_path)
        if _valid_daily_item(item)
    ]
    counts = {
        source: sum(item.source == source for item in items)
        for source in REQUIRED_SOURCES
    }
    missing = [source for source in REQUIRED_SOURCES if counts[source] == 0]

    out_dir = out_dir.resolve()
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    staging = out_dir.parent / f".{out_dir.name}.materialize-{token}"
    backup = out_dir.parent / f".{out_dir.name}.backup-{token}"
    staging.mkdir(parents=True)
    staged_paths = write_items(items, staging)

    moved_old = False
    try:
        if out_dir.exists():
            out_dir.replace(backup)
            moved_old = True
        staging.replace(out_dir)
    except Exception:
        if moved_old and backup.exists() and not out_dir.exists():
            backup.replace(out_dir)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    if backup.exists():
        shutil.rmtree(backup)
    written = [out_dir / path.name for path in staged_paths]
    return MaterializeResult(
        report_date=report_date,
        window_start=start,
        window_end=end,
        output_dir=out_dir,
        counts=counts,
        missing_sources=missing,
        written=written,
    )
