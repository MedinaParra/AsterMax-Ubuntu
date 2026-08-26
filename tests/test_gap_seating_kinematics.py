from __future__ import annotations

import math

import pytest

from astermax.geometry.seating_kinematics import (
    BoltHoleFit,
    CylindricalPadArc,
    GapBand,
    SeatingCompatibilityStatus,
    bolt_relative_offset_limit_mm,
    cylindrical_pad_gap_mm,
    evaluate_seating_compatibility,
    translation_for_gap_mm,
    translation_interval_for_gap_band,
)


OT1613_PADS = (
    CylindricalPadArc("PAD_A", 398.05, 26.898317, 33.710104),
    CylindricalPadArc("PAD_B", 398.05, -33.739793, -26.928006),
)
OT1613_GAP = GapBand(0.10, 0.40)
OT1613_BOLT_FIT = BoltHoleFit(
    segment_hole_diameter_mm=24.5,
    hub_hole_diameter_mm=25.0,
    bolt_nominal_diameter_mm=22.225,
)


def test_exact_cylindrical_gap_inverse_round_trip():
    delta = translation_for_gap_mm(
        pad_radius_mm=398.05,
        flange_radius_mm=398.435,
        target_gap_mm=0.25,
        pad_angle_deg=30.0,
    )
    recovered = cylindrical_pad_gap_mm(
        pad_radius_mm=398.05,
        flange_radius_mm=398.435,
        radial_translation_mm=delta,
        pad_angle_deg=30.0,
    )
    assert recovered == pytest.approx(0.25, abs=1.0e-12)


def test_ot1613_pad_arc_interval_reconciles_test_flange_with_measured_gap():
    interval = translation_interval_for_gap_band(
        arcs=OT1613_PADS,
        flange_radius_mm=796.87 / 2.0,
        gap_band=OT1613_GAP,
    )
    assert interval is not None
    lower, upper = interval
    assert lower == pytest.approx(0.5830768898949259, abs=2.0e-9)
    assert upper == pytest.approx(0.8800087156050722, abs=2.0e-9)

    # Continuous pad extrema are bounded by the measured endpoint band.
    for delta in interval:
        gaps = [
            cylindrical_pad_gap_mm(
                pad_radius_mm=arc.radius_mm,
                flange_radius_mm=796.87 / 2.0,
                radial_translation_mm=delta,
                pad_angle_deg=angle,
            )
            for arc in OT1613_PADS
            for angle in (arc.angle_min_deg, arc.angle_max_deg)
        ]
        assert min(gaps) >= 0.10 - 1.0e-9 or math.isclose(delta, upper)
        assert max(gaps) <= 0.40 + 1.0e-9 or math.isclose(delta, lower)


def test_reported_fastener_clearance_is_larger_than_required_seating_translation():
    offset_limit = bolt_relative_offset_limit_mm(OT1613_BOLT_FIT)
    assert offset_limit == pytest.approx(2.525, abs=1.0e-12)

    decision = evaluate_seating_compatibility(
        arcs=OT1613_PADS,
        flange_diameter_mm=796.87,
        gap_band=OT1613_GAP,
        bolt_fit=OT1613_BOLT_FIT,
    )
    assert decision.status == SeatingCompatibilityStatus.KINEMATICALLY_COMPATIBLE_REQUIRES_CONTACT_FEA
    assert decision.concentric_clearance_mm == pytest.approx(-0.385, abs=1.0e-12)
    assert decision.required_radial_translation_interval_mm is not None
    assert decision.required_radial_translation_interval_mm[0] == pytest.approx(0.5830768898949259, abs=2.0e-9)
    assert decision.required_radial_translation_interval_mm[1] == pytest.approx(0.8800087156050722, abs=2.0e-9)
    assert decision.fastener_relative_offset_limit_mm == pytest.approx(2.525, abs=1.0e-12)
    assert decision.fastener_margin_at_required_max_mm == pytest.approx(
        2.525 - 0.8800087156050722,
        abs=2.0e-9,
    )
    assert decision.authentic_fea_result_claimed is False
    assert decision.industrial_validation_claimed is False


def test_negative_concentric_clearance_does_not_by_itself_reject_a_translatable_segment():
    decision = evaluate_seating_compatibility(
        arcs=OT1613_PADS,
        flange_diameter_mm=796.87,
        gap_band=OT1613_GAP,
        bolt_fit=OT1613_BOLT_FIT,
    )
    # R398.05 - R398.435 is an interference only in the unshifted concentric pose.
    assert decision.concentric_clearance_mm < 0.0
    assert decision.status == SeatingCompatibilityStatus.KINEMATICALLY_COMPATIBLE_REQUIRES_CONTACT_FEA


def test_gate_blocks_when_fastener_clearance_cannot_accommodate_required_translation():
    tight_fit = BoltHoleFit(
        segment_hole_diameter_mm=24.5,
        hub_hole_diameter_mm=25.0,
        bolt_nominal_diameter_mm=24.4,
    )
    decision = evaluate_seating_compatibility(
        arcs=OT1613_PADS,
        flange_diameter_mm=796.87,
        gap_band=OT1613_GAP,
        bolt_fit=tight_fit,
    )
    assert decision.status == SeatingCompatibilityStatus.BLOCKED_BY_FASTENER_CLEARANCE
    assert decision.fastener_relative_offset_limit_mm == pytest.approx(0.35, abs=1.0e-12)
    assert decision.fastener_margin_at_required_max_mm is not None
    assert decision.fastener_margin_at_required_max_mm < 0.0


def test_gap_band_refuses_derived_midpoint_mislabelling():
    with pytest.raises(ValueError, match="measured endpoint ranges"):
        GapBand(0.25, 0.25, evidence_class="MEASURED_VALUE")
