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
from astermax.solver.result_conversion import convert_rmed_result
from astermax.solver.result_loader import load_converted_solver_result
from test_med_result import build_structural_med


def artifact(path: Path, root: Path, media_type: str | None = None) -> ArtifactDigestV1:
    data = path.read_bytes()
    return ArtifactDigestV1(
        relative_path=path.relative_to(root).as_posix(),
        sha256=hashlib.sha256(data).hexdigest(),
        byte_size=len(data),
        media_type=media_type,
    )


def make_request() -> SolverRequestV1:
    placeholder = ArtifactDigestV1(relative_path="input/x", sha256="a" * 64, byte_size=1)
    return SolverRequestV1(
        request_id="req",
        run_id="run",
        project_id="p",
        backend_id="code_aster_wsl2",
        model=SolverModelV1(
            model_id="m",
            project_id="p",
            analysis_type="linear_static",
            unit_system="SI",
            geometry=placeholder,
            mesh=placeholder,
            model_definition=placeholder,
        ),
        requested_fields=["displacement", "stress"],
    )


def persist_manifest(root: Path, source: ArtifactDigestV1) -> SolverRunManifestV1:
    now = datetime.now(timezone.utc)
    manifest = SolverRunManifestV1(
        run_id="run",
        request_id="req",
        backend_id="code_aster_wsl2",
        backend_version="18.1.0",
        worker_id="worker",
        started_at=now,
        finished_at=now,
        termination=SolverTermination.SUCCEEDED,
        output_artifacts=[source],
    )
    (root / "output" / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return manifest


def test_conversion_manifest_links_solver_rmed_descriptor_and_vtu(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    rmed = output / "solver.rmed"
    build_structural_med(rmed)
    source = artifact(rmed, tmp_path, "application/x-med")
    manifest = persist_manifest(tmp_path, source)
    request = make_request()

    conversion = convert_rmed_result(
        tmp_path,
        request,
        manifest,
        source_relative_path="output/solver.rmed",
    )
    assert conversion.source_artifact.sha256 == source.sha256
    assert {item.relative_path for item in conversion.output_artifacts} == {
        "output/result.vtu",
        "output/result_descriptor.json",
    }

    result = load_converted_solver_result(tmp_path, request, manifest)
    assert result.manifest_sha256 == conversion.source_run_manifest_sha256
    assert [field.location.value for field in result.fields] == ["NODAL", "ELEMENT_NODAL"]
    assert all(field.artifact.relative_path == "output/result.vtu" for field in result.fields)
    assert result.metadata["converter_version"] == "astermax-med3-v1"


def test_converted_loader_rejects_vtu_mutation(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    rmed = output / "solver.rmed"
    build_structural_med(rmed)
    source = artifact(rmed, tmp_path)
    manifest = persist_manifest(tmp_path, source)
    request = make_request()

    convert_rmed_result(
        tmp_path,
        request,
        manifest,
        source_relative_path="output/solver.rmed",
    )
    (output / "result.vtu").write_text("tampered", encoding="utf-8")
    with pytest.raises(SolverEvidenceError, match="artifact digest mismatch"):
        load_converted_solver_result(tmp_path, request, manifest)
