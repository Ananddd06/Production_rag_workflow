"""
ChromaDB‑backed vector store for document embeddings.

Uses the ``sentence-transformers/all-MiniLM-L6-v2`` embedding function
shipped with chromadb so that embedding generation and storage happen
in a single process with no external API calls.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from config import settings

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "rag_documents"


class VectorStore:
    """Persistent ChromaDB vector store.

    Parameters
    ----------
    persist_dir : str, optional
        Directory for ChromaDB on‑disk storage.  Defaults to
        ``settings.CHROMA_PERSIST_DIR``.
    """

    def __init__(self, persist_dir: str | None = None) -> None:
        self._persist_dir = persist_dir or settings.CHROMA_PERSIST_DIR

        self._ef = SentenceTransformerEmbeddingFunction(
            model_name=settings.HF_EMBEDDING_MODEL,
        )

        self._client = chromadb.PersistentClient(path=self._persist_dir)

        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

        logger.info(
            "VectorStore ready  dir=%s  collection=%s  count=%d",
            self._persist_dir,
            _COLLECTION_NAME,
            self._collection.count(),
        )

    # ── write ──────────────────────────────────────────────────────────

    def add_documents(self, documents: List[dict]) -> None:
        """Batch‑add documents to the collection.

        Each *document* dict must contain:
        * ``id``   – unique string identifier
        * ``text`` – the document text

        Optional:
        * ``metadata`` – dict of metadata fields
        """
        if not documents:
            return

        ids = [d["id"] for d in documents]
        texts = [d["text"] for d in documents]
        metadatas = [d.get("metadata", {}) for d in documents]

        # ChromaDB has a per‑batch cap; split into safe chunks
        batch_size = 5_000
        for start in range(0, len(ids), batch_size):
            end = start + batch_size
            self._collection.add(
                ids=ids[start:end],
                documents=texts[start:end],
                metadatas=metadatas[start:end],
            )

        logger.info("added %d documents to collection", len(ids))

    # ── read ───────────────────────────────────────────────────────────

    def search(
        self,
        query_text: str,
        top_k: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[dict]:
        """Semantic similarity search.

        Returns a list of dicts with ``id``, ``text``, ``metadata``, and
        ``score`` keys, sorted by descending relevance.
        """
        kwargs: dict[str, Any] = {
            "query_texts": [query_text],
            "n_results": min(top_k, self._collection.count() or top_k),
        }
        if filters:
            kwargs["where"] = filters

        results = self._collection.query(**kwargs)

        docs: list[dict] = []
        if not results or not results["ids"] or not results["ids"][0]:
            return docs

        for doc_id, text, meta, distance in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # ChromaDB cosine distance → similarity score
            score = 1.0 - distance
            docs.append(
                {
                    "id": doc_id,
                    "text": text,
                    "metadata": meta or {},
                    "score": round(score, 6),
                    "source": "semantic",
                }
            )

        return docs

    def get_all_documents(self) -> List[dict]:
        """Return every document in the collection (for BM25 indexing)."""
        count = self._collection.count()
        if count == 0:
            return []

        data = self._collection.get(include=["documents", "metadatas"])
        docs: list[dict] = []
        for doc_id, text, meta in zip(
            data["ids"],
            data["documents"],
            data["metadatas"],
        ):
            docs.append(
                {
                    "id": doc_id,
                    "text": text or "",
                    "metadata": meta or {},
                }
            )
        return docs

    # ── admin ──────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Collection statistics."""
        return {
            "collection_name": _COLLECTION_NAME,
            "document_count": self._collection.count(),
            "persist_dir": self._persist_dir,
        }

    def delete_collection(self) -> None:
        """Drop and recreate the collection (full reset)."""
        self._client.delete_collection(_COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

    def get_all_sources(self) -> list[str]:
        """Get a list of all unique document sources in the collection."""
        try:
            data = self._collection.get(include=["metadatas"])
            sources = set()
            for meta in data.get("metadatas", []):
                if meta and "source" in meta:
                    sources.add(meta["source"])
            return list(sources)
        except Exception as e:
            logger.error(f"Error getting sources: {e}")
            return []

    def delete_document(self, source: str) -> None:
        """Delete all chunks associated with a specific document source."""
        try:
            self._collection.delete(where={"source": source})
            logger.info(f"Deleted document source from vector store: {source}")
        except Exception as e:
            logger.error(f"Failed to delete document {source}: {e}")
        logger.warning("collection %s deleted and recreated", _COLLECTION_NAME)
