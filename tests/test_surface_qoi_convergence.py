import pytest

from astermax.fea.surface_qoi_convergence import (
    SurfaceAxialQOIConvergenceError,
    SurfaceAxialQOIConvergencePolicy,
    SurfaceAxialQOIRefinementSample,
    evaluate_surface_axial_qoi_convergence,
)


DIGEST = "a" * 64


def _sample(size, metric, qoi, point, disp=0.1, force=1e-10, moment=1e-8, faces=100):
    return SurfaceAxialQOIRefinementSample(
        local_target_size_mm=size,
        local_mean_max_corner_edge_mm=metric,
        node_count=int(1000 / size),
        tet10_count=int(700 / size),
        transition_tri6_count=faces,
        surface_sample_count=4 * faces,
        sampled_max_axial_normal_stress_mpa=qoi,
        maximum_point_mm=point,
        max_displacement_mm=disp,
        force_residual_n=force,
        moment_residual_nmm=moment,
        mesh_sha256=DIGEST,
        measurement_sha256=DIGEST,
        equilibrium_sha256=DIGEST,
    )


def _passing_samples():
    # Final two maxima rotate in azimuth but occupy almost the same meridional
    # (x,rho) location. C20 must not reject an axisymmetric solution because an
    # unstructured mesh selected another circumferential point on the same ring.
    return (
        _sample(2.0, 2.2, 6.00, (38.00, 0.0, 10.00), disp=0.1000, faces=90),
        _sample(1.8, 2.0, 6.20, (38.10, 7.0, 7.1414284285), disp=0.1005, faces=110),
        _sample(1.6, 1.8, 6.32, (38.20, 0.0, 10.10), disp=0.1008, faces=130),
        _sample(1.4, 1.6, 6.40, (38.22, 10.09, 0.0), disp=0.1010, faces=150),
    )


def test_surface_sampled_qoi_convergence_passes_frozen_contract():
    decision = evaluate_surface_axial_qoi_convergence(_passing_samples())
    assert decision.passed
    assert decision.classification == "SURFACE_SAMPLED_AXIAL_QOI_CONVERGED"
    assert decision.continuous_surface_peak_convergence_claim is False
    assert decision.checks["penultimate_qoi_change"]
    assert decision.checks["last_qoi_change"]
    assert decision.checks["last_maximum_meridional_location_stability"]


def test_axisymmetric_azimuth_rotation_does_not_create_false_location_failure():
    decision = evaluate_surface_axial_qoi_convergence(_passing_samples())
    assert decision.metrics["last_maximum_meridional_shift_mm"] < 0.05
    assert decision.checks["last_maximum_meridional_location_stability"]


def test_large_last_qoi_change_fails_closed():
    samples = list(_passing_samples())
    last = samples[-1]
    samples[-1] = SurfaceAxialQOIRefinementSample(
        **{**last.__dict__, "sampled_max_axial_normal_stress_mpa": 7.2}
    )
    decision = evaluate_surface_axial_qoi_convergence(samples)
    assert not decision.passed
    assert not decision.checks["last_qoi_change"]
    assert decision.classification == "SURFACE_SAMPLED_AXIAL_QOI_NOT_CONVERGED"


def test_large_penultimate_qoi_change_fails_even_if_last_change_is_small():
    samples = list(_passing_samples())
    middle = samples[-2]
    samples[-2] = SurfaceAxialQOIRefinementSample(
        **{**middle.__dict__, "sampled_max_axial_normal_stress_mpa": 7.0}
    )
    last = samples[-1]
    samples[-1] = SurfaceAxialQOIRefinementSample(
        **{**last.__dict__, "sampled_max_axial_normal_stress_mpa": 7.05}
    )
    decision = evaluate_surface_axial_qoi_convergence(samples)
    assert not decision.passed
    assert not decision.checks["penultimate_qoi_change"]
    assert decision.checks["last_qoi_change"]


def test_meridional_location_jump_fails_closed():
    samples = list(_passing_samples())
    last = samples[-1]
    samples[-1] = SurfaceAxialQOIRefinementSample(
        **{**last.__dict__, "maximum_point_mm": (41.0, 14.0, 0.0)}
    )
    decision = evaluate_surface_axial_qoi_convergence(samples)
    assert not decision.passed
    assert not decision.checks["last_maximum_meridional_location_stability"]


def test_equilibrium_failure_blocks_convergence():
    samples = list(_passing_samples())
    bad = samples[1]
    samples[1] = SurfaceAxialQOIRefinementSample(
        **{**bad.__dict__, "force_residual_n": 1.0e-3}
    )
    decision = evaluate_surface_axial_qoi_convergence(samples)
    assert not decision.passed
    assert not decision.checks["global_force_balance"]


def test_surface_rule_must_remain_four_points_per_tri6():
    sample = _passing_samples()[0]
    bad = SurfaceAxialQOIRefinementSample(**{**sample.__dict__, "surface_sample_count": 399})
    with pytest.raises(SurfaceAxialQOIConvergenceError, match="four-point"):
        evaluate_surface_axial_qoi_convergence((bad,) + _passing_samples()[1:])


def test_target_sequence_must_strictly_refine():
    samples = list(_passing_samples())
    bad = samples[2]
    samples[2] = SurfaceAxialQOIRefinementSample(**{**bad.__dict__, "local_target_size_mm": 1.8})
    with pytest.raises(SurfaceAxialQOIConvergenceError, match="strictly decreasing"):
        evaluate_surface_axial_qoi_convergence(samples)


def test_policy_requires_enough_samples_for_claim():
    decision = evaluate_surface_axial_qoi_convergence(
        _passing_samples()[:3],
        policy=SurfaceAxialQOIConvergencePolicy(min_samples=4),
    )
    assert not decision.passed
    assert not decision.checks["minimum_sample_count"]
