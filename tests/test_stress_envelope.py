import math

import pytest

from astermax.fea.analytical_witness import LinearNormalStressWitness
from astermax.fea.circular_torsion import CircularTorsionWitness
from astermax.fea.combined_stress import evaluate_combined_stress
from astermax.fea.stress_envelope import circular_combined_stress_envelope


def _normal(sigma0=10.0, a=1.2, b=-0.7):
    return LinearNormalStressWitness(
        schema="AsterMaxLinearNormalStressWitnessV1",
        selection_id="S",
        section_sha256="1" * 64,
        axial_force_n=0.0,
        moment_u_nmm=0.0,
        moment_v_nmm=0.0,
        sigma0_mpa=sigma0,
        gradient_u_mpa_per_mm=a,
        gradient_v_mpa_per_mm=b,
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


def test_exact_envelope_bounds_dense_boundary_sweep():
    normal = _normal()
    torsion = _torsion()
    envelope = circular_combined_stress_envelope(normal, torsion)

    sampled = []
    for i in range(7200):
        angle = 2.0 * math.pi * i / 7200.0
        point = evaluate_combined_stress(
            normal,
            torsion,
            u_mm=torsion.radius_mm * math.cos(angle),
            v_mm=torsion.radius_mm * math.sin(angle),
        )
        sampled.append(point.von_mises_mpa)

    assert max(sampled) <= envelope.max_von_mises_mpa + 1e-10
    assert envelope.max_von_mises_mpa - max(sampled) < 1e-5


def test_zero_bending_gradient_still_places_critical_point_on_boundary():
    envelope = circular_combined_stress_envelope(_normal(a=0.0, b=0.0), _torsion())
    assert envelope.critical_u_mm == pytest.approx(10.0)
    assert envelope.critical_v_mm == pytest.approx(0.0)
    assert envelope.max_abs_normal_stress_mpa == pytest.approx(10.0)
