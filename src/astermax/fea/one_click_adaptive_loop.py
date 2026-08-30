from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

from astermax.credibility import canonical_sha256
from .adaptive_demo_session import AdaptiveDemoSessionV1, build_adaptive_demo_session
from .adaptive_results_dashboard import AdaptiveResultsDashboardV1, build_adaptive_results_dashboard
from .adaptive_second_solve import build_adaptive_physical_route, execute_provenance_matched_second_solve
from .evidence import sha256_file
from .face_ownership import Tet10FaceOwnershipInventory, mesh_step_tet10_with_face_ownership
from .named_selections import PersistentNamedSelection


class OneClickAdaptiveLoopError(ValueError):
    pass


@dataclass(frozen=True)
class OneClickAdaptiveRunV1:
    schema: str
    source_step_sha256: str
    support_named_selection_sha256: str
    load_named_selection_sha256: str
    route_sha256: str
    baseline_target_size_mm: float
    refined_target_size_mm: float
    young_modulus_mpa: float
    poisson_ratio: float
    resultant_n: tuple[float, float, float]
    maximum_relative_qoi_change: float
    requires_human_approval: bool
    changes_physics: bool
    run_sha256: str


@dataclass(frozen=True)
class OneClickAdaptiveApprovalV1:
    schema: str
    run_sha256: str
    approved: bool
    approver: str
    scope: str
    approval_sha256: str


@dataclass(frozen=True)
class OneClickAdaptiveExecutionV1:
    schema: str
    run_sha256: str
    approval_sha256: str
    baseline_mesh_sha256: str
    refined_mesh_sha256: str
    adaptive_evidence_sha256: str
    session_sha256: str
    dashboard_sha256: str
    qoi_status: str
    qoi_relative_change: float
    global_analysis_converged: bool
    industrial_validation: bool
    ansys_equivalence: bool
    execution_sha256: str


def _positive(value: float, code: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise OneClickAdaptiveLoopError(code)
    return result


def prepare_one_click_adaptive_run(
    step_path: str | Path,
    support: PersistentNamedSelection,
    load: PersistentNamedSelection,
    *,
    baseline_target_size_mm: float,
    refined_target_size_mm: float,
    young_modulus_mpa: float,
    poisson_ratio: float,
    resultant_n: tuple[float, float, float],
    maximum_relative_qoi_change: float,
) -> OneClickAdaptiveRunV1:
    step = Path(step_path)
    if step.suffix.lower() not in {".step", ".stp"} or not step.is_file():
        raise OneClickAdaptiveLoopError("ONE_CLICK_STEP_REQUIRED")
    source_sha = sha256_file(step)
    coarse = _positive(baseline_target_size_mm, "ONE_CLICK_BASELINE_SIZE")
    fine = _positive(refined_target_size_mm, "ONE_CLICK_REFINED_SIZE")
    if fine >= coarse:
        raise OneClickAdaptiveLoopError("ONE_CLICK_REFINEMENT_ORDER")
    criterion = float(maximum_relative_qoi_change)
    if not math.isfinite(criterion) or criterion < 0.0:
        raise OneClickAdaptiveLoopError("ONE_CLICK_QOI_CRITERION")
    route = build_adaptive_physical_route(
        source_step_sha256=source_sha,
        support=support,
        load=load,
        young_modulus_mpa=young_modulus_mpa,
        poisson_ratio=poisson_ratio,
        resultant_n=resultant_n,
    )
    core = {
        "schema": "AsterMaxOneClickAdaptiveRunV1",
        "source_step_sha256": source_sha,
        "support_named_selection_sha256": support.named_selection_sha256,
        "load_named_selection_sha256": load.named_selection_sha256,
        "route_sha256": route.route_sha256,
        "baseline_target_size_mm": coarse,
        "refined_target_size_mm": fine,
        "young_modulus_mpa": route.young_modulus_mpa,
        "poisson_ratio": route.poisson_ratio,
        "resultant_n": route.resultant_n,
        "maximum_relative_qoi_change": criterion,
        "requires_human_approval": True,
        "changes_physics": False,
    }
    return OneClickAdaptiveRunV1(**core, run_sha256=canonical_sha256(core))


def approve_one_click_adaptive_run(run: OneClickAdaptiveRunV1, *, approver: str, approved: bool) -> OneClickAdaptiveApprovalV1:
    if run.schema != "AsterMaxOneClickAdaptiveRunV1":
        raise OneClickAdaptiveLoopError("ONE_CLICK_RUN_SCHEMA")
    name = approver.strip() if isinstance(approver, str) else ""
    if not name:
        raise OneClickAdaptiveLoopError("ONE_CLICK_APPROVER_REQUIRED")
    core = {
        "schema": "AsterMaxOneClickAdaptiveApprovalV1",
        "run_sha256": run.run_sha256,
        "approved": bool(approved),
        "approver": name,
        "scope": "MESH_DISCRETIZATION_ONLY_PHYSICS_FROZEN",
    }
    return OneClickAdaptiveApprovalV1(**core, approval_sha256=canonical_sha256(core))


def execute_approved_one_click_adaptive_run(
    step_path: str | Path,
    support: PersistentNamedSelection,
    load: PersistentNamedSelection,
    run: OneClickAdaptiveRunV1,
    approval: OneClickAdaptiveApprovalV1,
) -> tuple[OneClickAdaptiveExecutionV1, AdaptiveDemoSessionV1, AdaptiveResultsDashboardV1, Tet10FaceOwnershipInventory, Tet10FaceOwnershipInventory]:
    if run.schema != "AsterMaxOneClickAdaptiveRunV1":
        raise OneClickAdaptiveLoopError("ONE_CLICK_RUN_SCHEMA")
    core = run.__dict__.copy(); core.pop("run_sha256")
    if canonical_sha256(core) != run.run_sha256:
        raise OneClickAdaptiveLoopError("ONE_CLICK_RUN_TAMPERED")
    if approval.schema != "AsterMaxOneClickAdaptiveApprovalV1" or approval.run_sha256 != run.run_sha256:
        raise OneClickAdaptiveLoopError("ONE_CLICK_APPROVAL_STALE")
    approval_core = approval.__dict__.copy(); approval_core.pop("approval_sha256")
    if canonical_sha256(approval_core) != approval.approval_sha256:
        raise OneClickAdaptiveLoopError("ONE_CLICK_APPROVAL_TAMPERED")
    if not approval.approved:
        raise OneClickAdaptiveLoopError("ONE_CLICK_HUMAN_APPROVAL_REQUIRED")
    if approval.scope != "MESH_DISCRETIZATION_ONLY_PHYSICS_FROZEN":
        raise OneClickAdaptiveLoopError("ONE_CLICK_APPROVAL_SCOPE")
    if sha256_file(Path(step_path)) != run.source_step_sha256:
        raise OneClickAdaptiveLoopError("ONE_CLICK_STEP_CHANGED")
    if support.named_selection_sha256 != run.support_named_selection_sha256 or load.named_selection_sha256 != run.load_named_selection_sha256:
        raise OneClickAdaptiveLoopError("ONE_CLICK_BC_LOAD_CHANGED")

    baseline = mesh_step_tet10_with_face_ownership(step_path, run.baseline_target_size_mm)
    refined = mesh_step_tet10_with_face_ownership(step_path, run.refined_target_size_mm)
    if refined.ownership_sha256 == baseline.ownership_sha256 or refined.elements.shape[0] <= baseline.elements.shape[0]:
        raise OneClickAdaptiveLoopError("ONE_CLICK_DISTINCT_REFINED_MESH_REQUIRED")

    evidence, coarse_qoi, fine_qoi, assessment = execute_provenance_matched_second_solve(
        step_path,
        baseline,
        refined,
        support,
        load,
        baseline_target_size_mm=run.baseline_target_size_mm,
        remesh_target_size_mm=run.refined_target_size_mm,
        young_modulus_mpa=run.young_modulus_mpa,
        poisson_ratio=run.poisson_ratio,
        resultant_n=run.resultant_n,
        maximum_relative_qoi_change=run.maximum_relative_qoi_change,
    )
    session = build_adaptive_demo_session(evidence, coarse_qoi, fine_qoi, assessment)
    dashboard = build_adaptive_results_dashboard(session)
    exec_core = {
        "schema": "AsterMaxOneClickAdaptiveExecutionV1",
        "run_sha256": run.run_sha256,
        "approval_sha256": approval.approval_sha256,
        "baseline_mesh_sha256": baseline.ownership_sha256,
        "refined_mesh_sha256": refined.ownership_sha256,
        "adaptive_evidence_sha256": evidence.evidence_sha256,
        "session_sha256": session.session_sha256,
        "dashboard_sha256": dashboard.dashboard_sha256,
        "qoi_status": assessment.status,
        "qoi_relative_change": float(assessment.relative_change),
        "global_analysis_converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    execution = OneClickAdaptiveExecutionV1(**exec_core, execution_sha256=canonical_sha256(exec_core))
    return execution, session, dashboard, baseline, refined
