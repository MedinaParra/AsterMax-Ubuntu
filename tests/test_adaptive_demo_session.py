from dataclasses import replace
import math

import pytest

from astermax.fea.adaptive_demo_session import (
    AdaptiveDemoSessionError,
    build_adaptive_demo_session,
    verify_adaptive_demo_session,
)
from astermax.fea.adaptive_second_solve import execute_provenance_matched_second_solve
from astermax.fea.face_ownership import mesh_step_tet10_with_face_ownership
from astermax.fea.named_selections import capture_named_selection


def _write_box_step(tmp_path):
    gmsh = pytest.importorskip("gmsh")
    path = tmp_path / "adaptive_demo_witness_20mm.step"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c55i_adaptive_demo")
        gmsh.model.occ.addBox(0, 0, 0, 20, 20, 20)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()
    return path


def _real_session(tmp_path):
    step = _write_box_step(tmp_path)
    coarse = mesh_step_tet10_with_face_ownership(step, 10.0)
    fine = mesh_step_tet10_with_face_ownership(step, 6.0)
    assert fine.elements.shape[0] > coarse.elements.shape[0]
    ordered = sorted(coarse.faces, key=lambda face: face.center_mm[0])
    support = capture_named_selection(step, [ordered[0].face_tag], "Fixed X-", "SUPPORT")
    load = capture_named_selection(step, [ordered[-1].face_tag], "Load X+", "LOAD")
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
    session = build_adaptive_demo_session(evidence, coarse_qoi, fine_qoi, assessment)
    return session, evidence, coarse_qoi, fine_qoi, assessment


def test_native_adaptive_demo_session_consumes_real_two_solve_evidence(tmp_path):
    session, evidence, coarse_qoi, fine_qoi, assessment = _real_session(tmp_path)
    verify_adaptive_demo_session(session)

    assert session.schema == "AsterMaxNativeAdaptiveDemoSessionV1"
    assert session.status == "READY"
    assert session.stage_count == session.ready_stage_count == 9
    assert session.progress_percent == 100
    assert [stage.name for stage in session.stages] == [
        "CAD_STEP_MM",
        "PHYSICS_ROUTE",
        "BASELINE_TET10",
        "BASELINE_SOLVE",
        "PERSISTENT_REBINDING",
        "REFINED_TET10",
        "REFINED_SOLVE",
        "QOI_COMPARISON",
        "ENGINEERING_EVIDENCE",
    ]
    assert session.baseline_mesh_sha256 != session.remesh_mesh_sha256
    assert session.baseline_solve_evidence_sha256 != session.remesh_solve_evidence_sha256
    assert session.baseline_qoi_value == pytest.approx(coarse_qoi.qoi_value)
    assert session.remesh_qoi_value == pytest.approx(fine_qoi.qoi_value)
    assert session.qoi_relative_change == pytest.approx(assessment.relative_change)
    assert math.isfinite(session.baseline_qoi_value) and session.baseline_qoi_value > 0.0
    assert math.isfinite(session.remesh_qoi_value) and session.remesh_qoi_value > 0.0
    assert session.claims["qoi_discretization_converged"] == evidence.qoi_discretization_converged
    assert session.claims["global_analysis_converged"] is False
    assert session.claims["industrial_validation"] is False
    assert session.claims["ansys_equivalence"] is False


def test_adaptive_demo_fails_closed_on_stale_qoi_provenance(tmp_path):
    _, evidence, coarse_qoi, fine_qoi, assessment = _real_session(tmp_path)
    stale = replace(fine_qoi, observation_sha256="f" * 64)
    with pytest.raises(AdaptiveDemoSessionError, match="REMESH_QOI_PROVENANCE"):
        build_adaptive_demo_session(evidence, coarse_qoi, stale, assessment)


def test_adaptive_demo_session_rejects_tamper_and_claim_overreach(tmp_path):
    session, _, _, _, _ = _real_session(tmp_path)
    with pytest.raises(AdaptiveDemoSessionError, match="SESSION_TAMPERED"):
        verify_adaptive_demo_session(replace(session, session_sha256="a" * 64))
    claims = dict(session.claims)
    claims["ansys_equivalence"] = True
    with pytest.raises(AdaptiveDemoSessionError, match="OVERCLAIM"):
        verify_adaptive_demo_session(replace(session, claims=claims))
