from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np

from .section_intersection import build_linearized_tet10_section_intersection
from .section_overlay import build_section_overlay_payload


@dataclass(frozen=True)
class NativeSectionPolylineV1:
    element_id: int
    canvas_xy: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class NativeSectionViewPayloadV1:
    schema: str
    semantics: str
    workspace_sha256: str
    solve_evidence_sha256: str
    geometry_sha256: str
    section_sha256: str
    overlay_sha256: str
    view_sha256: str
    axis: str
    offset_mm: float
    polyline_count: int
    polylines: tuple[NativeSectionPolylineV1, ...]


def _sha256_json(payload) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def section_axis_plane(axis: str, offset_mm: float):
    name = str(axis).upper()
    offset = float(offset_mm)
    if not math.isfinite(offset):
        raise ValueError("SECTION_VIEW_OFFSET")
    if name == "X":
        return (offset, 0.0, 0.0), (1.0, 0.0, 0.0)
    if name == "Y":
        return (0.0, offset, 0.0), (0.0, 1.0, 0.0)
    if name == "Z":
        return (0.0, 0.0, offset), (0.0, 0.0, 1.0)
    raise ValueError("SECTION_VIEW_AXIS")


def _canvas_map(points: np.ndarray, view_points: np.ndarray, width: float, height: float, margin: float):
    if width <= 0.0 or height <= 0.0 or margin < 0.0 or not all(math.isfinite(v) for v in (width, height, margin)):
        raise ValueError("SECTION_VIEW_CANVAS")
    reference = np.asarray(view_points, dtype=float)
    if reference.ndim != 2 or reference.shape[1] != 2 or not np.all(np.isfinite(reference)):
        raise ValueError("SECTION_VIEW_REFERENCE")
    if reference.shape[0] == 0:
        raise ValueError("SECTION_VIEW_REFERENCE_EMPTY")
    low = np.min(reference, axis=0)
    high = np.max(reference, axis=0)
    span = np.maximum(high - low, 1.0e-12)
    sx = max(width - 2.0 * margin, 1.0) / span[0]
    sy = max(height - 2.0 * margin, 1.0) / span[1]
    scale = min(sx, sy)
    mapped = (np.asarray(points, dtype=float) - low) * scale
    mapped[:, 0] += margin + 0.5 * max(width - 2.0 * margin - span[0] * scale, 0.0)
    mapped[:, 1] += margin + 0.5 * max(height - 2.0 * margin - span[1] * scale, 0.0)
    return mapped


def build_native_section_view_payload(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    *,
    workspace_sha256: str,
    solve_evidence_sha256: str,
    axis: str,
    offset_mm: float,
    projected_view_xy: np.ndarray,
    canvas_width: float,
    canvas_height: float,
    margin: float = 38.0,
    tolerance_mm: float = 1.0e-9,
) -> NativeSectionViewPayloadV1:
    """Build a canvas-ready section outline bound to exact solve provenance.

    The section is geometry-only and uses the validated C5.4i linearized TET10
    corner geometry. No cut-surface stress/displacement interpolation, smoothing,
    extrapolation, section force, or ANSYS-equivalence claim is produced.
    """
    origin, normal = section_axis_plane(axis, offset_mm)
    section = build_linearized_tet10_section_intersection(
        nodes_mm,
        elements,
        plane_origin_mm=origin,
        plane_normal=normal,
        tolerance_mm=tolerance_mm,
        workspace_sha256=workspace_sha256,
        solve_evidence_sha256=solve_evidence_sha256,
    )
    overlay = build_section_overlay_payload(
        section,
        expected_workspace_sha256=workspace_sha256,
        expected_solve_evidence_sha256=solve_evidence_sha256,
    )

    reference = np.asarray(projected_view_xy, dtype=float)
    polylines = []
    for polyline in overlay.polylines:
        points = np.asarray(polyline.projected_xy, dtype=float)
        mapped = _canvas_map(points, reference, float(canvas_width), float(canvas_height), float(margin))
        polylines.append(
            NativeSectionPolylineV1(
                element_id=int(polyline.element_id),
                canvas_xy=tuple((float(x), float(y)) for x, y in mapped),
            )
        )

    identity = {
        "schema": "AsterMaxNativeSectionViewPayloadV1",
        "semantics": "native_results_linearized_section_outline_visualization_only",
        "workspace_sha256": workspace_sha256,
        "solve_evidence_sha256": solve_evidence_sha256,
        "geometry_sha256": section.geometry_sha256,
        "section_sha256": section.section_sha256,
        "overlay_sha256": overlay.overlay_sha256,
        "axis": str(axis).upper(),
        "offset_mm": float(offset_mm),
        "canvas": [float(canvas_width), float(canvas_height), float(margin)],
        "polylines": [
            {"element_id": p.element_id, "canvas_xy": [list(q) for q in p.canvas_xy]}
            for p in polylines
        ],
    }
    view_sha = _sha256_json(identity)
    return NativeSectionViewPayloadV1(
        schema="AsterMaxNativeSectionViewPayloadV1",
        semantics="native_results_linearized_section_outline_visualization_only",
        workspace_sha256=workspace_sha256,
        solve_evidence_sha256=solve_evidence_sha256,
        geometry_sha256=section.geometry_sha256,
        section_sha256=section.section_sha256,
        overlay_sha256=overlay.overlay_sha256,
        view_sha256=view_sha,
        axis=str(axis).upper(),
        offset_mm=float(offset_mm),
        polyline_count=len(polylines),
        polylines=tuple(polylines),
    )
