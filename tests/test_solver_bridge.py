from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest

from astermax.solver.bridge import SolverBridge
from astermax.solver.contracts import (
    ArtifactDigestV1,
    FieldLocation,
    SolverCapabilityV1,
    SolverFieldV1,
    SolverModelV1,
    SolverRequestV1,
    SolverResultV1,
    SolverRunManifestV1,
    SolverTermination,
)
from astermax.solver.errors import SolverEvidenceError, UnsupportedSolverCapability


class StubAdapter:
    def capability(self) -> SolverCapabilityV1:
        return SolverCapabilityV1(
            backend_id="code_aster_wsl2",
            backend_version="test-stub",
            capabilities=["linear_static", "tetrahedral_solid"],
            result_field_names=["displacement", "von_mises"],
        )

    def execute(self, request: SolverRequestV1, run_directory: Path) -> SolverRunManifestV1:
        raise AssertionError("pure contract test must not execute a solver")


def digest(path: Path, root: Path) -> ArtifactDigestV1:
    data = path.read_bytes()
    return ArtifactDigestV1(
        relative_path=path.relative_to(root).as_posix(),
        sha256=hashlib.sha256(data).hexdigest(),
        byte_size=len(data),
    )


def request(required: list[str] | None = None, fields: list[str] | None = None) -> SolverRequestV1:
    placeholder = ArtifactDigestV1(relative_path="input/model.json", sha256="a" * 64, byte_size=1)
    return SolverRequestV1(
        request_id="req-1",
        run_id="run-1",
        project_id="hub-sprocket",
        backend_id="code_aster_wsl2",
        model=SolverModelV1(
            model_id="model-1",
            project_id="hub-sprocket",
            analysis_type="linear_static",
            unit_system="SI",
            geometry=placeholder,
            mesh=placeholder,
            model_definition=placeholder,
            required_capabilities=required or ["linear_static"],
        ),
        requested_fields=fields or ["displacement"],
    )


def test_bridge_fails_closed_on_missing_capability() -> None:
    bridge = SolverBridge(StubAdapter())
    with pytest.raises(UnsupportedSolverCapability, match="contact_frictional"):
        bridge.validate_request(request(required=["linear_static", "contact_frictional"]))


def test_bridge_fails_closed_on_unsupported_field() -> None:
    bridge = SolverBridge(StubAdapter())
    with pytest.raises(UnsupportedSolverCapability, match="contact_pressure"):
        bridge.validate_request(request(fields=["contact_pressure"]))


def test_bridge_accepts_only_hash_linked_solver_field(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    field_file = output_dir / "result.vtu"
    field_file.write_bytes(b"authentic-backend-artifact-placeholder-for-contract-test")
    field_artifact = digest(field_file, tmp_path)
    req = request()
    now = datetime.now(timezone.utc)
    manifest = SolverRunManifestV1(
        run_id=req.run_id,
        request_id=req.request_id,
        backend_id=req.backend_id,
        backend_version="test-stub",
        worker_id="test-stub-no-solver-execution",
        started_at=now,
        finished_at=now,
        termination=SolverTermination.SUCCEEDED,
        output_artifacts=[field_artifact],
    )
    result = SolverResultV1(
        run_id=req.run_id,
        request_id=req.request_id,
        manifest_sha256="b" * 64,
        fields=[
            SolverFieldV1(
                name="displacement",
                location=FieldLocation.NODAL,
                components=["UX", "UY", "UZ"],
                unit="m",
                artifact=field_artifact,
            )
        ],
    )
    bridge = SolverBridge(StubAdapter())
    bridge.validate_manifest(req, manifest, tmp_path)
    bridge.validate_result(req, manifest, result, tmp_path, "b" * 64)


def test_bridge_rejects_tampered_artifact(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    field_file = output_dir / "result.vtu"
    field_file.write_bytes(b"original")
    field_artifact = digest(field_file, tmp_path)
    field_file.write_bytes(b"tampered")
    req = request()
    now = datetime.now(timezone.utc)
    manifest = SolverRunManifestV1(
        run_id=req.run_id,
        request_id=req.request_id,
        backend_id=req.backend_id,
        backend_version="test-stub",
        worker_id="test-stub-no-solver-execution",
        started_at=now,
        finished_at=now,
        termination=SolverTermination.SUCCEEDED,
        output_artifacts=[field_artifact],
    )
    with pytest.raises(SolverEvidenceError, match="digest mismatch"):
        SolverBridge(StubAdapter()).validate_manifest(req, manifest, tmp_path)
