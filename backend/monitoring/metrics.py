"""
Quality metrics tracking for the RAG pipeline.

Records and aggregates feedback, citation accuracy, and hallucination checks.
"""

from typing import Optional


class QualityMetrics:
    """Tracks and aggregates RAG output quality signals."""

    def __init__(self, monitoring_db) -> None:
        """
        Initialize the quality metrics tracker.

        Args:
            monitoring_db: A MonitoringDB instance for persistent storage.
        """
        self.monitoring_db = monitoring_db

    def record_feedback(
        self, query_id: str, feedback: str, query_text: str = None
    ) -> None:
        """
        Record user feedback (thumbs up/down) for a query.

        Args:
            query_id: The query to associate feedback with.
            feedback: Either 'up' or 'down'.
            query_text: Optional query text for context logging.
        """
        if feedback not in ("up", "down"):
            raise ValueError(f"Feedback must be 'up' or 'down', got '{feedback}'")

        self.monitoring_db.log_feedback(query_id, feedback)

        if query_text:
            self.monitoring_db.log_event(
                "feedback",
                f"User gave thumbs {feedback} for query: {query_text[:100]}",
                {"query_id": query_id, "feedback": feedback},
            )

    def record_citation_accuracy(
        self, query_id: str, citations_provided: int, citations_used: int
    ) -> None:
        """
        Record how many provided citations were actually used.

        Args:
            query_id: The query to associate the metric with.
            citations_provided: Total number of citations available.
            citations_used: Number of citations the response actually referenced.
        """
        accuracy = (
            citations_used / citations_provided if citations_provided > 0 else 0.0
        )
        self.monitoring_db.log_quality(
            query_id, citation_accuracy=accuracy, is_grounded=True
        )

    def record_hallucination_check(
        self, query_id: str, is_grounded: bool
    ) -> None:
        """
        Record whether a response is grounded in its source documents.

        Args:
            query_id: The query to associate the check with.
            is_grounded: True if the response is factually grounded.
        """
        self.monitoring_db.log_quality(
            query_id, citation_accuracy=0.0, is_grounded=is_grounded
        )

    def get_quality_summary(self, hours: int = 24) -> dict:
        """
        Aggregate quality metrics over a time window.

        Returns:
            Dictionary with feedback_ratio, total_feedback, thumbs_up,
            thumbs_down, citation_accuracy, hallucination_rate, and
            answer_completeness.
        """
        feedback = self.monitoring_db.get_feedback_summary(hours=hours)
        quality = self.monitoring_db.get_quality_history(hours=hours)

        return {
            "feedback_ratio": feedback.get("ratio", 0.0),
            "total_feedback": feedback.get("total", 0),
            "thumbs_up": feedback.get("thumbs_up", 0),
            "thumbs_down": feedback.get("thumbs_down", 0),
            "citation_accuracy": quality.get("avg_citation_accuracy", 0.0),
            "hallucination_rate": quality.get("hallucination_rate", 0.0),
            "answer_completeness": 1.0 - quality.get("hallucination_rate", 0.0),
        }
