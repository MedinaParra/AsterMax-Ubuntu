from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

import numpy as np

from astermax.credibility import canonical_sha256
from .adaptive_second_solve import prepare_existing_inventory_for_solve
from .arbitrary_bc import solve_arbitrary_bc_model
from .gmsh_bridge import _gmsh
from .gmsh_local_refinement import execute_configured_tet10_mesh, verify_gmsh_local_remesh_evidence
from .local_refinement_plan import (
    ControlledLocalRefinementPlanV1,
    RefinementApprovalV1,
    approve_refinement_plan,
    build_controlled_local_refinement_plan,
)
from .msh_ownership_importer import import_tet10_ownership_from_msh
from .named_selections import PersistentNamedSelection
from .one_click_adaptive_loop import OneClickAdaptiveApprovalV1, OneClickAdaptiveRunV1
from .qoi_convergence import QoiConvergenceCriteriaV1, assess_qoi_convergence, make_qoi_observation
from .solution_driven_adaptivity import (
    SolutionDrivenRefinementEvidenceV1,
    build_solution_driven_local_refinement_review,
    build_solution_driven_refinement_evidence,
)
from .face_ownership import Tet10FaceOwnershipInventory, mesh_step_tet10_with_face_ownership
from .evidence import sha256_file


class SolutionDrivenLocalLoopError(ValueError):
    pass


@dataclass(frozen=True)
class SolutionDrivenLocalProposalV1:
    schema: str
    run_sha256: str
    baseline_mesh_sha256: str
    baseline_solve_evidence_sha256: str
    solution_indicator_evidence_sha256: str
    review_sha256: str
    plan_sha256: str
    candidate_element_indices: tuple[int, ...]
    requires_human_approval: bool
    proposal_sha256: str


@dataclass(frozen=True)
class SolutionDrivenLocalLoopEvidenceV1:
    schema: str
    run_sha256: str
    proposal_sha256: str
    refinement_approval_sha256: str
    baseline_mesh_sha256: str
    refined_mesh_sha256: str
    local_remesh_evidence_sha256: str
    mesh_import_evidence_sha256: str
    baseline_solve_evidence_sha256: str
    refined_solve_evidence_sha256: str
    baseline_indicator_evidence_sha256: str
    refined_indicator_evidence_sha256: str
    baseline_max_indicator: float
    refined_max_indicator: float
    indicator_relative_change: float
    indicator_status: str
    qoi_assessment_sha256: str
    qoi_status: str
    qoi_relative_change: float
    baseline_force_residual_n: float
    refined_force_residual_n: float
    baseline_moment_residual_nmm: float
    refined_moment_residual_nmm: float
    estimator_certified: bool
    solution_error_bound_claimed: bool
    global_analysis_converged: bool
    industrial_validation: bool
    ansys_equivalence: bool
    evidence_sha256: str


def _verify_run(step_path: str | Path, support: PersistentNamedSelection, load: PersistentNamedSelection, run: OneClickAdaptiveRunV1, approval: OneClickAdaptiveApprovalV1) -> None:
    if run.schema != "AsterMaxOneClickAdaptiveRunV1":
        raise SolutionDrivenLocalLoopError("SOLUTION_LOOP_RUN_SCHEMA")
    core = run.__dict__.copy(); core.pop("run_sha256")
    if canonical_sha256(core) != run.run_sha256:
        raise SolutionDrivenLocalLoopError("SOLUTION_LOOP_RUN_TAMPERED")
    acore = approval.__dict__.copy(); acore.pop("approval_sha256")
    if approval.schema != "AsterMaxOneClickAdaptiveApprovalV1" or canonical_sha256(acore) != approval.approval_sha256:
        raise SolutionDrivenLocalLoopError("SOLUTION_LOOP_RUN_APPROVAL_TAMPERED")
    if approval.run_sha256 != run.run_sha256 or not approval.approved or approval.scope != "MESH_DISCRETIZATION_ONLY_PHYSICS_FROZEN":
        raise SolutionDrivenLocalLoopError("SOLUTION_LOOP_RUN_APPROVAL_REQUIRED")
    if sha256_file(Path(step_path)) != run.source_step_sha256:
        raise SolutionDrivenLocalLoopError("SOLUTION_LOOP_STEP_CHANGED")
    if support.named_selection_sha256 != run.support_named_selection_sha256 or load.named_selection_sha256 != run.load_named_selection_sha256:
        raise SolutionDrivenLocalLoopError("SOLUTION_LOOP_BC_LOAD_CHANGED")


def _solve_inventory(step_path, inventory, support, load, run):
    prepared = prepare_existing_inventory_for_solve(step_path, inventory, support, load)
    return solve_arbitrary_bc_model(
        prepared,
        young_modulus_mpa=run.young_modulus_mpa,
        poisson_ratio=run.poisson_ratio,
        resultant_n=run.resultant_n,
    )


def _max_displacement_mm(result) -> float:
    field = np.asarray(result.displacement_mm, dtype=float)
    if field.ndim != 2 or field.shape[1] != 3 or field.shape[0] == 0 or not np.all(np.isfinite(field)):
        raise SolutionDrivenLocalLoopError("SOLUTION_LOOP_DISPLACEMENT_FIELD")
    return float(np.linalg.norm(field, axis=1).max())


def prepare_solution_driven_local_proposal(
    step_path: str | Path,
    support: PersistentNamedSelection,
    load: PersistentNamedSelection,
    run: OneClickAdaptiveRunV1,
    run_approval: OneClickAdaptiveApprovalV1,
    *,
    maximum_candidates: int = 4,
    influence_radius_factor: float = 2.0,
):
    _verify_run(step_path, support, load, run, run_approval)
    baseline = mesh_step_tet10_with_face_ownership(step_path, run.baseline_target_size_mm)
    baseline_solved = _solve_inventory(step_path, baseline, support, load, run)
    solve_ev = baseline_solved["solve_evidence"]
    indicator = build_solution_driven_refinement_evidence(
        source_step_sha256=run.source_step_sha256,
        mesh_identity_sha256=baseline.ownership_sha256,
        solve_evidence_sha256=solve_ev.solve_evidence_sha256,
        nodes_mm=baseline.nodes_mm,
        elements=baseline.elements,
        result=baseline_solved["result"],
        maximum_candidates=maximum_candidates,
    )
    review = build_solution_driven_local_refinement_review(indicator)
    plan = build_controlled_local_refinement_plan(
        source_step_sha256=run.source_step_sha256,
        route_sha256=run.route_sha256,
        baseline_mesh_sha256=baseline.ownership_sha256,
        review=review,
        baseline_size_mm=run.baseline_target_size_mm,
        refined_size_factor=run.refined_target_size_mm / run.baseline_target_size_mm,
        influence_radius_factor=influence_radius_factor,
    )
    core = {
        "schema": "AsterMaxSolutionDrivenLocalProposalV1",
        "run_sha256": run.run_sha256,
        "baseline_mesh_sha256": baseline.ownership_sha256,
        "baseline_solve_evidence_sha256": solve_ev.solve_evidence_sha256,
        "solution_indicator_evidence_sha256": indicator.evidence_sha256,
        "review_sha256": review.review_sha256,
        "plan_sha256": plan.plan_sha256,
        "candidate_element_indices": tuple(indicator.candidate_element_indices),
        "requires_human_approval": True,
    }
    proposal = SolutionDrivenLocalProposalV1(**core, proposal_sha256=canonical_sha256(core))
    return proposal, plan, baseline, baseline_solved, indicator


def approve_solution_driven_local_proposal(proposal: SolutionDrivenLocalProposalV1, plan: ControlledLocalRefinementPlanV1, *, approver: str, approved: bool) -> RefinementApprovalV1:
    core = proposal.__dict__.copy(); core.pop("proposal_sha256")
    if proposal.schema != "AsterMaxSolutionDrivenLocalProposalV1" or canonical_sha256(core) != proposal.proposal_sha256:
        raise SolutionDrivenLocalLoopError("SOLUTION_LOOP_PROPOSAL_TAMPERED")
    if proposal.plan_sha256 != plan.plan_sha256:
        raise SolutionDrivenLocalLoopError("SOLUTION_LOOP_PROPOSAL_PLAN_MISMATCH")
    return approve_refinement_plan(plan, approver=approver, approved=approved)


def execute_solution_driven_local_loop(
    step_path: str | Path,
    support: PersistentNamedSelection,
    load: PersistentNamedSelection,
    run: OneClickAdaptiveRunV1,
    run_approval: OneClickAdaptiveApprovalV1,
    proposal: SolutionDrivenLocalProposalV1,
    plan: ControlledLocalRefinementPlanV1,
    refinement_approval: RefinementApprovalV1,
    baseline: Tet10FaceOwnershipInventory,
    baseline_solved,
    baseline_indicator: SolutionDrivenRefinementEvidenceV1,
    *,
    output_msh_path: str | Path,
    maximum_indicator_candidates: int = 4,
) -> tuple[SolutionDrivenLocalLoopEvidenceV1, Tet10FaceOwnershipInventory]:
    _verify_run(step_path, support, load, run, run_approval)
    pcore = proposal.__dict__.copy(); pcore.pop("proposal_sha256")
    if canonical_sha256(pcore) != proposal.proposal_sha256:
        raise SolutionDrivenLocalLoopError("SOLUTION_LOOP_PROPOSAL_TAMPERED")
    if proposal.run_sha256 != run.run_sha256 or proposal.plan_sha256 != plan.plan_sha256:
        raise SolutionDrivenLocalLoopError("SOLUTION_LOOP_PROPOSAL_STALE")
    if proposal.baseline_mesh_sha256 != baseline.ownership_sha256 or plan.baseline_mesh_sha256 != baseline.ownership_sha256:
        raise SolutionDrivenLocalLoopError("SOLUTION_LOOP_BASELINE_STALE")
    if proposal.solution_indicator_evidence_sha256 != baseline_indicator.evidence_sha256:
        raise SolutionDrivenLocalLoopError("SOLUTION_LOOP_BASELINE_INDICATOR_STALE")
    if proposal.baseline_solve_evidence_sha256 != baseline_solved["solve_evidence"].solve_evidence_sha256:
        raise SolutionDrivenLocalLoopError("SOLUTION_LOOP_BASELINE_SOLVE_STALE")
    if refinement_approval.plan_sha256 != plan.plan_sha256 or not refinement_approval.approved:
        raise SolutionDrivenLocalLoopError("SOLUTION_LOOP_REFINEMENT_APPROVAL_REQUIRED")

    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_c55n_solution_driven_local")
        gmsh.model.occ.importShapes(str(Path(step_path)))
        gmsh.model.occ.synchronize()
        remesh_ev = execute_configured_tet10_mesh(gmsh, plan=plan, approval=refinement_approval, output_path=output_msh_path)
    finally:
        gmsh.finalize()
    verify_gmsh_local_remesh_evidence(remesh_ev)

    refined, import_ev = import_tet10_ownership_from_msh(step_path, output_msh_path, expected_mesh_sha256=remesh_ev.output_mesh_sha256)
    if refined.ownership_sha256 == baseline.ownership_sha256:
        raise SolutionDrivenLocalLoopError("SOLUTION_LOOP_REFINED_MESH_NOT_DISTINCT")
    refined_solved = _solve_inventory(step_path, refined, support, load, run)
    refined_indicator = build_solution_driven_refinement_evidence(
        source_step_sha256=run.source_step_sha256,
        mesh_identity_sha256=refined.ownership_sha256,
        solve_evidence_sha256=refined_solved["solve_evidence"].solve_evidence_sha256,
        nodes_mm=refined.nodes_mm,
        elements=refined.elements,
        result=refined_solved["result"],
        maximum_candidates=maximum_indicator_candidates,
    )

    coarse_qoi = make_qoi_observation(
        source_step_sha256=run.source_step_sha256,
        route_sha256=run.route_sha256,
        solve_evidence_sha256=baseline_solved["solve_evidence"].solve_evidence_sha256,
        mesh_identity_sha256=baseline.ownership_sha256,
        mesh_target_size_mm=run.baseline_target_size_mm,
        element_count=int(baseline.elements.shape[0]),
        qoi_name="MAX_DISPLACEMENT_MAGNITUDE",
        qoi_unit="mm",
        qoi_value=_max_displacement_mm(baseline_solved["result"]),
    )
    fine_qoi = make_qoi_observation(
        source_step_sha256=run.source_step_sha256,
        route_sha256=run.route_sha256,
        solve_evidence_sha256=refined_solved["solve_evidence"].solve_evidence_sha256,
        mesh_identity_sha256=refined.ownership_sha256,
        mesh_target_size_mm=plan.refined_size_mm,
        element_count=int(refined.elements.shape[0]),
        qoi_name="MAX_DISPLACEMENT_MAGNITUDE",
        qoi_unit="mm",
        qoi_value=_max_displacement_mm(refined_solved["result"]),
    )
    qoi = assess_qoi_convergence(coarse_qoi, fine_qoi, QoiConvergenceCriteriaV1(maximum_relative_change=run.maximum_relative_qoi_change, require_finer_mesh=True))

    base_i = float(baseline_indicator.maximum_indicator)
    fine_i = float(refined_indicator.maximum_indicator)
    if not all(math.isfinite(v) and v >= 0.0 for v in (base_i, fine_i)) or base_i <= 0.0:
        raise SolutionDrivenLocalLoopError("SOLUTION_LOOP_INDICATOR_VALUES")
    indicator_change = (fine_i - base_i) / base_i
    indicator_status = "REDUCED" if fine_i < base_i else "NOT_REDUCED"

    bsev = baseline_solved["solve_evidence"]
    rsev = refined_solved["solve_evidence"]
    core = {
        "schema": "AsterMaxSolutionDrivenLocalLoopEvidenceV1",
        "run_sha256": run.run_sha256,
        "proposal_sha256": proposal.proposal_sha256,
        "refinement_approval_sha256": refinement_approval.approval_sha256,
        "baseline_mesh_sha256": baseline.ownership_sha256,
        "refined_mesh_sha256": refined.ownership_sha256,
        "local_remesh_evidence_sha256": remesh_ev.evidence_sha256,
        "mesh_import_evidence_sha256": import_ev.evidence_sha256,
        "baseline_solve_evidence_sha256": bsev.solve_evidence_sha256,
        "refined_solve_evidence_sha256": rsev.solve_evidence_sha256,
        "baseline_indicator_evidence_sha256": baseline_indicator.evidence_sha256,
        "refined_indicator_evidence_sha256": refined_indicator.evidence_sha256,
        "baseline_max_indicator": base_i,
        "refined_max_indicator": fine_i,
        "indicator_relative_change": float(indicator_change),
        "indicator_status": indicator_status,
        "qoi_assessment_sha256": qoi.assessment_sha256,
        "qoi_status": qoi.status,
        "qoi_relative_change": float(qoi.relative_change),
        "baseline_force_residual_n": float(bsev.force_residual_n),
        "refined_force_residual_n": float(rsev.force_residual_n),
        "baseline_moment_residual_nmm": float(bsev.moment_residual_nmm),
        "refined_moment_residual_nmm": float(rsev.moment_residual_nmm),
        "estimator_certified": False,
        "solution_error_bound_claimed": False,
        "global_analysis_converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    evidence = SolutionDrivenLocalLoopEvidenceV1(**core, evidence_sha256=canonical_sha256(core))
    return evidence, refined
