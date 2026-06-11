"""
Cross‑encoder reranker for second‑stage relevance scoring.

Uses the ``cross-encoder/ms-marco-MiniLM-L-6-v2`` model from
sentence-transformers to score (query, document) pairs and select the
most relevant candidates.
"""

from __future__ import annotations

import logging
import time
from typing import List

from sentence_transformers import CrossEncoder

from config import settings

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """Second‑stage reranker built on a cross‑encoder model.

    The model is loaded once on construction and kept in memory for
    subsequent calls.

    Parameters
    ----------
    model_name : str, optional
        HuggingFace model identifier.  Defaults to the value in
        ``settings.HF_RERANKER_MODEL``.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or settings.HF_RERANKER_MODEL
        logger.info("loading cross‑encoder model %s …", self._model_name)
        self._model = CrossEncoder(self._model_name)
        logger.info("cross‑encoder model loaded")

    # ── public API ─────────────────────────────────────────────────────

    def rerank(
        self,
        query: str,
        documents: List[dict],
        top_k: int = 5,
    ) -> List[dict]:
        """Score and rerank *documents* against *query*.

        Parameters
        ----------
        query : str
            The user's query string.
        documents : list[dict]
            Each dict must contain at least a ``"text"`` key.
        top_k : int
            Number of top‑scoring documents to return.

        Returns
        -------
        list[dict]
            The *top_k* documents sorted by descending rerank score,
            each augmented with a ``rerank_score`` field (0–1).
        """
        if not documents:
            return []

        start = time.perf_counter()

        # Build sentence pairs for the cross‑encoder
        pairs = [(query, doc["text"]) for doc in documents]

        # Raw scores from the model (can be negative)
        raw_scores: list[float] = self._model.predict(pairs).tolist()

        # Normalise to [0, 1]
        normalised = self._normalise(raw_scores)

        # Attach scores to documents
        scored_docs: list[dict] = []
        for doc, score in zip(documents, normalised):
            enriched = {**doc, "rerank_score": round(score, 6)}
            scored_docs.append(enriched)

        # Sort descending and truncate
        scored_docs.sort(key=lambda d: d["rerank_score"], reverse=True)
        result = scored_docs[:top_k]

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "reranked %d → %d docs in %.1f ms  top_score=%.4f",
            len(documents),
            len(result),
            elapsed_ms,
            result[0]["rerank_score"] if result else 0.0,
        )
        return result

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _normalise(scores: list[float]) -> list[float]:
        """Min‑max normalise *scores* to the 0–1 range."""
        lo = min(scores)
        hi = max(scores)
        rng = hi - lo if hi != lo else 1.0
        return [(s - lo) / rng for s in scores]
