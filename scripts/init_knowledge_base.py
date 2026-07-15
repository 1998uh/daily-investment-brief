from __future__ import annotations

from pipeline.workstation import ensure_knowledge_base


def main() -> int:
    for result in ensure_knowledge_base():
        action = "Created" if result.created else "Exists"
        print(f"{action}: {result.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
