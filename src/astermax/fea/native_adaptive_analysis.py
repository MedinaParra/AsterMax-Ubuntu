from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from astermax.credibility import canonical_sha256
from .adaptive_execution_bundle import build_adaptive_execution_artifact_bundle, bind_native_adaptive_results
from .adaptive_hotspot_visualization import AdaptiveHotspotVisualizationV1
from .adaptive_stress_comparison import AdaptiveStressComparisonV1
from .live_project_capture import LiveProjectCaptureCoordinatorV1, verify_live_project_capture_receipt
from .one_click_adaptive_loop import approve_one_click_adaptive_run, prepare_one_click_adaptive_run
from .portable_adaptive_results import open_portable_adaptive_results_package, verify_portable_adaptive_results_package, write_portable_adaptive_results_package
from .pre_solve_review import verify_acceptance
from .solution_driven_local_loop import (
    approve_solution_driven_local_proposal,
    execute_solution_driven_local_loop,
    prepare_solution_driven_local_proposal,
)


class NativeAdaptiveAnalysisError(ValueError):
    pass


@dataclass(frozen=True)
class NativeAdaptiveProposalContextV1:
    schema: str
    source_step_sha256: str
    run_sha256: str
    run_approval_sha256: str
    proposal_sha256: str
    plan_sha256: str
    baseline_mesh_sha256: str
    baseline_solve_evidence_sha256: str
    baseline_indicator_evidence_sha256: str
    candidate_count: int
    baseline_target_size_mm: float
    refined_target_size_mm: float
    maximum_relative_qoi_change: float
    requires_refinement_approval: bool
    context_sha256: str
    run: Any
    run_approval: Any
    proposal: Any
    plan: Any
    baseline: Any
    baseline_solved: Any
    baseline_indicator: Any


@dataclass(frozen=True)
class NativeAdaptiveAnalysisReceiptV1:
    schema: str
    status: str
    source_step_sha256: str
    run_sha256: str
    proposal_sha256: str
    refinement_approval_sha256: str
    loop_evidence_sha256: str
    bundle_sha256: str
    result_package_path: str
    result_package_sha256: str
    baseline_mesh_sha256: str
    refined_mesh_sha256: str
    baseline_solve_evidence_sha256: str
    refined_solve_evidence_sha256: str
    qoi_status: str
    qoi_relative_change: float
    indicator_status: str
    indicator_relative_change: float
    native_results_bound: bool
    captured_to_active_project: bool
    captured_revision: int | None
    global_analysis_converged: bool
    industrial_validation: bool
    ansys_equivalence: bool
    receipt_sha256: str


def _context_core(context: NativeAdaptiveProposalContextV1) -> dict[str, Any]:
    return {
        "schema": context.schema,
        "source_step_sha256": context.source_step_sha256,
        "run_sha256": context.run_sha256,
        "run_approval_sha256": context.run_approval_sha256,
        "proposal_sha256": context.proposal_sha256,
        "plan_sha256": context.plan_sha256,
        "baseline_mesh_sha256": context.baseline_mesh_sha256,
        "baseline_solve_evidence_sha256": context.baseline_solve_evidence_sha256,
        "baseline_indicator_evidence_sha256": context.baseline_indicator_evidence_sha256,
        "candidate_count": context.candidate_count,
        "baseline_target_size_mm": context.baseline_target_size_mm,
        "refined_target_size_mm": context.refined_target_size_mm,
        "maximum_relative_qoi_change": context.maximum_relative_qoi_change,
        "requires_refinement_approval": context.requires_refinement_approval,
    }


def prepare_native_adaptive_analysis(
    prepared: dict[str, Any],
    acceptance: Any,
    *,
    approver: str,
    approved: bool,
    refined_size_factor: float = 0.5,
    maximum_relative_qoi_change: float = 0.05,
    maximum_candidates: int = 4,
    influence_radius_factor: float = 2.0,
) -> NativeAdaptiveProposalContextV1:
    """Run the verified baseline solve and build a solution-driven local refinement proposal.

    The first human approval freezes STEP/material/BC/load physics before the baseline solve.
    Local remeshing is not executed here; it remains behind a second explicit approval.
    """
    verify_acceptance(prepared, acceptance)
    review = prepared["review"]
    source = Path(prepared["source"])
    support = prepared["support_selection"]
    load = prepared["load_named_selection"]
    factor = float(refined_size_factor)
    if not 0.0 < factor < 1.0:
        raise NativeAdaptiveAnalysisError("NATIVE_ADAPTIVE_REFINED_SIZE_FACTOR")
    refined_size = float(review.mesh_target_size_mm) * factor
    run = prepare_one_click_adaptive_run(
        source,
        support,
        load,
        baseline_target_size_mm=float(review.mesh_target_size_mm),
        refined_target_size_mm=refined_size,
        young_modulus_mpa=float(review.material_young_modulus_mpa),
        poisson_ratio=float(review.material_poisson_ratio),
        resultant_n=tuple(float(v) for v in review.resultant_n),
        maximum_relative_qoi_change=float(maximum_relative_qoi_change),
    )
    run_approval = approve_one_click_adaptive_run(run, approver=approver, approved=approved)
    if not run_approval.approved:
        raise NativeAdaptiveAnalysisError("NATIVE_ADAPTIVE_RUN_APPROVAL_REQUIRED")
    proposal, plan, baseline, baseline_solved, baseline_indicator = prepare_solution_driven_local_proposal(
        source,
        support,
        load,
        run,
        run_approval,
        maximum_candidates=maximum_candidates,
        influence_radius_factor=influence_radius_factor,
    )
    core = {
        "schema": "AsterMaxNativeAdaptiveProposalContextV1",
        "source_step_sha256": run.source_step_sha256,
        "run_sha256": run.run_sha256,
        "run_approval_sha256": run_approval.approval_sha256,
        "proposal_sha256": proposal.proposal_sha256,
        "plan_sha256": plan.plan_sha256,
        "baseline_mesh_sha256": baseline.ownership_sha256,
        "baseline_solve_evidence_sha256": baseline_solved["solve_evidence"].solve_evidence_sha256,
        "baseline_indicator_evidence_sha256": baseline_indicator.evidence_sha256,
        "candidate_count": len(proposal.candidate_element_indices),
        "baseline_target_size_mm": float(run.baseline_target_size_mm),
        "refined_target_size_mm": float(run.refined_target_size_mm),
        "maximum_relative_qoi_change": float(run.maximum_relative_qoi_change),
        "requires_refinement_approval": True,
    }
    return NativeAdaptiveProposalContextV1(
        **core,
        context_sha256=canonical_sha256(core),
        run=run,
        run_approval=run_approval,
        proposal=proposal,
        plan=plan,
        baseline=baseline,
        baseline_solved=baseline_solved,
        baseline_indicator=baseline_indicator,
    )


def verify_native_adaptive_proposal_context(context: NativeAdaptiveProposalContextV1) -> None:
    if context.schema != "AsterMaxNativeAdaptiveProposalContextV1" or not context.requires_refinement_approval:
        raise NativeAdaptiveAnalysisError("NATIVE_ADAPTIVE_CONTEXT_SCHEMA")
    if canonical_sha256(_context_core(context)) != context.context_sha256:
        raise NativeAdaptiveAnalysisError("NATIVE_ADAPTIVE_CONTEXT_TAMPERED")
    if context.run.run_sha256 != context.run_sha256 or context.run_approval.approval_sha256 != context.run_approval_sha256:
        raise NativeAdaptiveAnalysisError("NATIVE_ADAPTIVE_CONTEXT_RUN_STALE")
    if context.proposal.proposal_sha256 != context.proposal_sha256 or context.plan.plan_sha256 != context.plan_sha256:
        raise NativeAdaptiveAnalysisError("NATIVE_ADAPTIVE_CONTEXT_PROPOSAL_STALE")
    if context.baseline.ownership_sha256 != context.baseline_mesh_sha256:
        raise NativeAdaptiveAnalysisError("NATIVE_ADAPTIVE_CONTEXT_BASELINE_STALE")
    if context.baseline_solved["solve_evidence"].solve_evidence_sha256 != context.baseline_solve_evidence_sha256:
        raise NativeAdaptiveAnalysisError("NATIVE_ADAPTIVE_CONTEXT_SOLVE_STALE")
    if context.baseline_indicator.evidence_sha256 != context.baseline_indicator_evidence_sha256:
        raise NativeAdaptiveAnalysisError("NATIVE_ADAPTIVE_CONTEXT_INDICATOR_STALE")


def execute_native_adaptive_analysis(
    prepared: dict[str, Any],
    acceptance: Any,
    context: NativeAdaptiveProposalContextV1,
    *,
    refinement_approver: str,
    refinement_approved: bool,
    output_dir: str | Path,
    hotspot_binder: Callable[[AdaptiveHotspotVisualizationV1], None],
    stress_binder: Callable[[AdaptiveStressComparisonV1], None],
    capture_coordinator: LiveProjectCaptureCoordinatorV1 | None = None,
    displacement_scale: float = 1.0,
) -> NativeAdaptiveAnalysisReceiptV1:
    """Execute approved local remesh/refined solve, package Results, then bind/capture them."""
    verify_acceptance(prepared, acceptance)
    verify_native_adaptive_proposal_context(context)
    review = prepared["review"]
    if review.step_sha256 != context.source_step_sha256:
        raise NativeAdaptiveAnalysisError("NATIVE_ADAPTIVE_PREPARATION_CHANGED")
    support = prepared["support_selection"]
    load = prepared["load_named_selection"]
    approval = approve_solution_driven_local_proposal(
        context.proposal,
        context.plan,
        approver=refinement_approver,
        approved=refinement_approved,
    )
    if not approval.approved:
        raise NativeAdaptiveAnalysisError("NATIVE_ADAPTIVE_REFINEMENT_APPROVAL_REQUIRED")

    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    msh_path = output / "astermax_adaptive_refined.msh"
    loop, refined, refined_solved, refined_indicator, _coarse_qoi, _fine_qoi, _qoi = execute_solution_driven_local_loop(
        prepared["source"],
        support,
        load,
        context.run,
        context.run_approval,
        context.proposal,
        context.plan,
        approval,
        context.baseline,
        context.baseline_solved,
        context.baseline_indicator,
        output_msh_path=msh_path,
        maximum_indicator_candidates=max(1, context.candidate_count),
        return_artifacts=True,
    )
    bundle = build_adaptive_execution_artifact_bundle(
        loop_evidence=loop,
        proposal=context.proposal,
        plan=context.plan,
        baseline_mesh=context.baseline,
        refined_mesh=refined,
        baseline_solved=context.baseline_solved,
        refined_solved=refined_solved,
        baseline_indicator=context.baseline_indicator,
        refined_indicator=refined_indicator,
        displacement_scale=displacement_scale,
    )
    package_name = f"astermax_adaptive_{bundle.bundle_sha256[:16]}.astermaxr"
    package_path = write_portable_adaptive_results_package(bundle, output / package_name)
    package = open_portable_adaptive_results_package(package_path)
    verify_portable_adaptive_results_package(package)

    captured = False
    captured_revision: int | None = None
    if capture_coordinator is not None and capture_coordinator.active_project_path:
        capture = capture_coordinator.capture_verified_results(package_path)
        verify_live_project_capture_receipt(capture)
        captured = True
        captured_revision = int(capture.revision)
    else:
        bind_native_adaptive_results(bundle, hotspot_binder=hotspot_binder, stress_binder=stress_binder)

    core = {
        "schema": "AsterMaxNativeAdaptiveAnalysisReceiptV1",
        "status": "VERIFIED_ADAPTIVE_RESULTS_READY",
        "source_step_sha256": context.source_step_sha256,
        "run_sha256": context.run_sha256,
        "proposal_sha256": context.proposal_sha256,
        "refinement_approval_sha256": approval.approval_sha256,
        "loop_evidence_sha256": loop.evidence_sha256,
        "bundle_sha256": bundle.bundle_sha256,
        "result_package_path": str(package_path.resolve()),
        "result_package_sha256": package.package_sha256,
        "baseline_mesh_sha256": loop.baseline_mesh_sha256,
        "refined_mesh_sha256": loop.refined_mesh_sha256,
        "baseline_solve_evidence_sha256": loop.baseline_solve_evidence_sha256,
        "refined_solve_evidence_sha256": loop.refined_solve_evidence_sha256,
        "qoi_status": loop.qoi_status,
        "qoi_relative_change": float(loop.qoi_relative_change),
        "indicator_status": loop.indicator_status,
        "indicator_relative_change": float(loop.indicator_relative_change),
        "native_results_bound": True,
        "captured_to_active_project": captured,
        "captured_revision": captured_revision,
        "global_analysis_converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    return NativeAdaptiveAnalysisReceiptV1(**core, receipt_sha256=canonical_sha256(core))


def verify_native_adaptive_analysis_receipt(receipt: NativeAdaptiveAnalysisReceiptV1) -> None:
    if receipt.schema != "AsterMaxNativeAdaptiveAnalysisReceiptV1" or receipt.status != "VERIFIED_ADAPTIVE_RESULTS_READY":
        raise NativeAdaptiveAnalysisError("NATIVE_ADAPTIVE_RECEIPT_SCHEMA")
    if receipt.global_analysis_converged or receipt.industrial_validation or receipt.ansys_equivalence:
        raise NativeAdaptiveAnalysisError("NATIVE_ADAPTIVE_RECEIPT_OVERCLAIM")
    core = receipt.__dict__.copy()
    core.pop("receipt_sha256")
    if canonical_sha256(core) != receipt.receipt_sha256:
        raise NativeAdaptiveAnalysisError("NATIVE_ADAPTIVE_RECEIPT_TAMPERED")
