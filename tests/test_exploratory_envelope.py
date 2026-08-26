import math

import pytest
from pydantic import ValidationError

from astermax.domain.evidence_readiness import EvidenceSourceClass
from astermax.domain.exploratory_envelope import (
    BoundedFloatV1,
    ExploratoryDriveGeometryV1,
    ExploratoryJointV1,
    ExploratoryLoadCaseV1,
    derive_load_case,
    pitch_diameter_m,
    screen_friction_slip_capacity,
)


def test_bounded_value_requires_monotonic_order() -> None:
    with pytest.raises(ValidationError, match="low <= nominal <= high"):
        BoundedFloatV1(low=2.0, nominal=1.0, high=3.0, units="x")


def test_joint_estimates_cannot_claim_authoritative_source() -> None:
    with pytest.raises(ValidationError, match="must remain ASSUMPTION"):
        ExploratoryJointV1(
            bolt_count=30,
            preload_per_bolt_kn=BoundedFloatV1(
                low=200.0, nominal=240.0, high=280.0, units="kN"
            ),
            contact_friction=BoundedFloatV1(
                low=0.10, nominal=0.15, high=0.20, units="dimensionless"
            ),
            effective_friction_radius_m=BoundedFloatV1(
                low=0.366, nominal=0.400, high=0.420, units="m"
            ),
            source_class=EvidenceSourceClass.CURRENT_AUTHORITATIVE,
        )


def test_pitch_diameter_is_deterministic_from_pitch_and_tooth_count() -> None:
    geometry = ExploratoryDriveGeometryV1(
        chain_pitch_mm=240.0,
        sprocket_tooth_count=25,
    )
    expected = 0.240 / math.sin(math.pi / 25.0)
    assert pitch_diameter_m(geometry) == pytest.approx(expected)
    assert pitch_diameter_m(geometry) == pytest.approx(1.9148951413)


def test_load_derivation_preserves_assumption_boundary() -> None:
    geometry = ExploratoryDriveGeometryV1(
        chain_pitch_mm=240.0,
        sprocket_tooth_count=25,
    )
    case = ExploratoryLoadCaseV1(
        case_id="jam_sensitivity",
        shaft_torque_knm=600.0,
        selected_sprocket_load_share_percent=60.0,
        chain_speed_mps=0.15,
        loaded_teeth_count=2,
        wrap_angle_deg=180.0,
        axial_thrust_kn=0.0,
    )
    result = derive_load_case(geometry, case)

    assert result.sprocket_speed_rpm == pytest.approx(1.5)
    assert result.selected_sprocket_torque_knm == pytest.approx(360.0)
    assert result.chain_tangential_force_kn == pytest.approx(375.999, rel=1e-3)
    assert result.force_per_loaded_tooth_kn == pytest.approx(187.999, rel=1e-3)
    assert result.result_class.value == "ASSUMPTION_DERIVATION"
    assert result.authentic_solver_authorized is False
    assert "sensitivity" in result.disclaimer.lower()


def test_load_case_estimate_cannot_be_relabelled_as_authoritative() -> None:
    with pytest.raises(ValidationError, match="must remain ASSUMPTION"):
        ExploratoryLoadCaseV1(
            case_id="invalid",
            shaft_torque_knm=250.0,
            selected_sprocket_load_share_percent=50.0,
            chain_speed_mps=0.15,
            loaded_teeth_count=5,
            wrap_angle_deg=180.0,
            source_class=EvidenceSourceClass.CURRENT_AUTHORITATIVE,
        )


def test_friction_slip_screen_is_bounded_and_non_authoritative() -> None:
    joint = ExploratoryJointV1(
        bolt_count=30,
        preload_per_bolt_kn=BoundedFloatV1(
            low=200.0, nominal=240.0, high=280.0, units="kN"
        ),
        contact_friction=BoundedFloatV1(
            low=0.10, nominal=0.15, high=0.20, units="dimensionless"
        ),
        effective_friction_radius_m=BoundedFloatV1(
            low=0.366, nominal=0.400, high=0.420, units="m"
        ),
    )
    screen = screen_friction_slip_capacity(joint)

    assert screen.total_clamp_force_kn.low == pytest.approx(6000.0)
    assert screen.total_clamp_force_kn.nominal == pytest.approx(7200.0)
    assert screen.total_clamp_force_kn.high == pytest.approx(8400.0)
    assert screen.friction_torque_capacity_knm.low == pytest.approx(219.6)
    assert screen.friction_torque_capacity_knm.nominal == pytest.approx(432.0)
    assert screen.friction_torque_capacity_knm.high == pytest.approx(705.6)
    assert screen.authentic_solver_authorized is False
    assert "screening-only" in screen.disclaimer.lower()
