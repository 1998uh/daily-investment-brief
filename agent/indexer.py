from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

# chromadb / langchain are lazy-imported inside the class so that
# huggingface_hub.constants is initialised AFTER load_env() sets HF_ENDPOINT.
from pipeline.ingest import load_markdown


COLLECTION_NAME = "investment_docs"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


@dataclass
class SearchResult:
    content: str
    metadata: dict[str, Any]
    score: float


def _doc_id(path: Path) -> str:
    return hashlib.sha1(str(path).encode()).hexdigest()


def _get_embedder(embedding_model: str, use_local: bool, api_key: str = "", base_url: str = ""):
    if use_local:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        return SentenceTransformerEmbeddingFunction(model_name=embedding_model)
    from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
    return OpenAIEmbeddingFunction(
        api_key=api_key,
        model_name=embedding_model,
        api_base=base_url or None,
    )


class ArticleIndexer:
    def __init__(
        self,
        chroma_path: Path,
        embedding_model: str = "text-embedding-3-small",
        use_local_embeddings: bool = False,
        llm_api_key: str = "",
        llm_base_url: str = "",
    ):
        chroma_path = Path(chroma_path)
        chroma_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(chroma_path))
        if use_local_embeddings:
            local_model = embedding_model if embedding_model != "text-embedding-3-small" else "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            ef = _get_embedder(local_model, use_local=True)
        else:
            ef = _get_embedder(embedding_model, use_local=False, api_key=llm_api_key, base_url=llm_base_url)
        self._col = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", "。", "，", " ", ""],
        )

    def _index_file(self, path: Path, doc_type: str) -> None:
        try:
            article = load_markdown(path)
            if not article.content.strip():
                return

            chunks = self._splitter.split_text(article.content)
            ids, docs, metas = [], [], []
            base_id = _doc_id(path)
            for i, chunk in enumerate(chunks):
                ids.append(f"{base_id}_{i}")
                docs.append(chunk)
                metas.append({
                    "doc_type": doc_type,
                    "source": article.source or "",
                    "author": article.author or "",
                    "title": article.title or "",
                    "url": article.url or "",
                    "date": article.published_at[:10] if article.published_at else "",
                    "file_path": str(path),
                })
            if ids:
                self._col.upsert(ids=ids, documents=docs, metadatas=metas)
        except Exception as exc:
            _log.warning("Skipping %s: %s", path, exc)

    def build(self, sources_root: Path, reports_root: Path) -> None:
        sources_root = Path(sources_root)
        reports_root = Path(reports_root)
        for path in sorted(sources_root.rglob("*.md")):
            self._index_file(path, "article")
        for path in sorted(reports_root.rglob("daily-brief*.md")):
            self._index_file(path, "report")

    def update(self, sources_root: Path, date_str: str) -> None:
        sources_root = Path(sources_root)
        date_dir = sources_root / date_str
        if date_dir.exists():
            for path in sorted(date_dir.glob("*.md")):
                self._index_file(path, "article")

    def search(
        self,
        query: str,
        top_k: int = 5,
        author: str | None = None,
        source: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        doc_type: str | None = None,
    ) -> list[SearchResult]:
        conditions = []
        if author:
            conditions.append({"author": {"$eq": author}})
        if source:
            conditions.append({"source": {"$eq": source}})
        if doc_type:
            conditions.append({"doc_type": {"$eq": doc_type}})
        if date_from:
            conditions.append({"date": {"$gte": date_from}})
        if date_to:
            conditions.append({"date": {"$lte": date_to}})

        where: dict = {}
        if len(conditions) == 1:
            where = conditions[0]
        elif len(conditions) > 1:
            where = {"$and": conditions}

        actual_top_k = min(top_k, self._col.count())
        if actual_top_k == 0:
            return []

        kwargs: dict = {"query_texts": [query], "n_results": actual_top_k}
        if where:
            kwargs["where"] = where

        try:
            results = self._col.query(**kwargs)
        except Exception:
            return []

        out = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            out.append(SearchResult(content=doc, metadata=meta, score=1 - dist))
        return out

    def stats(self) -> dict:
        return {"total_docs": self._col.count()}


def make_indexer(settings) -> "ArticleIndexer":
    """Construct ArticleIndexer from AgentSettings, respecting embedding config."""
    return ArticleIndexer(
        chroma_path=settings.chroma_path,
        embedding_model=settings.embedding_model,
        use_local_embeddings=settings.use_local_embeddings,
        llm_api_key=settings.llm_api_key,
        llm_base_url=settings.llm_base_url,
    )
