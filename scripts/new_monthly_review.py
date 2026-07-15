from __future__ import annotations

import argparse

from pipeline.workstation import create_monthly_review, default_current_month


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a monthly investment review template.")
    parser.add_argument(
        "--month",
        default=default_current_month(),
        help="Month, e.g. 2026-07. Defaults to current month.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing review.")
    args = parser.parse_args()

    result = create_monthly_review(args.month, overwrite=args.overwrite)
    action = "Created" if result.created else "Exists"
    print(f"{action}: {result.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
