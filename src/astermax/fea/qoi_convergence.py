from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from astermax.credibility import canonical_sha256
from .worst_element_inspector import WorstElementQualitySnapshot


@dataclass(frozen=True)
class QoiObservationV1:
    schema: str
    source_step_sha256: str
    route_sha256: str
    solve_evidence_sha256: str
    mesh_identity_sha256: str
    mesh_target_size_mm: float
    element_count: int
    qoi_name: str
    qoi_unit: str
    qoi_value: float
    observation_sha256: str


@dataclass(frozen=True)
class QoiConvergenceCriteriaV1:
    maximum_relative_change: float
    require_finer_mesh: bool = True


@dataclass(frozen=True)
class QoiConvergenceAssessmentV1:
    schema: str
    status: str
    coarse_observation_sha256: str
    fine_observation_sha256: str
    qoi_name: str
    qoi_unit: str
    coarse_value: float
    fine_value: float
    absolute_change: float
    relative_change: float
    criterion_maximum_relative_change: float
    provenance_match: bool
    refinement_order_verified: bool
    blockers: tuple[str, ...]
    claims: dict[str, bool]
    assessment_sha256: str


@dataclass(frozen=True)
class LocalRefinementReviewV1:
    schema: str
    inspector_snapshot_sha256: str
    candidate_element_indices: tuple[int, ...]
    candidate_centroids_mm: tuple[tuple[float, float, float], ...]
    rationale: tuple[str, ...]
    requires_human_approval: bool
    auto_execution_allowed: bool
    changes_physics: bool
    review_sha256: str


def _valid_sha(value: Any, error: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(error)
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(error) from exc
    return value


def make_qoi_observation(
    *,
    source_step_sha256: str,
    route_sha256: str,
    solve_evidence_sha256: str,
    mesh_identity_sha256: str,
    mesh_target_size_mm: float,
    element_count: int,
    qoi_name: str,
    qoi_unit: str,
    qoi_value: float,
) -> QoiObservationV1:
    source = _valid_sha(source_step_sha256, "QOI_SOURCE_STEP_SHA")
    route = _valid_sha(route_sha256, "QOI_ROUTE_SHA")
    solve = _valid_sha(solve_evidence_sha256, "QOI_SOLVE_SHA")
    mesh = _valid_sha(mesh_identity_sha256, "QOI_MESH_SHA")
    size = float(mesh_target_size_mm)
    count = int(element_count)
    value = float(qoi_value)
    if not math.isfinite(size) or size <= 0.0:
        raise ValueError("QOI_MESH_TARGET_SIZE")
    if count <= 0:
        raise ValueError("QOI_ELEMENT_COUNT")
    if not isinstance(qoi_name, str) or not qoi_name.strip():
        raise ValueError("QOI_NAME_REQUIRED")
    if not isinstance(qoi_unit, str) or not qoi_unit.strip():
        raise ValueError("QOI_UNIT_REQUIRED")
    if not math.isfinite(value):
        raise ValueError("QOI_VALUE_NONFINITE")
    core = {
        "schema": "AsterMaxQoiObservationV1",
        "source_step_sha256": source,
        "route_sha256": route,
        "solve_evidence_sha256": solve,
        "mesh_identity_sha256": mesh,
        "mesh_target_size_mm": size,
        "element_count": count,
        "qoi_name": qoi_name.strip(),
        "qoi_unit": qoi_unit.strip(),
        "qoi_value": value,
    }
    return QoiObservationV1(**core, observation_sha256=canonical_sha256(core))


def assess_qoi_convergence(
    coarse: QoiObservationV1,
    fine: QoiObservationV1,
    criteria: QoiConvergenceCriteriaV1,
) -> QoiConvergenceAssessmentV1:
    if coarse.schema != "AsterMaxQoiObservationV1" or fine.schema != "AsterMaxQoiObservationV1":
        raise ValueError("QOI_OBSERVATION_SCHEMA")
    maximum = float(criteria.maximum_relative_change)
    if not math.isfinite(maximum) or maximum < 0.0:
        raise ValueError("QOI_CONVERGENCE_CRITERION")

    provenance_match = (
        coarse.source_step_sha256 == fine.source_step_sha256
        and coarse.route_sha256 == fine.route_sha256
        and coarse.qoi_name == fine.qoi_name
        and coarse.qoi_unit == fine.qoi_unit
    )
    refinement_order_verified = (
        fine.mesh_target_size_mm < coarse.mesh_target_size_mm
        and fine.element_count > coarse.element_count
        and fine.mesh_identity_sha256 != coarse.mesh_identity_sha256
        and fine.solve_evidence_sha256 != coarse.solve_evidence_sha256
    )
    blockers: list[str] = []
    if not provenance_match:
        blockers.append("QOI_PHYSICAL_MODEL_PROVENANCE_MISMATCH")
    if criteria.require_finer_mesh and not refinement_order_verified:
        blockers.append("QOI_REFINEMENT_ORDER_NOT_VERIFIED")

    absolute_change = abs(fine.qoi_value - coarse.qoi_value)
    scale = max(abs(fine.qoi_value), abs(coarse.qoi_value))
    if scale == 0.0:
        relative_change = 0.0
    else:
        relative_change = absolute_change / scale
    if relative_change > maximum:
        blockers.append("QOI_RELATIVE_CHANGE_ABOVE_EXPLICIT_CRITERION")

    status = "PASS" if not blockers else "FAIL"
    claims = {
        "qoi_discretization_converged": status == "PASS",
        "global_analysis_converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    core = {
        "schema": "AsterMaxQoiConvergenceAssessmentV1",
        "status": status,
        "coarse_observation_sha256": coarse.observation_sha256,
        "fine_observation_sha256": fine.observation_sha256,
        "qoi_name": coarse.qoi_name,
        "qoi_unit": coarse.qoi_unit,
        "coarse_value": coarse.qoi_value,
        "fine_value": fine.qoi_value,
        "absolute_change": absolute_change,
        "relative_change": relative_change,
        "criterion_maximum_relative_change": maximum,
        "provenance_match": provenance_match,
        "refinement_order_verified": refinement_order_verified,
        "blockers": blockers,
        "claims": claims,
    }
    return QoiConvergenceAssessmentV1(
        schema=core["schema"],
        status=status,
        coarse_observation_sha256=coarse.observation_sha256,
        fine_observation_sha256=fine.observation_sha256,
        qoi_name=coarse.qoi_name,
        qoi_unit=coarse.qoi_unit,
        coarse_value=coarse.qoi_value,
        fine_value=fine.qoi_value,
        absolute_change=absolute_change,
        relative_change=relative_change,
        criterion_maximum_relative_change=maximum,
        provenance_match=provenance_match,
        refinement_order_verified=refinement_order_verified,
        blockers=tuple(blockers),
        claims=claims,
        assessment_sha256=canonical_sha256(core),
    )


def build_local_refinement_review(
    inspector: WorstElementQualitySnapshot,
    *,
    maximum_candidates: int = 8,
) -> LocalRefinementReviewV1:
    if inspector.schema != "AsterMaxWorstElementQualityInspectorV1":
        raise ValueError("LOCAL_REFINEMENT_INSPECTOR_SCHEMA")
    if inspector.ansys_metric_equivalence:
        raise ValueError("LOCAL_REFINEMENT_ANSYS_METRIC_OVERCLAIM")
    if not inspector.crosscheck_verified:
        raise ValueError("LOCAL_REFINEMENT_CROSSCHECK_REQUIRED")
    count = int(maximum_candidates)
    if count < 1:
        raise ValueError("LOCAL_REFINEMENT_CANDIDATE_COUNT")
    rows = inspector.worst_elements[:count]
    if not rows:
        raise ValueError("LOCAL_REFINEMENT_WORST_ELEMENTS_REQUIRED")
    indices = tuple(int(row["element_index"]) for row in rows)
    centroids = tuple(tuple(float(v) for v in row["centroid_mm"]) for row in rows)
    if len(set(indices)) != len(indices):
        raise ValueError("LOCAL_REFINEMENT_DUPLICATE_ELEMENT")
    core = {
        "schema": "AsterMaxLocalRefinementReviewV1",
        "inspector_snapshot_sha256": inspector.snapshot_sha256,
        "candidate_element_indices": indices,
        "candidate_centroids_mm": centroids,
        "rationale": (
            "CANDIDATES_LOCALIZED_FROM_CROSSCHECKED_WORST_ELEMENT_INSPECTOR",
            "LOCALIZATION_IS_A_REVIEW_TARGET_NOT_AN_AUTOMATIC_MESH_COMMAND",
            "RE_SOLVE_AND_COMPARE_EXPLICIT_QOI_AFTER_ANY_APPROVED_REFINEMENT",
        ),
        "requires_human_approval": True,
        "auto_execution_allowed": False,
        "changes_physics": False,
    }
    return LocalRefinementReviewV1(**core, review_sha256=canonical_sha256(core))


def verify_qoi_convergence_boundary(assessment: QoiConvergenceAssessmentV1) -> None:
    if assessment.schema != "AsterMaxQoiConvergenceAssessmentV1":
        raise ValueError("QOI_ASSESSMENT_SCHEMA")
    if assessment.claims.get("global_analysis_converged"):
        raise ValueError("QOI_GLOBAL_CONVERGENCE_OVERCLAIM")
    if assessment.claims.get("industrial_validation"):
        raise ValueError("QOI_INDUSTRIAL_VALIDATION_OVERCLAIM")
    if assessment.claims.get("ansys_equivalence"):
        raise ValueError("QOI_ANSYS_EQUIVALENCE_OVERCLAIM")
    if assessment.claims.get("qoi_discretization_converged") != (assessment.status == "PASS"):
        raise ValueError("QOI_CONVERGENCE_STATUS_STALE")
