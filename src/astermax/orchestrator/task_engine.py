from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from astermax.agents.registry import AgentRegistry
from astermax.audit.store import AuditStore
from astermax.domain.models import (
    AgentResultStatus,
    AgentResultV1,
    AgentTaskV1,
    ArtifactRecordV1,
    EvidenceClass,
)


class ContractViolation(RuntimeError):
    pass


class AgentTaskEngine:
    """Deterministic contract boundary around future agent implementations."""

    def __init__(self, registry: AgentRegistry, audit_store: AuditStore) -> None:
        self.registry = registry
        self.audit_store = audit_store

    def create_task(
        self,
        *,
        project_id: str,
        agent_id: str,
        objective: str,
        expected_output_contract: str,
        acceptance_criteria: Iterable[str],
        allowed_inputs: Iterable[str] = (),
        prohibited_actions: Iterable[str] = (),
        human_approval_required: bool = False,
        timeout_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
        parent_task_id: str | None = None,
    ) -> AgentTaskV1:
        self.registry.get(agent_id)
        task = AgentTaskV1(
            task_id=f"task-{uuid.uuid4().hex}",
            project_id=project_id,
            agent_id=agent_id,
            objective=objective,
            allowed_inputs=list(allowed_inputs),
            expected_output_contract=expected_output_contract,
            acceptance_criteria=list(acceptance_criteria),
            prohibited_actions=list(prohibited_actions),
            human_approval_required=human_approval_required,
            timeout_seconds=timeout_seconds,
            metadata=metadata or {},
            parent_task_id=parent_task_id,
        )
        self.audit_store.append_task(task)
        return task

    def record_result(self, result: AgentResultV1) -> None:
        task = self.audit_store.get_task(result.task_id)
        if task is None:
            raise ContractViolation(f"Unknown task: {result.task_id}")
        if result.project_id != task.project_id:
            raise ContractViolation("Result project_id does not match its task.")
        if result.agent_id != task.agent_id:
            raise ContractViolation("Result agent_id does not match its task.")
        if result.output_contract != task.expected_output_contract:
            raise ContractViolation(
                "Result output_contract does not match the task contract."
            )
        self.audit_store.append_result(result)

    def register_artifact(
        self,
        *,
        project_id: str,
        evidence_class: EvidenceClass,
        uri: str,
        task_id: str | None = None,
        sha256: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRecordV1:
        if task_id is not None:
            task = self.audit_store.get_task(task_id)
            if task is None:
                raise ContractViolation(f"Unknown task: {task_id}")
            if task.project_id != project_id:
                raise ContractViolation("Artifact project_id does not match task.")
        artifact = ArtifactRecordV1(
            artifact_id=f"artifact-{uuid.uuid4().hex}",
            project_id=project_id,
            task_id=task_id,
            evidence_class=evidence_class,
            uri=uri,
            sha256=sha256,
            metadata=metadata or {},
        )
        self.audit_store.append_artifact(artifact)
        return artifact

    @staticmethod
    def success_result(
        task: AgentTaskV1,
        *,
        summary: str,
        evidence_class: EvidenceClass = EvidenceClass.AGENT_PROPOSAL,
        artifact_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentResultV1:
        return AgentResultV1(
            task_id=task.task_id,
            project_id=task.project_id,
            agent_id=task.agent_id,
            status=AgentResultStatus.SUCCESS,
            output_contract=task.expected_output_contract,
            evidence_class=evidence_class,
            summary=summary,
            artifact_ids=artifact_ids or [],
            metadata=metadata or {},
        )
