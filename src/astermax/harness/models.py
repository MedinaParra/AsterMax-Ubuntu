from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


class HarnessDecision(StrEnum):
    PASS = "PASS"
    REWORK = "REWORK"
    REJECT = "REJECT"


class WorkPackageV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="WorkPackageV1", pattern=r"^WorkPackageV1$")
    workpackage_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    issue: int | None = Field(default=None, ge=1)
    allowed_files: list[str] = Field(min_length=1)
    forbidden_paths: list[str] = Field(default_factory=list)
    max_files_changed: int = Field(default=25, ge=1)
    prohibited_actions: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(min_length=1)
    required_gates: list[str] = Field(min_length=1)
    numerical_impact: bool = False
    human_merge_required: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class GateResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="GateResultV1", pattern=r"^GateResultV1$")
    gate_id: str = Field(min_length=1)
    status: GateStatus
    evidence_type: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    command: list[str] | None = None
    exit_code: int | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class HarnessDecisionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="HarnessDecisionV1", pattern=r"^HarnessDecisionV1$")
    workpackage_id: str
    workpackage_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: HarnessDecision
    changed_files: list[str] = Field(default_factory=list)
    gates: list[GateResultV1] = Field(default_factory=list)
    human_merge_required: bool = True
    reasons: list[str] = Field(default_factory=list)
