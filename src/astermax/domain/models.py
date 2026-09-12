from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkflowState(StrEnum):
    NEW = "NEW"
    INTENT_STRUCTURED = "INTENT_STRUCTURED"
    GEOMETRY_READY = "GEOMETRY_READY"
    PHYSICS_PROPOSED = "PHYSICS_PROPOSED"
    MODEL_REVIEW = "MODEL_REVIEW"
    MESH_READY = "MESH_READY"
    SOLVER_READY = "SOLVER_READY"
    SOLVING = "SOLVING"
    VERIFYING = "VERIFYING"
    REJECTED = "REJECTED"
    ACCEPTED = "ACCEPTED"
    EXPERIMENTING = "EXPERIMENTING"
    DATASET_READY = "DATASET_READY"
    SURROGATE_READY = "SURROGATE_READY"
    RCA_READY = "RCA_READY"
    REPORT_READY = "REPORT_READY"


class EvidenceClass(StrEnum):
    USER_INPUT = "USER_INPUT"
    AGENT_PROPOSAL = "AGENT_PROPOSAL"
    DETERMINISTIC_CALCULATION = "DETERMINISTIC_CALCULATION"
    SOLVER_RESULT = "SOLVER_RESULT"
    SURROGATE_PREDICTION = "SURROGATE_PREDICTION"


class AgentResultStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class AgentTaskV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = Field(default="AgentTaskV1", pattern=r"^AgentTaskV1$")
    task_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    agent_id: str = Field(pattern=r"^A([0-9]|1[0-2])$")
    objective: str = Field(min_length=1)
    allowed_inputs: list[str] = Field(default_factory=list)
    expected_output_contract: str = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1)
    prohibited_actions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    parent_task_id: str | None = None
    human_approval_required: bool = False
    timeout_seconds: int | None = Field(default=None, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = Field(default="AgentResultV1", pattern=r"^AgentResultV1$")
    task_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    agent_id: str = Field(pattern=r"^A([0-9]|1[0-2])$")
    status: AgentResultStatus
    output_contract: str = Field(min_length=1)
    evidence_class: EvidenceClass
    summary: str = Field(min_length=1)
    artifact_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = Field(default="ArtifactRecordV1", pattern=r"^ArtifactRecordV1$")
    artifact_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    task_id: str | None = None
    evidence_class: EvidenceClass
    uri: str = Field(min_length=1)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(min_length=1)
    from_state: WorkflowState
    to_state: WorkflowState
    actor: str = Field(min_length=1)
    evidence_class: EvidenceClass
    reason: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = Field(default="ProjectSnapshotV1", pattern=r"^ProjectSnapshotV1$")
    project_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    engineering_question: str = ""
    state: WorkflowState = WorkflowState.NEW
    parameters: dict[str, float | int | str | bool] = Field(default_factory=dict)
