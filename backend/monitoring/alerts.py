"""
Alert management for the RAG pipeline.

Monitors latency, cost, and quality thresholds and generates alerts
at configurable severity levels.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional


class AlertManager:
    """Monitors pipeline metrics against configurable thresholds and generates alerts."""

    def __init__(self, monitoring_db) -> None:
        """
        Initialize the alert manager.

        Args:
            monitoring_db: A MonitoringDB instance for persisting alerts.
        """
        self.monitoring_db = monitoring_db

        # Configurable thresholds
        self.latency_warning_ms: float = 2000
        self.latency_critical_ms: float = 5000
        self.cost_per_1k_warning: float = 0.50
        self.hallucination_rate_warning: float = 0.10
        self.hallucination_rate_critical: float = 0.20

    def _create_alert(
        self,
        severity: str,
        alert_type: str,
        message: str,
        value: float,
        threshold: float,
    ) -> dict:
        """
        Build a standardised alert dictionary and persist it.

        Args:
            severity: One of 'info', 'warning', 'critical'.
            alert_type: Category (e.g. 'latency', 'cost', 'quality').
            message: Human-readable description.
            value: The observed metric value.
            threshold: The threshold that was exceeded.

        Returns:
            The complete alert dictionary.
        """
        alert = {
            "id": str(uuid.uuid4()),
            "severity": severity,
            "type": alert_type,
            "message": message,
            "value": value,
            "threshold": threshold,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.monitoring_db.log_alert(alert)
        return alert

    def check_latency(self, latency_ms: float) -> Optional[dict]:
        """
        Check whether a query's latency exceeds configured thresholds.

        Args:
            latency_ms: Total query latency in milliseconds.

        Returns:
            An alert dict if a threshold is exceeded, otherwise None.
        """
        if latency_ms >= self.latency_critical_ms:
            return self._create_alert(
                severity="critical",
                alert_type="latency",
                message=f"Critical latency: {latency_ms:.0f}ms exceeds {self.latency_critical_ms:.0f}ms threshold",
                value=latency_ms,
                threshold=self.latency_critical_ms,
            )
        elif latency_ms >= self.latency_warning_ms:
            return self._create_alert(
                severity="warning",
                alert_type="latency",
                message=f"High latency: {latency_ms:.0f}ms exceeds {self.latency_warning_ms:.0f}ms threshold",
                value=latency_ms,
                threshold=self.latency_warning_ms,
            )
        return None

    def check_cost(self, cost_per_1k: float) -> Optional[dict]:
        """
        Check whether the cost per 1,000 queries exceeds the warning threshold.

        Args:
            cost_per_1k: Estimated cost per 1,000 queries in USD.

        Returns:
            An alert dict if the threshold is exceeded, otherwise None.
        """
        if cost_per_1k >= self.cost_per_1k_warning:
            return self._create_alert(
                severity="warning",
                alert_type="cost",
                message=f"High cost: ${cost_per_1k:.4f}/1k queries exceeds ${self.cost_per_1k_warning:.2f} threshold",
                value=cost_per_1k,
                threshold=self.cost_per_1k_warning,
            )
        return None

    def check_quality(self, metrics: dict) -> Optional[dict]:
        """
        Check whether the hallucination rate exceeds configured thresholds.

        Args:
            metrics: Quality summary dict with a 'hallucination_rate' key.

        Returns:
            An alert dict if a threshold is exceeded, otherwise None.
        """
        hallucination_rate = metrics.get("hallucination_rate", 0.0)

        if hallucination_rate >= self.hallucination_rate_critical:
            return self._create_alert(
                severity="critical",
                alert_type="quality",
                message=f"Critical hallucination rate: {hallucination_rate:.1%} exceeds {self.hallucination_rate_critical:.0%} threshold",
                value=hallucination_rate,
                threshold=self.hallucination_rate_critical,
            )
        elif hallucination_rate >= self.hallucination_rate_warning:
            return self._create_alert(
                severity="warning",
                alert_type="quality",
                message=f"High hallucination rate: {hallucination_rate:.1%} exceeds {self.hallucination_rate_warning:.0%} threshold",
                value=hallucination_rate,
                threshold=self.hallucination_rate_warning,
            )
        return None

    def get_recent_alerts(self, limit: int = 50) -> list[dict]:
        """
        Retrieve the most recent alerts from the database.

        Args:
            limit: Maximum number of alerts to return.

        Returns:
            List of alert dictionaries ordered by timestamp descending.
        """
        return self.monitoring_db.get_recent_alerts(limit=limit)
