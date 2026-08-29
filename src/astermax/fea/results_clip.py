from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np

from .results_workspace import AsterMaxProfessionalResultsWorkspaceV1, deformed_coordinates_mm
from .results_workspace_ui import ResultsRenderPayloadV1, ResultsRenderTriangleV1, build_results_render_payload
from .solver import Tet10LinearStaticResult


@dataclass(frozen=True)
class ClipPlaneContractV1:
    schema: str
    origin_mm: tuple[float, float, float]
    normal_unit: tuple[float, float, float]
    keep_side: str
    tolerance_mm: float
    workspace_sha256: str
    solve_evidence_sha256: str
    clip_sha256: str


@dataclass(frozen=True)
class ClippedResultsRenderPayloadV1:
    schema: str
    base_payload: ResultsRenderPayloadV1
    clip_plane: ClipPlaneContractV1
    triangles: tuple[ResultsRenderTriangleV1, ...]
    kept_triangle_count: int
    removed_triangle_count: int


def _normalized_plane(origin_mm, normal, keep_side: str, tolerance_mm: float, workspace):
    origin = np.asarray(origin_mm, dtype=float)
    vector = np.asarray(normal, dtype=float)
    if origin.shape != (3,) or not np.all(np.isfinite(origin)):
        raise ValueError("RESULTS_CLIP_ORIGIN")
    if vector.shape != (3,) or not np.all(np.isfinite(vector)):
        raise ValueError("RESULTS_CLIP_NORMAL")
    norm = float(np.linalg.norm(vector))
    if not math.isfinite(norm) or norm <= 1.0e-15:
        raise ValueError("RESULTS_CLIP_NORMAL_ZERO")
    if keep_side not in {"POSITIVE", "NEGATIVE"}:
        raise ValueError("RESULTS_CLIP_KEEP_SIDE")
    tolerance = float(tolerance_mm)
    if not math.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError("RESULTS_CLIP_TOLERANCE")
    unit = vector / norm
    payload = {
        "schema": "AsterMaxClipPlaneContractV1",
        "origin_mm": [float(v) for v in origin],
        "normal_unit": [float(v) for v in unit],
        "keep_side": keep_side,
        "tolerance_mm": tolerance,
        "workspace_sha256": workspace.workspace_sha256,
        "solve_evidence_sha256": workspace.solve_evidence_sha256,
        "semantics": "boundary_triangle_centroid_visibility_clip",
    }
    clip_sha = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return origin, unit, ClipPlaneContractV1(
        schema="AsterMaxClipPlaneContractV1",
        origin_mm=tuple(float(v) for v in origin),
        normal_unit=tuple(float(v) for v in unit),
        keep_side=keep_side,
        tolerance_mm=tolerance,
        workspace_sha256=workspace.workspace_sha256,
        solve_evidence_sha256=workspace.solve_evidence_sha256,
        clip_sha256=clip_sha,
    )


def build_clipped_results_render_payload(
    workspace: AsterMaxProfessionalResultsWorkspaceV1,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    result: Tet10LinearStaticResult,
    *,
    field: str,
    plane_origin_mm=(0.0, 0.0, 0.0),
    plane_normal=(1.0, 0.0, 0.0),
    keep_side: str = "POSITIVE",
    tolerance_mm: float = 0.0,
    deformation_scale: float | None = None,
) -> ClippedResultsRenderPayloadV1:
    """Build a provenance-bound clipping-plane view of the native Results payload.

    This is a visualization instrument only. The clip decision is performed on
    boundary-triangle centroids in deformed 3-D coordinates. It does not alter
    the mesh, solver fields, stresses, integration points, or validation claims,
    and it is not an exact geometric cut-surface reconstruction.
    """
    base = build_results_render_payload(
        workspace,
        nodes_mm,
        elements,
        result,
        field=field,
        deformation_scale=deformation_scale,
    )
    if base.workspace_sha256 != workspace.workspace_sha256 or base.solve_evidence_sha256 != workspace.solve_evidence_sha256:
        raise ValueError("RESULTS_CLIP_PROVENANCE_MISMATCH")

    origin, normal, plane = _normalized_plane(plane_origin_mm, plane_normal, keep_side, tolerance_mm, workspace)
    nodes = np.asarray(nodes_mm, dtype=float)
    deformed = deformed_coordinates_mm(nodes, result, base.deformation_scale)
    kept: list[ResultsRenderTriangleV1] = []
    for triangle in base.triangles:
        centroid = np.mean(deformed[list(triangle.node_ids)], axis=0)
        signed_distance = float(np.dot(centroid - origin, normal))
        if keep_side == "POSITIVE":
            visible = signed_distance >= -plane.tolerance_mm
        else:
            visible = signed_distance <= plane.tolerance_mm
        if visible:
            kept.append(triangle)

    return ClippedResultsRenderPayloadV1(
        schema="AsterMaxClippedResultsRenderPayloadV1",
        base_payload=base,
        clip_plane=plane,
        triangles=tuple(kept),
        kept_triangle_count=len(kept),
        removed_triangle_count=len(base.triangles) - len(kept),
    )
