from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np

from .adaptive_tet10_section import build_adaptive_tet10_section
from .section_polyline_assembly import assemble_section_polylines
from .section_displacement_field import SectionDisplacementFieldV1, build_section_displacement_field


@dataclass(frozen=True)
class SectionDisplacementContourPolylineV1:
    closed: bool
    canvas_xy: tuple[tuple[float, float], ...]
    displacement_magnitude_mm: tuple[float, ...]
    normalized_scalar: tuple[float, ...]
    contributing_element_ids: tuple[int, ...]


@dataclass(frozen=True)
class SectionDisplacementContourV1:
    schema: str
    semantics: str
    length_unit: str
    workspace_sha256: str
    solve_evidence_sha256: str
    geometry_sha256: str
    assembly_sha256: str
    field_sha256: str
    contour_sha256: str
    status: str
    blockers: tuple[str, ...]
    axis: str
    offset_mm: float
    min_displacement_magnitude_mm: float
    max_displacement_magnitude_mm: float
    max_geometry_residual_mm: float
    max_cross_element_disagreement_mm: float
    polyline_count: int
    polylines: tuple[SectionDisplacementContourPolylineV1, ...]


@dataclass(frozen=True)
class SectionDisplacementProbeV1:
    hit: bool
    polyline_index: int | None
    point_index: int | None
    canvas_xy: tuple[float, float] | None
    point_mm: tuple[float, float, float] | None
    displacement_mm: tuple[float, float, float] | None
    displacement_magnitude_mm: float | None
    distance_px: float | None
    field_sha256: str


def _sha(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _axis_plane(axis: str, offset_mm: float):
    name = str(axis).upper()
    offset = float(offset_mm)
    if not math.isfinite(offset):
        raise ValueError("SECTION_CONTOUR_OFFSET")
    normals = {"X": ((offset, 0.0, 0.0), (1.0, 0.0, 0.0)), "Y": ((0.0, offset, 0.0), (0.0, 1.0, 0.0)), "Z": ((0.0, 0.0, offset), (0.0, 0.0, 1.0))}
    if name not in normals:
        raise ValueError("SECTION_CONTOUR_AXIS")
    return normals[name]


def _project(points: np.ndarray) -> np.ndarray:
    pts = np.asarray(points, dtype=float)
    return np.column_stack((pts[:, 0] + 0.36 * pts[:, 2], -pts[:, 1] + 0.22 * pts[:, 2]))


def _canvas_map(points_xy: np.ndarray, reference_xy: np.ndarray, width: float, height: float, margin: float) -> np.ndarray:
    reference = np.asarray(reference_xy, dtype=float)
    if reference.ndim != 2 or reference.shape[1] != 2 or len(reference) == 0 or not np.all(np.isfinite(reference)):
        raise ValueError("SECTION_CONTOUR_REFERENCE")
    if not all(math.isfinite(v) for v in (width, height, margin)) or width <= 0 or height <= 0 or margin < 0:
        raise ValueError("SECTION_CONTOUR_CANVAS")
    low, high = np.min(reference, axis=0), np.max(reference, axis=0)
    span = np.maximum(high - low, 1.0e-12)
    scale = min(max(width - 2 * margin, 1.0) / span[0], max(height - 2 * margin, 1.0) / span[1])
    mapped = (np.asarray(points_xy, dtype=float) - low) * scale
    mapped[:, 0] += margin + 0.5 * max(width - 2 * margin - span[0] * scale, 0.0)
    mapped[:, 1] += margin + 0.5 * max(height - 2 * margin - span[1] * scale, 0.0)
    return mapped


def build_section_displacement_contour(nodes_mm: np.ndarray, elements: np.ndarray, nodal_displacements_mm: np.ndarray, *, workspace_sha256: str, solve_evidence_sha256: str, axis: str, offset_mm: float, projected_view_xy: np.ndarray, canvas_width: float, canvas_height: float, margin: float = 38.0, target_error_mm: float = 1.0e-3, topology_tolerance_mm: float = 1.0e-7, initial_sampling_divisions: int = 8, max_sampling_divisions: int = 128, geometry_tolerance_mm: float = 1.0e-8, cross_element_tolerance_mm: float = 1.0e-8) -> SectionDisplacementContourV1:
    """Build a Results-ready U_MAG contour on a verified quadratic TET10 section.

    Geometry and displacement must both pass their fail-closed contracts. This function
    does not recover stress, extrapolate integration-point values or compute resultants.
    """
    if not workspace_sha256 or not solve_evidence_sha256:
        raise ValueError("SECTION_CONTOUR_PROVENANCE")
    origin, normal = _axis_plane(axis, offset_mm)
    section = build_adaptive_tet10_section(np.asarray(nodes_mm, float), np.asarray(elements, np.int64), plane_origin_mm=origin, plane_normal=normal, workspace_sha256=str(workspace_sha256), solve_evidence_sha256=str(solve_evidence_sha256), target_error_mm=float(target_error_mm), topology_tolerance_mm=float(topology_tolerance_mm), initial_sampling_divisions=int(initial_sampling_divisions), max_sampling_divisions=int(max_sampling_divisions))
    assembly = assemble_section_polylines(section, endpoint_tolerance_mm=float(topology_tolerance_mm))
    blockers: list[str] = []
    if not section.converged:
        blockers.append("SECTION_GEOMETRY_NOT_CONVERGED")
    if not assembly.ready_for_results:
        blockers.append("SECTION_TOPOLOGY_NOT_READY")
    field = None
    if not blockers:
        field = build_section_displacement_field(np.asarray(nodes_mm, float), np.asarray(elements, np.int64), np.asarray(nodal_displacements_mm, float), assembly, workspace_sha256=str(workspace_sha256), solve_evidence_sha256=str(solve_evidence_sha256), geometry_tolerance_mm=float(geometry_tolerance_mm), cross_element_tolerance_mm=float(cross_element_tolerance_mm))
        if field.status != "READY":
            blockers.extend(field.blockers or ("SECTION_DISPLACEMENT_NOT_READY",))
    polylines: list[SectionDisplacementContourPolylineV1] = []
    if not blockers and field is not None:
        by_key = {(s.polyline_index, s.point_index): s for s in field.samples}
        lo, hi = field.min_displacement_magnitude_mm, field.max_displacement_magnitude_mm
        span = hi - lo
        for pi, poly in enumerate(assembly.polylines):
            pts = np.asarray(poly.points_mm, float)
            mapped = _canvas_map(_project(pts), np.asarray(projected_view_xy, float), float(canvas_width), float(canvas_height), float(margin))
            mags = tuple(float(by_key[(pi, j)].displacement_magnitude_mm) for j in range(len(poly.points_mm)))
            norm = tuple(0.5 if abs(span) <= 1.0e-15 else (v - lo) / span for v in mags)
            polylines.append(SectionDisplacementContourPolylineV1(bool(poly.closed), tuple((float(x), float(y)) for x, y in mapped), mags, tuple(float(v) for v in norm), poly.contributing_element_ids))
    status = "READY" if not blockers else "BLOCKED"
    field_sha = field.field_sha256 if field is not None else ""
    identity = {"schema":"AsterMaxSectionDisplacementContourV1","workspace_sha256":workspace_sha256,"solve_evidence_sha256":solve_evidence_sha256,"geometry_sha256":section.geometry_sha256,"assembly_sha256":assembly.assembly_sha256,"field_sha256":field_sha,"axis":str(axis).upper(),"offset_mm":float(offset_mm),"status":status,"blockers":blockers,"canvas":[float(canvas_width),float(canvas_height),float(margin)],"polylines":[p.__dict__ for p in polylines]}
    return SectionDisplacementContourV1("AsterMaxSectionDisplacementContourV1","verified_tet10_section_u_mag_contour_and_probe","mm",str(workspace_sha256),str(solve_evidence_sha256),section.geometry_sha256,assembly.assembly_sha256,field_sha,_sha(identity),status,tuple(blockers),str(axis).upper(),float(offset_mm),field.min_displacement_magnitude_mm if field and not blockers else 0.0,field.max_displacement_magnitude_mm if field and not blockers else 0.0,field.max_geometry_residual_mm if field else 0.0,field.max_cross_element_disagreement_mm if field else 0.0,len(polylines),tuple(polylines))


def probe_section_displacement(contour: SectionDisplacementContourV1, field: SectionDisplacementFieldV1, *, canvas_x: float, canvas_y: float, max_distance_px: float = 12.0) -> SectionDisplacementProbeV1:
    if contour.status != "READY":
        raise ValueError("SECTION_PROBE_CONTOUR_NOT_READY")
    if field.status != "READY" or field.field_sha256 != contour.field_sha256 or field.workspace_sha256 != contour.workspace_sha256 or field.solve_evidence_sha256 != contour.solve_evidence_sha256:
        raise ValueError("SECTION_PROBE_FIELD_PROVENANCE")
    radius = float(max_distance_px)
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("SECTION_PROBE_RADIUS")
    sample_map = {(int(s.polyline_index), int(s.point_index)): s for s in field.samples}
    best = None
    for pi, poly in enumerate(contour.polylines):
        for ji, (x, y) in enumerate(poly.canvas_xy):
            d = math.hypot(float(x) - float(canvas_x), float(y) - float(canvas_y))
            if best is None or d < best[0]:
                best = (d, pi, ji, x, y)
    if best is None or best[0] > radius:
        return SectionDisplacementProbeV1(False,None,None,None,None,None,None,None,contour.field_sha256)
    d, pi, ji, x, y = best
    sample = sample_map[(pi, ji)]
    return SectionDisplacementProbeV1(True,pi,ji,(float(x),float(y)),sample.point_mm,sample.displacement_mm,float(sample.displacement_magnitude_mm),float(d),contour.field_sha256)
