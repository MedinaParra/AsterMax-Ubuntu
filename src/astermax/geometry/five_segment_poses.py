from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import math
from typing import Iterable

from .seating_kinematics import (
    BoltHoleFit,
    CylindricalPadArc,
    GapBand,
    bolt_relative_offset_limit_mm,
    cylindrical_pad_gap_mm,
)


class FiveSegmentPoseStatus(StrEnum):
    CONTACT_READY_KINEMATICS_VALIDATED = "CONTACT_READY_KINEMATICS_VALIDATED"
    BLOCKED_INVALID_RING_SPACING = "BLOCKED_INVALID_RING_SPACING"
    BLOCKED_FASTENER_CLEARANCE = "BLOCKED_FASTENER_CLEARANCE"
    BLOCKED_PAD_GAP_BAND = "BLOCKED_PAD_GAP_BAND"


@dataclass(frozen=True)
class SegmentSeatingPose:
    segment_id: str
    angular_position_deg: float
    radial_translation_mm: float

    def __post_init__(self) -> None:
        if not self.segment_id:
            raise ValueError("segment_id must be non-empty")
        if not all(
            math.isfinite(v)
            for v in (self.angular_position_deg, self.radial_translation_mm)
        ):
            raise ValueError("segment pose values must be finite")
        if self.radial_translation_mm < 0.0:
            raise ValueError("radial translation must be non-negative")


@dataclass(frozen=True)
class SegmentPoseCheck:
    segment_id: str
    angular_position_deg: float
    radial_translation_mm: float
    translation_vector_cross_section_mm: tuple[float, float]
    pad_gap_min_mm: float
    pad_gap_max_mm: float
    fastener_relative_offset_limit_mm: float
    fastener_margin_mm: float
    gap_band_ok: bool
    fastener_clearance_ok: bool
    contact_seed_points: tuple[dict, ...]


@dataclass(frozen=True)
class FiveSegmentPoseDecision:
    schema_version: str
    result_class: str
    status: FiveSegmentPoseStatus
    ring_pitch_deg: float
    ring_phase_deg: float | None
    segment_checks: tuple[dict, ...]
    worst_gap_min_mm: float | None
    worst_gap_max_mm: float | None
    minimum_fastener_margin_mm: float | None
    contact_fea_executed: bool
    industrial_validation_claimed: bool
    next_gate: str


def _normalize_deg(angle_deg: float) -> float:
    value = float(angle_deg) % 360.0
    return 0.0 if math.isclose(value, 360.0, abs_tol=1.0e-12) else value


def radial_unit_vector(angle_deg: float) -> tuple[float, float]:
    if not math.isfinite(angle_deg):
        raise ValueError("angle must be finite")
    theta = math.radians(angle_deg)
    return (math.cos(theta), math.sin(theta))


def radial_translation_vector_mm(pose: SegmentSeatingPose) -> tuple[float, float]:
    uy, uz = radial_unit_vector(pose.angular_position_deg)
    return (
        pose.radial_translation_mm * uy,
        pose.radial_translation_mm * uz,
    )


def pad_point_cross_section_mm(
    pose: SegmentSeatingPose,
    *,
    pad_radius_mm: float,
    local_pad_angle_deg: float,
) -> tuple[float, float]:
    """Return one translated pad point in a hub-centered cross-section.

    Coordinates are in an arbitrary orthonormal pair transverse to the assembly
    axis. The segment radial centerline is at ``angular_position_deg`` and the
    cylindrical pad point is offset by ``local_pad_angle_deg`` from that line.
    """
    if not all(math.isfinite(v) for v in (pad_radius_mm, local_pad_angle_deg)):
        raise ValueError("pad-point inputs must be finite")
    if pad_radius_mm <= 0.0:
        raise ValueError("pad radius must be positive")
    global_theta = math.radians(pose.angular_position_deg + local_pad_angle_deg)
    dy, dz = radial_translation_vector_mm(pose)
    return (
        pad_radius_mm * math.cos(global_theta) + dy,
        pad_radius_mm * math.sin(global_theta) + dz,
    )


def _pad_seed_angles(arc: CylindricalPadArc) -> tuple[float, ...]:
    midpoint = 0.5 * (arc.angle_min_deg + arc.angle_max_deg)
    values = [arc.angle_min_deg, midpoint, arc.angle_max_deg]
    if arc.angle_min_deg <= 0.0 <= arc.angle_max_deg:
        values.append(0.0)
    return tuple(sorted(set(values)))


def _pad_extreme_angles(arc: CylindricalPadArc) -> tuple[float, ...]:
    values = [arc.angle_min_deg, arc.angle_max_deg]
    if arc.angle_min_deg <= 0.0 <= arc.angle_max_deg:
        values.append(0.0)
    return tuple(values)


def evaluate_segment_pose(
    pose: SegmentSeatingPose,
    *,
    arcs: Iterable[CylindricalPadArc],
    flange_radius_mm: float,
    gap_band: GapBand,
    bolt_fit: BoltHoleFit,
) -> SegmentPoseCheck:
    arc_tuple = tuple(arcs)
    if not arc_tuple:
        raise ValueError("at least one pad arc is required")
    if not math.isfinite(flange_radius_mm) or flange_radius_mm <= 0.0:
        raise ValueError("flange radius must be finite and positive")
    radii = {round(arc.radius_mm, 12) for arc in arc_tuple}
    if len(radii) != 1:
        raise ValueError("five-segment pose gate requires one common pad radius")
    pad_radius = arc_tuple[0].radius_mm

    extreme_gaps = [
        cylindrical_pad_gap_mm(
            pad_radius_mm=pad_radius,
            flange_radius_mm=flange_radius_mm,
            radial_translation_mm=pose.radial_translation_mm,
            pad_angle_deg=angle,
        )
        for arc in arc_tuple
        for angle in _pad_extreme_angles(arc)
    ]
    gap_min = min(extreme_gaps)
    gap_max = max(extreme_gaps)
    tolerance = 1.0e-9
    gap_ok = (
        gap_min >= gap_band.minimum_mm - tolerance
        and gap_max <= gap_band.maximum_mm + tolerance
    )

    offset_limit = bolt_relative_offset_limit_mm(bolt_fit)
    fastener_margin = offset_limit - pose.radial_translation_mm
    fastener_ok = fastener_margin >= -tolerance

    seeds: list[dict] = []
    for arc in arc_tuple:
        for local_angle in _pad_seed_angles(arc):
            y, z = pad_point_cross_section_mm(
                pose,
                pad_radius_mm=pad_radius,
                local_pad_angle_deg=local_angle,
            )
            global_radius = math.hypot(y, z)
            seeds.append(
                {
                    "segment_id": pose.segment_id,
                    "pad_id": arc.pad_id,
                    "local_pad_angle_deg": local_angle,
                    "global_cross_section_mm": [y, z],
                    "global_radius_mm": global_radius,
                    "radial_gap_mm": global_radius - flange_radius_mm,
                }
            )

    return SegmentPoseCheck(
        segment_id=pose.segment_id,
        angular_position_deg=_normalize_deg(pose.angular_position_deg),
        radial_translation_mm=pose.radial_translation_mm,
        translation_vector_cross_section_mm=radial_translation_vector_mm(pose),
        pad_gap_min_mm=gap_min,
        pad_gap_max_mm=gap_max,
        fastener_relative_offset_limit_mm=offset_limit,
        fastener_margin_mm=fastener_margin,
        gap_band_ok=gap_ok,
        fastener_clearance_ok=fastener_ok,
        contact_seed_points=tuple(seeds),
    )


def _regular_ring_phase_deg(
    poses: tuple[SegmentSeatingPose, ...],
    *,
    pitch_deg: float,
    tolerance_deg: float = 1.0e-8,
) -> float | None:
    angles = sorted(_normalize_deg(pose.angular_position_deg) for pose in poses)
    if len(angles) != 5:
        return None
    cyclic_steps = [
        (angles[(i + 1) % 5] - angles[i]) % 360.0 for i in range(5)
    ]
    if not all(abs(step - pitch_deg) <= tolerance_deg for step in cyclic_steps):
        return None
    return angles[0]


def evaluate_five_segment_poses(
    poses: Iterable[SegmentSeatingPose],
    *,
    arcs: Iterable[CylindricalPadArc],
    flange_radius_mm: float,
    gap_band: GapBand,
    bolt_fit: BoltHoleFit,
    ring_pitch_deg: float = 72.0,
) -> FiveSegmentPoseDecision:
    pose_tuple = tuple(poses)
    if len(pose_tuple) != 5:
        raise ValueError("exactly five segment poses are required")
    if len({pose.segment_id for pose in pose_tuple}) != 5:
        raise ValueError("segment ids must be unique")
    if not math.isfinite(ring_pitch_deg) or ring_pitch_deg <= 0.0:
        raise ValueError("ring pitch must be finite and positive")

    phase = _regular_ring_phase_deg(pose_tuple, pitch_deg=ring_pitch_deg)
    if phase is None:
        return FiveSegmentPoseDecision(
            schema_version="AsterMaxFiveSegmentPoseGateV1",
            result_class="CONTACT_PREPROCESSING_KINEMATICS_NOT_FEA",
            status=FiveSegmentPoseStatus.BLOCKED_INVALID_RING_SPACING,
            ring_pitch_deg=ring_pitch_deg,
            ring_phase_deg=None,
            segment_checks=(),
            worst_gap_min_mm=None,
            worst_gap_max_mm=None,
            minimum_fastener_margin_mm=None,
            contact_fea_executed=False,
            industrial_validation_claimed=False,
            next_gate="FIX_RING_POSE_DEFINITION",
        )

    arc_tuple = tuple(arcs)
    checks = tuple(
        evaluate_segment_pose(
            pose,
            arcs=arc_tuple,
            flange_radius_mm=flange_radius_mm,
            gap_band=gap_band,
            bolt_fit=bolt_fit,
        )
        for pose in pose_tuple
    )

    if any(not check.fastener_clearance_ok for check in checks):
        status = FiveSegmentPoseStatus.BLOCKED_FASTENER_CLEARANCE
        next_gate = "REDUCE_SEGMENT_TRANSLATION_OR_REVIEW_FASTENER_GEOMETRY"
    elif any(not check.gap_band_ok for check in checks):
        status = FiveSegmentPoseStatus.BLOCKED_PAD_GAP_BAND
        next_gate = "MOVE_SEGMENT_POSES_INTO_MEASURED_GAP_BAND"
    else:
        status = FiveSegmentPoseStatus.CONTACT_READY_KINEMATICS_VALIDATED
        next_gate = "SYNTHETIC_UNILATERAL_CONTACT_LAW_VERIFICATION"

    return FiveSegmentPoseDecision(
        schema_version="AsterMaxFiveSegmentPoseGateV1",
        result_class="CONTACT_PREPROCESSING_KINEMATICS_NOT_FEA",
        status=status,
        ring_pitch_deg=ring_pitch_deg,
        ring_phase_deg=phase,
        segment_checks=tuple(asdict(check) for check in checks),
        worst_gap_min_mm=min(check.pad_gap_min_mm for check in checks),
        worst_gap_max_mm=max(check.pad_gap_max_mm for check in checks),
        minimum_fastener_margin_mm=min(check.fastener_margin_mm for check in checks),
        contact_fea_executed=False,
        industrial_validation_claimed=False,
        next_gate=next_gate,
    )
