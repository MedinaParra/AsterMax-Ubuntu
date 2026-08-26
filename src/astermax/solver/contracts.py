from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SolverTermination(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INVALID_ARTIFACTS = "INVALID_ARTIFACTS"


class FieldLocation(StrEnum):
    NODAL = "NODAL"
    ELEMENTAL = "ELEMENTAL"
    ELEMENT_NODAL = "ELEMENT_NODAL"
    INTEGRATION_POINT = "INTEGRATION_POINT"
    GLOBAL = "GLOBAL"


class ArtifactDigestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0)
    media_type: str | None = None


class SolverCapabilityV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="SolverCapabilityV1", pattern=r"^SolverCapabilityV1$")
    backend_id: str = Field(min_length=1)
    backend_version: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    result_field_names: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SolverModelV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="SolverModelV1", pattern=r"^SolverModelV1$")
    model_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    analysis_type: str = Field(min_length=1)
    unit_system: str = Field(min_length=1)
    geometry: ArtifactDigestV1
    mesh: ArtifactDigestV1
    model_definition: ArtifactDigestV1
    required_capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SolverRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="SolverRequestV1", pattern=r"^SolverRequestV1$")
    request_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    backend_id: str = Field(min_length=1)
    model: SolverModelV1
    requested_fields: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def project_ids_match(self) -> "SolverRequestV1":
        if self.project_id != self.model.project_id:
            raise ValueError("request project_id must match model project_id")
        return self


class SolverRunManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="SolverRunManifestV1", pattern=r"^SolverRunManifestV1$")
    run_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    backend_id: str = Field(min_length=1)
    backend_version: str = Field(min_length=1)
    worker_id: str = Field(min_length=1)
    started_at: datetime
    finished_at: datetime
    termination: SolverTermination
    exit_code: int | None = None
    input_artifacts: list[ArtifactDigestV1] = Field(default_factory=list)
    output_artifacts: list[ArtifactDigestV1] = Field(default_factory=list)
    stdout_artifact: ArtifactDigestV1 | None = None
    stderr_artifact: ArtifactDigestV1 | None = None
    environment: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_timing_and_success(self) -> "SolverRunManifestV1":
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        if self.termination == SolverTermination.SUCCEEDED and not self.output_artifacts:
            raise ValueError("successful solver run requires output_artifacts")
        return self


class SolverFieldV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    location: FieldLocation
    components: list[str] = Field(min_length=1)
    unit: str | None = None
    artifact: ArtifactDigestV1
    metadata: dict[str, Any] = Field(default_factory=dict)


class SolverResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="SolverResultV1", pattern=r"^SolverResultV1$")
    run_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fields: list[SolverFieldV1] = Field(min_length=1)
    reaction_artifacts: list[ArtifactDigestV1] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
