from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from astermax.solver.contracts import (
    ArtifactDigestV1,
    SolverModelV1,
    SolverRequestV1,
    SolverRunManifestV1,
    SolverTermination,
)
from astermax.solver.errors import SolverEvidenceError
from astermax.solver.result_loader import load_solver_result


def artifact(path: Path, root: Path) -> ArtifactDigestV1:
    data = path.read_bytes()
    return ArtifactDigestV1(relative_path=path.relative_to(root).as_posix(), sha256=hashlib.sha256(data).hexdigest(), byte_size=len(data))


def make_request() -> SolverRequestV1:
    placeholder = ArtifactDigestV1(relative_path="input/x", sha256="a" * 64, byte_size=1)
    return SolverRequestV1(
        request_id="req",
        run_id="run",
        project_id="p",
        backend_id="code_aster_wsl2",
        model=SolverModelV1(model_id="m", project_id="p", analysis_type="linear_static", unit_system="SI", geometry=placeholder, mesh=placeholder, model_definition=placeholder),
    )


def persisted_manifest(tmp_path: Path, output_artifacts: list[ArtifactDigestV1]) -> SolverRunManifestV1:
    now = datetime.now(timezone.utc)
    manifest = SolverRunManifestV1(
        run_id="run",
        request_id="req",
        backend_id="code_aster_wsl2",
        backend_version="16.test",
        worker_id="worker",
        started_at=now,
        finished_at=now,
        termination=SolverTermination.SUCCEEDED,
        output_artifacts=output_artifacts,
    )
    path = tmp_path / "output" / "manifest.json"
    path.write_text(json.dumps(manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    return manifest


def test_loader_builds_result_only_from_manifest_declared_fields(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    field = output / "displacement.vtu"
    field.write_bytes(b"vtk-field-bytes")
    descriptor = output / "result_descriptor.json"
    descriptor.write_text(json.dumps({"schema_version": "ResultDescriptorV1", "fields": [{"name": "displacement", "location": "NODAL", "components": ["UX", "UY", "UZ"], "unit": "m", "artifact_path": "output/displacement.vtu"}], "reaction_artifact_paths": []}), encoding="utf-8")
    manifest = persisted_manifest(tmp_path, [artifact(field, tmp_path), artifact(descriptor, tmp_path)])
    result = load_solver_result(tmp_path, make_request(), manifest)
    assert result.fields[0].artifact.sha256 == artifact(field, tmp_path).sha256
    assert (output / "result.json").is_file()


def test_loader_rejects_descriptor_reference_not_in_manifest(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    descriptor = output / "result_descriptor.json"
    descriptor.write_text(json.dumps({"schema_version": "ResultDescriptorV1", "fields": [{"name": "displacement", "location": "NODAL", "components": ["UX"], "artifact_path": "output/untracked.vtu"}], "reaction_artifact_paths": []}), encoding="utf-8")
    manifest = persisted_manifest(tmp_path, [artifact(descriptor, tmp_path)])
    with pytest.raises(SolverEvidenceError, match="undeclared artifact"):
        load_solver_result(tmp_path, make_request(), manifest)
