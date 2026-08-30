from dataclasses import replace

import pytest

from astermax.fea.adaptive_demo_session import build_adaptive_demo_session
from astermax.fea.adaptive_results_dashboard import (
    AdaptiveResultsDashboardError,
    build_adaptive_results_dashboard,
    load_adaptive_demo_session_json,
    save_adaptive_demo_session_json,
)
from astermax.fea.adaptive_second_solve import execute_provenance_matched_second_solve
from astermax.fea.face_ownership import mesh_step_tet10_with_face_ownership
from astermax.fea.named_selections import capture_named_selection


def _write_box_step(tmp_path):
    gmsh = pytest.importorskip("gmsh")
    path = tmp_path / "adaptive_dashboard_20mm.step"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c55j_dashboard")
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
    ordered = sorted(coarse.faces, key=lambda face: face.center_mm[0])
    support = capture_named_selection(step, [ordered[0].face_tag], "Fixed X-", "SUPPORT")
    load = capture_named_selection(step, [ordered[-1].face_tag], "Load X+", "LOAD")
    evidence, coarse_qoi, fine_qoi, assessment = execute_provenance_matched_second_solve(
        step, coarse, fine, support, load,
        baseline_target_size_mm=10.0,
        remesh_target_size_mm=6.0,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(1000.0, 0.0, 0.0),
        maximum_relative_qoi_change=10.0,
    )
    return build_adaptive_demo_session(evidence, coarse_qoi, fine_qoi, assessment)


def test_real_two_solve_session_projects_to_native_results_dashboard(tmp_path):
    session = _real_session(tmp_path)
    dashboard = build_adaptive_results_dashboard(session)
    assert dashboard.schema == "AsterMaxNativeAdaptiveResultsDashboardV1"
    assert dashboard.status == "READY"
    assert dashboard.session_sha256 == session.session_sha256
    assert len(dashboard.metrics) == 3
    assert dashboard.metrics[0].baseline_value == pytest.approx(session.baseline_qoi_value)
    assert dashboard.metrics[0].refined_value == pytest.approx(session.remesh_qoi_value)
    assert dashboard.metrics[0].relative_change == pytest.approx(session.qoi_relative_change)
    assert len(dashboard.stages) == 9 and all(stage.status == "READY" for stage in dashboard.stages)
    assert dashboard.claims["global_analysis_converged"] is False
    assert dashboard.claims["industrial_validation"] is False
    assert dashboard.claims["ansys_equivalence"] is False


def test_verified_session_json_roundtrip_preserves_dashboard_identity(tmp_path):
    session = _real_session(tmp_path)
    path = save_adaptive_demo_session_json(session, tmp_path / "adaptive_session.json")
    loaded = load_adaptive_demo_session_json(path)
    assert loaded.session_sha256 == session.session_sha256
    assert build_adaptive_results_dashboard(loaded).session_sha256 == session.session_sha256


def test_dashboard_fails_closed_on_tampered_session(tmp_path):
    session = _real_session(tmp_path)
    with pytest.raises(AdaptiveResultsDashboardError, match="SESSION_TAMPERED"):
        build_adaptive_results_dashboard(replace(session, baseline_qoi_value=session.baseline_qoi_value * 2.0))
