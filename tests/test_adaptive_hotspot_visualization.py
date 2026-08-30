import math
import pytest

from astermax.fea.face_ownership import mesh_step_tet10_with_face_ownership
from astermax.fea.named_selections import capture_named_selection
from astermax.fea.one_click_adaptive_loop import prepare_one_click_adaptive_run, approve_one_click_adaptive_run
from astermax.fea.solution_driven_local_loop import prepare_solution_driven_local_proposal, approve_solution_driven_local_proposal, execute_solution_driven_local_loop
from astermax.fea.adaptive_hotspot_visualization import build_adaptive_hotspot_visualization


def _write_box_step(tmp_path):
    gmsh = pytest.importorskip("gmsh")
    path = tmp_path / "hotspot_visualization_20mm.step"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c55o_hotspot_visualization")
        gmsh.model.occ.addBox(0, 0, 0, 20, 20, 20)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()
    return path


def test_real_closed_loop_builds_native_hotspot_projection(tmp_path):
    step = _write_box_step(tmp_path)
    witness = mesh_step_tet10_with_face_ownership(step, 8.0)
    faces = sorted(witness.faces, key=lambda f: f.center_mm[0])
    support = capture_named_selection(step, [faces[0].face_tag], "Fixed X-", "SUPPORT")
    load = capture_named_selection(step, [faces[-1].face_tag], "Load X+", "LOAD")
    run = prepare_one_click_adaptive_run(step, support, load, baseline_target_size_mm=8.0, refined_target_size_mm=4.0, young_modulus_mpa=200000.0, poisson_ratio=0.30, resultant_n=(1000.0, 250.0, 0.0), maximum_relative_qoi_change=10.0)
    run_approval = approve_one_click_adaptive_run(run, approver="Harness Reviewer", approved=True)
    proposal, plan, baseline, baseline_solved, baseline_indicator = prepare_solution_driven_local_proposal(step, support, load, run, run_approval, maximum_candidates=3, influence_radius_factor=1.5)
    approval = approve_solution_driven_local_proposal(proposal, plan, approver="Harness Reviewer", approved=True)
    loop, refined = execute_solution_driven_local_loop(step, support, load, run, run_approval, proposal, plan, approval, baseline, baseline_solved, baseline_indicator, output_msh_path=tmp_path / "c55o_local.msh", maximum_indicator_candidates=3)
    view = build_adaptive_hotspot_visualization(proposal=proposal, plan=plan, baseline=baseline, refined=refined, baseline_indicator=baseline_indicator, loop_evidence=loop)
    assert view.status == "READY"
    assert view.baseline_mesh_sha256 == baseline.ownership_sha256
    assert view.refined_mesh_sha256 == refined.ownership_sha256
    assert view.refined_element_count > 0 and view.baseline_element_count > 0
    assert len(view.hotspot_markers) == len(plan.regions) == 3
    assert all(math.isfinite(v.normalized_indicator) and v.normalized_indicator > 0 for v in view.hotspot_markers)
    assert view.indicator_status in {"REDUCED", "NOT_REDUCED"}
    assert view.qoi_status in {"PASS", "FAIL"}
    assert view.claims["hotspots_from_computed_solution"] is True
    assert view.claims["refinement_regions_executed"] is True
    assert view.claims["estimator_certified"] is False
    assert view.claims["global_analysis_converged"] is False
    assert view.claims["ansys_equivalence"] is False
    assert len(view.visualization_sha256) == 64
