from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

from .results_section_displacement import (
    ProductionSectionDisplacementContourV1,
    SectionDisplacementProbeV1,
    probe_section_displacement_contour,
)


@dataclass(frozen=True)
class SectionLegendTickV1:
    fraction: float
    value_mm: float
    label: str


@dataclass(frozen=True)
class NativeSectionContourPointV1:
    canvas_xy: tuple[float, float]
    normalized_scalar: float
    displacement_magnitude_mm: float


@dataclass(frozen=True)
class NativeSectionContourPolylineV1:
    polyline_index: int
    points: tuple[NativeSectionContourPointV1, ...]


@dataclass(frozen=True)
class NativeSectionContourUiV1:
    schema: str
    semantics: str
    contour_sha256: str
    ui_sha256: str
    status: str
    blockers: tuple[str, ...]
    scalar_name: str
    scalar_unit: str
    min_value_mm: float
    max_value_mm: float
    legend_ticks: tuple[SectionLegendTickV1, ...]
    polylines: tuple[NativeSectionContourPolylineV1, ...]
    sample_count: int


def _sha256_json(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def build_native_section_contour_ui(
    contour: ProductionSectionDisplacementContourV1,
    *,
    legend_tick_count: int = 5,
) -> NativeSectionContourUiV1:
    """Build a deterministic native-Results presentation payload for verified U_MAG.

    This adapter performs presentation only. It does not interpolate the field,
    recover stress, smooth samples, or alter the verified C5.4t scalar values.
    """
    tick_count = int(legend_tick_count)
    if tick_count < 2 or tick_count > 11:
        raise ValueError("SECTION_CONTOUR_UI_LEGEND_TICKS")
    blockers: list[str] = []
    if contour.status != "READY" or not contour.samples:
        blockers.append("SECTION_CONTOUR_NOT_READY")
    if contour.scalar_name != "U_MAG" or contour.scalar_unit != "mm":
        blockers.append("SECTION_CONTOUR_SCALAR_CONTRACT")

    ticks: list[SectionLegendTickV1] = []
    polylines: list[NativeSectionContourPolylineV1] = []
    if not blockers:
        low = float(contour.min_value_mm)
        high = float(contour.max_value_mm)
        if not math.isfinite(low) or not math.isfinite(high) or high < low:
            blockers.append("SECTION_CONTOUR_RANGE")
        else:
            for index in range(tick_count):
                fraction = index / float(tick_count - 1)
                value = low + fraction * (high - low)
                ticks.append(SectionLegendTickV1(fraction=fraction, value_mm=value, label=f"{value:.6g} mm"))
            groups: dict[int, list[NativeSectionContourPointV1]] = {}
            for sample in contour.samples:
                groups.setdefault(sample.polyline_index, []).append(
                    NativeSectionContourPointV1(
                        canvas_xy=sample.canvas_xy,
                        normalized_scalar=sample.normalized_scalar,
                        displacement_magnitude_mm=sample.displacement_magnitude_mm,
                    )
                )
            for polyline_index in sorted(groups):
                polylines.append(NativeSectionContourPolylineV1(polyline_index=polyline_index, points=tuple(groups[polyline_index])))

    if blockers:
        ticks = []
        polylines = []
    status = "READY" if not blockers else "BLOCKED"
    identity = {
        "schema": "AsterMaxNativeSectionContourUiV1",
        "semantics": "native_results_verified_section_u_mag_presentation_only",
        "contour_sha256": contour.contour_sha256,
        "status": status,
        "blockers": blockers,
        "legend_ticks": [tick.__dict__ for tick in ticks],
        "polylines": [
            {"polyline_index": line.polyline_index, "points": [point.__dict__ for point in line.points]}
            for line in polylines
        ],
    }
    return NativeSectionContourUiV1(
        schema="AsterMaxNativeSectionContourUiV1",
        semantics="native_results_verified_section_u_mag_presentation_only",
        contour_sha256=contour.contour_sha256,
        ui_sha256=_sha256_json(identity),
        status=status,
        blockers=tuple(blockers),
        scalar_name="U_MAG",
        scalar_unit="mm",
        min_value_mm=(contour.min_value_mm if not blockers else 0.0),
        max_value_mm=(contour.max_value_mm if not blockers else 0.0),
        legend_ticks=tuple(ticks),
        polylines=tuple(polylines),
        sample_count=(contour.sample_count if not blockers else 0),
    )


def probe_native_section_contour_ui(
    ui: NativeSectionContourUiV1,
    contour: ProductionSectionDisplacementContourV1,
    canvas_x: float,
    canvas_y: float,
    *,
    max_distance_px: float | None = 12.0,
) -> SectionDisplacementProbeV1:
    """Probe only the exact verified samples represented by the active UI payload."""
    if ui.status != "READY" or ui.contour_sha256 != contour.contour_sha256:
        raise ValueError("SECTION_CONTOUR_UI_STALE")
    return probe_section_displacement_contour(
        contour, canvas_x, canvas_y, max_distance_px=max_distance_px
    )
