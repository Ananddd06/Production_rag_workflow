"""
Latency and cost tracking for the RAG pipeline.

Provides high-resolution timing via perf_counter and per-query cost estimation.
"""

import time
from contextlib import contextmanager


class LatencyTracker:
    """High-resolution latency tracker for individual pipeline stages."""

    def __init__(self) -> None:
        self._start_times: dict[str, float] = {}
        self._durations: dict[str, float] = {}

    def start(self, stage: str) -> None:
        """Begin timing a pipeline stage."""
        self._start_times[stage] = time.perf_counter()

    def stop(self, stage: str) -> float:
        """Stop timing a pipeline stage and record the duration.

        Returns:
            Elapsed time in milliseconds.
        """
        if stage not in self._start_times:
            raise ValueError(f"Stage '{stage}' was never started")

        elapsed_ms = (time.perf_counter() - self._start_times[stage]) * 1000
        self._durations[stage] = elapsed_ms
        del self._start_times[stage]
        return elapsed_ms

    @contextmanager
    def track(self, stage: str):
        """Context manager for timing a stage.

        Usage:
            with tracker.track('retrieval'):
                results = retriever.search(query)
        """
        self.start(stage)
        try:
            yield
        finally:
            self.stop(stage)

    def get_breakdown(self) -> dict:
        """Return a latency breakdown for all tracked stages."""
        breakdown = {}
        known_stages = [
            "retrieval",
            "reranking",
            "generation",
            "preprocessing",
            "assembly",
        ]

        for stage in known_stages:
            key = f"{stage}_ms"
            breakdown[key] = round(self._durations.get(stage, 0.0), 2)

        # Include any custom stages not in the known list
        for stage, duration in self._durations.items():
            if stage not in known_stages:
                breakdown[f"{stage}_ms"] = round(duration, 2)

        breakdown["total_ms"] = round(sum(self._durations.values()), 2)
        return breakdown

    def reset(self) -> None:
        """Clear all recorded timings."""
        self._start_times.clear()
        self._durations.clear()


class CostTracker:
    """Estimates per-query costs for embedding, generation, and vector DB operations."""

    def __init__(
        self,
        embedding_cost_per_1k: float = 0.0001,
        generation_cost_per_1k: float = 0.0006,
    ) -> None:
        self.embedding_cost_per_1k = embedding_cost_per_1k
        self.generation_cost_per_1k = generation_cost_per_1k
        self._vector_db_cost_per_query = 0.00001

        self._embedding_tokens = 0
        self._generation_tokens = 0
        self._vector_db_queries = 0

    def track_embedding(self, num_tokens: int) -> None:
        """Record tokens consumed by an embedding call."""
        self._embedding_tokens += num_tokens

    def track_generation(self, num_tokens: int) -> None:
        """Record tokens consumed by LLM generation."""
        self._generation_tokens += num_tokens

    def track_vector_db(self, num_queries: int) -> None:
        """Record vector database queries at an estimated $0.00001 per query."""
        self._vector_db_queries += num_queries

    def get_query_cost(self) -> dict:
        """Calculate the cost breakdown for the current query."""
        embedding_cost = (self._embedding_tokens / 1000) * self.embedding_cost_per_1k
        generation_cost = (
            (self._generation_tokens / 1000) * self.generation_cost_per_1k
        )
        vector_db_cost = self._vector_db_queries * self._vector_db_cost_per_query

        return {
            "embedding_cost": round(embedding_cost, 8),
            "generation_cost": round(generation_cost, 8),
            "vector_db_cost": round(vector_db_cost, 8),
            "total_cost": round(embedding_cost + generation_cost + vector_db_cost, 8),
        }

    def reset(self) -> None:
        """Clear all accumulated costs."""
        self._embedding_tokens = 0
        self._generation_tokens = 0
        self._vector_db_queries = 0
