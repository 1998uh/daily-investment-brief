from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json


@dataclass(frozen=True)
class Account:
    source: str
    name: str
    url: str = ""
    uid: str = ""
    enabled: bool = True
    urls: list[str] = field(default_factory=list)
    rss_url: str = ""


def load_accounts(path: Path) -> list[Account]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    accounts: list[Account] = []

    for source, entries in payload.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            accounts.append(
                Account(
                    source=normalize_source(source),
                    name=str(entry.get("name") or ""),
                    url=str(entry.get("url") or ""),
                    uid=str(entry.get("uid") or ""),
                    enabled=bool(entry.get("enabled", True)),
                    urls=[str(value) for value in entry.get("urls", []) if value],
                    rss_url=str(entry.get("rss_url") or ""),
                )
            )

    return [account for account in accounts if account.name]


def normalize_source(value: str) -> str:
    lower = value.lower()
    if lower in {"xueqiu", "雪球"}:
        return "雪球"
    if lower in {"wechat", "weixin", "微信公众号", "微信"}:
        return "微信公众号"
    if lower in {"weibo", "微博"}:
        return "微博"
    return value
