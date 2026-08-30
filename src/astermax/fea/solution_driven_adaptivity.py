from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from astermax.credibility import canonical_sha256
from .qoi_convergence import LocalRefinementReviewV1
from .solver import Tet10LinearStaticResult


class SolutionDrivenAdaptivityError(ValueError):
    pass


@dataclass(frozen=True)
class SolutionDrivenElementIndicatorV1:
    element_index: int
    centroid_mm: tuple[float, float, float]
    mean_von_mises_mpa: float
    ip_spread_mpa: float
    neighbor_jump_mpa: float
    normalized_indicator: float


@dataclass(frozen=True)
class SolutionDrivenRefinementEvidenceV1:
    schema: str
    source_step_sha256: str
    mesh_identity_sha256: str
    solve_evidence_sha256: str
    indicator_name: str
    element_count: int
    candidate_count: int
    global_von_mises_scale_mpa: float
    maximum_indicator: float
    candidate_element_indices: tuple[int, ...]
    candidates: tuple[SolutionDrivenElementIndicatorV1, ...]
    estimator_certified: bool
    solution_error_bound_claimed: bool
    global_analysis_converged: bool
    industrial_validation: bool
    ansys_equivalence: bool
    evidence_sha256: str


def _valid_sha(value: Any, code: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise SolutionDrivenAdaptivityError(code)
    try:
        int(value, 16)
    except ValueError as exc:
        raise SolutionDrivenAdaptivityError(code) from exc
    return value


def _validate_mesh(nodes_mm: np.ndarray, elements: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise SolutionDrivenAdaptivityError("SOLUTION_ADAPTIVITY_NODES")
    if elems.ndim != 2 or elems.shape[1] != 10 or elems.shape[0] == 0:
        raise SolutionDrivenAdaptivityError("SOLUTION_ADAPTIVITY_TET10")
    if np.any(elems < 0) or np.any(elems >= nodes.shape[0]):
        raise SolutionDrivenAdaptivityError("SOLUTION_ADAPTIVITY_CONNECTIVITY")
    return nodes, elems


def _shared_face_neighbor_jumps(elements: np.ndarray, element_mean: np.ndarray) -> np.ndarray:
    """Maximum von-Mises jump to a face-neighbor using TET10 corner topology only."""
    faces: dict[tuple[int, int, int], list[int]] = {}
    corner_faces = ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3))
    for element_index, conn in enumerate(elements):
        corners = conn[:4]
        for local in corner_faces:
            key = tuple(sorted(int(corners[i]) for i in local))
            faces.setdefault(key, []).append(int(element_index))
    jumps = np.zeros(elements.shape[0], dtype=float)
    for owners in faces.values():
        if len(owners) == 1:
            continue
        if len(owners) != 2:
            raise SolutionDrivenAdaptivityError("SOLUTION_ADAPTIVITY_NONMANIFOLD_FACE")
        a, b = owners
        jump = abs(float(element_mean[a]) - float(element_mean[b]))
        jumps[a] = max(jumps[a], jump)
        jumps[b] = max(jumps[b], jump)
    return jumps


def build_solution_driven_refinement_evidence(
    *,
    source_step_sha256: str,
    mesh_identity_sha256: str,
    solve_evidence_sha256: str,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    result: Tet10LinearStaticResult,
    maximum_candidates: int = 6,
) -> SolutionDrivenRefinementEvidenceV1:
    """Rank local refinement candidates from the *computed* TET10 stress field.

    Indicator V1 = max(integration-point von-Mises spread within an element,
    face-neighbor jump in element-mean von Mises), normalized by a robust global
    stress scale. This is deliberately a refinement heuristic, not a certified
    discretization-error estimator or a solution error bound.
    """
    source = _valid_sha(source_step_sha256, "SOLUTION_ADAPTIVITY_STEP_SHA")
    mesh = _valid_sha(mesh_identity_sha256, "SOLUTION_ADAPTIVITY_MESH_SHA")
    solve = _valid_sha(solve_evidence_sha256, "SOLUTION_ADAPTIVITY_SOLVE_SHA")
    nodes, elems = _validate_mesh(nodes_mm, elements)
    if not isinstance(result, Tet10LinearStaticResult):
        raise SolutionDrivenAdaptivityError("SOLUTION_ADAPTIVITY_RESULT_TYPE")
    vm = np.asarray(result.integration_point_von_mises_mpa, dtype=float)
    if vm.shape != (elems.shape[0], 4) or not np.all(np.isfinite(vm)):
        raise SolutionDrivenAdaptivityError("SOLUTION_ADAPTIVITY_VM_IP_FIELD")
    if np.any(vm < 0.0):
        raise SolutionDrivenAdaptivityError("SOLUTION_ADAPTIVITY_VM_NEGATIVE")
    count = int(maximum_candidates)
    if count < 1:
        raise SolutionDrivenAdaptivityError("SOLUTION_ADAPTIVITY_CANDIDATE_COUNT")

    element_mean = np.mean(vm, axis=1)
    ip_spread = np.max(vm, axis=1) - np.min(vm, axis=1)
    neighbor_jump = _shared_face_neighbor_jumps(elems, element_mean)
    raw = np.maximum(ip_spread, neighbor_jump)
    positive = vm[vm > 0.0]
    if positive.size == 0:
        raise SolutionDrivenAdaptivityError("SOLUTION_ADAPTIVITY_ZERO_STRESS_FIELD")
    scale = float(np.percentile(positive, 95.0))
    if not math.isfinite(scale) or scale <= 0.0:
        raise SolutionDrivenAdaptivityError("SOLUTION_ADAPTIVITY_STRESS_SCALE")
    indicator = raw / scale
    if not np.all(np.isfinite(indicator)):
        raise SolutionDrivenAdaptivityError("SOLUTION_ADAPTIVITY_INDICATOR_NONFINITE")
    maximum = float(np.max(indicator))
    if maximum <= 1.0e-12:
        raise SolutionDrivenAdaptivityError("SOLUTION_ADAPTIVITY_NO_LOCAL_VARIATION")

    order = np.lexsort((np.arange(indicator.size, dtype=np.int64), -indicator))
    selected = order[: min(count, indicator.size)]
    rows: list[SolutionDrivenElementIndicatorV1] = []
    for element_index in selected:
        corners = nodes[elems[element_index, :4]]
        centroid = np.mean(corners, axis=0)
        rows.append(
            SolutionDrivenElementIndicatorV1(
                element_index=int(element_index),
                centroid_mm=tuple(float(v) for v in centroid),
                mean_von_mises_mpa=float(element_mean[element_index]),
                ip_spread_mpa=float(ip_spread[element_index]),
                neighbor_jump_mpa=float(neighbor_jump[element_index]),
                normalized_indicator=float(indicator[element_index]),
            )
        )

    core = {
        "schema": "AsterMaxSolutionDrivenRefinementEvidenceV1",
        "source_step_sha256": source,
        "mesh_identity_sha256": mesh,
        "solve_evidence_sha256": solve,
        "indicator_name": "TET10_IP_SPREAD_OR_FACE_NEIGHBOR_VM_JUMP_NORMALIZED_V1",
        "element_count": int(elems.shape[0]),
        "candidate_count": len(rows),
        "global_von_mises_scale_mpa": scale,
        "maximum_indicator": maximum,
        "candidate_element_indices": tuple(row.element_index for row in rows),
        "candidates": tuple(rows),
        "estimator_certified": False,
        "solution_error_bound_claimed": False,
        "global_analysis_converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    return SolutionDrivenRefinementEvidenceV1(**core, evidence_sha256=canonical_sha256(core))


def build_solution_driven_local_refinement_review(
    evidence: SolutionDrivenRefinementEvidenceV1,
) -> LocalRefinementReviewV1:
    if evidence.schema != "AsterMaxSolutionDrivenRefinementEvidenceV1":
        raise SolutionDrivenAdaptivityError("SOLUTION_ADAPTIVITY_EVIDENCE_SCHEMA")
    core_evidence = evidence.__dict__.copy(); core_evidence.pop("evidence_sha256")
    if canonical_sha256(core_evidence) != evidence.evidence_sha256:
        raise SolutionDrivenAdaptivityError("SOLUTION_ADAPTIVITY_EVIDENCE_TAMPERED")
    if evidence.estimator_certified or evidence.solution_error_bound_claimed:
        raise SolutionDrivenAdaptivityError("SOLUTION_ADAPTIVITY_ESTIMATOR_OVERCLAIM")
    if evidence.global_analysis_converged or evidence.industrial_validation or evidence.ansys_equivalence:
        raise SolutionDrivenAdaptivityError("SOLUTION_ADAPTIVITY_VALIDATION_OVERCLAIM")
    if not evidence.candidates:
        raise SolutionDrivenAdaptivityError("SOLUTION_ADAPTIVITY_CANDIDATES_REQUIRED")
    indices = tuple(row.element_index for row in evidence.candidates)
    centroids = tuple(row.centroid_mm for row in evidence.candidates)
    core = {
        "schema": "AsterMaxLocalRefinementReviewV1",
        "inspector_snapshot_sha256": evidence.evidence_sha256,
        "candidate_element_indices": indices,
        "candidate_centroids_mm": centroids,
        "rationale": (
            "CANDIDATES_LOCALIZED_FROM_COMPUTED_TET10_VON_MISES_VARIATION",
            "INDICATOR_COMBINES_INTEGRATION_POINT_SPREAD_AND_FACE_NEIGHBOR_JUMP",
            "HEURISTIC_REFINEMENT_SIGNAL_NOT_CERTIFIED_SOLUTION_ERROR_ESTIMATOR",
            "REQUIRES_HUMAN_APPROVAL_BEFORE_ANY_REMESH_EXECUTION",
        ),
        "requires_human_approval": True,
        "auto_execution_allowed": False,
        "changes_physics": False,
    }
    return LocalRefinementReviewV1(**core, review_sha256=canonical_sha256(core))
