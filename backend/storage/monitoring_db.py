"""
SQLite-backed monitoring database for the RAG pipeline.

Stores query logs, feedback, quality metrics, alerts, and system events
with thread-safe access and ISO 8601 timestamps.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional


class MonitoringDB:
    """Persistent monitoring storage using SQLite."""

    def __init__(self, db_path: str = "./monitoring.db") -> None:
        """
        Initialize the monitoring database.

        Creates all required tables if they do not already exist.

        Args:
            db_path: Filesystem path to the SQLite database file.
        """
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        """Create all monitoring tables if they don't exist."""
        cursor = self.conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS query_logs (
                id TEXT PRIMARY KEY,
                query_text TEXT,
                response_text TEXT,
                latency_breakdown TEXT,
                cost_breakdown TEXT,
                citations TEXT,
                model_used TEXT,
                timestamp TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id TEXT PRIMARY KEY,
                query_id TEXT,
                feedback_type TEXT,
                timestamp TEXT,
                FOREIGN KEY (query_id) REFERENCES query_logs(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quality_metrics (
                id TEXT PRIMARY KEY,
                query_id TEXT,
                citation_accuracy REAL,
                is_grounded INTEGER,
                timestamp TEXT,
                FOREIGN KEY (query_id) REFERENCES query_logs(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY,
                severity TEXT,
                alert_type TEXT,
                message TEXT,
                value REAL,
                threshold REAL,
                timestamp TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_events (
                id TEXT PRIMARY KEY,
                event_type TEXT,
                message TEXT,
                metadata TEXT,
                timestamp TEXT
            )
        """)

        self.conn.commit()

    def _now_iso(self) -> str:
        """Return the current UTC time in ISO 8601 format."""
        return datetime.now(timezone.utc).isoformat()

    def _hours_ago_iso(self, hours: int) -> str:
        """Return an ISO 8601 timestamp for N hours ago."""
        return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    def log_query(self, data: dict) -> str:
        """
        Log a completed RAG query.

        Args:
            data: Dictionary with keys: query_text, response_text,
                  latency_breakdown, cost_breakdown, citations, model_used.

        Returns:
            The generated query_id (UUID).
        """
        query_id = data.get("query_id", str(uuid.uuid4()))
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO query_logs (id, query_text, response_text, latency_breakdown,
                                    cost_breakdown, citations, model_used, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                query_id,
                data.get("query_text", ""),
                data.get("response_text", ""),
                json.dumps(data.get("latency_breakdown", {})),
                json.dumps(data.get("cost_breakdown", {})),
                json.dumps(data.get("citations", [])),
                data.get("model_used", ""),
                self._now_iso(),
            ),
        )
        self.conn.commit()
        return query_id

    def log_feedback(self, query_id: str, feedback_type: str) -> None:
        """
        Log user feedback for a query.

        Args:
            query_id: The query this feedback relates to.
            feedback_type: Either 'up' or 'down'.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO feedback (id, query_id, feedback_type, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), query_id, feedback_type, self._now_iso()),
        )
        self.conn.commit()

    def log_quality(self, query_id: str, citation_accuracy: float, is_grounded: bool) -> None:
        """
        Log quality metrics for a query.

        Args:
            query_id: The query this metric relates to.
            citation_accuracy: Ratio of citations used vs. provided (0-1).
            is_grounded: Whether the response is grounded in the sources.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO quality_metrics (id, query_id, citation_accuracy, is_grounded, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), query_id, citation_accuracy, int(is_grounded), self._now_iso()),
        )
        self.conn.commit()

    def log_alert(self, alert: dict) -> None:
        """
        Persist an alert to the database.

        Args:
            alert: Dictionary with severity, type, message, value, threshold.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO alerts (id, severity, alert_type, message, value, threshold, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert.get("id", str(uuid.uuid4())),
                alert.get("severity", "info"),
                alert.get("type", "unknown"),
                alert.get("message", ""),
                alert.get("value", 0.0),
                alert.get("threshold", 0.0),
                alert.get("timestamp", self._now_iso()),
            ),
        )
        self.conn.commit()

    def log_event(self, event_type: str, message: str, metadata: dict = None) -> None:
        """
        Log a system event.

        Args:
            event_type: Category of the event (e.g. 'startup', 'ingest').
            message: Human-readable description.
            metadata: Optional dictionary of additional context.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO system_events (id, event_type, message, metadata, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                event_type,
                message,
                json.dumps(metadata or {}),
                self._now_iso(),
            ),
        )
        self.conn.commit()

    def get_latency_history(self, hours: int = 24) -> list[dict]:
        """Retrieve latency data points from recent queries."""
        cursor = self.conn.cursor()
        since = self._hours_ago_iso(hours)
        cursor.execute(
            """
            SELECT id, latency_breakdown, timestamp
            FROM query_logs
            WHERE timestamp >= ?
            ORDER BY timestamp DESC
            """,
            (since,),
        )
        rows = cursor.fetchall()
        return [
            {
                "query_id": row["id"],
                "latency_breakdown": json.loads(row["latency_breakdown"]),
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]

    def get_cost_history(self, hours: int = 24) -> list[dict]:
        """Retrieve cost data points from recent queries."""
        cursor = self.conn.cursor()
        since = self._hours_ago_iso(hours)
        cursor.execute(
            """
            SELECT id, cost_breakdown, timestamp
            FROM query_logs
            WHERE timestamp >= ?
            ORDER BY timestamp DESC
            """,
            (since,),
        )
        rows = cursor.fetchall()
        return [
            {
                "query_id": row["id"],
                "cost_breakdown": json.loads(row["cost_breakdown"]),
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]

    def get_quality_history(self, hours: int = 24) -> dict:
        """Aggregate quality metrics over a time window."""
        cursor = self.conn.cursor()
        since = self._hours_ago_iso(hours)
        cursor.execute(
            """
            SELECT citation_accuracy, is_grounded
            FROM quality_metrics
            WHERE timestamp >= ?
            """,
            (since,),
        )
        rows = cursor.fetchall()

        if not rows:
            return {
                "avg_citation_accuracy": 0.0,
                "hallucination_rate": 0.0,
                "total_evaluated": 0,
            }

        total = len(rows)
        avg_citation = sum(r["citation_accuracy"] for r in rows) / total
        grounded_count = sum(1 for r in rows if r["is_grounded"])
        hallucination_rate = 1.0 - (grounded_count / total)

        return {
            "avg_citation_accuracy": round(avg_citation, 4),
            "hallucination_rate": round(hallucination_rate, 4),
            "total_evaluated": total,
        }

    def get_feedback_summary(self, hours: int = 24) -> dict:
        """Summarize user feedback over a time window."""
        cursor = self.conn.cursor()
        since = self._hours_ago_iso(hours)
        cursor.execute(
            """
            SELECT feedback_type, COUNT(*) as count
            FROM feedback
            WHERE timestamp >= ?
            GROUP BY feedback_type
            """,
            (since,),
        )
        rows = cursor.fetchall()

        summary = {"thumbs_up": 0, "thumbs_down": 0, "total": 0, "ratio": 0.0}
        for row in rows:
            if row["feedback_type"] == "up":
                summary["thumbs_up"] = row["count"]
            elif row["feedback_type"] == "down":
                summary["thumbs_down"] = row["count"]

        summary["total"] = summary["thumbs_up"] + summary["thumbs_down"]
        if summary["total"] > 0:
            summary["ratio"] = round(summary["thumbs_up"] / summary["total"], 4)

        return summary

    def get_recent_alerts(self, limit: int = 50) -> list[dict]:
        """Retrieve the most recent alerts."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, severity, alert_type, message, value, threshold, timestamp
            FROM alerts
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "severity": row["severity"],
                "type": row["alert_type"],
                "message": row["message"],
                "value": row["value"],
                "threshold": row["threshold"],
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]

    def get_recent_events(self, limit: int = 50) -> list[dict]:
        """Retrieve the most recent system events."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, event_type, message, metadata, timestamp
            FROM system_events
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "event_type": row["event_type"],
                "message": row["message"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]

    def get_dashboard_summary(self) -> dict:
        """Build an aggregated summary for the monitoring dashboard."""
        cursor = self.conn.cursor()

        # Total query count
        cursor.execute("SELECT COUNT(*) as count FROM query_logs")
        query_count = cursor.fetchone()["count"]

        # Average latency (last 24h)
        latency_history = self.get_latency_history(hours=24)
        avg_latency = {}
        if latency_history:
            all_keys: set[str] = set()
            for entry in latency_history:
                all_keys.update(entry["latency_breakdown"].keys())
            for key in all_keys:
                values = [
                    entry["latency_breakdown"].get(key, 0.0)
                    for entry in latency_history
                ]
                avg_latency[key] = round(sum(values) / len(values), 2)

        # Total cost (last 24h)
        cost_history = self.get_cost_history(hours=24)
        total_cost = {}
        if cost_history:
            all_cost_keys: set[str] = set()
            for entry in cost_history:
                all_cost_keys.update(entry["cost_breakdown"].keys())
            for key in all_cost_keys:
                values = [
                    entry["cost_breakdown"].get(key, 0.0) for entry in cost_history
                ]
                total_cost[key] = round(sum(values), 8)

        return {
            "query_count": query_count,
            "avg_latency": avg_latency,
            "total_cost": total_cost,
            "latency_history": latency_history,
            "cost_history": cost_history,
            "quality": self.get_quality_history(hours=24),
            "feedback": self.get_feedback_summary(hours=24),
            "recent_alerts": self.get_recent_alerts(limit=10),
            "recent_events": self.get_recent_events(limit=10),
        }
