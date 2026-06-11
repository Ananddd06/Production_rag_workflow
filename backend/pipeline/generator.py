"""
LLM generation module using HuggingFace Inference API.

Constructs grounded prompts from assembled context, enforces rate
limiting, and parses citation references from the model output.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import List, Optional

from huggingface_hub import InferenceClient

from config import settings

logger = logging.getLogger(__name__)

# ── system prompt template ─────────────────────────────────────────────
_SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer the question based ONLY on the "
    "provided context. Always cite your sources using [1], [2] etc. "
    "If the context doesn't contain enough information, say so."
)


class _TokenBucket:
    """Simple thread‑safe token‑bucket rate limiter.

    Allows at most *rpm* requests per 60‑second window.
    """

    def __init__(self, rpm: int) -> None:
        self._interval = 60.0 / max(rpm, 1)  # seconds between requests
        self._last: float = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block until the next request slot is available."""
        with self._lock:
            now = time.monotonic()
            wait = self._last + self._interval - now
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()


class LLMGenerator:
    """Generate grounded answers via HuggingFace Inference API.

    Parameters
    ----------
    model_id : str, optional
        Default model for generation.  Falls back to
        ``settings.HF_MODEL_ID``.
    """

    def __init__(self, model_id: str | None = None) -> None:
        self._model_id = model_id or settings.HF_MODEL_ID
        self._client = InferenceClient(base_url="https://router.huggingface.co/v1", token=settings.HF_API_TOKEN)
        self._limiter = _TokenBucket(settings.RATE_LIMIT_RPM)
        logger.info("LLMGenerator initialised  model=%s", self._model_id)

    # ── public API ─────────────────────────────────────────────────────

    def generate(
        self,
        query: str,
        context: dict,
        model_override: Optional[str] = None,
    ) -> dict:
        """Generate a grounded answer for *query* given *context*.

        Parameters
        ----------
        query : str
            The user's question.
        context : dict
            Output of ``ContextAssembler.assemble()`` — must contain
            ``context`` (str) and ``citations`` (list).
        model_override : str, optional
            Use a specific model for this call.

        Returns
        -------
        dict
            ``answer``, ``citations_used``, ``model``, ``tokens_used``,
            ``generation_time_ms``.
        """
        model = model_override or self._model_id
        context_text = context.get("context", "")
        citations = context.get("citations", [])

        # Build messages
        messages = self._build_messages(query, context_text)

        # Rate‑limit
        self._limiter.acquire()

        # Call the model using universal router to bypass ISP DNS blocks
        start = time.perf_counter()
        try:
            response = self._client.chat_completion(
                model=model,
                messages=messages,
                max_tokens=1024,
                temperature=0.3,
            )
            answer = response.choices[0].message.content.strip()
            tokens_used = getattr(response.usage, "total_tokens", 0) if response.usage else 0
        except Exception:
            logger.exception("generation failed for model=%s", model)
            raise

        elapsed_ms = (time.perf_counter() - start) * 1000

        # Extract cited reference numbers from the answer
        citations_used = self._extract_citations(answer, len(citations))

        logger.info(
            "generated answer  model=%s  tokens=%d  time=%.0fms  "
            "citations=%s  query=%r",
            model,
            tokens_used,
            elapsed_ms,
            citations_used,
            query[:80],
        )

        return {
            "answer": answer,
            "citations_used": citations_used,
            "model": model,
            "tokens_used": tokens_used,
            "generation_time_ms": round(elapsed_ms, 2),
        }

    # ── prompt construction ────────────────────────────────────────────

    @staticmethod
    def _build_messages(query: str, context_text: str) -> list[dict]:
        """Build the chat messages list."""
        user_content = (
            f"Context:\n{context_text}\n\n"
            f"Question: {query}"
        )
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    # ── citation extraction ────────────────────────────────────────────

    @staticmethod
    def _extract_citations(text: str, max_id: int) -> List[int]:
        """Parse ``[n]`` markers from *text* and return valid IDs."""
        found = re.findall(r"\[(\d+)]", text)
        ids: list[int] = []
        seen: set[int] = set()
        for raw in found:
            n = int(raw)
            if 1 <= n <= max_id and n not in seen:
                ids.append(n)
                seen.add(n)
        return sorted(ids)
