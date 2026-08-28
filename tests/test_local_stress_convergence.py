from dataclasses import replace

from astermax.fea.local_stress_convergence import (
    LocalStressConvergencePolicy,
    LocalStressRefinementSample,
    evaluate_local_stress_convergence,
)


def _sample(size, edge, peak, probe, disp, distance=1.0):
    return LocalStressRefinementSample(
        local_target_size_mm=size,
        local_mean_max_corner_edge_mm=edge,
        node_count=int(1000 / size),
        tet10_count=int(800 / size),
        local_ip_peak_mpa=peak,
        probe_ring_mean_mpa=probe,
        probe_ring_max_mpa=peak * 0.98,
        probe_ring_max_distance_mm=distance,
        max_displacement_mm=disp,
        force_residual_n=1.0e-9,
        moment_residual_nmm=1.0e-7,
    )


def test_predeclared_gate_passes_only_when_peak_probe_and_displacement_stabilize():
    samples = (
        _sample(6.0, 8.0, 4.0, 3.6, 0.00090, 2.0),
        _sample(5.0, 7.0, 4.3, 3.8, 0.00094, 1.7),
        _sample(4.0, 6.0, 4.5, 3.9, 0.00096, 1.4),
        _sample(3.0, 4.8, 4.60, 3.95, 0.000970, 1.1),
        _sample(2.5, 4.1, 4.65, 3.98, 0.000975, 0.9),
    )
    decision = evaluate_local_stress_convergence(samples)
    assert decision.passed is True
    assert decision.classification == "LOCAL_STRESS_CONVERGED"
    assert all(decision.checks.values())


def test_peak_that_keeps_moving_blocks_convergence_even_with_good_equilibrium():
    samples = (
        _sample(6.0, 8.0, 4.0, 3.6, 0.00090, 2.0),
        _sample(5.0, 7.0, 4.5, 3.8, 0.00094, 1.7),
        _sample(4.0, 6.0, 5.0, 3.9, 0.00096, 1.4),
        _sample(3.0, 4.8, 5.7, 3.95, 0.000970, 1.1),
        _sample(2.5, 4.1, 6.5, 3.98, 0.000975, 0.9),
    )
    decision = evaluate_local_stress_convergence(samples)
    assert decision.passed is False
    assert decision.classification == "LOCAL_STRESS_NOT_CONVERGED"
    assert decision.checks["last_peak_change"] is False


def test_probe_distance_is_a_real_spatial_gate_not_metadata_only():
    samples = (
        _sample(6.0, 8.0, 4.0, 3.6, 0.00090, 2.5),
        _sample(5.0, 7.0, 4.3, 3.8, 0.00094, 2.2),
        _sample(4.0, 6.0, 4.5, 3.9, 0.00096, 2.0),
        _sample(3.0, 4.8, 4.60, 3.95, 0.000970, 1.8),
        _sample(2.5, 4.1, 4.65, 3.98, 0.000975, 1.7),
    )
    decision = evaluate_local_stress_convergence(samples)
    assert decision.passed is False
    assert decision.checks["final_probe_spatial_resolution"] is False


def test_policy_threshold_change_changes_decision_hash():
    samples = (
        _sample(4.0, 6.0, 4.5, 3.9, 0.00096),
        _sample(3.0, 4.8, 4.60, 3.95, 0.000970),
        _sample(2.5, 4.1, 4.65, 3.98, 0.000975),
        _sample(2.0, 3.5, 4.67, 3.99, 0.000978),
    )
    a = evaluate_local_stress_convergence(samples)
    b = evaluate_local_stress_convergence(
        samples,
        policy=replace(LocalStressConvergencePolicy(), max_last_peak_relative_change=0.04),
    )
    assert a.decision_sha256 != b.decision_sha256
