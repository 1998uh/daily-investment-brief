"""python -m agent [--rebuild-index] [--update-index DATE] [--port 8080]"""
from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Investment Agent backend")
    parser.add_argument("--rebuild-index", action="store_true",
                        help="Rebuild ChromaDB index from scratch")
    parser.add_argument("--update-index", metavar="DATE",
                        help="Incremental index update for DATE (YYYY-MM-DD)")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    from agent.config import get_agent_settings
    cfg = get_agent_settings()

    if args.rebuild_index:
        print("[info] Building ChromaDB index from scratch...")
        from agent.indexer import make_indexer
        indexer = make_indexer(cfg)
        indexer.build(sources_root=cfg.sources_root, reports_root=cfg.reports_root)
        stats = indexer.stats()
        print(f"[info] Index built: {stats['total_docs']} chunks")
        sys.exit(0)

    if args.update_index:
        print(f"[info] Updating ChromaDB index for {args.update_index}...")
        from agent.indexer import make_indexer
        indexer = make_indexer(cfg)
        indexer.update(sources_root=cfg.sources_root, date_str=args.update_index)
        print(f"[info] Index updated for {args.update_index}")
        sys.exit(0)

    import uvicorn
    uvicorn.run("agent.main:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
