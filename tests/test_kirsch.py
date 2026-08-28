import math
import pytest

from astermax.fea.kirsch import (
    KirschError,
    build_kirsch_hole_witness,
    kirsch_boundary_kt,
    kirsch_polar_stress_mpa,
)


def test_kirsch_boundary_recovers_stress_concentration_factor_three():
    witness = build_kirsch_hole_witness(
        witness_id="HOLE",
        hole_radius_mm=10.0,
        far_field_stress_mpa=100.0,
        boundary_clearance_over_diameter=4.0,
    )
    sigma_rr, sigma_tt, tau_rt = kirsch_polar_stress_mpa(
        witness,
        radius_mm=10.0,
        theta_rad=0.5 * math.pi,
    )
    assert sigma_rr == pytest.approx(0.0, abs=1.0e-12)
    assert tau_rt == pytest.approx(0.0, abs=1.0e-12)
    assert sigma_tt == pytest.approx(300.0)
    assert kirsch_boundary_kt(witness) == pytest.approx(3.0)


def test_kirsch_query_inside_hole_fails_closed():
    witness = build_kirsch_hole_witness(
        witness_id="HOLE",
        hole_radius_mm=10.0,
        far_field_stress_mpa=100.0,
        boundary_clearance_over_diameter=4.0,
    )
    with pytest.raises(KirschError, match="INSIDE_HOLE"):
        kirsch_polar_stress_mpa(witness, radius_mm=9.0, theta_rad=0.0)


def test_kirsch_rejects_boundary_too_close_for_infinite_plate_assumption():
    with pytest.raises(KirschError, match="OUT_OF_DOMAIN"):
        build_kirsch_hole_witness(
            witness_id="HOLE",
            hole_radius_mm=10.0,
            far_field_stress_mpa=100.0,
            boundary_clearance_over_diameter=2.0,
        )
