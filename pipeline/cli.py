from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path
import sys

from .config import ROOT, get_settings
from .cancel import PipelineCancelled, cancellation_context, raise_if_cancelled
from .collectors.runner import collect_to_sources, collect_single_account
from .generator import generate_brief, synthesize_from_batches, build_direct_prompt
from .html import wrap_html
from .ingest import load_articles


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        with cancellation_context():
            raise_if_cancelled()
            if args.command == "generate":
                return generate_command(args)
            if args.command == "collect":
                return collect_command(args)
            if args.command == "collect-one":
                return collect_one_command(args)

            parser.print_help()
            return 1
    except (KeyboardInterrupt, PipelineCancelled):
        print("\n[info] Interrupted, exiting...", flush=True)
        if argv is None:
            try:
                from .collectors.browser import close_browser
                close_browser()
            except Exception:
                pass
            sys.stdout.flush()
            sys.stderr.flush()
            import os
            os._exit(130)
        return 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a daily investment brief.")
    subparsers = parser.add_subparsers(dest="command")

    collect = subparsers.add_parser("collect", help="Collect source articles into Markdown files.")
    date_group = collect.add_mutually_exclusive_group(required=True)
    date_group.add_argument("--date", help="Brief date, e.g. 2026-06-07.")
    date_group.add_argument(
        "--start-date",
        help="Start date for range collection, e.g. 2026-06-10. Must be used with --end-date.",
    )
    collect.add_argument(
        "--end-date",
        help="End date for range collection (inclusive), e.g. 2026-06-17. Must be used with --start-date.",
    )
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
    one_date_group = collect_one.add_mutually_exclusive_group(required=True)
    one_date_group.add_argument("--date", help="Brief date, e.g. 2026-06-09.")
    one_date_group.add_argument(
        "--start-date",
        help="Start date for range collection, e.g. 2026-06-10. Must be used with --end-date.",
    )
    collect_one.add_argument(
        "--end-date",
        help="End date for range collection (inclusive), e.g. 2026-06-17. Must be used with --start-date.",
    )
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
        "--accounts",
        help="Account config JSON for coverage stats. Defaults to config/accounts.json.",
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
    generate.add_argument(
        "--batches-only",
        action="store_true",
        help="Only run batch summarization and save batch-summaries.json. Skip final synthesis.",
    )
    generate.add_argument(
        "--from-batches",
        action="store_true",
        help="Skip batch summarization. Read batch-summaries.json from out-dir and synthesize directly.",
    )
    generate.add_argument(
        "--no-batches",
        action="store_true",
        help="Skip all LLM calls. Pack raw articles into a single prompt file for external models.",
    )
    return parser


def collect_command(args: argparse.Namespace) -> int:
    # --start-date / --end-date 范围采集
    if args.start_date:
        if not args.end_date:
            print("--start-date requires --end-date", file=sys.stderr)
            return 2
        return _collect_date_range(args)

    # 单日采集
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
            accounts=str(accounts_path),
            markdown_only=args.markdown_only,
        )
        return generate_command(generate_args)

    return 0 if not log.errors else 1


def _collect_date_range(args: argparse.Namespace) -> int:
    """按日期范围逐日采集。"""
    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    if start > end:
        print(f"--start-date ({start}) must be <= --end-date ({end})", file=sys.stderr)
        return 2

    accounts_path = Path(args.accounts) if args.accounts else default_accounts_path()
    settings = get_settings()

    if not accounts_path.exists():
        print(f"Account config not found: {accounts_path}", file=sys.stderr)
        return 2

    total_days = (end - start).days + 1
    total_written = 0
    has_errors = False

    print(f"\n{'='*60}")
    print(f"范围采集: {start} ~ {end} ({total_days} 天)")
    print(f"{'='*60}")

    current = start
    while current <= end:
        date_str = current.isoformat()
        day_out_dir = Path(args.out_dir) if args.out_dir else ROOT / "sources" / date_str

        print(f"\n{'─'*40}")
        print(f"📅 {date_str} ({(current - start).days + 1}/{total_days})")
        print(f"{'─'*40}")

        try:
            written, log = collect_to_sources(
                accounts_path=accounts_path,
                out_dir=day_out_dir,
                brief_date=current,
                settings=settings,
                limit=args.limit,
                include_undated=args.include_undated,
                dry_run=args.dry_run,
                parallel=not args.sequential,
            )
            print_collection_log(log)

            if not args.dry_run:
                print(f"Written files: {len(written)}")
                total_written += len(written)

            if log.errors:
                has_errors = True
        except KeyboardInterrupt:
            print(f"\n[info] {date_str} 采集中被中断，正在退出…", flush=True)
            raise
        except Exception as exc:
            print(f"[error] {date_str}: {exc}", file=sys.stderr)
            has_errors = True

        current += timedelta(days=1)

    if not args.dry_run:
        print(f"\n{'='*60}")
        print(f"范围采集完成: {total_days} 天, 共写入 {total_written} 个文件")
        print(f"{'='*60}")

    if args.and_generate:
        print("\n[info] --and-generate 在范围采集模式下不生效，请逐日手动 generate。")

    return 1 if has_errors else 0


def collect_one_command(args: argparse.Namespace) -> int:
    import logging as _logging

    if args.verbose:
        _logging.basicConfig(level=_logging.DEBUG, format="%(name)s %(message)s")

    # --start-date / --end-date 范围采集
    if args.start_date:
        if not args.end_date:
            print("--start-date requires --end-date", file=sys.stderr)
            return 2
        return _collect_one_date_range(args)

    # 单日采集
    brief_date = date.fromisoformat(args.date)
    accounts_path = Path(args.accounts) if args.accounts else default_accounts_path()
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "sources" / args.date
    settings = get_settings()

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


def _collect_one_date_range(args: argparse.Namespace) -> int:
    """按日期范围逐日采集单个账号。"""
    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    if start > end:
        print(f"--start-date ({start}) must be <= --end-date ({end})", file=sys.stderr)
        return 2

    accounts_path = Path(args.accounts) if args.accounts else default_accounts_path()
    settings = get_settings()

    if not accounts_path.exists():
        print(f"Account config not found: {accounts_path}", file=sys.stderr)
        return 2

    total_days = (end - start).days + 1
    total_written = 0
    has_errors = False

    print(f"\n{'='*60}")
    print(f"单账号范围采集: {args.name} | {start} ~ {end} ({total_days} 天)")
    print(f"{'='*60}")

    current = start
    while current <= end:
        date_str = current.isoformat()
        day_out_dir = Path(args.out_dir) if args.out_dir else ROOT / "sources" / date_str

        print(f"\n{'─'*40}")
        print(f"📅 {date_str} ({(current - start).days + 1}/{total_days})")
        print(f"{'─'*40}")

        try:
            written, log = collect_single_account(
                name=args.name,
                accounts_path=accounts_path,
                out_dir=day_out_dir,
                brief_date=current,
                settings=settings,
                limit=args.limit,
                include_undated=args.include_undated,
            )
            print_collection_log(log)
            print(f"Written files: {len(written)}")
            total_written += len(written)

            if log.errors:
                has_errors = True
        except KeyboardInterrupt:
            print(f"\n[info] {date_str} 采集中被中断，正在退出…", flush=True)
            raise
        except Exception as exc:
            print(f"[error] {date_str}: {exc}", file=sys.stderr)
            has_errors = True

        current += timedelta(days=1)

    print(f"\n{'='*60}")
    print(f"范围采集完成: {args.name} | {total_days} 天, 共写入 {total_written} 个文件")
    print(f"{'='*60}")

    return 1 if has_errors else 0


def generate_command(args: argparse.Namespace) -> int:
    import json as _json

    brief_date = date.fromisoformat(args.date)
    source_dir = Path(args.source_dir) if args.source_dir else ROOT / "sources" / args.date
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "reports" / args.date

    accounts_arg = getattr(args, "accounts", None)
    accounts_path = Path(accounts_arg) if accounts_arg else default_accounts_path()
    if not accounts_path.exists():
        accounts_path = None

    settings = get_settings()
    batches_only = getattr(args, "batches_only", False)
    from_batches = getattr(args, "from_batches", False)
    no_batches = getattr(args, "no_batches", False)

    # ── 路径 D：--no-batches，打包原文 prompt，不调任何 LLM ─────────────────
    if no_batches:
        articles = load_articles(source_dir)
        if not articles:
            print(f"No articles found in {source_dir}", file=sys.stderr)
            return 2

        from .ingest import expected_authors_from_accounts, build_coverage
        expected = expected_authors_from_accounts(accounts_path) if accounts_path else None
        coverage = build_coverage(articles, expected)

        prompt = build_direct_prompt(articles, coverage, brief_date, settings)
        out_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = out_dir / "prompt-for-external.md"
        prompt_path.write_text(prompt, encoding="utf-8")

        char_count = len(prompt)
        print(f"Prompt saved: {prompt_path}")
        print(f"Size: {char_count:,} chars (~{char_count // 4:,} tokens estimated)")
        print(f"Articles: {len(articles)} | System prompt: 你是中文每日投资简报主编。")
        print(f"Next: paste prompt-for-external.md into Claude / GPT / Gemini to generate the brief.")
        return 0

    # ── 路径 A：--from-batches，跳过提炼，直接从落盘 JSON 合成 ──────────────
    if from_batches:
        batches_path = out_dir / "batch-summaries.json"
        if not batches_path.exists():
            print(f"batch-summaries.json not found: {batches_path}", file=sys.stderr)
            print("Run without --from-batches first to generate it.", file=sys.stderr)
            return 2

        summaries = _json.loads(batches_path.read_text(encoding="utf-8"))
        articles = load_articles(source_dir)
        from .ingest import expected_authors_from_accounts, build_coverage
        expected = expected_authors_from_accounts(accounts_path) if accounts_path else None
        coverage = build_coverage(articles, expected)

        print(f"[info] Synthesizing from {batches_path} ({len(summaries)} batches)", flush=True)
        markdown = synthesize_from_batches(summaries, coverage, brief_date, settings)
        result_model = settings.model
        used_llm = True

    # ── 路径 B：--batches-only，只提炼落盘，不合成 ──────────────────────────
    elif batches_only:
        articles = load_articles(source_dir)
        if not articles:
            print(f"No articles found in {source_dir}", file=sys.stderr)
            return 2

        from .generator import chunked_by_author, _summarize_batches, read_template
        import json as _json2

        batch_prompt = read_template("batch_summary_prompt.md")
        batches = chunked_by_author(articles, settings.batch_max_chars)
        summaries = _summarize_batches(batches, settings, batch_prompt)

        out_dir.mkdir(parents=True, exist_ok=True)
        batches_path = out_dir / "batch-summaries.json"
        batches_path.write_text(
            _json2.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Batch summaries saved: {batches_path}")
        print(f"Batches: {len(summaries)}")
        print(f"Next step: synthesize with any model using final_brief_prompt.md + batch-summaries.json")
        print(f"  or run: python -m pipeline.cli generate --date {args.date} --from-batches")
        return 0

    # ── 路径 C：默认全流程 ──────────────────────────────────────────────────
    else:
        articles = load_articles(source_dir)
        if not articles:
            print(f"No articles found in {source_dir}", file=sys.stderr)
            return 2

        result = generate_brief(
            articles, brief_date, settings,
            accounts_path=accounts_path,
            out_dir=out_dir,
        )
        markdown = result.markdown
        result_model = result.model
        used_llm = result.used_llm

    # ── 写出文件（路径 A / C 共用）────────────────────────────────────────
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "daily-brief.md"
    md_path.write_text(markdown, encoding="utf-8")

    markdown_only = getattr(args, "markdown_only", False)
    if not markdown_only:
        html_path = out_dir / "daily-brief.html"
        html_path.write_text(wrap_html(markdown, "每日投资简报"), encoding="utf-8")
    else:
        html_path = None

    print(f"Generated Markdown: {md_path}")
    if html_path:
        print(f"Generated HTML: {html_path}")
    print(f"Mode: {'LLM' if used_llm else 'fallback'} ({result_model})")
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
