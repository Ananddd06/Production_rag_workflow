"""
Hybrid retriever combining dense (semantic) and sparse (BM25) search.

Scores are fused with a configurable weighted average to improve recall
over either method alone.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional

from rank_bm25 import BM25Okapi

from config import settings

logger = logging.getLogger(__name__)


class HybridRetriever:
    """Hybrid (semantic + BM25) retriever with optional cache integration.

    Parameters
    ----------
    vector_store : VectorStore
        Provides ``.search()`` and ``.get_all_documents()`` methods.
    cache_manager : object, optional
        Any object exposing ``.get(key)`` and ``.set(key, value)`` methods.
    semantic_weight : float
        Weight for the dense (embedding) score.  BM25 weight is
        ``1 - semantic_weight``.
    """

    def __init__(
        self,
        vector_store: Any,
        cache_manager: Any | None = None,
        semantic_weight: float = 0.7,
    ) -> None:
        self._store = vector_store
        self._cache = cache_manager
        self._semantic_w = semantic_weight
        self._bm25_w = 1.0 - semantic_weight

        # BM25 index — lazily built on first retrieval
        self._bm25: BM25Okapi | None = None
        self._bm25_corpus: list[dict] = []

    # ── public API ─────────────────────────────────────────────────────

    def retrieve(
        self,
        query_data: dict,
        top_k: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[dict]:
        """Return the top‑*k* documents for a preprocessed query.

        Parameters
        ----------
        query_data : dict
            Output of ``QueryPreprocessor.preprocess()``.  Must contain at
            least ``"processed"`` (str).
        top_k : int
            Maximum number of results to return.
        filters : dict, optional
            Metadata filters forwarded to the vector store.

        Returns
        -------
        list[dict]
            Each dict contains ``id``, ``text``, ``metadata``, ``score``,
            and ``source``.
        """
        query_text: str = query_data.get("processed", query_data.get("original", ""))

        # ── cache check ────────────────────────────────────────────────
        cache_key = self._cache_key(query_text, top_k, filters)
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.info("cache HIT for query=%r", query_text[:80])
                return cached

        # ── semantic search ────────────────────────────────────────────
        semantic_results = self._store.search(
            query_text=query_text,
            top_k=top_k,
            filters=filters,
        )

        # ── BM25 search ───────────────────────────────────────────────
        bm25_results = self._bm25_search(query_text, top_k=top_k)

        # ── score fusion ───────────────────────────────────────────────
        merged = self._fuse_scores(semantic_results, bm25_results, top_k)

        # ── cache store ────────────────────────────────────────────────
        if self._cache is not None:
            self._cache.set(cache_key, merged)

        logger.info(
            "retrieved %d docs  semantic=%d  bm25=%d  query=%r",
            len(merged),
            len(semantic_results),
            len(bm25_results),
            query_text[:80],
        )
        return merged

    def rebuild_bm25_index(self) -> int:
        """Force a full rebuild of the BM25 index from the vector store.

        Returns the number of documents indexed.
        """
        return self._build_bm25_index()

    # ── BM25 helpers ───────────────────────────────────────────────────

    def _build_bm25_index(self) -> int:
        """(Re)build the BM25 index from all documents in the store."""
        docs = self._store.get_all_documents()
        if not docs:
            self._bm25 = None
            self._bm25_corpus = []
            return 0

        self._bm25_corpus = docs
        tokenized = [doc.get("text", "").lower().split() for doc in docs]
        self._bm25 = BM25Okapi(tokenized)
        logger.info("BM25 index built with %d documents", len(docs))
        return len(docs)

    def _bm25_search(self, query: str, top_k: int = 20) -> list[dict]:
        """Run a BM25 keyword search, building the index if needed."""
        if self._bm25 is None:
            self._build_bm25_index()
        if self._bm25 is None or not self._bm25_corpus:
            return []

        tokens = query.lower().split()
        scores = self._bm25.get_scores(tokens)

        # Pair each doc with its BM25 score and sort
        scored = sorted(
            zip(self._bm25_corpus, scores),
            key=lambda x: x[1],
            reverse=True,
        )[:top_k]

        results: list[dict] = []
        for doc, raw_score in scored:
            if raw_score <= 0:
                continue
            results.append(
                {
                    "id": doc.get("id", ""),
                    "text": doc.get("text", ""),
                    "metadata": doc.get("metadata", {}),
                    "score": float(raw_score),
                    "source": "bm25",
                }
            )
        return results

    # ── score fusion ───────────────────────────────────────────────────

    def _fuse_scores(
        self,
        semantic: list[dict],
        bm25: list[dict],
        top_k: int,
    ) -> list[dict]:
        """Weighted linear fusion of semantic and BM25 scores."""
        # Normalise each list independently to 0‑1
        semantic = self._normalise(semantic)
        bm25 = self._normalise(bm25)

        combined: dict[str, dict] = {}

        for doc in semantic:
            doc_id = doc["id"]
            combined[doc_id] = {
                **doc,
                "score": doc["score"] * self._semantic_w,
                "source": "semantic",
            }

        for doc in bm25:
            doc_id = doc["id"]
            if doc_id in combined:
                combined[doc_id]["score"] += doc["score"] * self._bm25_w
                combined[doc_id]["source"] = "hybrid"
            else:
                combined[doc_id] = {
                    **doc,
                    "score": doc["score"] * self._bm25_w,
                    "source": "bm25",
                }

        ranked = sorted(combined.values(), key=lambda d: d["score"], reverse=True)
        return ranked[:top_k]

    # ── utilities ──────────────────────────────────────────────────────

    @staticmethod
    def _normalise(docs: list[dict]) -> list[dict]:
        """Min‑max normalise scores to [0, 1]."""
        if not docs:
            return docs
        scores = [d["score"] for d in docs]
        lo, hi = min(scores), max(scores)
        rng = hi - lo if hi != lo else 1.0
        for d in docs:
            d["score"] = (d["score"] - lo) / rng
        return docs

    @staticmethod
    def _cache_key(
        query: str,
        top_k: int,
        filters: dict | None,
    ) -> str:
        """Deterministic cache key from query parameters."""
        raw = f"{query}||{top_k}||{filters}"
        return hashlib.sha256(raw.encode()).hexdigest()
