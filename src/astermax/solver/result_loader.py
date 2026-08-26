from __future__ import annotations

import hashlib
import json
from pathlib import Path

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
from astermax.solver.errors import SolverEvidenceError


class ResultFieldDescriptorV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    location: FieldLocation
    components: list[str] = Field(min_length=1)
    unit: str | None = None
    artifact_path: str = Field(min_length=1)


class ResultDescriptorV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="ResultDescriptorV1", pattern=r"^ResultDescriptorV1$")
    fields: list[ResultFieldDescriptorV1] = Field(min_length=1)
    reaction_artifact_paths: list[str] = Field(default_factory=list)


def _canonical_json_bytes(model: BaseModel) -> bytes:
    return (json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def load_solver_result(
    run_directory: Path,
    request: SolverRequestV1,
    manifest: SolverRunManifestV1,
) -> SolverResultV1:
    run_directory = run_directory.resolve()
    if manifest.termination != SolverTermination.SUCCEEDED:
        raise SolverEvidenceError("cannot load result from non-successful solver manifest")

    manifest_path = run_directory / "output" / "manifest.json"
    if not manifest_path.is_file():
        raise SolverEvidenceError("missing persisted solver manifest")
    persisted = SolverRunManifestV1.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if persisted != manifest:
        raise SolverEvidenceError("persisted solver manifest differs from validated manifest")
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

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
