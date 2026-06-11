"""
Query preprocessor for the RAG pipeline.

Handles query cleaning, expansion, and complexity classification
before retrieval.  Entirely local — no external API calls.
"""

from __future__ import annotations

import re
import logging
from typing import List

logger = logging.getLogger(__name__)

# ── Question‑word sets used for complexity heuristics ──────────────────
_QUESTION_WORDS = frozenset({
    "who", "what", "when", "where", "why", "how",
    "which", "whom", "whose", "is", "are", "was",
    "were", "do", "does", "did", "can", "could",
    "should", "would", "will", "shall",
})

# ── Simple hand‑rolled synonym map (fallback when NLTK is absent) ─────
_BASIC_SYNONYMS: dict[str, list[str]] = {
    "fast": ["quick", "rapid", "speedy"],
    "quick": ["fast", "rapid", "speedy"],
    "big": ["large", "huge", "massive"],
    "large": ["big", "huge", "massive"],
    "small": ["tiny", "little", "compact"],
    "good": ["great", "excellent", "fine"],
    "bad": ["poor", "terrible", "awful"],
    "help": ["assist", "aid", "support"],
    "show": ["display", "present", "demonstrate"],
    "find": ["search", "locate", "discover"],
    "make": ["create", "build", "construct"],
    "use": ["utilize", "employ", "apply"],
    "start": ["begin", "initiate", "launch"],
    "stop": ["end", "halt", "cease"],
    "error": ["bug", "issue", "problem", "fault"],
    "fix": ["repair", "resolve", "patch"],
    "improve": ["enhance", "optimize", "boost"],
    "remove": ["delete", "eliminate", "discard"],
    "change": ["modify", "alter", "update"],
    "get": ["retrieve", "obtain", "fetch"],
}

# ── Multi‑part connectors (signals a *complex* query) ─────────────────
_MULTI_PART_MARKERS = re.compile(
    r"\b(and also|as well as|in addition|furthermore|moreover|additionally"
    r"|compare|versus|vs\.?|difference between|pros and cons)\b",
    re.IGNORECASE,
)


def _wordnet_synonyms(word: str) -> list[str]:
    """Return WordNet synonyms for *word*, or an empty list on failure."""
    try:
        from nltk.corpus import wordnet  # type: ignore[import-untyped]

        synsets = wordnet.synsets(word)
        synonyms: set[str] = set()
        for syn in synsets[:3]:  # cap to avoid explosion
            for lemma in syn.lemmas()[:4]:
                name = lemma.name().replace("_", " ").lower()
                if name != word:
                    synonyms.add(name)
        return sorted(synonyms)[:5]
    except Exception:
        return []


class QueryPreprocessor:
    """Light‑weight, zero‑dependency query preprocessor.

    Usage::

        qp = QueryPreprocessor()
        result = qp.preprocess("What is the fastest sorting algorithm?")
        # result["processed"]       → cleaned text
        # result["expanded_terms"]  → synonym expansions
        # result["complexity"]      → 'simple' | 'medium' | 'complex'
    """

    # ── public API ─────────────────────────────────────────────────────
    def preprocess(self, query: str) -> dict:
        """Clean, expand, and classify *query*.

        Returns
        -------
        dict
            Keys: ``original``, ``processed``, ``expanded_terms``,
            ``complexity``.
        """
        original = query
        processed = self._clean(query)
        expanded_terms = self._expand(processed)
        complexity = self._classify_complexity(processed)

        logger.debug(
            "preprocessed query  original=%r  processed=%r  "
            "expanded=%s  complexity=%s",
            original,
            processed,
            expanded_terms,
            complexity,
        )

        return {
            "original": original,
            "processed": processed,
            "expanded_terms": expanded_terms,
            "complexity": complexity,
        }

    # ── internals ──────────────────────────────────────────────────────
    @staticmethod
    def _clean(text: str) -> str:
        """Strip, lowercase, collapse whitespace, remove special chars."""
        text = text.strip().lower()
        # Keep alphanumerics, basic punctuation, and whitespace
        text = re.sub(r"[^\w\s?.!,'-]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _expand(text: str) -> List[str]:
        """Generate synonym expansions for content words."""
        words = text.split()
        expansions: list[str] = []
        seen: set[str] = set(words)

        for word in words:
            if len(word) < 3 or word in _QUESTION_WORDS:
                continue

            # Try WordNet first, fall back to hand‑rolled map
            syns = _wordnet_synonyms(word)
            if not syns:
                syns = _BASIC_SYNONYMS.get(word, [])

            for s in syns:
                if s not in seen:
                    seen.add(s)
                    expansions.append(s)

        return expansions

    @staticmethod
    def _classify_complexity(text: str) -> str:
        """Heuristic complexity bucket: simple / medium / complex."""
        words = text.split()
        word_count = len(words)

        has_question_word = any(w in _QUESTION_WORDS for w in words)
        has_multi_part = bool(_MULTI_PART_MARKERS.search(text))

        if has_multi_part or word_count > 20:
            return "complex"
        if has_question_word:
            return "medium"
        if word_count < 8:
            return "simple"
        return "medium"
