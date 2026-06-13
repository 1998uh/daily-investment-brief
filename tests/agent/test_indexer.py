from __future__ import annotations

import pytest
from pathlib import Path
from agent.indexer import ArticleIndexer, SearchResult


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def indexer(tmp_path):
    return ArticleIndexer(
        chroma_path=tmp_path / "chroma",
        use_local_embeddings=True,
    )


def test_build_index_finds_articles(indexer):
    indexer.build(
        sources_root=FIXTURES,
        reports_root=FIXTURES / "reports",
    )
    stats = indexer.stats()
    assert stats["total_docs"] > 0


def test_search_returns_results(indexer):
    indexer.build(sources_root=FIXTURES, reports_root=FIXTURES / "reports")
    results = indexer.search("美光 HBM 存储", top_k=3)
    assert len(results) >= 1
    assert isinstance(results[0], SearchResult)
    assert results[0].content
    assert results[0].metadata.get("author") is not None


def test_search_with_author_filter(indexer):
    indexer.build(sources_root=FIXTURES, reports_root=FIXTURES / "reports")
    results = indexer.search("美光", top_k=5, author="测试作者")
    assert len(results) >= 1
    assert all(r.metadata["author"] == "测试作者" for r in results)


def test_incremental_update(indexer, tmp_path):
    indexer.build(sources_root=FIXTURES, reports_root=FIXTURES / "reports")
    before = indexer.stats()["total_docs"]

    new_dir = tmp_path / "sources" / "2026-06-13"
    new_dir.mkdir(parents=True)
    (new_dir / "xueqiu-new-article-12345678.md").write_text(
        "---\nsource: 雪球\nauthor: 新作者\ntitle: 新文章\nurl: https://x.com/2\npublished_at: 2026-06-13 09:00:00\ncollected_at: 2026-06-13 10:00:00\n---\n\nNVDA 最新动态。",
        encoding="utf-8",
    )

    indexer.update(sources_root=tmp_path / "sources", date_str="2026-06-13")
    after = indexer.stats()["total_docs"]
    assert after > before
