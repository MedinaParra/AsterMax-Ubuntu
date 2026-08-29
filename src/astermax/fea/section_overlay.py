from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

import numpy as np

from .section_intersection import SectionIntersectionContractV1


@dataclass(frozen=True)
class SectionOverlayPolylineV1:
    element_id: int
    projected_xy: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class SectionOverlayPayloadV1:
    schema: str
    semantics: str
    workspace_sha256: str
    solve_evidence_sha256: str
    geometry_sha256: str
    section_sha256: str
    overlay_sha256: str
    polyline_count: int
    polylines: tuple[SectionOverlayPolylineV1, ...]


def _sha256_json(payload) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _project_oblique_point(point_mm: tuple[float, float, float]) -> tuple[float, float]:
    point = np.asarray(point_mm, dtype=float)
    if point.shape != (3,) or not np.all(np.isfinite(point)):
        raise ValueError("SECTION_OVERLAY_POINT")
    return float(point[0] + 0.36 * point[2]), float(-point[1] + 0.22 * point[2])


def build_section_overlay_payload(
    section: SectionIntersectionContractV1,
    *,
    expected_workspace_sha256: str,
    expected_solve_evidence_sha256: str,
) -> SectionOverlayPayloadV1:
    """Project a validated geometric section into the native Results view.

    This payload is visualization-only. It preserves the exact section polygons
    produced by the section-intersection contract and applies the same oblique
    projection used by the native Results workspace. It does not interpolate,
    smooth, extrapolate or integrate any FEA field on the cut.
    """
    if section.schema != "AsterMaxSectionIntersectionContractV1":
        raise ValueError("SECTION_OVERLAY_SCHEMA")
    if section.workspace_sha256 != expected_workspace_sha256:
        raise ValueError("SECTION_OVERLAY_WORKSPACE_STALE")
    if section.solve_evidence_sha256 != expected_solve_evidence_sha256:
        raise ValueError("SECTION_OVERLAY_SOLVE_STALE")
    if not section.geometry_sha256 or not section.section_sha256:
        raise ValueError("SECTION_OVERLAY_PROVENANCE")

    polylines = tuple(
        SectionOverlayPolylineV1(
            element_id=int(polygon.element_id),
            projected_xy=tuple(_project_oblique_point(point) for point in polygon.points_mm),
        )
        for polygon in section.polygons
    )

    identity = {
        "schema": "AsterMaxSectionOverlayPayloadV1",
        "semantics": "linearized_tet10_section_outline_visualization_only",
        "workspace_sha256": section.workspace_sha256,
        "solve_evidence_sha256": section.solve_evidence_sha256,
        "geometry_sha256": section.geometry_sha256,
        "section_sha256": section.section_sha256,
        "polylines": [
            {
                "element_id": polyline.element_id,
                "projected_xy": [list(point) for point in polyline.projected_xy],
            }
            for polyline in polylines
        ],
    }
    overlay_sha = _sha256_json(identity)
    return SectionOverlayPayloadV1(
        schema="AsterMaxSectionOverlayPayloadV1",
        semantics="linearized_tet10_section_outline_visualization_only",
        workspace_sha256=section.workspace_sha256,
        solve_evidence_sha256=section.solve_evidence_sha256,
        geometry_sha256=section.geometry_sha256,
        section_sha256=section.section_sha256,
        overlay_sha256=overlay_sha,
        polyline_count=len(polylines),
        polylines=polylines,
    )
