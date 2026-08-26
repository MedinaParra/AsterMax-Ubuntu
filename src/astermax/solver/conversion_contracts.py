from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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
    converter_id: str = Field(min_length=1)
    converter_version: str = Field(min_length=1)
    started_at: datetime
    finished_at: datetime
    source_run_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_artifact: ArtifactDigestV1
    output_artifacts: list[ArtifactDigestV1] = Field(min_length=1)
    fields: list[ConversionFieldInventoryV1] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
