from dataclasses import replace
import math

import pytest

from astermax.fea.adaptive_second_solve import (
    AdaptiveSecondSolveError,
    execute_provenance_matched_second_solve,
    verify_second_solve_evidence,
)
from astermax.fea.face_ownership import mesh_step_tet10_with_face_ownership
from astermax.fea.named_selections import capture_named_selection


def _write_box_step(tmp_path):
    gmsh = pytest.importorskip("gmsh")
    path = tmp_path / "second_solve_witness_20mm.step"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c55d_second_solve_witness")
        gmsh.model.occ.addBox(0, 0, 0, 20, 20, 20)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()
    return path


def _setup(tmp_path):
    step = _write_box_step(tmp_path)
    coarse = mesh_step_tet10_with_face_ownership(step, 10.0)
    fine = mesh_step_tet10_with_face_ownership(step, 6.0)
    assert fine.ownership_sha256 != coarse.ownership_sha256
    assert fine.elements.shape[0] > coarse.elements.shape[0]
    ordered = sorted(coarse.faces, key=lambda face: face.center_mm[0])
    support = capture_named_selection(step, [ordered[0].face_tag], "Fixed X-", "SUPPORT")
    load = capture_named_selection(step, [ordered[-1].face_tag], "Load X+", "LOAD")
    return step, coarse, fine, support, load


def test_real_provenance_matched_second_solve_produces_real_qoi_pair(tmp_path):
    step, coarse, fine, support, load = _setup(tmp_path)
    evidence, coarse_qoi, fine_qoi, assessment = execute_provenance_matched_second_solve(
        step,
        coarse,
        fine,
        support,
        load,
        baseline_target_size_mm=10.0,
        remesh_target_size_mm=6.0,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(1000.0, 0.0, 0.0),
        maximum_relative_qoi_change=10.0,
    )
    verify_second_solve_evidence(evidence)

    assert coarse_qoi.qoi_name == "MAX_DISPLACEMENT_MAGNITUDE"
    assert fine_qoi.qoi_name == coarse_qoi.qoi_name
    assert coarse_qoi.qoi_unit == "mm" and fine_qoi.qoi_unit == "mm"
    assert math.isfinite(coarse_qoi.qoi_value) and coarse_qoi.qoi_value > 0.0
    assert math.isfinite(fine_qoi.qoi_value) and fine_qoi.qoi_value > 0.0
    assert coarse_qoi.mesh_identity_sha256 != fine_qoi.mesh_identity_sha256
    assert coarse_qoi.solve_evidence_sha256 != fine_qoi.solve_evidence_sha256
    assert coarse_qoi.route_sha256 == fine_qoi.route_sha256 == evidence.route_sha256
    assert assessment.provenance_match is True
    assert assessment.refinement_order_verified is True
    assert assessment.status == "PASS"
    assert evidence.qoi_discretization_converged is True
    assert evidence.global_analysis_converged is False
    assert evidence.industrial_validation is False
    assert evidence.ansys_equivalence is False


def test_second_solve_rejects_invalid_refinement_order(tmp_path):
    step, coarse, fine, support, load = _setup(tmp_path)
    with pytest.raises(AdaptiveSecondSolveError, match="SECOND_SOLVE_REFINEMENT_ORDER"):
        execute_provenance_matched_second_solve(
            step,
            coarse,
            fine,
            support,
            load,
            baseline_target_size_mm=6.0,
            remesh_target_size_mm=10.0,
            young_modulus_mpa=200000.0,
            poisson_ratio=0.30,
            resultant_n=(1000.0, 0.0, 0.0),
            maximum_relative_qoi_change=0.05,
        )


def test_second_solve_evidence_fails_closed_on_overclaim_and_tamper(tmp_path):
    step, coarse, fine, support, load = _setup(tmp_path)
    evidence, _, _, _ = execute_provenance_matched_second_solve(
        step,
        coarse,
        fine,
        support,
        load,
        baseline_target_size_mm=10.0,
        remesh_target_size_mm=6.0,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(1000.0, 0.0, 0.0),
        maximum_relative_qoi_change=10.0,
    )
    with pytest.raises(AdaptiveSecondSolveError, match="GLOBAL_CONVERGENCE_OVERCLAIM"):
        verify_second_solve_evidence(replace(evidence, global_analysis_converged=True))
    with pytest.raises(AdaptiveSecondSolveError, match="VALIDATION_OVERCLAIM"):
        verify_second_solve_evidence(replace(evidence, ansys_equivalence=True))
    with pytest.raises(AdaptiveSecondSolveError, match="EVIDENCE_TAMPERED"):
        verify_second_solve_evidence(replace(evidence, evidence_sha256="a" * 64))
