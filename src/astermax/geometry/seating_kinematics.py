from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import math
from typing import Iterable


class SeatingCompatibilityStatus(StrEnum):
    KINEMATICALLY_COMPATIBLE_REQUIRES_CONTACT_FEA = (
        "KINEMATICALLY_COMPATIBLE_REQUIRES_CONTACT_FEA"
    )
    BLOCKED_BY_FASTENER_CLEARANCE = "BLOCKED_BY_FASTENER_CLEARANCE"
    BLOCKED_NO_TRANSLATION_INTERVAL = "BLOCKED_NO_TRANSLATION_INTERVAL"


@dataclass(frozen=True)
class CylindricalPadArc:
    """One concave cylindrical pad arc in a segment-local radial frame.

    ``angle_min_deg`` and ``angle_max_deg`` are angular offsets around the
    assembly axis from the segment radial centerline. They can be negative or
    positive; only the actual arc envelope is used by the compatibility gate.
    """

    pad_id: str
    radius_mm: float
    angle_min_deg: float
    angle_max_deg: float

    def __post_init__(self) -> None:
        if not self.pad_id:
            raise ValueError("pad_id must be non-empty")
        if not math.isfinite(self.radius_mm) or self.radius_mm <= 0.0:
            raise ValueError("pad radius must be finite and positive")
        if not all(math.isfinite(v) for v in (self.angle_min_deg, self.angle_max_deg)):
            raise ValueError("pad angles must be finite")
        if self.angle_max_deg <= self.angle_min_deg:
            raise ValueError("pad angle_max_deg must exceed angle_min_deg")
        if max(abs(self.angle_min_deg), abs(self.angle_max_deg)) >= 90.0:
            raise ValueError("this radial seating gate requires pad arcs within +/-90 degrees")


@dataclass(frozen=True)
class GapBand:
    minimum_mm: float
    maximum_mm: float
    evidence_class: str = "MEASURED_ENDPOINT_RANGE"

    def __post_init__(self) -> None:
        if not all(math.isfinite(v) for v in (self.minimum_mm, self.maximum_mm)):
            raise ValueError("gap band must be finite")
        if self.minimum_mm < 0.0:
            raise ValueError("minimum gap must be non-negative")
        if self.maximum_mm < self.minimum_mm:
            raise ValueError("maximum gap must not be below minimum gap")
        if self.evidence_class != "MEASURED_ENDPOINT_RANGE":
            raise ValueError("GAP-A accepts measured endpoint ranges only")


@dataclass(frozen=True)
class BoltHoleFit:
    segment_hole_diameter_mm: float
    hub_hole_diameter_mm: float
    bolt_nominal_diameter_mm: float

    def __post_init__(self) -> None:
        values = (
            self.segment_hole_diameter_mm,
            self.hub_hole_diameter_mm,
            self.bolt_nominal_diameter_mm,
        )
        if not all(math.isfinite(v) and v > 0.0 for v in values):
            raise ValueError("bolt and hole diameters must be finite and positive")
        if self.bolt_nominal_diameter_mm > min(
            self.segment_hole_diameter_mm,
            self.hub_hole_diameter_mm,
        ):
            raise ValueError("nominal bolt diameter must fit inside both holes")


@dataclass(frozen=True)
class SeatingCompatibilityDecision:
    schema_version: str
    result_class: str
    status: SeatingCompatibilityStatus
    pad_radius_mm: float
    flange_radius_mm: float
    concentric_clearance_mm: float
    measured_gap_band_mm: tuple[float, float]
    required_radial_translation_interval_mm: tuple[float, float] | None
    fastener_relative_offset_limit_mm: float
    fastener_margin_at_required_max_mm: float | None
    pad_arcs: tuple[dict, ...]
    assumptions: tuple[str, ...]
    authentic_fea_result_claimed: bool
    industrial_validation_claimed: bool


def bolt_relative_offset_limit_mm(fit: BoltHoleFit) -> float:
    """Upper-bound relative hole-center offset for a straight circular bolt.

    The bolt can float to opposite sides of the two clearance holes. This is a
    geometric fit bound only; it is not a preload, bearing, washer or service
    criterion. The expression is conservative with respect to using the nominal
    bolt major diameter as the shank envelope.
    """

    segment_radial_clearance = 0.5 * (
        fit.segment_hole_diameter_mm - fit.bolt_nominal_diameter_mm
    )
    hub_radial_clearance = 0.5 * (
        fit.hub_hole_diameter_mm - fit.bolt_nominal_diameter_mm
    )
    return segment_radial_clearance + hub_radial_clearance


def cylindrical_pad_gap_mm(
    *,
    pad_radius_mm: float,
    flange_radius_mm: float,
    radial_translation_mm: float,
    pad_angle_deg: float,
) -> float:
    """Exact radial gap after translating a concave cylindrical pad outward.

    Before translation the pad cylinder is concentric with the flange axis.
    The whole segment is translated along its radial centerline by ``delta``.
    A pad point at angular offset theta then has global radius

        sqrt(Rp^2 + delta^2 + 2*Rp*delta*cos(theta)).

    Gap is that radius minus the centered trial-flange radius. Positive means
    clearance; negative means geometric penetration in this kinematic screen.
    """

    values = (pad_radius_mm, flange_radius_mm, radial_translation_mm, pad_angle_deg)
    if not all(math.isfinite(v) for v in values):
        raise ValueError("seating inputs must be finite")
    if pad_radius_mm <= 0.0 or flange_radius_mm <= 0.0:
        raise ValueError("pad and flange radii must be positive")
    if radial_translation_mm < 0.0:
        raise ValueError("radial translation must be non-negative")
    theta = math.radians(pad_angle_deg)
    global_radius_sq = (
        pad_radius_mm * pad_radius_mm
        + radial_translation_mm * radial_translation_mm
        + 2.0 * pad_radius_mm * radial_translation_mm * math.cos(theta)
    )
    return math.sqrt(max(global_radius_sq, 0.0)) - flange_radius_mm


def translation_for_gap_mm(
    *,
    pad_radius_mm: float,
    flange_radius_mm: float,
    target_gap_mm: float,
    pad_angle_deg: float,
) -> float:
    """Solve the positive outward translation that gives one target radial gap."""

    if not all(
        math.isfinite(v)
        for v in (pad_radius_mm, flange_radius_mm, target_gap_mm, pad_angle_deg)
    ):
        raise ValueError("seating inputs must be finite")
    if pad_radius_mm <= 0.0 or flange_radius_mm <= 0.0:
        raise ValueError("pad and flange radii must be positive")
    if target_gap_mm < 0.0:
        raise ValueError("target gap must be non-negative")
    theta = math.radians(pad_angle_deg)
    target_radius = flange_radius_mm + target_gap_mm
    radicand = target_radius * target_radius - (
        pad_radius_mm * math.sin(theta)
    ) ** 2
    if radicand < -1.0e-12:
        raise ValueError("target gap cannot be reached by outward radial translation")
    delta = -pad_radius_mm * math.cos(theta) + math.sqrt(max(radicand, 0.0))
    if delta < -1.0e-12:
        raise ValueError("target gap requires inward rather than outward translation")
    return max(delta, 0.0)


def _arc_extreme_angles(arcs: Iterable[CylindricalPadArc]) -> tuple[float, ...]:
    points: list[float] = []
    for arc in arcs:
        points.extend((arc.angle_min_deg, arc.angle_max_deg))
        if arc.angle_min_deg <= 0.0 <= arc.angle_max_deg:
            points.append(0.0)
    if not points:
        raise ValueError("at least one pad arc is required")
    return tuple(points)


def translation_interval_for_gap_band(
    *,
    arcs: Iterable[CylindricalPadArc],
    flange_radius_mm: float,
    gap_band: GapBand,
) -> tuple[float, float] | None:
    """Return translations for which every pad point lies inside the gap band.

    For outward translations and pad arcs restricted to +/-90 degrees, gap is
    monotone with ``cos(theta)``. Evaluating arc endpoints plus zero (if an arc
    crosses it) is therefore sufficient to bound the continuous pad surfaces.
    """

    arc_tuple = tuple(arcs)
    if not arc_tuple:
        raise ValueError("at least one pad arc is required")
    radii = {round(arc.radius_mm, 12) for arc in arc_tuple}
    if len(radii) != 1:
        raise ValueError("GAP-A requires one common cylindrical pad radius")
    pad_radius = arc_tuple[0].radius_mm
    if not math.isfinite(flange_radius_mm) or flange_radius_mm <= 0.0:
        raise ValueError("flange radius must be finite and positive")

    angles = _arc_extreme_angles(arc_tuple)
    lower = max(
        translation_for_gap_mm(
            pad_radius_mm=pad_radius,
            flange_radius_mm=flange_radius_mm,
            target_gap_mm=gap_band.minimum_mm,
            pad_angle_deg=angle,
        )
        for angle in angles
    )
    upper = min(
        translation_for_gap_mm(
            pad_radius_mm=pad_radius,
            flange_radius_mm=flange_radius_mm,
            target_gap_mm=gap_band.maximum_mm,
            pad_angle_deg=angle,
        )
        for angle in angles
    )
    if upper + 1.0e-12 < lower:
        return None
    return (lower, upper)


def evaluate_seating_compatibility(
    *,
    arcs: Iterable[CylindricalPadArc],
    flange_diameter_mm: float,
    gap_band: GapBand,
    bolt_fit: BoltHoleFit,
) -> SeatingCompatibilityDecision:
    arc_tuple = tuple(arcs)
    if not arc_tuple:
        raise ValueError("at least one pad arc is required")
    if not math.isfinite(flange_diameter_mm) or flange_diameter_mm <= 0.0:
        raise ValueError("flange diameter must be finite and positive")
    pad_radii = {round(arc.radius_mm, 12) for arc in arc_tuple}
    if len(pad_radii) != 1:
        raise ValueError("GAP-A requires one common cylindrical pad radius")
    pad_radius = arc_tuple[0].radius_mm
    flange_radius = 0.5 * flange_diameter_mm
    interval = translation_interval_for_gap_band(
        arcs=arc_tuple,
        flange_radius_mm=flange_radius,
        gap_band=gap_band,
    )
    offset_limit = bolt_relative_offset_limit_mm(bolt_fit)

    if interval is None:
        status = SeatingCompatibilityStatus.BLOCKED_NO_TRANSLATION_INTERVAL
        margin = None
    else:
        required_max = interval[1]
        margin = offset_limit - required_max
        status = (
            SeatingCompatibilityStatus.KINEMATICALLY_COMPATIBLE_REQUIRES_CONTACT_FEA
            if margin >= -1.0e-12
            else SeatingCompatibilityStatus.BLOCKED_BY_FASTENER_CLEARANCE
        )

    return SeatingCompatibilityDecision(
        schema_version="AsterMaxGapSeatingKinematicsV1",
        result_class="GEOMETRIC_KINEMATIC_SCREENING_NOT_CONTACT_FEA",
        status=status,
        pad_radius_mm=pad_radius,
        flange_radius_mm=flange_radius,
        concentric_clearance_mm=pad_radius - flange_radius,
        measured_gap_band_mm=(gap_band.minimum_mm, gap_band.maximum_mm),
        required_radial_translation_interval_mm=interval,
        fastener_relative_offset_limit_mm=offset_limit,
        fastener_margin_at_required_max_mm=margin,
        pad_arcs=tuple(asdict(arc) for arc in arc_tuple),
        assumptions=(
            "trial flange is centered on the hub axis",
            "segment translates radially as a rigid body during this kinematic screen",
            "pad arcs retain the CAD cylindrical radius and angular extent",
            "bolt fit is a geometric upper bound; preload, washers, bearing and friction are not solved",
            "positive measured GAP is interpreted along the local radial direction",
            "compatibility does not confirm the OEM pad profile or authorize an industrial solve",
        ),
        authentic_fea_result_claimed=False,
        industrial_validation_claimed=False,
    )
