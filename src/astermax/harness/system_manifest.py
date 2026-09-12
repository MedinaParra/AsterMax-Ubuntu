from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from astermax.harness.models import EvaluationBudgetV1


class SystemUnderTestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="SystemUnderTestV1", pattern=r"^SystemUnderTestV1$")
    model_provider: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    reasoning_setting: str | None = None
    tool_access: list[str] = Field(default_factory=list)
    harness_commit: str = Field(min_length=7)
    safeguards: list[str] = Field(default_factory=list)
    evaluation_budget: EvaluationBudgetV1 = Field(default_factory=EvaluationBudgetV1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationRunManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="EvaluationRunManifestV1", pattern=r"^EvaluationRunManifestV1$")
    run_id: str = Field(min_length=1)
    workpackage_id: str = Field(min_length=1)
    suite_id: str = Field(min_length=1)
    suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    system: SystemUnderTestV1
    attempt: int = Field(default=1, ge=1)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    result_artifacts: list[str] = Field(default_factory=list)
    validity_notes: list[str] = Field(default_factory=list)
