from __future__ import annotations

import argparse
from datetime import date

from pipeline.workstation import create_journal_entry


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a daily personal investment journal.")
    parser.add_argument("--date", required=True, help="Entry date, e.g. 2026-07-15.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing entry.")
    args = parser.parse_args()

    result = create_journal_entry(date.fromisoformat(args.date), overwrite=args.overwrite)
    action = "Created" if result.created else "Exists"
    print(f"{action}: {result.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
