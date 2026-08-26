from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from astermax.domain.models import WorkflowEvent


class AuditStore:
    """Append-only SQLite audit log for agentic workflow evidence."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    from_state TEXT NOT NULL,
                    to_state TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    evidence_class TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_workflow_project
                ON workflow_events(project_id, id)
                """
            )

    def append_event(self, event: WorkflowEvent) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workflow_events(
                    project_id, from_state, to_state, actor, evidence_class,
                    reason, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.project_id,
                    event.from_state.value,
                    event.to_state.value,
                    event.actor,
                    event.evidence_class.value,
                    event.reason,
                    event.created_at.isoformat(),
                    json.dumps(event.metadata, sort_keys=True),
                ),
            )

    def list_events(self, project_id: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT project_id, from_state, to_state, actor, evidence_class,
                       reason, created_at, metadata_json
                FROM workflow_events
                WHERE project_id = ?
                ORDER BY id ASC
                """,
                (project_id,),
            ).fetchall()

        return [
            {
                "project_id": row["project_id"],
                "from_state": row["from_state"],
                "to_state": row["to_state"],
                "actor": row["actor"],
                "evidence_class": row["evidence_class"],
                "reason": row["reason"],
                "created_at": row["created_at"],
                "metadata": json.loads(row["metadata_json"]),
            }
            for row in rows
        ]
