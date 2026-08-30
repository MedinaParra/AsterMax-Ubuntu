from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from astermax.credibility import canonical_sha256
from .adaptive_demo_session import AdaptiveDemoSessionV1, build_adaptive_demo_session
from .adaptive_results_dashboard import AdaptiveResultsDashboardV1, build_adaptive_results_dashboard
from .adaptive_second_solve import execute_provenance_matched_second_solve
from .evidence import sha256_file
from .face_ownership import Tet10FaceOwnershipInventory, mesh_step_tet10_with_face_ownership
from .gmsh_bridge import _gmsh
from .gmsh_local_refinement import GmshLocalRemeshEvidenceV1, execute_configured_tet10_mesh, verify_gmsh_local_remesh_evidence
from .local_refinement_plan import (
    ControlledLocalRefinementPlanV1,
    RefinementApprovalV1,
    approve_refinement_plan,
    build_controlled_local_refinement_plan,
)
from .msh_ownership_importer import MshOwnershipImportEvidenceV1, import_tet10_ownership_from_msh
from .named_selections import PersistentNamedSelection
from .one_click_adaptive_loop import OneClickAdaptiveApprovalV1, OneClickAdaptiveRunV1
from .qoi_convergence import build_local_refinement_review
from .tet_quality import build_tet10_corner_quality_snapshot, require_quality_crosscheck
from .worst_element_inspector import build_worst_element_quality_snapshot


class LocalAdaptiveOneClickError(ValueError):
    pass


@dataclass(frozen=True)
class LocalAdaptiveProposalV1:
    schema: str
    run_sha256: str
    baseline_mesh_sha256: str
    quality_snapshot_sha256: str
    inspector_snapshot_sha256: str
    review_sha256: str
    plan_sha256: str
    candidate_element_indices: tuple[int, ...]
    baseline_size_mm: float
    local_refined_size_mm: float
    radius_mm: float
    requires_separate_refinement_approval: bool
    proposal_sha256: str


@dataclass(frozen=True)
class LocalAdaptiveExecutionV1:
    schema: str
    run_sha256: str
    proposal_sha256: str
    refinement_approval_sha256: str
    local_remesh_evidence_sha256: str
    mesh_import_evidence_sha256: str
    baseline_mesh_sha256: str
    refined_mesh_sha256: str
    adaptive_evidence_sha256: str
    session_sha256: str
    dashboard_sha256: str
    qoi_status: str
    qoi_relative_change: float
    refinement_driver: str
    global_analysis_converged: bool
    industrial_validation: bool
    ansys_equivalence: bool
    execution_sha256: str


def _verify_run_and_approval(
    step_path: str | Path,
    support: PersistentNamedSelection,
    load: PersistentNamedSelection,
    run: OneClickAdaptiveRunV1,
    approval: OneClickAdaptiveApprovalV1,
) -> None:
    if run.schema != "AsterMaxOneClickAdaptiveRunV1":
        raise LocalAdaptiveOneClickError("LOCAL_ADAPTIVE_RUN_SCHEMA")
    run_core = run.__dict__.copy(); run_core.pop("run_sha256")
    if canonical_sha256(run_core) != run.run_sha256:
        raise LocalAdaptiveOneClickError("LOCAL_ADAPTIVE_RUN_TAMPERED")
    if approval.schema != "AsterMaxOneClickAdaptiveApprovalV1" or approval.run_sha256 != run.run_sha256:
        raise LocalAdaptiveOneClickError("LOCAL_ADAPTIVE_RUN_APPROVAL_STALE")
    approval_core = approval.__dict__.copy(); approval_core.pop("approval_sha256")
    if canonical_sha256(approval_core) != approval.approval_sha256:
        raise LocalAdaptiveOneClickError("LOCAL_ADAPTIVE_RUN_APPROVAL_TAMPERED")
    if not approval.approved or approval.scope != "MESH_DISCRETIZATION_ONLY_PHYSICS_FROZEN":
        raise LocalAdaptiveOneClickError("LOCAL_ADAPTIVE_RUN_APPROVAL_REQUIRED")
    if sha256_file(Path(step_path)) != run.source_step_sha256:
        raise LocalAdaptiveOneClickError("LOCAL_ADAPTIVE_STEP_CHANGED")
    if support.named_selection_sha256 != run.support_named_selection_sha256 or load.named_selection_sha256 != run.load_named_selection_sha256:
        raise LocalAdaptiveOneClickError("LOCAL_ADAPTIVE_BC_LOAD_CHANGED")


def prepare_local_adaptive_proposal(
    step_path: str | Path,
    support: PersistentNamedSelection,
    load: PersistentNamedSelection,
    run: OneClickAdaptiveRunV1,
    approval: OneClickAdaptiveApprovalV1,
    *,
    maximum_candidates: int = 4,
    influence_radius_factor: float = 2.0,
) -> tuple[LocalAdaptiveProposalV1, ControlledLocalRefinementPlanV1, Tet10FaceOwnershipInventory]:
    """Build a mesh-quality-guided local refinement proposal from the frozen one-click run.

    This stage does not execute the local remesh. A second human approval is intentionally
    required after the actual baseline mesh has been inspected and the candidate regions are known.
    """
    _verify_run_and_approval(step_path, support, load, run, approval)
    baseline = mesh_step_tet10_with_face_ownership(step_path, run.baseline_target_size_mm)
    quality = build_tet10_corner_quality_snapshot(baseline.nodes_mm, baseline.elements)
    require_quality_crosscheck(quality)
    inspector = build_worst_element_quality_snapshot(
        nodes_mm=baseline.nodes_mm,
        elements=baseline.elements,
        tetra_quality=asdict(quality),
        worst_count=int(maximum_candidates),
    )
    review = build_local_refinement_review(inspector, maximum_candidates=int(maximum_candidates))
    factor = run.refined_target_size_mm / run.baseline_target_size_mm
    plan = build_controlled_local_refinement_plan(
        source_step_sha256=run.source_step_sha256,
        route_sha256=run.route_sha256,
        baseline_mesh_sha256=baseline.ownership_sha256,
        review=review,
        baseline_size_mm=run.baseline_target_size_mm,
        refined_size_factor=factor,
        influence_radius_factor=influence_radius_factor,
    )
    core = {
        "schema": "AsterMaxLocalAdaptiveProposalV1",
        "run_sha256": run.run_sha256,
        "baseline_mesh_sha256": baseline.ownership_sha256,
        "quality_snapshot_sha256": quality.snapshot_sha256,
        "inspector_snapshot_sha256": inspector.snapshot_sha256,
        "review_sha256": review.review_sha256,
        "plan_sha256": plan.plan_sha256,
        "candidate_element_indices": tuple(int(v) for v in review.candidate_element_indices),
        "baseline_size_mm": plan.baseline_size_mm,
        "local_refined_size_mm": plan.refined_size_mm,
        "radius_mm": plan.radius_mm,
        "requires_separate_refinement_approval": True,
    }
    return LocalAdaptiveProposalV1(**core, proposal_sha256=canonical_sha256(core)), plan, baseline


def approve_local_adaptive_proposal(
    proposal: LocalAdaptiveProposalV1,
    plan: ControlledLocalRefinementPlanV1,
    *,
    approver: str,
    approved: bool,
) -> RefinementApprovalV1:
    if proposal.schema != "AsterMaxLocalAdaptiveProposalV1" or proposal.plan_sha256 != plan.plan_sha256:
        raise LocalAdaptiveOneClickError("LOCAL_ADAPTIVE_PROPOSAL_PLAN_MISMATCH")
    core = proposal.__dict__.copy(); core.pop("proposal_sha256")
    if canonical_sha256(core) != proposal.proposal_sha256:
        raise LocalAdaptiveOneClickError("LOCAL_ADAPTIVE_PROPOSAL_TAMPERED")
    return approve_refinement_plan(plan, approver=approver, approved=approved)


def execute_approved_local_adaptive_cutover(
    step_path: str | Path,
    support: PersistentNamedSelection,
    load: PersistentNamedSelection,
    run: OneClickAdaptiveRunV1,
    run_approval: OneClickAdaptiveApprovalV1,
    proposal: LocalAdaptiveProposalV1,
    plan: ControlledLocalRefinementPlanV1,
    refinement_approval: RefinementApprovalV1,
    baseline: Tet10FaceOwnershipInventory,
    *,
    output_msh_path: str | Path,
) -> tuple[
    LocalAdaptiveExecutionV1,
    AdaptiveDemoSessionV1,
    AdaptiveResultsDashboardV1,
    GmshLocalRemeshEvidenceV1,
    MshOwnershipImportEvidenceV1,
    Tet10FaceOwnershipInventory,
]:
    _verify_run_and_approval(step_path, support, load, run, run_approval)
    proposal_core = proposal.__dict__.copy(); proposal_core.pop("proposal_sha256")
    if canonical_sha256(proposal_core) != proposal.proposal_sha256:
        raise LocalAdaptiveOneClickError("LOCAL_ADAPTIVE_PROPOSAL_TAMPERED")
    if proposal.run_sha256 != run.run_sha256 or proposal.plan_sha256 != plan.plan_sha256:
        raise LocalAdaptiveOneClickError("LOCAL_ADAPTIVE_PROPOSAL_STALE")
    if proposal.baseline_mesh_sha256 != baseline.ownership_sha256 or plan.baseline_mesh_sha256 != baseline.ownership_sha256:
        raise LocalAdaptiveOneClickError("LOCAL_ADAPTIVE_BASELINE_STALE")
    if plan.route_sha256 != run.route_sha256 or plan.source_step_sha256 != run.source_step_sha256:
        raise LocalAdaptiveOneClickError("LOCAL_ADAPTIVE_PLAN_PROVENANCE")
    if refinement_approval.plan_sha256 != plan.plan_sha256 or not refinement_approval.approved:
        raise LocalAdaptiveOneClickError("LOCAL_ADAPTIVE_REFINEMENT_APPROVAL_REQUIRED")

    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_c55l_local_adaptive")
        gmsh.model.occ.importShapes(str(Path(step_path)))
        gmsh.model.occ.synchronize()
        remesh_evidence = execute_configured_tet10_mesh(
            gmsh,
            plan=plan,
            approval=refinement_approval,
            output_path=output_msh_path,
        )
    finally:
        gmsh.finalize()
    verify_gmsh_local_remesh_evidence(remesh_evidence)

    refined, import_evidence = import_tet10_ownership_from_msh(
        step_path,
        output_msh_path,
        expected_mesh_sha256=remesh_evidence.output_mesh_sha256,
    )
    if refined.ownership_sha256 == baseline.ownership_sha256:
        raise LocalAdaptiveOneClickError("LOCAL_ADAPTIVE_DISTINCT_REFINED_MESH_REQUIRED")

    evidence, coarse_qoi, fine_qoi, assessment = execute_provenance_matched_second_solve(
        step_path,
        baseline,
        refined,
        support,
        load,
        baseline_target_size_mm=run.baseline_target_size_mm,
        remesh_target_size_mm=plan.refined_size_mm,
        young_modulus_mpa=run.young_modulus_mpa,
        poisson_ratio=run.poisson_ratio,
        resultant_n=run.resultant_n,
        maximum_relative_qoi_change=run.maximum_relative_qoi_change,
    )
    session = build_adaptive_demo_session(evidence, coarse_qoi, fine_qoi, assessment)
    dashboard = build_adaptive_results_dashboard(session)
    exec_core = {
        "schema": "AsterMaxLocalAdaptiveExecutionV1",
        "run_sha256": run.run_sha256,
        "proposal_sha256": proposal.proposal_sha256,
        "refinement_approval_sha256": refinement_approval.approval_sha256,
        "local_remesh_evidence_sha256": remesh_evidence.evidence_sha256,
        "mesh_import_evidence_sha256": import_evidence.evidence_sha256,
        "baseline_mesh_sha256": baseline.ownership_sha256,
        "refined_mesh_sha256": refined.ownership_sha256,
        "adaptive_evidence_sha256": evidence.evidence_sha256,
        "session_sha256": session.session_sha256,
        "dashboard_sha256": dashboard.dashboard_sha256,
        "qoi_status": assessment.status,
        "qoi_relative_change": float(assessment.relative_change),
        "refinement_driver": "CROSSCHECKED_TET10_MEAN_RATIO_WORST_ELEMENT_LOCALIZATION",
        "global_analysis_converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    execution = LocalAdaptiveExecutionV1(**exec_core, execution_sha256=canonical_sha256(exec_core))
    return execution, session, dashboard, remesh_evidence, import_evidence, refined
