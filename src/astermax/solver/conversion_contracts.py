from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from astermax.solver.contracts import ArtifactDigestV1


class ConversionFieldInventoryV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_field_name: str = Field(min_length=1)
    source_association: str = Field(min_length=1)
    source_dataset_path: str = Field(min_length=1)
    components: list[str] = Field(min_length=1)
    unit: str | None = None
    raw_shape: list[int] = Field(min_length=1)
    vtk_array_name: str = Field(min_length=1)
    vtk_scope: str = Field(min_length=1)
    derived_vtk_array_names: list[str] = Field(default_factory=list)


class ResultConversionManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="ResultConversionManifestV1",
        pattern=r"^ResultConversionManifestV1$",
    )
    run_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    converter_id: str = Field(pattern=r"^astermax\.med_to_vtu$")
    converter_version: str = Field(pattern=r"^astermax-med3-v1$")
    started_at: datetime
    finished_at: datetime
    source_run_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_artifact: ArtifactDigestV1
    output_artifacts: list[ArtifactDigestV1] = Field(min_length=1)
    fields: list[ConversionFieldInventoryV1] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_conversion_invariants(self) -> "ResultConversionManifestV1":
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")

        output_paths = [artifact.relative_path for artifact in self.output_artifacts]
        if len(output_paths) != len(set(output_paths)):
            raise ValueError("conversion output artifact paths must be unique")
        if self.source_artifact.relative_path in output_paths:
            raise ValueError("conversion must not overwrite the solver source artifact")

        field_keys = [
            (field.source_field_name, field.source_association)
            for field in self.fields
        ]
        if len(field_keys) != len(set(field_keys)):
            raise ValueError("conversion field inventory entries must be unique")
        return self
