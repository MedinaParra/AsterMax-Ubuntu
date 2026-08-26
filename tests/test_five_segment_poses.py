from __future__ import annotations

import math

import pytest

from astermax.geometry.five_segment_poses import (
    FiveSegmentPoseStatus,
    SegmentSeatingPose,
    evaluate_five_segment_poses,
    pad_point_cross_section_mm,
    radial_translation_vector_mm,
)
from astermax.geometry.seating_kinematics import BoltHoleFit, CylindricalPadArc, GapBand


PADS = (
    CylindricalPadArc("PAD_A", 398.05, 26.898317, 33.710104),
    CylindricalPadArc("PAD_B", 398.05, -33.739793, -26.928006),
)
GAP = GapBand(0.10, 0.40)
BOLT_FIT = BoltHoleFit(24.5, 25.0, 22.225)
FLANGE_RADIUS = 796.87 / 2.0
LOWER = 0.5830768898949259
UPPER = 0.8800087156050722
MID = 0.5 * (LOWER + UPPER)


def _five_poses(phase_deg: float = 0.0):
    deltas = [LOWER, 0.65, MID, 0.80, UPPER]
    return tuple(
        SegmentSeatingPose(f"S{i + 1}", phase_deg + 72.0 * i, delta)
        for i, delta in enumerate(deltas)
    )


def test_radial_translation_vector_rotates_with_segment_position():
    pose = SegmentSeatingPose("S2", 90.0, 0.75)
    vector = radial_translation_vector_mm(pose)
    assert vector[0] == pytest.approx(0.0, abs=1.0e-14)
    assert vector[1] == pytest.approx(0.75, abs=1.0e-14)
    assert math.hypot(*vector) == pytest.approx(0.75, abs=1.0e-14)


def test_contact_seed_radius_matches_translated_pad_geometry():
    pose = SegmentSeatingPose("S3", 144.0, MID)
    y, z = pad_point_cross_section_mm(
        pose,
        pad_radius_mm=398.05,
        local_pad_angle_deg=30.0,
    )
    radius = math.hypot(y, z)
    expected = math.sqrt(
        398.05**2
        + MID**2
        + 2.0 * 398.05 * MID * math.cos(math.radians(30.0))
    )
    assert radius == pytest.approx(expected, abs=1.0e-12)


def test_five_segment_pose_ensemble_is_contact_ready_kinematically():
    decision = evaluate_five_segment_poses(
        _five_poses(),
        arcs=PADS,
        flange_radius_mm=FLANGE_RADIUS,
        gap_band=GAP,
        bolt_fit=BOLT_FIT,
    )
    assert decision.status == FiveSegmentPoseStatus.CONTACT_READY_KINEMATICS_VALIDATED
    assert decision.ring_pitch_deg == 72.0
    assert decision.ring_phase_deg == pytest.approx(0.0, abs=1.0e-12)
    assert len(decision.segment_checks) == 5
    assert decision.worst_gap_min_mm == pytest.approx(0.10, abs=1.0e-9)
    assert decision.worst_gap_max_mm == pytest.approx(0.40, abs=1.0e-9)
    assert decision.minimum_fastener_margin_mm == pytest.approx(
        2.525 - UPPER,
        abs=2.0e-9,
    )
    assert decision.contact_fea_executed is False
    assert decision.industrial_validation_claimed is False
    assert decision.next_gate == "SYNTHETIC_UNILATERAL_CONTACT_LAW_VERIFICATION"

    for check in decision.segment_checks:
        assert check["gap_band_ok"] is True
        assert check["fastener_clearance_ok"] is True
        assert len(check["contact_seed_points"]) == 6
        assert math.hypot(*check["translation_vector_cross_section_mm"]) == pytest.approx(
            check["radial_translation_mm"], abs=1.0e-12
        )
        for seed in check["contact_seed_points"]:
            assert 0.10 - 1.0e-9 <= seed["radial_gap_mm"] <= 0.40 + 1.0e-9


def test_regular_ring_can_have_arbitrary_global_phase():
    decision = evaluate_five_segment_poses(
        _five_poses(phase_deg=18.0),
        arcs=PADS,
        flange_radius_mm=FLANGE_RADIUS,
        gap_band=GAP,
        bolt_fit=BOLT_FIT,
    )
    assert decision.status == FiveSegmentPoseStatus.CONTACT_READY_KINEMATICS_VALIDATED
    assert decision.ring_phase_deg == pytest.approx(18.0, abs=1.0e-12)


def test_invalid_angular_spacing_fails_closed_before_contact_seed_is_authorized():
    poses = list(_five_poses())
    poses[3] = SegmentSeatingPose("S4", 220.0, poses[3].radial_translation_mm)
    decision = evaluate_five_segment_poses(
        poses,
        arcs=PADS,
        flange_radius_mm=FLANGE_RADIUS,
        gap_band=GAP,
        bolt_fit=BOLT_FIT,
    )
    assert decision.status == FiveSegmentPoseStatus.BLOCKED_INVALID_RING_SPACING
    assert decision.segment_checks == ()
    assert decision.next_gate == "FIX_RING_POSE_DEFINITION"


def test_pose_outside_measured_gap_band_blocks_contact_seed():
    poses = list(_five_poses())
    poses[0] = SegmentSeatingPose("S1", 0.0, 0.40)
    decision = evaluate_five_segment_poses(
        poses,
        arcs=PADS,
        flange_radius_mm=FLANGE_RADIUS,
        gap_band=GAP,
        bolt_fit=BOLT_FIT,
    )
    assert decision.status == FiveSegmentPoseStatus.BLOCKED_PAD_GAP_BAND
    assert decision.next_gate == "MOVE_SEGMENT_POSES_INTO_MEASURED_GAP_BAND"


def test_pose_beyond_geometric_fastener_bound_blocks_first():
    poses = list(_five_poses())
    poses[4] = SegmentSeatingPose("S5", 288.0, 2.60)
    decision = evaluate_five_segment_poses(
        poses,
        arcs=PADS,
        flange_radius_mm=FLANGE_RADIUS,
        gap_band=GAP,
        bolt_fit=BOLT_FIT,
    )
    assert decision.status == FiveSegmentPoseStatus.BLOCKED_FASTENER_CLEARANCE
    assert decision.minimum_fastener_margin_mm is not None
    assert decision.minimum_fastener_margin_mm < 0.0
    assert decision.next_gate == "REDUCE_SEGMENT_TRANSLATION_OR_REVIEW_FASTENER_GEOMETRY"
