"""
Context assembler: deduplicates, merges, and formats retrieved chunks
into a citation‑mapped context string ready for the LLM.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from config import settings

logger = logging.getLogger(__name__)

# ── constants ──────────────────────────────────────────────────────────
_TOKEN_FACTOR = 1.3  # rough word→token multiplier for English text


class ContextAssembler:
    """Build a prompt‑ready context from a set of ranked documents.

    Responsibilities:
    * **De‑duplication** – drop documents whose text overlaps ≥ 85 %
      with an already‑selected document.
    * **Adjacent‑chunk merging** – merge sequential chunks from the
      same source file into a single, larger passage.
    * **Citation mapping** – assign ``[1]``, ``[2]``, … markers to each
      unique source for inline referencing.
    * **Token budgeting** – estimate token usage and truncate to
      *max_tokens*.
    """

    # ── public API ─────────────────────────────────────────────────────

    def assemble(
        self,
        query: str,
        documents: List[dict],
        max_tokens: int = 3000,
    ) -> dict:
        """Assemble the final context payload.

        Parameters
        ----------
        query : str
            The original user query (used for logging / metadata).
        documents : list[dict]
            Ranked list of document dicts, each with at least ``"text"``
            and ``"metadata"`` keys.
        max_tokens : int
            Approximate token budget for the context block.

        Returns
        -------
        dict
            ``context`` – formatted string,
            ``citations`` – list of citation dicts,
            ``num_chunks`` – count of chunks kept,
            ``total_tokens`` – estimated token count.
        """
        if not documents:
            return self._empty_result()

        # 1. De-duplicate near‑identical chunks
        deduped = self._deduplicate(documents)

        # 2. Merge adjacent chunks from the same source
        merged = self._merge_adjacent(deduped)

        # 3. Token‑budget truncation
        truncated = self._truncate(merged, max_tokens)

        # 4. Build citation map & formatted context
        context_str, citations = self._build_context(truncated)

        total_tokens = self._estimate_tokens(context_str)

        logger.info(
            "assembled context  chunks=%d→%d→%d  tokens≈%d  query=%r",
            len(documents),
            len(deduped),
            len(truncated),
            total_tokens,
            query[:80],
        )

        return {
            "context": context_str,
            "citations": citations,
            "num_chunks": len(truncated),
            "total_tokens": total_tokens,
        }

    # ── de‑duplication ─────────────────────────────────────────────────

    @staticmethod
    def _deduplicate(docs: list[dict], threshold: float = 0.85) -> list[dict]:
        """Remove documents with ≥ *threshold* word‑level overlap."""
        kept: list[dict] = []
        kept_word_sets: list[set[str]] = []

        for doc in docs:
            words = set(doc.get("text", "").lower().split())
            if not words:
                continue

            is_dup = False
            for existing_words in kept_word_sets:
                overlap = len(words & existing_words)
                smaller = min(len(words), len(existing_words)) or 1
                if overlap / smaller >= threshold:
                    is_dup = True
                    break

            if not is_dup:
                kept.append(doc)
                kept_word_sets.append(words)

        return kept

    # ── adjacent‑chunk merging ─────────────────────────────────────────

    @staticmethod
    def _merge_adjacent(docs: list[dict]) -> list[dict]:
        """Merge chunks that come from the same source and are sequential.

        Adjacency is detected via ``metadata.chunk_index`` (integer) and
        ``metadata.source`` (string).  If those keys are absent the chunk
        is passed through unchanged.
        """
        if not docs:
            return docs

        merged: list[dict] = []
        current: dict | None = None

        for doc in docs:
            meta = doc.get("metadata", {})
            src = meta.get("source", "")
            idx = meta.get("chunk_index")

            if (
                current is not None
                and idx is not None
                and src == current["metadata"].get("source", "")
                and idx == current["metadata"].get("chunk_index", -999) + 1
            ):
                # Merge into current
                current["text"] = current["text"] + "\n" + doc["text"]
                current["metadata"]["chunk_index"] = idx
            else:
                if current is not None:
                    merged.append(current)
                current = {
                    "id": doc.get("id", ""),
                    "text": doc.get("text", ""),
                    "metadata": dict(meta),
                    "score": doc.get("score", 0.0),
                }

        if current is not None:
            merged.append(current)

        return merged

    # ── token budgeting ────────────────────────────────────────────────

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Quick token estimate: words × 1.3."""
        return int(len(text.split()) * _TOKEN_FACTOR)

    def _truncate(self, docs: list[dict], max_tokens: int) -> list[dict]:
        """Keep as many docs as fit within *max_tokens*."""
        kept: list[dict] = []
        running = 0
        for doc in docs:
            doc_tokens = self._estimate_tokens(doc.get("text", ""))
            if running + doc_tokens > max_tokens and kept:
                break
            kept.append(doc)
            running += doc_tokens
        return kept

    # ── context formatting ─────────────────────────────────────────────

    @staticmethod
    def _build_context(docs: list[dict]) -> tuple[str, list[dict]]:
        """Format docs into a numbered context block with citation info."""
        lines: list[str] = []
        citations: list[dict] = []

        for idx, doc in enumerate(docs, start=1):
            meta = doc.get("metadata", {})
            title = meta.get("title", meta.get("source", f"Source {idx}"))
            text = doc.get("text", "").strip()
            preview = text[:200] + ("…" if len(text) > 200 else "")

            lines.append(f"[{idx}] Source: {title}\n{text}\n")
            citations.append(
                {
                    "id": idx,
                    "source": meta.get("source", ""),
                    "title": title,
                    "text_preview": preview,
                }
            )

        context_str = "\n".join(lines)
        return context_str, citations

    @staticmethod
    def _empty_result() -> dict:
        return {
            "context": "",
            "citations": [],
            "num_chunks": 0,
            "total_tokens": 0,
        }
