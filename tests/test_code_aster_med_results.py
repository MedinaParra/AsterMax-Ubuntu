from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import meshio
import numpy as np
import pytest

from astermax.code_aster_med_results import (
    CodeAsterMedResultError,
    build_code_aster_cae_scene,
    read_verified_code_aster_nodal_results,
)
from astermax.code_aster_reference_run import GenuineReferenceSolveEvidence


def _mesh() -> meshio.Mesh:
    points = np.array([
        [0.0, 0.0, 0.0],
        [10.0, 0.0, 0.0],
        [0.0, 10.0, 0.0],
        [0.0, 0.0, 10.0],
        [5.0, 0.0, 0.0],
        [5.0, 5.0, 0.0],
        [0.0, 5.0, 0.0],
        [0.0, 0.0, 5.0],
        [0.0, 5.0, 5.0],
        [5.0, 0.0, 5.0],
    ])
    tet10 = np.array([[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]], dtype=int)
    displacement = np.zeros((10, 3), dtype=float)
    displacement[:, 0] = np.linspace(0.0, 0.025, 10)
    mises = np.linspace(45.0, 50.0, 10)
    return meshio.Mesh(
        points=points,
        cells=[("tetra10", tet10)],
        point_data={
            "result_DEPL": displacement,
            "result_SIEQ_NOEU": mises,
        },
    )


def _evidence(result_hash: str) -> GenuineReferenceSolveEvidence:
    h = "a" * 64
    return GenuineReferenceSolveEvidence(
        engine_kind="CODE_ASTER_WSL2_WINDOWS_HOST",
        distribution="Ubuntu",
        export_sha256=h,
        command_sha256=h,
        input_med_sha256=h,
        mesh_quality_report_sha256=h,
        mesh_quality_artifact_sha256=h,
        reference_case_evidence_sha256=h,
        result_med_sha256=result_hash,
        message_sha256=h,
        displacement_table_sha256=h,
        reaction_table_sha256=h,
        stress_table_sha256=h,
        solver_stdout_sha256=h,
        returncode=0,
        message_diagnostic_ok=True,
        message_execution_exit_code=0,
        runtime_qualified=True,
        runtime_attested_immediately_before_solve=True,
        mesh_attested_immediately_before_solve=True,
        run_aster_sha256=h,
        config_sha256=h,
        detected_version="17.x-test-double",
        fea_solve_executed=True,
        numerical_verification=True,
        results_verified=True,
        ux_relative_error=0.0,
        reaction_relative_error=0.0,
        stress_relative_error=0.0,
    )


def _write(tmp_path: Path, mesh: meshio.Mesh | None = None) -> Path:
    path = tmp_path / "astermax_result.med"
    meshio.write(path, mesh or _mesh(), file_format="med")
    return path


def test_verified_result_med_builds_code_aster_noeu_scene(tmp_path: Path):
    path = _write(tmp_path)
    digest = sha256(path.read_bytes()).hexdigest()
    evidence = _evidence(digest)
    result = read_verified_code_aster_nodal_results(path, evidence)
    assert result.field_location == "NOEU"
    assert result.displacement_mm.shape == (10, 3)
    assert result.von_mises_mpa.shape == (10,)
    assert "DEPL" in result.displacement_field_name.upper()
    assert "SIEQ_NOEU" in result.von_mises_field_name.upper()

    scene = build_code_aster_cae_scene(result, evidence, deformation_scale=10.0)
    assert scene.length_unit == "mm"
    assert scene.stress_unit == "MPa"
    assert scene.deformation_scale == 10.0
    assert scene.surface_triangles.shape[1] == 3
    assert "CODE_ASTER_SIEQ_NOEU" in scene.stress_representation
    assert scene.workspace_sha256 == digest


def test_result_med_hash_mismatch_fails_closed(tmp_path: Path):
    path = _write(tmp_path)
    with pytest.raises(CodeAsterMedResultError, match="HASH_MISMATCH"):
        read_verified_code_aster_nodal_results(path, _evidence("0" * 64))


def test_unverified_solve_cannot_enter_professional_scene(tmp_path: Path):
    path = _write(tmp_path)
    digest = sha256(path.read_bytes()).hexdigest()
    evidence = replace(_evidence(digest), results_verified=False)
    with pytest.raises(CodeAsterMedResultError, match="SOLVE_NOT_VERIFIED"):
        read_verified_code_aster_nodal_results(path, evidence)


def test_elno_only_stress_is_not_silently_promoted_to_noeu(tmp_path: Path):
    mesh = _mesh()
    mesh.point_data.pop("result_SIEQ_NOEU")
    # A cell-supported stress field exists, but the scene bridge must not invent a
    # nodal projection and call it native Code_Aster NOEU evidence.
    mesh.cell_data["result_SIEQ_ELNO"] = [np.array([50.0], dtype=float)]
    path = _write(tmp_path, mesh)
    digest = sha256(path.read_bytes()).hexdigest()
    with pytest.raises(CodeAsterMedResultError, match="FIELD_MISSING:SIEQ_NOEU"):
        read_verified_code_aster_nodal_results(path, _evidence(digest))


def test_ambiguous_nodal_fields_fail_closed(tmp_path: Path):
    mesh = _mesh()
    mesh.point_data["second_DEPL"] = np.asarray(mesh.point_data["result_DEPL"]).copy()
    path = _write(tmp_path, mesh)
    digest = sha256(path.read_bytes()).hexdigest()
    with pytest.raises(CodeAsterMedResultError, match="FIELD_AMBIGUOUS:DEPL"):
        read_verified_code_aster_nodal_results(path, _evidence(digest))
