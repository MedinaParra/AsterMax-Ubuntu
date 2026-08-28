from pathlib import Path

import numpy as np
import pytest

from astermax.app import run_step_analysis
from astermax.fea.gmsh_bridge import _gmsh, mesh_step_tet10
from astermax.fea.live_analysis_evidence import build_live_analysis_evidence, file_sha256
from astermax.fea.model_preparation_evidence import (
    ModelPreparationEvidenceError,
    build_model_preparation_evidence,
    capture_axis_face_selection,
    evaluate_tet10_mesh_preparation_gate,
)
from astermax.fea.tet10 import straight_sided_tet10_from_vertices


def _write_box(path: Path, *, dx: float = 100.0, dy: float = 20.0, dz: float = 10.0) -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c4_3_fixture")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, dx, dy, dz)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def test_straight_tet10_mesh_gate_reports_positive_gauss_point_jacobians() -> None:
    vertices = np.asarray(
        [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 10.0]],
        dtype=float,
    )
    nodes = straight_sided_tet10_from_vertices(vertices)
    gate = evaluate_tet10_mesh_preparation_gate(nodes, np.arange(10, dtype=np.int64)[None, :])
    assert gate.tet10_count == 1
    assert gate.integration_point_count == 4
    assert gate.minimum_det_jacobian_mm3 > 0.0
    assert gate.positive_jacobian_fraction == 1.0
    assert gate.maximum_midside_deviation_mm == pytest.approx(0.0, abs=1.0e-14)
    assert gate.straight_sided_verified is True
    assert gate.positive_jacobian_verified is True
    assert len(gate.gate_sha256) == 64


def test_curved_midside_node_fails_closed_before_solver_claim() -> None:
    vertices = np.asarray(
        [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 10.0]],
        dtype=float,
    )
    nodes = straight_sided_tet10_from_vertices(vertices)
    nodes[4, 2] += 0.05
    with pytest.raises(ModelPreparationEvidenceError, match="CURVED_TET10_OUTSIDE_VERIFICATION_SCOPE"):
        evaluate_tet10_mesh_preparation_gate(nodes, np.arange(10, dtype=np.int64)[None, :])


def test_axis_scopes_are_persistent_and_bound_to_exact_step(tmp_path: Path) -> None:
    step = tmp_path / "box.step"
    _write_box(step)
    diagonal = float(np.linalg.norm([100.0, 20.0, 10.0]))
    support = capture_axis_face_selection(
        step, axis=0, side="MIN", expected_coordinate_mm=0.0,
        model_diagonal_mm=diagonal, selection_id="CURRENT_MODEL_X_MIN_CONSTRAINT",
    )
    load = capture_axis_face_selection(
        step, axis=0, side="MAX", expected_coordinate_mm=100.0,
        model_diagonal_mm=diagonal, selection_id="CURRENT_MODEL_X_MAX_LOAD",
    )
    assert support.source_sha256 == load.source_sha256 == file_sha256(step)
    assert support.selection_sha256 != load.selection_sha256
    assert support.signature.center_mm[0] == pytest.approx(0.0, abs=1.0e-8)
    assert load.signature.center_mm[0] == pytest.approx(100.0, abs=1.0e-8)
    assert support.signature.area_mm2 == pytest.approx(200.0, rel=1.0e-9)
    assert load.signature.area_mm2 == pytest.approx(200.0, rel=1.0e-9)


def test_full_step_to_model_preparation_snapshot_is_deterministic(tmp_path: Path) -> None:
    step = tmp_path / "box.step"
    _write_box(step)
    mesh = mesh_step_tet10(step, 10.0)
    kwargs = dict(
        step_path=step,
        step_sha256=file_sha256(step),
        bbox_mm=mesh.bbox_mm,
        nodes_mm=mesh.nodes_mm,
        elements=mesh.elements,
    )
    first = build_model_preparation_evidence(**kwargs)
    second = build_model_preparation_evidence(**kwargs)
    assert first.snapshot_sha256 == second.snapshot_sha256
    assert first.step_sha256 == file_sha256(step)
    assert first.constraint_selection_sha256 != first.load_selection_sha256
    assert first.mesh_gate["positive_jacobian_verified"] is True
    assert first.mesh_gate["straight_sided_verified"] is True
    assert first.mesh_gate["tet10_count"] == mesh.elements.shape[0]
    assert "NOT_GENERAL_CAD_NAMED_SELECTIONS" in first.evidence_boundary


def test_wrong_step_hash_cannot_bind_preparation_evidence(tmp_path: Path) -> None:
    step = tmp_path / "box.step"
    _write_box(step)
    mesh = mesh_step_tet10(step, 20.0)
    with pytest.raises(ModelPreparationEvidenceError, match="source SHA"):
        build_model_preparation_evidence(
            step,
            step_sha256="0" * 64,
            bbox_mm=mesh.bbox_mm,
            nodes_mm=mesh.nodes_mm,
            elements=mesh.elements,
        )


def test_run_step_analysis_binds_real_preparation_solve_and_artifact_chain(tmp_path: Path) -> None:
    step = tmp_path / "box.step"
    _write_box(step, dx=60.0, dy=20.0, dz=10.0)
    summary = run_step_analysis(
        step,
        tmp_path / "result",
        mesh_size_mm=20.0,
        resultant_n=(1000.0, 0.0, 0.0),
    )
    preparation = summary["model_preparation"]
    assert preparation["step_sha256"] == summary["source_step_sha256"] == file_sha256(step)
    assert preparation["constraint_selection_sha256"] != preparation["load_selection_sha256"]
    assert preparation["mesh_gate"]["positive_jacobian_verified"] is True
    assert preparation["mesh_gate"]["straight_sided_verified"] is True
    assert preparation["mesh_gate"]["tet10_count"] == summary["mesh"]["elements"]
    assert Path(summary["artifacts"]["vtu"]).is_file()
    assert Path(summary["artifacts"]["viewer"]).is_file()
    live = build_live_analysis_evidence(summary)
    assert live.step_sha256 == summary["source_step_sha256"]
    assert live.preparation_snapshot_sha256 == preparation["snapshot_sha256"]
    assert live.converged is False
    assert live.industrial_validation is False
    assert live.ansys_equivalence is False
