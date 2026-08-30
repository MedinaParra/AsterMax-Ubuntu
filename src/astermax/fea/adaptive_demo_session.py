from __future__ import annotations

from dataclasses import dataclass
import math

from astermax.credibility import canonical_sha256
from .adaptive_second_solve import AdaptiveSecondSolveEvidenceV1, verify_second_solve_evidence
from .qoi_convergence import QoiObservationV1, QoiConvergenceAssessmentV1, verify_qoi_convergence_boundary


class AdaptiveDemoSessionError(ValueError):
    pass


@dataclass(frozen=True)
class AdaptiveDemoStageV1:
    index: int
    name: str
    label: str
    status: str
    evidence_sha256: str


@dataclass(frozen=True)
class AdaptiveDemoSessionV1:
    schema: str
    semantics: str
    status: str
    title: str
    subtitle: str
    source_step_sha256: str
    route_sha256: str
    baseline_mesh_sha256: str
    remesh_mesh_sha256: str
    baseline_solve_evidence_sha256: str
    remesh_solve_evidence_sha256: str
    qoi_name: str
    qoi_unit: str
    baseline_qoi_value: float
    remesh_qoi_value: float
    qoi_relative_change: float
    qoi_criterion_maximum_relative_change: float
    qoi_status: str
    baseline_force_residual_n: float
    remesh_force_residual_n: float
    baseline_moment_residual_nmm: float
    remesh_moment_residual_nmm: float
    stage_count: int
    ready_stage_count: int
    progress_percent: int
    stages: tuple[AdaptiveDemoStageV1, ...]
    claims: dict[str, bool]
    session_sha256: str


_STAGE_LABELS = (
    ("CAD_STEP_MM", "CAD / STEP [mm]"),
    ("PHYSICS_ROUTE", "Persistent BC/load physical route"),
    ("BASELINE_TET10", "Baseline TET10 discretization"),
    ("BASELINE_SOLVE", "Baseline sparse structural solve"),
    ("PERSISTENT_REBINDING", "Persistent CAD↔mesh rebinding"),
    ("REFINED_TET10", "Refined TET10 discretization"),
    ("REFINED_SOLVE", "Refined sparse structural solve"),
    ("QOI_COMPARISON", "QoI discretization comparison"),
    ("ENGINEERING_EVIDENCE", "Engineering evidence closure"),
)


def _require_sha(value: str, code: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise AdaptiveDemoSessionError(code)
    try:
        int(value, 16)
    except ValueError as exc:
        raise AdaptiveDemoSessionError(code) from exc
    return value


def build_adaptive_demo_session(
    second_solve: AdaptiveSecondSolveEvidenceV1,
    baseline_qoi: QoiObservationV1,
    remesh_qoi: QoiObservationV1,
    assessment: QoiConvergenceAssessmentV1,
) -> AdaptiveDemoSessionV1:
    """Create a presentation-safe adaptive FEA session from already verified evidence.

    This builder performs no meshing and no structural solve. It exposes only values
    produced by the provenance-matched second-solve loop and deliberately keeps global,
    industrial and ANSYS-equivalence claims false.
    """
    try:
        verify_second_solve_evidence(second_solve)
        verify_qoi_convergence_boundary(assessment)
    except ValueError as exc:
        raise AdaptiveDemoSessionError(f"ADAPTIVE_DEMO_UPSTREAM_EVIDENCE:{exc}") from exc

    if baseline_qoi.schema != "AsterMaxQoiObservationV1" or remesh_qoi.schema != "AsterMaxQoiObservationV1":
        raise AdaptiveDemoSessionError("ADAPTIVE_DEMO_QOI_SCHEMA")
    if assessment.schema != "AsterMaxQoiConvergenceAssessmentV1":
        raise AdaptiveDemoSessionError("ADAPTIVE_DEMO_ASSESSMENT_SCHEMA")

    source = _require_sha(baseline_qoi.source_step_sha256, "ADAPTIVE_DEMO_STEP_SHA")
    route = _require_sha(second_solve.route_sha256, "ADAPTIVE_DEMO_ROUTE_SHA")
    if remesh_qoi.source_step_sha256 != source:
        raise AdaptiveDemoSessionError("ADAPTIVE_DEMO_STEP_PROVENANCE")
    if baseline_qoi.route_sha256 != route or remesh_qoi.route_sha256 != route:
        raise AdaptiveDemoSessionError("ADAPTIVE_DEMO_ROUTE_PROVENANCE")
    if baseline_qoi.observation_sha256 != second_solve.baseline_qoi_observation_sha256:
        raise AdaptiveDemoSessionError("ADAPTIVE_DEMO_BASELINE_QOI_PROVENANCE")
    if remesh_qoi.observation_sha256 != second_solve.remesh_qoi_observation_sha256:
        raise AdaptiveDemoSessionError("ADAPTIVE_DEMO_REMESH_QOI_PROVENANCE")
    if assessment.assessment_sha256 != second_solve.qoi_assessment_sha256:
        raise AdaptiveDemoSessionError("ADAPTIVE_DEMO_ASSESSMENT_PROVENANCE")
    if assessment.coarse_observation_sha256 != baseline_qoi.observation_sha256 or assessment.fine_observation_sha256 != remesh_qoi.observation_sha256:
        raise AdaptiveDemoSessionError("ADAPTIVE_DEMO_QOI_ASSESSMENT_LINK")
    if baseline_qoi.mesh_identity_sha256 != second_solve.baseline_mesh_sha256 or remesh_qoi.mesh_identity_sha256 != second_solve.remesh_mesh_sha256:
        raise AdaptiveDemoSessionError("ADAPTIVE_DEMO_MESH_PROVENANCE")
    if baseline_qoi.solve_evidence_sha256 != second_solve.baseline_solve_evidence_sha256 or remesh_qoi.solve_evidence_sha256 != second_solve.remesh_solve_evidence_sha256:
        raise AdaptiveDemoSessionError("ADAPTIVE_DEMO_SOLVE_PROVENANCE")
    if baseline_qoi.qoi_name != remesh_qoi.qoi_name or baseline_qoi.qoi_unit != remesh_qoi.qoi_unit:
        raise AdaptiveDemoSessionError("ADAPTIVE_DEMO_QOI_IDENTITY")
    if assessment.qoi_name != baseline_qoi.qoi_name or assessment.qoi_unit != baseline_qoi.qoi_unit:
        raise AdaptiveDemoSessionError("ADAPTIVE_DEMO_ASSESSMENT_QOI_IDENTITY")
    if not assessment.provenance_match or not assessment.refinement_order_verified:
        raise AdaptiveDemoSessionError("ADAPTIVE_DEMO_REFINEMENT_PROVENANCE")

    numeric = (
        baseline_qoi.qoi_value,
        remesh_qoi.qoi_value,
        assessment.relative_change,
        assessment.criterion_maximum_relative_change,
        second_solve.baseline_force_residual_n,
        second_solve.remesh_force_residual_n,
        second_solve.baseline_moment_residual_nmm,
        second_solve.remesh_moment_residual_nmm,
    )
    if not all(math.isfinite(float(value)) for value in numeric):
        raise AdaptiveDemoSessionError("ADAPTIVE_DEMO_NONFINITE")

    stage_evidence = (
        source,
        route,
        second_solve.baseline_mesh_sha256,
        second_solve.baseline_solve_evidence_sha256,
        second_solve.boundary_route_evidence_sha256,
        second_solve.remesh_mesh_sha256,
        second_solve.remesh_solve_evidence_sha256,
        assessment.assessment_sha256,
        second_solve.evidence_sha256,
    )
    stages = tuple(
        AdaptiveDemoStageV1(index=i, name=name, label=label, status="READY", evidence_sha256=_require_sha(evidence, "ADAPTIVE_DEMO_STAGE_SHA"))
        for i, ((name, label), evidence) in enumerate(zip(_STAGE_LABELS, stage_evidence), start=1)
    )

    claims = {
        "qoi_discretization_converged": bool(second_solve.qoi_discretization_converged),
        "global_analysis_converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    if claims["qoi_discretization_converged"] != (assessment.status == "PASS"):
        raise AdaptiveDemoSessionError("ADAPTIVE_DEMO_QOI_STATUS_STALE")

    core = {
        "schema": "AsterMaxNativeAdaptiveDemoSessionV1",
        "status": "READY",
        "source_step_sha256": source,
        "route_sha256": route,
        "baseline_mesh_sha256": second_solve.baseline_mesh_sha256,
        "remesh_mesh_sha256": second_solve.remesh_mesh_sha256,
        "baseline_solve_evidence_sha256": second_solve.baseline_solve_evidence_sha256,
        "remesh_solve_evidence_sha256": second_solve.remesh_solve_evidence_sha256,
        "qoi_name": baseline_qoi.qoi_name,
        "qoi_unit": baseline_qoi.qoi_unit,
        "baseline_qoi_value": float(baseline_qoi.qoi_value),
        "remesh_qoi_value": float(remesh_qoi.qoi_value),
        "qoi_relative_change": float(assessment.relative_change),
        "qoi_criterion_maximum_relative_change": float(assessment.criterion_maximum_relative_change),
        "qoi_status": assessment.status,
        "baseline_force_residual_n": float(second_solve.baseline_force_residual_n),
        "remesh_force_residual_n": float(second_solve.remesh_force_residual_n),
        "baseline_moment_residual_nmm": float(second_solve.baseline_moment_residual_nmm),
        "remesh_moment_residual_nmm": float(second_solve.remesh_moment_residual_nmm),
        "stages": [stage.__dict__ for stage in stages],
        "claims": claims,
    }
    return AdaptiveDemoSessionV1(
        schema=core["schema"],
        semantics="presentation_only_from_provenance_matched_real_solve_evidence_no_physics_recomputation",
        status="READY",
        title="AsterMax · Adaptive FEA Evidence Session",
        subtitle="STEP [mm] → BC/load → baseline TET10 → solve → persistent rebinding → refined TET10 → solve → QoI evidence",
        source_step_sha256=source,
        route_sha256=route,
        baseline_mesh_sha256=second_solve.baseline_mesh_sha256,
        remesh_mesh_sha256=second_solve.remesh_mesh_sha256,
        baseline_solve_evidence_sha256=second_solve.baseline_solve_evidence_sha256,
        remesh_solve_evidence_sha256=second_solve.remesh_solve_evidence_sha256,
        qoi_name=baseline_qoi.qoi_name,
        qoi_unit=baseline_qoi.qoi_unit,
        baseline_qoi_value=float(baseline_qoi.qoi_value),
        remesh_qoi_value=float(remesh_qoi.qoi_value),
        qoi_relative_change=float(assessment.relative_change),
        qoi_criterion_maximum_relative_change=float(assessment.criterion_maximum_relative_change),
        qoi_status=assessment.status,
        baseline_force_residual_n=float(second_solve.baseline_force_residual_n),
        remesh_force_residual_n=float(second_solve.remesh_force_residual_n),
        baseline_moment_residual_nmm=float(second_solve.baseline_moment_residual_nmm),
        remesh_moment_residual_nmm=float(second_solve.remesh_moment_residual_nmm),
        stage_count=len(stages),
        ready_stage_count=len(stages),
        progress_percent=100,
        stages=stages,
        claims=claims,
        session_sha256=canonical_sha256(core),
    )


def verify_adaptive_demo_session(session: AdaptiveDemoSessionV1) -> None:
    if session.schema != "AsterMaxNativeAdaptiveDemoSessionV1" or session.status != "READY":
        raise AdaptiveDemoSessionError("ADAPTIVE_DEMO_SESSION_SCHEMA_STATUS")
    if session.stage_count != len(session.stages) or session.ready_stage_count != session.stage_count or session.progress_percent != 100:
        raise AdaptiveDemoSessionError("ADAPTIVE_DEMO_STAGE_CLOSURE")
    if any(stage.status != "READY" for stage in session.stages):
        raise AdaptiveDemoSessionError("ADAPTIVE_DEMO_STAGE_NOT_READY")
    if session.claims.get("global_analysis_converged") or session.claims.get("industrial_validation") or session.claims.get("ansys_equivalence"):
        raise AdaptiveDemoSessionError("ADAPTIVE_DEMO_OVERCLAIM")
    core = {
        "schema": session.schema,
        "status": session.status,
        "source_step_sha256": session.source_step_sha256,
        "route_sha256": session.route_sha256,
        "baseline_mesh_sha256": session.baseline_mesh_sha256,
        "remesh_mesh_sha256": session.remesh_mesh_sha256,
        "baseline_solve_evidence_sha256": session.baseline_solve_evidence_sha256,
        "remesh_solve_evidence_sha256": session.remesh_solve_evidence_sha256,
        "qoi_name": session.qoi_name,
        "qoi_unit": session.qoi_unit,
        "baseline_qoi_value": session.baseline_qoi_value,
        "remesh_qoi_value": session.remesh_qoi_value,
        "qoi_relative_change": session.qoi_relative_change,
        "qoi_criterion_maximum_relative_change": session.qoi_criterion_maximum_relative_change,
        "qoi_status": session.qoi_status,
        "baseline_force_residual_n": session.baseline_force_residual_n,
        "remesh_force_residual_n": session.remesh_force_residual_n,
        "baseline_moment_residual_nmm": session.baseline_moment_residual_nmm,
        "remesh_moment_residual_nmm": session.remesh_moment_residual_nmm,
        "stages": [stage.__dict__ for stage in session.stages],
        "claims": session.claims,
    }
    if canonical_sha256(core) != session.session_sha256:
        raise AdaptiveDemoSessionError("ADAPTIVE_DEMO_SESSION_TAMPERED")
