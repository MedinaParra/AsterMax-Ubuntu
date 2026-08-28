from dataclasses import replace
import math

import pytest

from astermax.fea.analytical_witness import LinearNormalStressWitness
from astermax.fea.circular_torsion import CircularTorsionWitness
from astermax.fea.combined_stress import CombinedStressError, evaluate_combined_stress


def _normal():
    return LinearNormalStressWitness(
        schema="AsterMaxLinearNormalStressWitnessV1",
        selection_id="S",
        section_sha256="1" * 64,
        axial_force_n=0.0,
        moment_u_nmm=0.0,
        moment_v_nmm=0.0,
        sigma0_mpa=10.0,
        gradient_u_mpa_per_mm=1.0,
        gradient_v_mpa_per_mm=-0.5,
        inertia_determinant_mm8=1.0,
        inertia_condition_indicator=1.0,
        reconstructed_axial_force_n=0.0,
        reconstructed_moment_u_nmm=0.0,
        reconstructed_moment_v_nmm=0.0,
        axial_force_relative_residual=0.0,
        moment_u_relative_residual=0.0,
        moment_v_relative_residual=0.0,
        max_relative_resultant_residual=0.0,
        convention="TEST",
        method="TEST",
        witness_sha256="2" * 64,
    )


def _torsion():
    return CircularTorsionWitness(
        schema="AsterMaxCircularTorsionWitnessV1",
        selection_id="S",
        section_sha256="1" * 64,
        applicability_sha256="3" * 64,
        torque_nmm=1000.0,
        radius_mm=10.0,
        polar_j_mm4=5000.0,
        shear_gradient_mpa_per_mm=0.2,
        tau_max_mpa=2.0,
        reconstructed_torque_nmm=1000.0,
        torque_relative_residual=0.0,
        method="TEST",
        witness_sha256="4" * 64,
    )


def test_combined_stress_matches_closed_form_point():
    point = evaluate_combined_stress(_normal(), _torsion(), u_mm=6.0, v_mm=8.0)
    sigma = 10.0 + 6.0 - 4.0
    tau = 2.0
    assert point.sigma_normal_mpa == pytest.approx(sigma)
    assert point.tau_magnitude_mpa == pytest.approx(tau)
    assert point.von_mises_mpa == pytest.approx(math.sqrt(sigma**2 + 3.0 * tau**2))


def test_combined_stress_rejects_cross_section_mix():
    bad = replace(_torsion(), section_sha256="9" * 64)
    with pytest.raises(CombinedStressError, match="SECTION_SHA_MISMATCH"):
        evaluate_combined_stress(_normal(), bad, u_mm=0.0, v_mm=0.0)


def test_combined_stress_rejects_point_outside_circle():
    with pytest.raises(CombinedStressError, match="POINT_OUTSIDE_SECTION"):
        evaluate_combined_stress(_normal(), _torsion(), u_mm=11.0, v_mm=0.0)
