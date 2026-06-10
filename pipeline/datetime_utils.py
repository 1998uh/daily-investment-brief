from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import re
from zoneinfo import ZoneInfo


def brief_window(
    brief_date: date,
    *,
    timezone_name: str,
    start_time: str,
    end_time: str,
) -> tuple[datetime, datetime]:
    zone = ZoneInfo(timezone_name)
    start_clock = parse_clock(start_time)
    end_clock = parse_clock(end_time)
    end_day = brief_date
    start_day = brief_date - timedelta(days=1)
    return (
        datetime.combine(start_day, start_clock, zone),
        datetime.combine(end_day, end_clock, zone),
    )


def parse_clock(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(hour=int(hour), minute=int(minute))


def format_window_cn(start: datetime, end: datetime) -> str:
    return f"{start:%Y-%m-%d %H:%M} ~ {end:%Y-%m-%d %H:%M}"


def parse_datetime(value: object, *, reference: datetime, timezone_name: str) -> datetime | None:
    if value is None:
        return None

    zone = ZoneInfo(timezone_name)
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, timezone.utc).astimezone(zone)

    text = str(value).strip()
    if not text:
        return None

    if text.isdigit():
        return parse_datetime(int(text), reference=reference, timezone_name=timezone_name)

    now_like = datetime.now(zone)
    if text in {"刚刚", "刚才"}:
        return now_like

    minute_match = re.match(r"^(\d+)\s*分钟前$", text)
    if minute_match:
        return now_like - timedelta(minutes=int(minute_match.group(1)))

    hour_match = re.match(r"^(\d+)\s*小时前$", text)
    if hour_match:
        return now_like - timedelta(hours=int(hour_match.group(1)))

    today_match = re.match(r"^今天\s*(\d{1,2}):(\d{2})$", text)
    if today_match:
        return datetime(
            reference.year,
            reference.month,
            reference.day,
            int(today_match.group(1)),
            int(today_match.group(2)),
            tzinfo=zone,
        )

    yesterday_match = re.match(r"^昨天\s*(\d{1,2}):(\d{2})$", text)
    if yesterday_match:
        day = reference.date() - timedelta(days=1)
        return datetime(
            day.year,
            day.month,
            day.day,
            int(yesterday_match.group(1)),
            int(yesterday_match.group(2)),
            tzinfo=zone,
        )

    month_day_match = re.match(r"^(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?$", text)
    if month_day_match:
        hour = int(month_day_match.group(3) or 0)
        minute = int(month_day_match.group(4) or 0)
        return datetime(
            reference.year,
            int(month_day_match.group(1)),
            int(month_day_match.group(2)),
            hour,
            minute,
            tzinfo=zone,
        )

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%a %b %d %H:%M:%S %z %Y",
    ]
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=zone)
        return parsed.astimezone(zone)

    return None
