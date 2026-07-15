from __future__ import annotations

import argparse

from pipeline.workstation import create_weekly_review, default_current_week


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a weekly investment review template.")
    parser.add_argument(
        "--week",
        default=default_current_week(),
        help="ISO week, e.g. 2026-W29. Defaults to current week.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing review.")
    args = parser.parse_args()

    result = create_weekly_review(args.week, overwrite=args.overwrite)
    action = "Created" if result.created else "Exists"
    print(f"{action}: {result.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
