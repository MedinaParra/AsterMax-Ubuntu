from dataclasses import replace

import pytest

from astermax.fea.circular_torsion import CircularTorsionError, CircularTorsionWitness
from astermax.fea.torsion_field import torsion_shear_point


def _witness():
    return CircularTorsionWitness(
        schema="AsterMaxCircularTorsionWitnessV1",
        selection_id="S",
        section_sha256="1" * 64,
        applicability_sha256="2" * 64,
        torque_nmm=1000.0,
        radius_mm=10.0,
        polar_j_mm4=5000.0,
        shear_gradient_mpa_per_mm=0.2,
        tau_max_mpa=2.0,
        reconstructed_torque_nmm=1000.0,
        torque_relative_residual=0.0,
        method="TEST",
        witness_sha256="3" * 64,
    )


def test_torsion_field_direction_and_magnitude():
    point = torsion_shear_point(_witness(), u_mm=6.0, v_mm=8.0)
    assert point.radius_mm == pytest.approx(10.0)
    assert point.tau_u_mpa == pytest.approx(-1.6)
    assert point.tau_v_mpa == pytest.approx(1.2)
    assert point.tau_magnitude_mpa == pytest.approx(2.0)


def test_torsion_field_center_is_zero():
    point = torsion_shear_point(_witness(), u_mm=0.0, v_mm=0.0)
    assert point.tau_magnitude_mpa == 0.0


def test_torsion_field_rejects_outside_point():
    with pytest.raises(CircularTorsionError, match="POINT_OUTSIDE_SECTION"):
        torsion_shear_point(_witness(), u_mm=10.1, v_mm=0.0)


def test_torsion_field_sign_reverses_with_torque():
    reversed_witness = replace(
        _witness(),
        torque_nmm=-1000.0,
        shear_gradient_mpa_per_mm=-0.2,
        witness_sha256="4" * 64,
    )
    point = torsion_shear_point(reversed_witness, u_mm=6.0, v_mm=8.0)
    assert point.tau_u_mpa == pytest.approx(1.6)
    assert point.tau_v_mpa == pytest.approx(-1.2)
