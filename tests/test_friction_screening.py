import math

import pytest
from pydantic import ValidationError

from astermax.domain.friction_screening import (
    ContactPatchV1,
    FrictionScreenInputV1,
    ScreeningEvidenceClass,
    SlipScreenStatus,
    evaluate_friction_screen,
)


def _input(*, pressure=100.0, mu=0.15, torque=100.0, segments=5):
    return FrictionScreenInputV1(
        evidence_class=ScreeningEvidenceClass.EXPLORATORY,
        patches=[
            ContactPatchV1(pressure_mpa=pressure, area_mm2=1000.0, radius_mm=350.0),
            ContactPatchV1(pressure_mpa=pressure / 2, area_mm2=500.0, radius_mm=400.0),
        ],
        friction_coefficient=mu,
        applied_torque_knm=torque,
        repeated_segments=segments,
    )


def test_capacity_scales_linearly_with_friction_coefficient():
    low = evaluate_friction_screen(_input(mu=0.10, torque=0.0))
    high = evaluate_friction_screen(_input(mu=0.20, torque=0.0))
    assert high.friction_torque_capacity_knm == pytest.approx(
        2.0 * low.friction_torque_capacity_knm
    )


def test_capacity_scales_linearly_with_normal_pressure():
    low = evaluate_friction_screen(_input(pressure=50.0, torque=0.0))
    high = evaluate_friction_screen(_input(pressure=100.0, torque=0.0))
    assert high.friction_torque_capacity_knm == pytest.approx(
        2.0 * low.friction_torque_capacity_knm
    )


def test_likely_gross_slip_when_applied_torque_exceeds_capacity():
    result = evaluate_friction_screen(_input(mu=0.10, torque=10_000.0))
    assert result.status == SlipScreenStatus.LIKELY_GROSS_SLIP
    assert result.utilization > 1.0
    assert result.solver_truth_claim_allowed is False
    assert result.acceptance_claim_allowed is False


def test_no_gross_slip_screen_is_never_acceptance():
    result = evaluate_friction_screen(_input(mu=0.20, torque=1.0))
    assert result.status == SlipScreenStatus.NO_GROSS_SLIP_SCREEN
    assert result.utilization < 1.0
    assert result.solver_truth_claim_allowed is False
    assert result.acceptance_claim_allowed is False
    assert "not a safety" in result.interpretation.lower()


def test_required_mu_is_inverse_of_capacity_per_mu():
    result = evaluate_friction_screen(_input(mu=0.15, torque=123.0))
    capacity_per_mu = result.friction_torque_capacity_knm / 0.15
    assert result.required_friction_coefficient == pytest.approx(123.0 / capacity_per_mu)


def test_pressure_weighted_radius_is_preserved():
    result = evaluate_friction_screen(_input(mu=0.15, torque=0.0, segments=1))
    expected = (
        100.0 * 1000.0 * 350.0 + 50.0 * 500.0 * 400.0
    ) / (100.0 * 1000.0 + 50.0 * 500.0)
    assert result.pressure_weighted_radius_mm == pytest.approx(expected)


def test_zero_pressure_field_fails_closed():
    with pytest.raises(ValidationError):
        FrictionScreenInputV1(
            evidence_class=ScreeningEvidenceClass.EXPLORATORY,
            patches=[ContactPatchV1(pressure_mpa=0.0, area_mm2=10.0, radius_mm=300.0)],
            friction_coefficient=0.15,
            applied_torque_knm=1.0,
            repeated_segments=5,
        )


def test_invalid_patch_geometry_fails_closed():
    with pytest.raises(ValidationError):
        ContactPatchV1(pressure_mpa=-1.0, area_mm2=10.0, radius_mm=300.0)
    with pytest.raises(ValidationError):
        ContactPatchV1(pressure_mpa=1.0, area_mm2=0.0, radius_mm=300.0)
    with pytest.raises(ValidationError):
        ContactPatchV1(pressure_mpa=1.0, area_mm2=10.0, radius_mm=0.0)


def test_non_exploratory_evidence_class_is_rejected():
    with pytest.raises(ValidationError):
        FrictionScreenInputV1(
            evidence_class="SOLVER_RESULT",
            patches=[ContactPatchV1(pressure_mpa=10.0, area_mm2=10.0, radius_mm=300.0)],
            friction_coefficient=0.15,
            applied_torque_knm=1.0,
            repeated_segments=5,
        )
