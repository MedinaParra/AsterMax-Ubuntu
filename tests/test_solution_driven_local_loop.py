from dataclasses import replace

import math
import pytest

from astermax.fea.evidence import sha256_file
from astermax.fea.named_selections import capture_named_selection
from astermax.fea.one_click_adaptive_loop import prepare_one_click_adaptive_run, approve_one_click_adaptive_run
from astermax.fea.face_ownership import mesh_step_tet10_with_face_ownership
from astermax.fea.solution_driven_local_loop import (
    SolutionDrivenLocalLoopError,
    prepare_solution_driven_local_proposal,
    approve_solution_driven_local_proposal,
    execute_solution_driven_local_loop,
)


def _write_box_step(tmp_path):
    gmsh = pytest.importorskip("gmsh")
    path = tmp_path / "solution_loop_20mm.step"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c55n_solution_loop")
        gmsh.model.occ.addBox(0, 0, 0, 20, 20, 20)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()
    return path


def _setup(tmp_path):
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
    return step, support, load, run, run_approval


def test_real_solution_driven_local_loop_closes_with_exact_msh_and_two_solves(tmp_path):
    step, support, load, run, run_approval = _setup(tmp_path)
    proposal, plan, baseline, baseline_solved, baseline_indicator = prepare_solution_driven_local_proposal(
        step, support, load, run, run_approval, maximum_candidates=3, influence_radius_factor=1.5
    )
    assert proposal.solution_indicator_evidence_sha256 == baseline_indicator.evidence_sha256
    assert proposal.baseline_solve_evidence_sha256 == baseline_solved["solve_evidence"].solve_evidence_sha256
    approval = approve_solution_driven_local_proposal(proposal, plan, approver="Harness Reviewer", approved=True)
    evidence, refined = execute_solution_driven_local_loop(
        step, support, load, run, run_approval, proposal, plan, approval, baseline, baseline_solved, baseline_indicator,
        output_msh_path=tmp_path / "solution_driven_local.msh",
        maximum_indicator_candidates=3,
    )
    assert refined.ownership_sha256 != baseline.ownership_sha256
    assert evidence.baseline_solve_evidence_sha256 != evidence.refined_solve_evidence_sha256
    assert evidence.baseline_indicator_evidence_sha256 != evidence.refined_indicator_evidence_sha256
    assert evidence.indicator_status in {"REDUCED", "NOT_REDUCED"}
    assert math.isfinite(evidence.indicator_relative_change)
    assert evidence.qoi_status in {"PASS", "FAIL"}
    assert math.isfinite(evidence.qoi_relative_change)
    assert math.isfinite(evidence.baseline_force_residual_n)
    assert math.isfinite(evidence.refined_force_residual_n)
    assert evidence.estimator_certified is False
    assert evidence.solution_error_bound_claimed is False
    assert evidence.global_analysis_converged is False
    assert evidence.industrial_validation is False
    assert evidence.ansys_equivalence is False


def test_solution_driven_loop_requires_second_human_approval(tmp_path):
    step, support, load, run, run_approval = _setup(tmp_path)
    proposal, plan, baseline, baseline_solved, baseline_indicator = prepare_solution_driven_local_proposal(step, support, load, run, run_approval, maximum_candidates=2)
    denied = approve_solution_driven_local_proposal(proposal, plan, approver="Harness Reviewer", approved=False)
    with pytest.raises(SolutionDrivenLocalLoopError, match="REFINEMENT_APPROVAL_REQUIRED"):
        execute_solution_driven_local_loop(
            step, support, load, run, run_approval, proposal, plan, denied, baseline, baseline_solved, baseline_indicator,
            output_msh_path=tmp_path / "denied.msh",
        )


def test_solution_driven_loop_rejects_stale_indicator_link(tmp_path):
    step, support, load, run, run_approval = _setup(tmp_path)
    proposal, plan, baseline, baseline_solved, baseline_indicator = prepare_solution_driven_local_proposal(step, support, load, run, run_approval, maximum_candidates=2)
    approval = approve_solution_driven_local_proposal(proposal, plan, approver="Harness Reviewer", approved=True)
    stale = replace(proposal, solution_indicator_evidence_sha256="f" * 64)
    with pytest.raises(SolutionDrivenLocalLoopError, match="PROPOSAL_TAMPERED"):
        execute_solution_driven_local_loop(
            step, support, load, run, run_approval, stale, plan, approval, baseline, baseline_solved, baseline_indicator,
            output_msh_path=tmp_path / "stale.msh",
        )
