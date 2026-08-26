from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from astermax.solver.bridge import verify_artifact
from astermax.solver.contracts import (
    ArtifactDigestV1,
    FieldLocation,
    SolverFieldV1,
    SolverRequestV1,
    SolverResultV1,
    SolverRunManifestV1,
    SolverTermination,
)
from astermax.solver.conversion_contracts import ResultConversionManifestV1
from astermax.solver.errors import SolverEvidenceError


class ResultFieldDescriptorV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    location: FieldLocation
    components: list[str] = Field(min_length=1)
    unit: str | None = None
    artifact_path: str = Field(min_length=1)
    artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    artifact_byte_size: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResultDescriptorV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="ResultDescriptorV1", pattern=r"^ResultDescriptorV1$")
    fields: list[ResultFieldDescriptorV1] = Field(min_length=1)
    reaction_artifact_paths: list[str] = Field(default_factory=list)
    source_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_artifact_path: str | None = None
    source_artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    converter_version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def _canonical_json_bytes(model: BaseModel) -> bytes:
    return (
        json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _validated_manifest_hash(run_directory: Path, manifest: SolverRunManifestV1) -> str:
    if manifest.termination != SolverTermination.SUCCEEDED:
        raise SolverEvidenceError("cannot load result from non-successful solver manifest")
    manifest_path = run_directory / "output" / "manifest.json"
    if not manifest_path.is_file():
        raise SolverEvidenceError("missing persisted solver manifest")
    persisted = SolverRunManifestV1.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if persisted != manifest:
        raise SolverEvidenceError("persisted solver manifest differs from validated manifest")
    return hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def load_solver_result(
    run_directory: Path,
    request: SolverRequestV1,
    manifest: SolverRunManifestV1,
) -> SolverResultV1:
    """Load legacy/direct solver fields that are already declared by the solver manifest."""
    run_directory = run_directory.resolve()
    manifest_hash = _validated_manifest_hash(run_directory, manifest)

    by_path = {artifact.relative_path: artifact for artifact in manifest.output_artifacts}
    descriptor_artifact = by_path.get("output/result_descriptor.json")
    if descriptor_artifact is None:
        raise SolverEvidenceError("solver manifest does not declare output/result_descriptor.json")
    verify_artifact(run_directory, descriptor_artifact)
    descriptor = ResultDescriptorV1.model_validate_json(
        (run_directory / descriptor_artifact.relative_path).read_text(encoding="utf-8")
    )

    fields: list[SolverFieldV1] = []
    for declared in descriptor.fields:
        artifact = by_path.get(declared.artifact_path)
        if artifact is None:
            raise SolverEvidenceError(f"result descriptor references undeclared artifact: {declared.artifact_path}")
        verify_artifact(run_directory, artifact)
        fields.append(
            SolverFieldV1(
                name=declared.name,
                location=declared.location,
                components=declared.components,
                unit=declared.unit,
                artifact=artifact,
                metadata=declared.metadata,
            )
        )

    reactions: list[ArtifactDigestV1] = []
    for relative_path in descriptor.reaction_artifact_paths:
        artifact = by_path.get(relative_path)
        if artifact is None:
            raise SolverEvidenceError(f"reaction descriptor references undeclared artifact: {relative_path}")
        verify_artifact(run_directory, artifact)
        reactions.append(artifact)

    result = SolverResultV1(
        run_id=request.run_id,
        request_id=request.request_id,
        manifest_sha256=manifest_hash,
        fields=fields,
        reaction_artifacts=reactions,
    )
    result_path = run_directory / "output" / "result.json"
    result_path.write_bytes(_canonical_json_bytes(result))
    return result


def load_converted_solver_result(
    run_directory: Path,
    request: SolverRequestV1,
    manifest: SolverRunManifestV1,
    *,
    conversion_manifest_path: str = "output/conversion_manifest.json",
) -> SolverResultV1:
    """Load AsterMax postprocessed fields without claiming that VTU was produced by the solver."""
    run_directory = run_directory.resolve()
    manifest_hash = _validated_manifest_hash(run_directory, manifest)

    conversion_path = (run_directory / conversion_manifest_path).resolve()
    try:
        conversion_path.relative_to(run_directory)
    except ValueError as exc:
        raise SolverEvidenceError("conversion manifest escapes run directory") from exc
    if not conversion_path.is_file():
        raise SolverEvidenceError("missing conversion manifest")
    conversion = ResultConversionManifestV1.model_validate_json(
        conversion_path.read_text(encoding="utf-8")
    )
    if conversion.run_id != request.run_id or conversion.request_id != request.request_id:
        raise SolverEvidenceError("conversion manifest identity does not match request")
    if conversion.source_run_manifest_sha256 != manifest_hash:
        raise SolverEvidenceError("conversion manifest does not link to validated solver manifest")

    original_outputs = {
        (artifact.relative_path, artifact.sha256, artifact.byte_size)
        for artifact in manifest.output_artifacts
    }
    source_key = (
        conversion.source_artifact.relative_path,
        conversion.source_artifact.sha256,
        conversion.source_artifact.byte_size,
    )
    if source_key not in original_outputs:
        raise SolverEvidenceError("conversion source artifact is not a validated solver output")
    verify_artifact(run_directory, conversion.source_artifact)

    converted_by_path = {artifact.relative_path: artifact for artifact in conversion.output_artifacts}
    for artifact in conversion.output_artifacts:
        verify_artifact(run_directory, artifact)
    descriptor_artifact = converted_by_path.get("output/result_descriptor.json")
    if descriptor_artifact is None:
        raise SolverEvidenceError("conversion manifest does not declare output/result_descriptor.json")
    descriptor = ResultDescriptorV1.model_validate_json(
        (run_directory / descriptor_artifact.relative_path).read_text(encoding="utf-8")
    )
    if (
        descriptor.source_manifest_sha256 != manifest_hash
        or descriptor.source_artifact_sha256 != conversion.source_artifact.sha256
        or descriptor.source_artifact_path != conversion.source_artifact.relative_path
        or descriptor.converter_version != conversion.converter_version
    ):
        raise SolverEvidenceError("result descriptor source linkage is invalid")

    fields: list[SolverFieldV1] = []
    for declared in descriptor.fields:
        artifact = converted_by_path.get(declared.artifact_path)
        if artifact is None:
            raise SolverEvidenceError(
                f"result descriptor references undeclared conversion artifact: {declared.artifact_path}"
            )
        if declared.artifact_sha256 != artifact.sha256 or declared.artifact_byte_size != artifact.byte_size:
            raise SolverEvidenceError(f"result descriptor artifact digest mismatch: {declared.name}")
        verify_artifact(run_directory, artifact)
        fields.append(
            SolverFieldV1(
                name=declared.name,
                location=declared.location,
                components=declared.components,
                unit=declared.unit,
                artifact=artifact,
                metadata=declared.metadata,
            )
        )

    conversion_hash = hashlib.sha256(conversion_path.read_bytes()).hexdigest()
    result = SolverResultV1(
        run_id=request.run_id,
        request_id=request.request_id,
        manifest_sha256=manifest_hash,
        fields=fields,
        metadata={
            "conversion_manifest_sha256": conversion_hash,
            "converter_id": conversion.converter_id,
            "converter_version": conversion.converter_version,
            "source_solver_artifact_sha256": conversion.source_artifact.sha256,
        },
    )
    result_path = run_directory / "output" / "result.json"
    result_path.write_bytes(_canonical_json_bytes(result))
    return result
