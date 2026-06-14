import os
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from agent.config import get_agent_settings
from agent.indexer import make_indexer

cfg = get_agent_settings()
idx = make_indexer(cfg)
print("total docs:", idx.stats()["total_docs"])
results = idx.search("A股市场行情", top_k=3)
for r in results:
    print("  [%s] score=%.3f  %s" % (r.metadata["author"], r.score, r.content[:60]))
