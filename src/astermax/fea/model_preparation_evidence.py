from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from astermax.credibility import canonical_sha256
from .persistent_geometry import (
    FaceSignature,
    PersistentFaceSelection,
    capture_face_selection,
    list_face_signatures,
    resolve_face_selection,
)
from .tet10 import TET10_GAUSS_POINTS, tet10_B_matrix


class ModelPreparationEvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class MeshPreparationGate:
    schema: str
    tet10_count: int
    integration_point_count: int
    minimum_det_jacobian_mm3: float
    maximum_det_jacobian_mm3: float
    positive_jacobian_fraction: float
    maximum_midside_deviation_mm: float
    maximum_relative_midside_deviation: float
    straight_sided_verified: bool
    positive_jacobian_verified: bool
    gate_sha256: str


@dataclass(frozen=True)
class ModelPreparationEvidenceSnapshot:
    schema: str
    step_sha256: str
    constraint_scope_name: str
    constraint_selection_sha256: str
    constraint_signature_sha256: str
    constraint_area_mm2: float
    constraint_center_mm: tuple[float, float, float]
    load_scope_name: str
    load_selection_sha256: str
    load_signature_sha256: str
    load_area_mm2: float
    load_center_mm: tuple[float, float, float]
    mesh_gate: dict[str, Any]
    evidence_boundary: str
    snapshot_sha256: str


def _axis_face_tag(
    step_path: str | Path,
    *,
    axis: int,
    side: str,
    expected_coordinate_mm: float,
    tolerance_mm: float,
) -> tuple[int, FaceSignature]:
    if axis not in (0, 1, 2):
        raise ModelPreparationEvidenceError("axis must be 0, 1 or 2")
    if side not in {"MIN", "MAX"}:
        raise ModelPreparationEvidenceError("side must be MIN or MAX")
    if not np.isfinite(expected_coordinate_mm) or not np.isfinite(tolerance_mm) or tolerance_mm <= 0.0:
        raise ModelPreparationEvidenceError("face coordinate and tolerance must be finite with positive tolerance")
    matches: list[tuple[int, FaceSignature]] = []
    for tag, signature in list_face_signatures(step_path):
        low = signature.bbox_mm[axis]
        high = signature.bbox_mm[axis + 3]
        if abs(low - expected_coordinate_mm) <= tolerance_mm and abs(high - expected_coordinate_mm) <= tolerance_mm:
            matches.append((int(tag), signature))
    if not matches:
        raise ModelPreparationEvidenceError(f"AXIS_FACE_NOT_FOUND:{axis}:{side}")
    if len(matches) != 1:
        raise ModelPreparationEvidenceError(
            f"AXIS_FACE_AMBIGUOUS:{axis}:{side}:" + ",".join(str(tag) for tag, _ in matches)
        )
    return matches[0]


def capture_axis_face_selection(
    step_path: str | Path,
    *,
    axis: int,
    side: str,
    expected_coordinate_mm: float,
    model_diagonal_mm: float,
    selection_id: str,
) -> PersistentFaceSelection:
    if not np.isfinite(model_diagonal_mm) or model_diagonal_mm <= 0.0:
        raise ModelPreparationEvidenceError("model_diagonal_mm must be finite and positive")
    tolerance_mm = max(model_diagonal_mm * 1.0e-8, 1.0e-9)
    tag, _ = _axis_face_tag(
        step_path,
        axis=axis,
        side=side,
        expected_coordinate_mm=expected_coordinate_mm,
        tolerance_mm=tolerance_mm,
    )
    selection = capture_face_selection(step_path, tag, selection_id)
    resolution = resolve_face_selection(step_path, selection)
    if resolution.signature_sha256 != selection.signature.sha256:
        raise ModelPreparationEvidenceError("PERSISTENT_FACE_SIGNATURE_MISMATCH")
    return selection


def evaluate_tet10_mesh_preparation_gate(nodes_mm: np.ndarray, elements: np.ndarray) -> MeshPreparationGate:
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise ModelPreparationEvidenceError("nodes_mm must have finite shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 10 or elems.shape[0] == 0:
        raise ModelPreparationEvidenceError("elements must contain at least one TET10")
    if np.any(elems < 0) or np.any(elems >= nodes.shape[0]):
        raise ModelPreparationEvidenceError("elements contains an out-of-range node index")

    determinants: list[float] = []
    maximum_midside_deviation = 0.0
    maximum_relative_midside_deviation = 0.0
    for conn in elems:
        coords = nodes[conn]
        corners = coords[:4]
        expected = np.asarray(
            [
                0.5 * (corners[0] + corners[1]),
                0.5 * (corners[1] + corners[2]),
                0.5 * (corners[2] + corners[0]),
                0.5 * (corners[0] + corners[3]),
                0.5 * (corners[2] + corners[3]),
                0.5 * (corners[1] + corners[3]),
            ],
            dtype=float,
        )
        deviations = np.linalg.norm(coords[4:] - expected, axis=1)
        element_scale = max(float(np.linalg.norm(corners.max(axis=0) - corners.min(axis=0))), 1.0e-30)
        maximum_midside_deviation = max(maximum_midside_deviation, float(np.max(deviations)))
        maximum_relative_midside_deviation = max(
            maximum_relative_midside_deviation,
            float(np.max(deviations) / element_scale),
        )
        for point in TET10_GAUSS_POINTS:
            _, det_j = tet10_B_matrix(coords, point)
            determinants.append(float(det_j))

    det = np.asarray(determinants, dtype=float)
    if not np.all(np.isfinite(det)):
        raise ModelPreparationEvidenceError("mesh Jacobian evidence contains non-finite values")
    positive_fraction = float(np.mean(det > 0.0))
    straight_verified = bool(maximum_relative_midside_deviation <= 1.0e-10)
    jacobian_verified = bool(positive_fraction == 1.0 and float(np.min(det)) > 0.0)
    payload = {
        "schema": "AsterMaxMeshPreparationGateV1",
        "tet10_count": int(elems.shape[0]),
        "integration_point_count": int(det.size),
        "minimum_det_jacobian_mm3": float(np.min(det)),
        "maximum_det_jacobian_mm3": float(np.max(det)),
        "positive_jacobian_fraction": positive_fraction,
        "maximum_midside_deviation_mm": maximum_midside_deviation,
        "maximum_relative_midside_deviation": maximum_relative_midside_deviation,
        "straight_sided_verified": straight_verified,
        "positive_jacobian_verified": jacobian_verified,
    }
    if not straight_verified:
        raise ModelPreparationEvidenceError("CURVED_TET10_OUTSIDE_VERIFICATION_SCOPE")
    if not jacobian_verified:
        raise ModelPreparationEvidenceError("NONPOSITIVE_TET10_JACOBIAN")
    return MeshPreparationGate(**payload, gate_sha256=canonical_sha256(payload))


def build_model_preparation_evidence(
    step_path: str | Path,
    *,
    step_sha256: str,
    bbox_mm: tuple[float, float, float, float, float, float],
    nodes_mm: np.ndarray,
    elements: np.ndarray,
) -> ModelPreparationEvidenceSnapshot:
    if len(step_sha256) != 64:
        raise ModelPreparationEvidenceError("step_sha256 must be a SHA-256 digest")
    bbox = tuple(float(v) for v in bbox_mm)
    if len(bbox) != 6 or not np.all(np.isfinite(np.asarray(bbox))):
        raise ModelPreparationEvidenceError("bbox_mm must contain six finite values")
    dims = np.asarray((bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2]), dtype=float)
    if np.any(dims <= 0.0):
        raise ModelPreparationEvidenceError("bbox_mm must have positive dimensions")
    diagonal = float(np.linalg.norm(dims))

    constraint = capture_axis_face_selection(
        step_path,
        axis=0,
        side="MIN",
        expected_coordinate_mm=bbox[0],
        model_diagonal_mm=diagonal,
        selection_id="CURRENT_MODEL_X_MIN_CONSTRAINT",
    )
    load = capture_axis_face_selection(
        step_path,
        axis=0,
        side="MAX",
        expected_coordinate_mm=bbox[3],
        model_diagonal_mm=diagonal,
        selection_id="CURRENT_MODEL_X_MAX_LOAD",
    )
    if constraint.source_sha256 != step_sha256 or load.source_sha256 != step_sha256:
        raise ModelPreparationEvidenceError("persistent scope source SHA does not match current STEP")
    if constraint.selection_sha256 == load.selection_sha256:
        raise ModelPreparationEvidenceError("constraint and load scopes must be distinct")

    mesh_gate = evaluate_tet10_mesh_preparation_gate(nodes_mm, elements)
    core = {
        "schema": "AsterMaxModelPreparationEvidenceV1",
        "step_sha256": step_sha256,
        "constraint_scope_name": constraint.selection_id,
        "constraint_selection_sha256": constraint.selection_sha256,
        "constraint_signature_sha256": constraint.signature.sha256,
        "constraint_area_mm2": float(constraint.signature.area_mm2),
        "constraint_center_mm": tuple(float(v) for v in constraint.signature.center_mm),
        "load_scope_name": load.selection_id,
        "load_selection_sha256": load.selection_sha256,
        "load_signature_sha256": load.signature.sha256,
        "load_area_mm2": float(load.signature.area_mm2),
        "load_center_mm": tuple(float(v) for v in load.signature.center_mm),
        "mesh_gate": asdict(mesh_gate),
        "evidence_boundary": "PERSISTENT_X_END_FACE_SCOPES_AND_STRAIGHT_SIDED_TET10_POSITIVE_GAUSS_POINT_JACOBIANS_NOT_GENERAL_CAD_NAMED_SELECTIONS",
    }
    return ModelPreparationEvidenceSnapshot(**core, snapshot_sha256=canonical_sha256(core))
