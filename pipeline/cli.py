from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

from .config import ROOT, get_settings
from .collectors.runner import collect_to_sources, collect_single_account
from .generator import generate_brief
from .html import wrap_html
from .ingest import load_articles


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "generate":
        return generate_command(args)
    if args.command == "collect":
        return collect_command(args)
    if args.command == "collect-one":
        return collect_one_command(args)

    parser.print_help()
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a daily investment brief.")
    subparsers = parser.add_subparsers(dest="command")

    collect = subparsers.add_parser("collect", help="Collect source articles into Markdown files.")
    collect.add_argument("--date", required=True, help="Brief date, e.g. 2026-06-07.")
    collect.add_argument(
        "--accounts",
        help="Account config JSON. Defaults to config/accounts.json, then config/accounts.example.json.",
    )
    collect.add_argument(
        "--out-dir",
        help="Output source directory. Defaults to sources/<date>.",
    )
    collect.add_argument("--limit", type=int, default=20, help="Maximum items per account.")
    collect.add_argument(
        "--include-undated",
        action="store_true",
        help="Keep items whose publish time cannot be parsed.",
    )
    collect.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate account config without fetching.",
    )
    collect.add_argument(
        "--sequential",
        action="store_true",
        help="Disable parallel collection; process accounts one by one.",
    )
    collect.add_argument(
        "--and-generate",
        action="store_true",
        help="Generate the brief after collection.",
    )
    collect.add_argument(
        "--markdown-only",
        action="store_true",
        help="When used with --and-generate, skip HTML output.",
    )

    generate = subparsers.add_parser("generate", help="Generate Markdown and HTML brief.")

    collect_one = subparsers.add_parser("collect-one", help="Collect articles from a single account.")
    collect_one.add_argument("--name", required=True, help="Account name as in accounts.json.")
    collect_one.add_argument("--date", required=True, help="Brief date, e.g. 2026-06-09.")
    collect_one.add_argument(
        "--accounts",
        help="Account config JSON. Defaults to config/accounts.json.",
    )
    collect_one.add_argument(
        "--out-dir",
        help="Output source directory. Defaults to sources/<date>.",
    )
    collect_one.add_argument("--limit", type=int, default=20, help="Maximum items.")
    collect_one.add_argument(
        "--include-undated",
        action="store_true",
        help="Keep items whose publish time cannot be parsed.",
    )
    collect_one.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG logging for detailed diagnostics.",
    )


    generate.add_argument("--date", required=True, help="Brief date, e.g. 2026-06-07.")
    generate.add_argument(
        "--source-dir",
        help="Source directory. Defaults to sources/<date>.",
    )
    generate.add_argument(
        "--out-dir",
        help="Output directory. Defaults to reports/<date>.",
    )
    generate.add_argument(
        "--markdown-only",
        action="store_true",
        help="Skip HTML output.",
    )
    return parser


def collect_command(args: argparse.Namespace) -> int:
    brief_date = date.fromisoformat(args.date)
    accounts_path = Path(args.accounts) if args.accounts else default_accounts_path()
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "sources" / args.date
    settings = get_settings()

    if not accounts_path.exists():
        print(f"Account config not found: {accounts_path}", file=sys.stderr)
        return 2

    written, log = collect_to_sources(
        accounts_path=accounts_path,
        out_dir=out_dir,
        brief_date=brief_date,
        settings=settings,
        limit=args.limit,
        include_undated=args.include_undated,
        dry_run=args.dry_run,
        parallel=not args.sequential,
    )
    print_collection_log(log)

    if args.dry_run:
        return 0

    print(f"Written files: {len(written)}")
    for path in written:
        print(f"- {path}")

    if args.and_generate:
        generate_args = argparse.Namespace(
            date=args.date,
            source_dir=str(out_dir),
            out_dir=None,
            markdown_only=args.markdown_only,
        )
        return generate_command(generate_args)

    return 0 if not log.errors else 1


def collect_one_command(args: argparse.Namespace) -> int:
    import logging as _logging

    brief_date = date.fromisoformat(args.date)
    accounts_path = Path(args.accounts) if args.accounts else default_accounts_path()
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "sources" / args.date
    settings = get_settings()

    if args.verbose:
        _logging.basicConfig(level=_logging.DEBUG, format="%(name)s %(message)s")

    if not accounts_path.exists():
        print(f"Account config not found: {accounts_path}", file=sys.stderr)
        return 2

    written, log = collect_single_account(
        name=args.name,
        accounts_path=accounts_path,
        out_dir=out_dir,
        brief_date=brief_date,
        settings=settings,
        limit=args.limit,
        include_undated=args.include_undated,
    )
    print_collection_log(log)

    print(f"\nWritten files: {len(written)}")
    for path in written:
        print(f"  - {path}")

    return 0 if not log.errors else 1


def generate_command(args: argparse.Namespace) -> int:
    brief_date = date.fromisoformat(args.date)
    source_dir = Path(args.source_dir) if args.source_dir else ROOT / "sources" / args.date
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "reports" / args.date

    settings = get_settings()
    articles = load_articles(source_dir)
    if not articles:
        print(f"No Markdown or JSON articles found in {source_dir}", file=sys.stderr)
        return 2

    result = generate_brief(articles, brief_date, settings)
    out_dir.mkdir(parents=True, exist_ok=True)

    md_path = out_dir / "daily-brief.md"
    md_path.write_text(result.markdown, encoding="utf-8")

    if not args.markdown_only:
        html_path = out_dir / "daily-brief.html"
        html_path.write_text(wrap_html(result.markdown, "每日投资简报"), encoding="utf-8")
    else:
        html_path = None

    print(f"Generated Markdown: {md_path}")
    if html_path:
        print(f"Generated HTML: {html_path}")
    print(f"Mode: {'LLM' if result.used_llm else 'fallback'} ({result.model})")
    return 0


def default_accounts_path() -> Path:
    local_path = ROOT / "config" / "accounts.json"
    if local_path.exists():
        return local_path
    return ROOT / "config" / "accounts.example.json"


def print_collection_log(log) -> None:
    for message in log.info:
        print(f"[info] {message}")
    for message in log.warnings:
        print(f"[warn] {message}")
    for message in log.errors:
        print(f"[error] {message}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
