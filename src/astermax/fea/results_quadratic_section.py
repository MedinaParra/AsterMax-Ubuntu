from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np

from .adaptive_tet10_section import build_adaptive_tet10_section
from .section_polyline_assembly import assemble_section_polylines


@dataclass(frozen=True)
class ProductionSectionPolylineV1:
    closed: bool
    canvas_xy: tuple[tuple[float, float], ...]
    contributing_element_ids: tuple[int, ...]
    polyline_sha256: str


@dataclass(frozen=True)
class ProductionQuadraticSectionViewV1:
    schema: str
    semantics: str
    length_unit: str
    workspace_sha256: str
    solve_evidence_sha256: str
    geometry_sha256: str
    plane_sha256: str
    adaptive_section_sha256: str
    assembly_sha256: str
    view_sha256: str
    axis: str
    offset_mm: float
    status: str
    ready_for_results: bool
    blockers: tuple[str, ...]
    target_error_mm: float
    selected_sampling_divisions: int
    max_plane_residual_mm: float
    max_chord_error_mm: float
    topology_valid: bool
    closed_polyline_count: int
    open_polyline_count: int
    polyline_count: int
    polylines: tuple[ProductionSectionPolylineV1, ...]


def _sha256_json(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _axis_plane(axis: str, offset_mm: float) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    name = str(axis).upper()
    offset = float(offset_mm)
    if not math.isfinite(offset):
        raise ValueError("PRODUCTION_SECTION_OFFSET")
    if name == "X":
        return (offset, 0.0, 0.0), (1.0, 0.0, 0.0)
    if name == "Y":
        return (0.0, offset, 0.0), (0.0, 1.0, 0.0)
    if name == "Z":
        return (0.0, 0.0, offset), (0.0, 0.0, 1.0)
    raise ValueError("PRODUCTION_SECTION_AXIS")


def _project_oblique(points_mm: np.ndarray) -> np.ndarray:
    points = np.asarray(points_mm, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not np.all(np.isfinite(points)):
        raise ValueError("PRODUCTION_SECTION_POINTS")
    return np.column_stack((points[:, 0] + 0.36 * points[:, 2], -points[:, 1] + 0.22 * points[:, 2]))


def _canvas_map(points_xy: np.ndarray, reference_xy: np.ndarray, width: float, height: float, margin: float) -> np.ndarray:
    values = (float(width), float(height), float(margin))
    if not all(math.isfinite(value) for value in values) or width <= 0.0 or height <= 0.0 or margin < 0.0:
        raise ValueError("PRODUCTION_SECTION_CANVAS")
    reference = np.asarray(reference_xy, dtype=float)
    if reference.ndim != 2 or reference.shape[1] != 2 or reference.shape[0] == 0 or not np.all(np.isfinite(reference)):
        raise ValueError("PRODUCTION_SECTION_REFERENCE")
    low = np.min(reference, axis=0)
    high = np.max(reference, axis=0)
    span = np.maximum(high - low, 1.0e-12)
    sx = max(width - 2.0 * margin, 1.0) / span[0]
    sy = max(height - 2.0 * margin, 1.0) / span[1]
    scale = min(sx, sy)
    mapped = (np.asarray(points_xy, dtype=float) - low) * scale
    mapped[:, 0] += margin + 0.5 * max(width - 2.0 * margin - span[0] * scale, 0.0)
    mapped[:, 1] += margin + 0.5 * max(height - 2.0 * margin - span[1] * scale, 0.0)
    return mapped


def build_production_quadratic_section_view(
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
    target_error_mm: float = 1.0e-3,
    topology_tolerance_mm: float = 1.0e-7,
    initial_sampling_divisions: int = 8,
    max_sampling_divisions: int = 128,
) -> ProductionQuadraticSectionViewV1:
    """Build the Results-ready quadratic TET10 section, failing closed on quality/topology.

    This is a geometry-only production cutover. It renders only adaptive TRI6/TET10
    section polylines whose declared geometric error converged and whose assembled
    cross-element topology passed C5.4q. No solver field is interpolated on the cut.
    """
    if not workspace_sha256 or not solve_evidence_sha256:
        raise ValueError("PRODUCTION_SECTION_PROVENANCE")
    origin, normal = _axis_plane(axis, offset_mm)
    section = build_adaptive_tet10_section(
        np.asarray(nodes_mm, dtype=float),
        np.asarray(elements, dtype=np.int64),
        plane_origin_mm=origin,
        plane_normal=normal,
        workspace_sha256=str(workspace_sha256),
        solve_evidence_sha256=str(solve_evidence_sha256),
        target_error_mm=float(target_error_mm),
        topology_tolerance_mm=float(topology_tolerance_mm),
        initial_sampling_divisions=int(initial_sampling_divisions),
        max_sampling_divisions=int(max_sampling_divisions),
    )
    assembly = assemble_section_polylines(section, endpoint_tolerance_mm=topology_tolerance_mm)

    blockers: list[str] = []
    if not section.converged:
        blockers.append("SECTION_GEOMETRY_NOT_CONVERGED")
    if not assembly.topology_valid:
        blockers.append("SECTION_TOPOLOGY_NOT_VERIFIED")
    if not assembly.ready_for_results:
        blockers.append("SECTION_NOT_READY_FOR_RESULTS")

    polylines: list[ProductionSectionPolylineV1] = []
    if not blockers:
        reference = np.asarray(projected_view_xy, dtype=float)
        for polyline in assembly.polylines:
            projected = _project_oblique(np.asarray(polyline.points_mm, dtype=float))
            mapped = _canvas_map(projected, reference, float(canvas_width), float(canvas_height), float(margin))
            polylines.append(
                ProductionSectionPolylineV1(
                    closed=bool(polyline.closed),
                    canvas_xy=tuple((float(x), float(y)) for x, y in mapped),
                    contributing_element_ids=polyline.contributing_element_ids,
                    polyline_sha256=polyline.polyline_sha256,
                )
            )

    status = "READY" if not blockers else "BLOCKED"
    identity = {
        "schema": "AsterMaxProductionQuadraticSectionViewV1",
        "semantics": "adaptive_quadratic_tet10_results_section_geometry_only_fail_closed",
        "workspace_sha256": workspace_sha256,
        "solve_evidence_sha256": solve_evidence_sha256,
        "geometry_sha256": section.geometry_sha256,
        "plane_sha256": section.plane_sha256,
        "adaptive_section_sha256": section.section_sha256,
        "assembly_sha256": assembly.assembly_sha256,
        "axis": str(axis).upper(),
        "offset_mm": float(offset_mm),
        "status": status,
        "blockers": blockers,
        "target_error_mm": section.target_error_mm,
        "selected_sampling_divisions": section.selected_sampling_divisions,
        "max_plane_residual_mm": section.max_plane_residual_mm,
        "max_chord_error_mm": section.max_chord_error_mm,
        "topology_valid": assembly.topology_valid,
        "canvas": [float(canvas_width), float(canvas_height), float(margin)],
        "polylines": [
            {
                "closed": item.closed,
                "canvas_xy": [list(point) for point in item.canvas_xy],
                "contributing_element_ids": list(item.contributing_element_ids),
                "polyline_sha256": item.polyline_sha256,
            }
            for item in polylines
        ],
    }
    return ProductionQuadraticSectionViewV1(
        schema="AsterMaxProductionQuadraticSectionViewV1",
        semantics="adaptive_quadratic_tet10_results_section_geometry_only_fail_closed",
        length_unit="mm",
        workspace_sha256=str(workspace_sha256),
        solve_evidence_sha256=str(solve_evidence_sha256),
        geometry_sha256=section.geometry_sha256,
        plane_sha256=section.plane_sha256,
        adaptive_section_sha256=section.section_sha256,
        assembly_sha256=assembly.assembly_sha256,
        view_sha256=_sha256_json(identity),
        axis=str(axis).upper(),
        offset_mm=float(offset_mm),
        status=status,
        ready_for_results=not blockers,
        blockers=tuple(blockers),
        target_error_mm=section.target_error_mm,
        selected_sampling_divisions=section.selected_sampling_divisions,
        max_plane_residual_mm=section.max_plane_residual_mm,
        max_chord_error_mm=section.max_chord_error_mm,
        topology_valid=assembly.topology_valid,
        closed_polyline_count=assembly.closed_polyline_count,
        open_polyline_count=assembly.open_polyline_count,
        polyline_count=len(polylines),
        polylines=tuple(polylines),
    )
