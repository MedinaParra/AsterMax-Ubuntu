from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable

from astermax.credibility import canonical_sha256
from .qoi_convergence import LocalRefinementReviewV1


@dataclass(frozen=True)
class LocalRefinementRegionV1:
    element_index: int
    centroid_mm: tuple[float, float, float]
    radius_mm: float
    target_size_mm: float


@dataclass(frozen=True)
class ControlledLocalRefinementPlanV1:
    schema: str
    source_step_sha256: str
    route_sha256: str
    baseline_mesh_sha256: str
    review_sha256: str
    baseline_size_mm: float
    refined_size_mm: float
    radius_mm: float
    regions: tuple[LocalRefinementRegionV1, ...]
    requires_human_approval: bool
    auto_execution_allowed: bool
    changes_physics: bool
    preserves_source_geometry: bool
    preserves_bc_load_route: bool
    plan_sha256: str


@dataclass(frozen=True)
class RefinementApprovalV1:
    schema: str
    plan_sha256: str
    approved: bool
    approver: str
    scope: str
    approval_sha256: str


def _valid_sha(value: Any, error: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(error)
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(error) from exc
    return value


def _finite_positive(value: float, error: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(error)
    return result


def build_controlled_local_refinement_plan(
    *,
    source_step_sha256: str,
    route_sha256: str,
    baseline_mesh_sha256: str,
    review: LocalRefinementReviewV1,
    baseline_size_mm: float,
    refined_size_factor: float = 0.5,
    influence_radius_factor: float = 2.0,
) -> ControlledLocalRefinementPlanV1:
    """Build a deterministic, review-only local mesh refinement plan.

    This contract deliberately does not call Gmsh or mutate the model. It turns
    cross-checked worst-element centroids into bounded spherical refinement
    regions while preserving STEP and BC/load provenance. Execution remains a
    separate, human-approved increment.
    """
    source = _valid_sha(source_step_sha256, "REFINEMENT_SOURCE_STEP_SHA")
    route = _valid_sha(route_sha256, "REFINEMENT_ROUTE_SHA")
    mesh = _valid_sha(baseline_mesh_sha256, "REFINEMENT_BASELINE_MESH_SHA")
    if review.schema != "AsterMaxLocalRefinementReviewV1":
        raise ValueError("REFINEMENT_REVIEW_SCHEMA")
    _valid_sha(review.review_sha256, "REFINEMENT_REVIEW_SHA")
    if review.auto_execution_allowed:
        raise ValueError("REFINEMENT_REVIEW_AUTO_EXECUTION_FORBIDDEN")
    if review.changes_physics:
        raise ValueError("REFINEMENT_REVIEW_PHYSICS_MUTATION_FORBIDDEN")
    if not review.requires_human_approval:
        raise ValueError("REFINEMENT_REVIEW_HUMAN_APPROVAL_REQUIRED")
    if len(review.candidate_element_indices) != len(review.candidate_centroids_mm):
        raise ValueError("REFINEMENT_REVIEW_CANDIDATE_ALIGNMENT")
    if not review.candidate_element_indices:
        raise ValueError("REFINEMENT_REVIEW_CANDIDATES_REQUIRED")

    baseline = _finite_positive(baseline_size_mm, "REFINEMENT_BASELINE_SIZE")
    factor = float(refined_size_factor)
    radius_factor = float(influence_radius_factor)
    if not math.isfinite(factor) or not 0.0 < factor < 1.0:
        raise ValueError("REFINEMENT_SIZE_FACTOR_RANGE")
    if not math.isfinite(radius_factor) or radius_factor <= 0.0:
        raise ValueError("REFINEMENT_RADIUS_FACTOR_RANGE")
    refined = baseline * factor
    radius = baseline * radius_factor

    seen: set[int] = set()
    regions: list[LocalRefinementRegionV1] = []
    for element_index, centroid in zip(review.candidate_element_indices, review.candidate_centroids_mm):
        index = int(element_index)
        if index < 0 or index in seen:
            raise ValueError("REFINEMENT_CANDIDATE_ELEMENT_ID")
        seen.add(index)
        if len(centroid) != 3:
            raise ValueError("REFINEMENT_CANDIDATE_CENTROID")
        point = tuple(float(v) for v in centroid)
        if not all(math.isfinite(v) for v in point):
            raise ValueError("REFINEMENT_CANDIDATE_CENTROID_NONFINITE")
        regions.append(LocalRefinementRegionV1(index, point, radius, refined))

    core = {
        "schema": "AsterMaxControlledLocalRefinementPlanV1",
        "source_step_sha256": source,
        "route_sha256": route,
        "baseline_mesh_sha256": mesh,
        "review_sha256": review.review_sha256,
        "baseline_size_mm": baseline,
        "refined_size_mm": refined,
        "radius_mm": radius,
        "regions": [
            {
                "element_index": region.element_index,
                "centroid_mm": region.centroid_mm,
                "radius_mm": region.radius_mm,
                "target_size_mm": region.target_size_mm,
            }
            for region in regions
        ],
        "requires_human_approval": True,
        "auto_execution_allowed": False,
        "changes_physics": False,
        "preserves_source_geometry": True,
        "preserves_bc_load_route": True,
    }
    return ControlledLocalRefinementPlanV1(
        schema=core["schema"],
        source_step_sha256=source,
        route_sha256=route,
        baseline_mesh_sha256=mesh,
        review_sha256=review.review_sha256,
        baseline_size_mm=baseline,
        refined_size_mm=refined,
        radius_mm=radius,
        regions=tuple(regions),
        requires_human_approval=True,
        auto_execution_allowed=False,
        changes_physics=False,
        preserves_source_geometry=True,
        preserves_bc_load_route=True,
        plan_sha256=canonical_sha256(core),
    )


def target_size_at_point(plan: ControlledLocalRefinementPlanV1, point_mm: Iterable[float]) -> float:
    if plan.schema != "AsterMaxControlledLocalRefinementPlanV1":
        raise ValueError("REFINEMENT_PLAN_SCHEMA")
    point = tuple(float(v) for v in point_mm)
    if len(point) != 3 or not all(math.isfinite(v) for v in point):
        raise ValueError("REFINEMENT_QUERY_POINT")
    target = plan.baseline_size_mm
    for region in plan.regions:
        distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(point, region.centroid_mm)))
        if distance <= region.radius_mm:
            target = min(target, region.target_size_mm)
    return float(target)


def approve_refinement_plan(
    plan: ControlledLocalRefinementPlanV1,
    *,
    approver: str,
    approved: bool,
) -> RefinementApprovalV1:
    if plan.schema != "AsterMaxControlledLocalRefinementPlanV1":
        raise ValueError("REFINEMENT_PLAN_SCHEMA")
    _valid_sha(plan.plan_sha256, "REFINEMENT_PLAN_SHA")
    name = approver.strip() if isinstance(approver, str) else ""
    if not name:
        raise ValueError("REFINEMENT_APPROVER_REQUIRED")
    core = {
        "schema": "AsterMaxRefinementApprovalV1",
        "plan_sha256": plan.plan_sha256,
        "approved": bool(approved),
        "approver": name,
        "scope": "MESH_DISCRETIZATION_ONLY_NO_PHYSICS_CHANGE",
    }
    return RefinementApprovalV1(**core, approval_sha256=canonical_sha256(core))


def verify_refinement_execution_boundary(
    plan: ControlledLocalRefinementPlanV1,
    approval: RefinementApprovalV1 | None = None,
) -> None:
    if plan.auto_execution_allowed:
        raise ValueError("REFINEMENT_AUTO_EXECUTION_OVERCLAIM")
    if plan.changes_physics:
        raise ValueError("REFINEMENT_PHYSICS_MUTATION_OVERCLAIM")
    if not plan.preserves_source_geometry or not plan.preserves_bc_load_route:
        raise ValueError("REFINEMENT_PROVENANCE_PRESERVATION_REQUIRED")
    if approval is not None:
        if approval.plan_sha256 != plan.plan_sha256:
            raise ValueError("REFINEMENT_APPROVAL_STALE")
        if approval.scope != "MESH_DISCRETIZATION_ONLY_NO_PHYSICS_CHANGE":
            raise ValueError("REFINEMENT_APPROVAL_SCOPE")
