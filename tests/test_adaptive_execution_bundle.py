import pytest
from dataclasses import replace

from astermax.fea.adaptive_execution_bundle import AdaptiveExecutionBundleError, bind_native_adaptive_results, build_adaptive_execution_artifact_bundle, verify_adaptive_execution_artifact_bundle
from astermax.fea.face_ownership import mesh_step_tet10_with_face_ownership
from astermax.fea.named_selections import capture_named_selection
from astermax.fea.one_click_adaptive_loop import approve_one_click_adaptive_run, prepare_one_click_adaptive_run
from astermax.fea.solution_driven_local_loop import approve_solution_driven_local_proposal, execute_solution_driven_local_loop, prepare_solution_driven_local_proposal


def _write_box_step(tmp_path):
    gmsh = pytest.importorskip("gmsh")
    path = tmp_path / "artifact_bundle_20mm.step"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c55q_bundle")
        gmsh.model.occ.addBox(0, 0, 0, 20, 20, 20)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()
    return path


def _real_bundle(tmp_path):
    step = _write_box_step(tmp_path)
    witness = mesh_step_tet10_with_face_ownership(step, 8.0)
    ordered = sorted(witness.faces, key=lambda face: face.center_mm[0])
    support = capture_named_selection(step, [ordered[0].face_tag], "Fixed X-", "SUPPORT")
    load = capture_named_selection(step, [ordered[-1].face_tag], "Load X+", "LOAD")
    run = prepare_one_click_adaptive_run(step, support, load, baseline_target_size_mm=8.0, refined_target_size_mm=4.0, young_modulus_mpa=200000.0, poisson_ratio=0.30, resultant_n=(1000.0, 250.0, 0.0), maximum_relative_qoi_change=10.0)
    run_approval = approve_one_click_adaptive_run(run, approver="Harness Reviewer", approved=True)
    proposal, plan, baseline, baseline_solved, baseline_indicator = prepare_solution_driven_local_proposal(step, support, load, run, run_approval, maximum_candidates=3, influence_radius_factor=1.5)
    approval = approve_solution_driven_local_proposal(proposal, plan, approver="Harness Reviewer", approved=True)
    loop, refined, refined_solved, refined_indicator, coarse_qoi, fine_qoi, qoi = execute_solution_driven_local_loop(step, support, load, run, run_approval, proposal, plan, approval, baseline, baseline_solved, baseline_indicator, output_msh_path=tmp_path / "bundle_refined.msh", maximum_indicator_candidates=3, return_artifacts=True)
    assert coarse_qoi.solve_evidence_sha256 == loop.baseline_solve_evidence_sha256
    assert fine_qoi.solve_evidence_sha256 == loop.refined_solve_evidence_sha256
    assert qoi.assessment_sha256 == loop.qoi_assessment_sha256
    bundle = build_adaptive_execution_artifact_bundle(loop_evidence=loop, proposal=proposal, plan=plan, baseline_mesh=baseline, refined_mesh=refined, baseline_solved=baseline_solved, refined_solved=refined_solved, baseline_indicator=baseline_indicator, refined_indicator=refined_indicator, displacement_scale=1.0)
    return bundle, loop


def test_real_bundle_uses_same_execution_results_and_binds_views(tmp_path):
    bundle, loop = _real_bundle(tmp_path)
    verify_adaptive_execution_artifact_bundle(bundle)
    assert bundle.baseline_solve_evidence_sha256 == loop.baseline_solve_evidence_sha256
    assert bundle.refined_solve_evidence_sha256 == loop.refined_solve_evidence_sha256
    assert bundle.claims["result_fields_carried_without_replay"] is True
    assert bundle.baseline_solved["result"].displacement_mm.flags.writeable is False
    assert bundle.refined_solved["result"].integration_point_von_mises_mpa.flags.writeable is False
    seen = []
    receipt = bind_native_adaptive_results(bundle, hotspot_binder=lambda view: seen.append(view.visualization_sha256), stress_binder=lambda view: seen.append(view.comparison_sha256))
    assert receipt.bound_tabs == ("Adaptive Hotspots", "Stress Compare")
    assert seen == [bundle.hotspot_visualization_sha256, bundle.stress_comparison_sha256]


def test_bundle_result_arrays_are_read_only(tmp_path):
    bundle, _ = _real_bundle(tmp_path)
    with pytest.raises(ValueError):
        bundle.baseline_solved["result"].displacement_mm[0, 0] = 123.0


def test_bundle_rejects_stale_hash_and_overclaim(tmp_path):
    bundle, _ = _real_bundle(tmp_path)
    stale = replace(bundle, refined_result_field_sha256="f" * 64)
    with pytest.raises(AdaptiveExecutionBundleError, match="REFINED_RESULT_MUTATED"):
        verify_adaptive_execution_artifact_bundle(stale)
    claims = dict(bundle.claims)
    claims["ansys_equivalence"] = True
    with pytest.raises(AdaptiveExecutionBundleError, match="VALIDATION_OVERCLAIM"):
        verify_adaptive_execution_artifact_bundle(replace(bundle, claims=claims))
