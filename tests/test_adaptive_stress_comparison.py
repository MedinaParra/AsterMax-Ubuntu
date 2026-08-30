from dataclasses import replace

import math
import pytest

from astermax.fea.adaptive_stress_comparison import (
    AdaptiveStressComparisonError,
    build_verified_adaptive_stress_comparison,
    verify_adaptive_stress_comparison,
)
from astermax.fea.face_ownership import mesh_step_tet10_with_face_ownership
from astermax.fea.named_selections import capture_named_selection
from astermax.fea.one_click_adaptive_loop import prepare_one_click_adaptive_run, approve_one_click_adaptive_run
from astermax.fea.solution_driven_local_loop import (
    _solve_inventory,
    approve_solution_driven_local_proposal,
    execute_solution_driven_local_loop,
    prepare_solution_driven_local_proposal,
)


def _write_box_step(tmp_path):
    gmsh = pytest.importorskip("gmsh")
    path = tmp_path / "stress_compare_20mm.step"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c55p_stress_compare")
        gmsh.model.occ.addBox(0, 0, 0, 20, 20, 20)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()
    return path


def _real_comparison(tmp_path):
    step = _write_box_step(tmp_path)
    witness = mesh_step_tet10_with_face_ownership(step, 8.0)
    ordered = sorted(witness.faces, key=lambda face: face.center_mm[0])
    support = capture_named_selection(step, [ordered[0].face_tag], "Fixed X-", "SUPPORT")
    load = capture_named_selection(step, [ordered[-1].face_tag], "Load X+", "LOAD")
    run = prepare_one_click_adaptive_run(
        step, support, load,
        baseline_target_size_mm=8.0,
        refined_target_size_mm=4.0,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(1000.0, 250.0, 0.0),
        maximum_relative_qoi_change=10.0,
    )
    run_approval = approve_one_click_adaptive_run(run, approver="Harness Reviewer", approved=True)
    proposal, plan, baseline, baseline_solved, baseline_indicator = prepare_solution_driven_local_proposal(
        step, support, load, run, run_approval, maximum_candidates=3, influence_radius_factor=1.5
    )
    approval = approve_solution_driven_local_proposal(proposal, plan, approver="Harness Reviewer", approved=True)
    loop, refined = execute_solution_driven_local_loop(
        step, support, load, run, run_approval, proposal, plan, approval, baseline, baseline_solved, baseline_indicator,
        output_msh_path=tmp_path / "stress_compare_refined.msh",
        maximum_indicator_candidates=3,
    )
    # Deterministic evidence replay used only by the harness to recover the exact
    # refined result object hidden by C5.5n's compact public return contract.
    refined_solved = _solve_inventory(step, refined, support, load, run)
    assert refined_solved["solve_evidence"].solve_evidence_sha256 == loop.refined_solve_evidence_sha256
    view = build_verified_adaptive_stress_comparison(
        loop_evidence=loop,
        baseline_mesh=baseline,
        refined_mesh=refined,
        baseline_solved=baseline_solved,
        refined_solved=refined_solved,
        displacement_scale=1.0,
    )
    return view, loop, baseline, refined, baseline_solved, refined_solved


def test_real_two_solve_stress_fields_use_same_mpa_scale_and_real_provenance(tmp_path):
    view, loop, baseline, refined, baseline_solved, refined_solved = _real_comparison(tmp_path)
    verify_adaptive_stress_comparison(view)
    assert view.baseline.mesh_identity_sha256 == baseline.ownership_sha256
    assert view.refined.mesh_identity_sha256 == refined.ownership_sha256
    assert view.baseline.solve_evidence_sha256 == loop.baseline_solve_evidence_sha256
    assert view.refined.solve_evidence_sha256 == loop.refined_solve_evidence_sha256
    assert view.baseline.element_count == baseline.elements.shape[0]
    assert view.refined.element_count == refined.elements.shape[0]
    assert view.common_scale_min_mpa == 0.0
    assert view.common_scale_max_mpa == max(view.baseline.stress_max_mpa, view.refined.stress_max_mpa)
    assert view.common_scale_max_mpa > 0.0
    assert view.baseline.stress_semantics.endswith("NO_NODAL_SMOOTHING")
    assert view.refined.stress_semantics.endswith("NO_NODAL_SMOOTHING")
    assert math.isfinite(view.peak_relative_change)
    assert view.claims["same_stress_scale_used_for_both_views"] is True
    assert view.claims["stress_from_computed_tet10_integration_points"] is True
    assert view.claims["nodal_stress_smoothing_used"] is False
    assert view.claims["pointwise_mesh_to_mesh_delta_claimed"] is False
    assert view.claims["global_analysis_converged"] is False
    assert view.claims["industrial_validation"] is False
    assert view.claims["ansys_equivalence"] is False


def test_comparison_rejects_stale_refined_solve(tmp_path):
    view, loop, baseline, refined, baseline_solved, refined_solved = _real_comparison(tmp_path)
    stale_loop = replace(loop, refined_solve_evidence_sha256="f" * 64)
    with pytest.raises(AdaptiveStressComparisonError, match="SOLVE_PROVENANCE"):
        build_verified_adaptive_stress_comparison(
            loop_evidence=stale_loop,
            baseline_mesh=baseline,
            refined_mesh=refined,
            baseline_solved=baseline_solved,
            refined_solved=refined_solved,
        )


def test_comparison_rejects_overclaim_and_hash_tampering(tmp_path):
    view, *_ = _real_comparison(tmp_path)
    bad_claims = dict(view.claims); bad_claims["ansys_equivalence"] = True
    tampered = replace(view, claims=bad_claims)
    with pytest.raises(AdaptiveStressComparisonError, match="VALIDATION_OVERCLAIM"):
        verify_adaptive_stress_comparison(tampered)
    tampered_peak = replace(view, refined_peak_mpa=view.refined_peak_mpa + 1.0)
    with pytest.raises(AdaptiveStressComparisonError, match="TAMPERED"):
        verify_adaptive_stress_comparison(tampered_peak)
