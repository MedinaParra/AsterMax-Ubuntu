from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

from .results_quadratic_section import ProductionQuadraticSectionViewV1
from .section_displacement_field import SectionDisplacementFieldV1


@dataclass(frozen=True)
class SectionDisplacementContourSampleV1:
    polyline_index: int
    point_index: int
    canvas_xy: tuple[float, float]
    point_mm: tuple[float, float, float]
    displacement_mm: tuple[float, float, float]
    displacement_magnitude_mm: float
    normalized_scalar: float
    element_id: int


@dataclass(frozen=True)
class ProductionSectionDisplacementContourV1:
    schema: str
    semantics: str
    length_unit: str
    workspace_sha256: str
    solve_evidence_sha256: str
    section_view_sha256: str
    assembly_sha256: str
    field_sha256: str
    contour_sha256: str
    status: str
    blockers: tuple[str, ...]
    scalar_name: str
    scalar_unit: str
    min_value_mm: float
    max_value_mm: float
    sample_count: int
    samples: tuple[SectionDisplacementContourSampleV1, ...]


@dataclass(frozen=True)
class SectionDisplacementProbeV1:
    schema: str
    contour_sha256: str
    sample_index: int
    polyline_index: int
    point_index: int
    canvas_xy: tuple[float, float]
    canvas_distance_px: float
    point_mm: tuple[float, float, float]
    displacement_mm: tuple[float, float, float]
    displacement_magnitude_mm: float
    element_id: int
    probe_sha256: str


def _sha256_json(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_production_section_displacement_contour(
    section_view: ProductionQuadraticSectionViewV1,
    displacement_field: SectionDisplacementFieldV1,
) -> ProductionSectionDisplacementContourV1:
    """Bind verified section displacement samples to the production Results canvas.

    The scalar is U_MAG in mm evaluated by C5.4s. This function performs no stress
    recovery, nodal smoothing, extrapolation, or section-resultant integration.
    It fails closed when section/field provenance or sample topology disagree.
    """
    blockers: list[str] = []
    if section_view.status != "READY" or not section_view.ready_for_results:
        blockers.append("SECTION_VIEW_NOT_READY")
    if displacement_field.status != "READY":
        blockers.append("SECTION_DISPLACEMENT_NOT_READY")
    if section_view.workspace_sha256 != displacement_field.workspace_sha256:
        blockers.append("WORKSPACE_PROVENANCE_MISMATCH")
    if section_view.solve_evidence_sha256 != displacement_field.solve_evidence_sha256:
        blockers.append("SOLVE_PROVENANCE_MISMATCH")
    if section_view.geometry_sha256 != displacement_field.geometry_sha256:
        blockers.append("GEOMETRY_PROVENANCE_MISMATCH")
    if section_view.assembly_sha256 != displacement_field.assembly_sha256:
        blockers.append("ASSEMBLY_PROVENANCE_MISMATCH")

    by_key = {
        (sample.polyline_index, sample.point_index): sample
        for sample in displacement_field.samples
    }
    samples: list[SectionDisplacementContourSampleV1] = []
    expected = 0
    if not blockers:
        low = float(displacement_field.min_displacement_magnitude_mm)
        high = float(displacement_field.max_displacement_magnitude_mm)
        span = high - low
        for polyline_index, polyline in enumerate(section_view.polylines):
            for point_index, canvas_xy in enumerate(polyline.canvas_xy):
                expected += 1
                field_sample = by_key.get((polyline_index, point_index))
                if field_sample is None:
                    blockers.append(f"MISSING_FIELD_SAMPLE:{polyline_index}:{point_index}")
                    continue
                magnitude = float(field_sample.displacement_magnitude_mm)
                normalized = 0.5 if abs(span) <= 1.0e-15 else (magnitude - low) / span
                normalized = min(1.0, max(0.0, float(normalized)))
                samples.append(
                    SectionDisplacementContourSampleV1(
                        polyline_index=int(polyline_index),
                        point_index=int(point_index),
                        canvas_xy=(float(canvas_xy[0]), float(canvas_xy[1])),
                        point_mm=field_sample.point_mm,
                        displacement_mm=field_sample.displacement_mm,
                        displacement_magnitude_mm=magnitude,
                        normalized_scalar=normalized,
                        element_id=int(field_sample.element_id),
                    )
                )
    if not blockers and len(samples) != expected:
        blockers.append("SECTION_CONTOUR_SAMPLE_COUNT")
    if blockers:
        samples = []

    status = "READY" if not blockers else "BLOCKED"
    identity = {
        "schema": "AsterMaxProductionSectionDisplacementContourV1",
        "semantics": "verified_tet10_section_u_mag_results_contour_no_smoothing",
        "workspace_sha256": section_view.workspace_sha256,
        "solve_evidence_sha256": section_view.solve_evidence_sha256,
        "section_view_sha256": section_view.view_sha256,
        "assembly_sha256": section_view.assembly_sha256,
        "field_sha256": displacement_field.field_sha256,
        "status": status,
        "blockers": blockers,
        "scalar_name": "U_MAG",
        "scalar_unit": "mm",
        "samples": [sample.__dict__ for sample in samples],
    }
    return ProductionSectionDisplacementContourV1(
        schema="AsterMaxProductionSectionDisplacementContourV1",
        semantics="verified_tet10_section_u_mag_results_contour_no_smoothing",
        length_unit="mm",
        workspace_sha256=section_view.workspace_sha256,
        solve_evidence_sha256=section_view.solve_evidence_sha256,
        section_view_sha256=section_view.view_sha256,
        assembly_sha256=section_view.assembly_sha256,
        field_sha256=displacement_field.field_sha256,
        contour_sha256=_sha256_json(identity),
        status=status,
        blockers=tuple(blockers),
        scalar_name="U_MAG",
        scalar_unit="mm",
        min_value_mm=(displacement_field.min_displacement_magnitude_mm if not blockers else 0.0),
        max_value_mm=(displacement_field.max_displacement_magnitude_mm if not blockers else 0.0),
        sample_count=len(samples),
        samples=tuple(samples),
    )


def probe_section_displacement_contour(
    contour: ProductionSectionDisplacementContourV1,
    canvas_x: float,
    canvas_y: float,
    *,
    max_distance_px: float | None = None,
) -> SectionDisplacementProbeV1:
    """Return the nearest verified section sample in canvas space.

    This is a deterministic display probe over already verified samples; it does not
    interpolate between samples and therefore cannot fabricate intermediate values.
    """
    if contour.status != "READY" or not contour.samples:
        raise ValueError("SECTION_PROBE_CONTOUR_NOT_READY")
    x = float(canvas_x)
    y = float(canvas_y)
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("SECTION_PROBE_COORDINATES")
    if max_distance_px is not None:
        limit = float(max_distance_px)
        if not math.isfinite(limit) or limit < 0.0:
            raise ValueError("SECTION_PROBE_DISTANCE_LIMIT")
    else:
        limit = None

    best_index = -1
    best_distance = math.inf
    for index, sample in enumerate(contour.samples):
        dx = sample.canvas_xy[0] - x
        dy = sample.canvas_xy[1] - y
        distance = math.hypot(dx, dy)
        if distance < best_distance - 1.0e-12 or (
            abs(distance - best_distance) <= 1.0e-12 and index < best_index
        ):
            best_index = index
            best_distance = distance
    if best_index < 0 or (limit is not None and best_distance > limit):
        raise ValueError("SECTION_PROBE_NO_SAMPLE_WITHIN_LIMIT")

    sample = contour.samples[best_index]
    identity = {
        "schema": "AsterMaxSectionDisplacementProbeV1",
        "contour_sha256": contour.contour_sha256,
        "sample_index": best_index,
        "canvas_query": [x, y],
        "canvas_distance_px": best_distance,
        "polyline_index": sample.polyline_index,
        "point_index": sample.point_index,
        "point_mm": list(sample.point_mm),
        "displacement_mm": list(sample.displacement_mm),
        "displacement_magnitude_mm": sample.displacement_magnitude_mm,
        "element_id": sample.element_id,
    }
    return SectionDisplacementProbeV1(
        schema="AsterMaxSectionDisplacementProbeV1",
        contour_sha256=contour.contour_sha256,
        sample_index=best_index,
        polyline_index=sample.polyline_index,
        point_index=sample.point_index,
        canvas_xy=sample.canvas_xy,
        canvas_distance_px=float(best_distance),
        point_mm=sample.point_mm,
        displacement_mm=sample.displacement_mm,
        displacement_magnitude_mm=sample.displacement_magnitude_mm,
        element_id=sample.element_id,
        probe_sha256=_sha256_json(identity),
    )
