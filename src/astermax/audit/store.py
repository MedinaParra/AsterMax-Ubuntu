from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from astermax.domain.models import (
    AgentResultV1,
    AgentTaskV1,
    ArtifactRecordV1,
    WorkflowEvent,
)


class AuditStore:
    """Append-only SQLite audit log for workflow, agent and artifact evidence."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
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
                );

                CREATE INDEX IF NOT EXISTS idx_workflow_project
                ON workflow_events(project_id, id);

                CREATE TABLE IF NOT EXISTS agent_tasks (
                    task_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    expected_output_contract TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_agent_tasks_project
                ON agent_tasks(project_id, created_at);

                CREATE TABLE IF NOT EXISTS agent_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    output_contract TEXT NOT NULL,
                    evidence_class TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES agent_tasks(task_id)
                );

                CREATE INDEX IF NOT EXISTS idx_agent_results_task
                ON agent_results(task_id, id);

                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    task_id TEXT,
                    evidence_class TEXT NOT NULL,
                    uri TEXT NOT NULL,
                    sha256 TEXT,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES agent_tasks(task_id)
                );

                CREATE INDEX IF NOT EXISTS idx_artifacts_project
                ON artifacts(project_id, created_at);
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

    def append_task(self, task: AgentTaskV1) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_tasks(
                    task_id, project_id, agent_id, objective,
                    expected_output_contract, created_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.task_id,
                    task.project_id,
                    task.agent_id,
                    task.objective,
                    task.expected_output_contract,
                    task.created_at.isoformat(),
                    task.model_dump_json(),
                ),
            )

    def append_result(self, result: AgentResultV1) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_results(
                    task_id, project_id, agent_id, status, output_contract,
                    evidence_class, summary, created_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.task_id,
                    result.project_id,
                    result.agent_id,
                    result.status.value,
                    result.output_contract,
                    result.evidence_class.value,
                    result.summary,
                    result.created_at.isoformat(),
                    result.model_dump_json(),
                ),
            )

    def append_artifact(self, artifact: ArtifactRecordV1) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO artifacts(
                    artifact_id, project_id, task_id, evidence_class, uri,
                    sha256, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.artifact_id,
                    artifact.project_id,
                    artifact.task_id,
                    artifact.evidence_class.value,
                    artifact.uri,
                    artifact.sha256,
                    artifact.created_at.isoformat(),
                    json.dumps(artifact.metadata, sort_keys=True),
                ),
            )

    def get_task(self, task_id: str) -> AgentTaskV1 | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM agent_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return AgentTaskV1.model_validate_json(row["payload_json"]) if row else None

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

    def list_results(self, task_id: str) -> list[AgentResultV1]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM agent_results
                WHERE task_id = ? ORDER BY id ASC
                """,
                (task_id,),
            ).fetchall()
        return [
            AgentResultV1.model_validate_json(row["payload_json"])
            for row in rows
        ]

    def list_artifacts(self, project_id: str) -> list[ArtifactRecordV1]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT artifact_id, project_id, task_id, evidence_class,
                       uri, sha256, created_at, metadata_json
                FROM artifacts WHERE project_id = ? ORDER BY created_at ASC
                """,
                (project_id,),
            ).fetchall()
        return [
            ArtifactRecordV1(
                artifact_id=row["artifact_id"],
                project_id=row["project_id"],
                task_id=row["task_id"],
                evidence_class=row["evidence_class"],
                uri=row["uri"],
                sha256=row["sha256"],
                created_at=row["created_at"],
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        ]
