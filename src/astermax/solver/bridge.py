from __future__ import annotations

import hashlib
from pathlib import Path

from astermax.solver.adapter import SolverAdapter
from astermax.solver.contracts import (
    ArtifactDigestV1,
    SolverRequestV1,
    SolverResultV1,
    SolverRunManifestV1,
    SolverTermination,
)
from astermax.solver.errors import SolverEvidenceError, UnsupportedSolverCapability


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def verify_artifact(root: Path, artifact: ArtifactDigestV1) -> None:
    candidate = (root / artifact.relative_path).resolve()
    root = root.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise SolverEvidenceError(f"artifact escapes run directory: {artifact.relative_path}") from exc
    if not candidate.is_file():
        raise SolverEvidenceError(f"missing solver artifact: {artifact.relative_path}")
    actual_hash, actual_size = _hash_file(candidate)
    if actual_hash != artifact.sha256 or actual_size != artifact.byte_size:
        raise SolverEvidenceError(f"artifact digest mismatch: {artifact.relative_path}")


class SolverBridge:
    """Deterministic boundary between AsterMax and a solver backend."""

    def __init__(self, adapter: SolverAdapter) -> None:
        self.adapter = adapter

    def validate_request(self, request: SolverRequestV1) -> None:
        capability = self.adapter.capability()
        if capability.backend_id != request.backend_id:
            raise UnsupportedSolverCapability(
                f"request backend {request.backend_id!r} does not match adapter {capability.backend_id!r}"
            )
        missing = sorted(set(request.model.required_capabilities) - set(capability.capabilities))
        if missing:
            raise UnsupportedSolverCapability("missing solver capabilities: " + ", ".join(missing))
        unsupported_fields = sorted(set(request.requested_fields) - set(capability.result_field_names))
        if unsupported_fields:
            raise UnsupportedSolverCapability("unsupported result fields: " + ", ".join(unsupported_fields))

    def validate_manifest(self, request: SolverRequestV1, manifest: SolverRunManifestV1, run_directory: Path) -> None:
        if manifest.run_id != request.run_id or manifest.request_id != request.request_id:
            raise SolverEvidenceError("manifest identity does not match request")
        if manifest.backend_id != request.backend_id:
            raise SolverEvidenceError("manifest backend does not match request")
        if manifest.termination != SolverTermination.SUCCEEDED:
            raise SolverEvidenceError(f"solver did not succeed: {manifest.termination.value}")
        for artifact in [*manifest.input_artifacts, *manifest.output_artifacts]:
            verify_artifact(run_directory, artifact)
        if manifest.stdout_artifact is not None:
            verify_artifact(run_directory, manifest.stdout_artifact)
        if manifest.stderr_artifact is not None:
            verify_artifact(run_directory, manifest.stderr_artifact)

    def validate_result(
        self,
        request: SolverRequestV1,
        manifest: SolverRunManifestV1,
        result: SolverResultV1,
        run_directory: Path,
        manifest_sha256: str,
    ) -> None:
        if result.run_id != request.run_id or result.request_id != request.request_id:
            raise SolverEvidenceError("result identity does not match request")
        if result.manifest_sha256 != manifest_sha256:
            raise SolverEvidenceError("result manifest hash does not match validated manifest")
        available_outputs = {(a.relative_path, a.sha256) for a in manifest.output_artifacts}
        for field in result.fields:
            key = (field.artifact.relative_path, field.artifact.sha256)
            if key not in available_outputs:
                raise SolverEvidenceError(f"field artifact is not declared by manifest: {field.name}")
            verify_artifact(run_directory, field.artifact)
        for artifact in result.reaction_artifacts:
            key = (artifact.relative_path, artifact.sha256)
            if key not in available_outputs:
                raise SolverEvidenceError("reaction artifact is not declared by manifest")
            verify_artifact(run_directory, artifact)
