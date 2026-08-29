from __future__ import annotations

import pytest

from astermax.fea.fixed_neighborhood_convergence import (
    FixedNeighborhoodConvergenceError,
    FixedNeighborhoodRefinementSample,
    evaluate_fixed_neighborhood_convergence,
)


def _sample(size: float, metric: float, peak: float, mean: float, rms: float, volume: float, disp: float) -> FixedNeighborhoodRefinementSample:
    return FixedNeighborhoodRefinementSample(
        local_target_size_mm=size,
        local_mean_max_corner_edge_mm=metric,
        node_count=int(1000 / size),
        tet10_count=int(700 / size),
        local_ip_peak_mpa=peak,
        fixed_neighborhood_mean_mpa=mean,
        fixed_neighborhood_rms_mpa=rms,
        sampled_physical_volume_mm3=volume,
        max_displacement_mm=disp,
        force_residual_n=1.0e-10,
        moment_residual_nmm=1.0e-8,
    )


def _passing_samples():
    return (
        _sample(2.0, 3.3, 5.70, 4.20, 4.25, 26.0, 0.000930),
        _sample(1.8, 3.0, 5.75, 4.25, 4.30, 25.8, 0.000936),
        _sample(1.6, 2.7, 5.80, 4.31, 4.35, 25.5, 0.000940),
        _sample(1.4, 2.3, 5.88, 4.39, 4.42, 25.0, 0.000941),
    )


def test_fixed_neighborhood_policy_can_pass_all_declared_gates():
    decision = evaluate_fixed_neighborhood_convergence(_passing_samples())
    assert decision.passed is True
    assert decision.classification == "FIXED_NEIGHBORHOOD_LOCAL_STRESS_CONVERGED"
    assert all(decision.checks.values())


def test_mean_gate_fails_closed_without_relaxing_threshold():
    samples = list(_passing_samples())
    last = samples[-1]
    samples[-1] = FixedNeighborhoodRefinementSample(
        **{**last.__dict__, "fixed_neighborhood_mean_mpa": 4.70}
    )
    decision = evaluate_fixed_neighborhood_convergence(samples)
    assert decision.passed is False
    assert decision.checks["last_fixed_neighborhood_mean_change"] is False


def test_rms_gate_is_independent_of_mean_gate():
    samples = list(_passing_samples())
    last = samples[-1]
    samples[-1] = FixedNeighborhoodRefinementSample(
        **{**last.__dict__, "fixed_neighborhood_rms_mpa": 4.80}
    )
    decision = evaluate_fixed_neighborhood_convergence(samples)
    assert decision.passed is False
    assert decision.checks["last_fixed_neighborhood_mean_change"] is True
    assert decision.checks["last_fixed_neighborhood_rms_change"] is False


def test_sampled_volume_gate_blocks_measurement_region_instability():
    samples = list(_passing_samples())
    last = samples[-1]
    samples[-1] = FixedNeighborhoodRefinementSample(
        **{**last.__dict__, "sampled_physical_volume_mm3": 23.0}
    )
    decision = evaluate_fixed_neighborhood_convergence(samples)
    assert decision.passed is False
    assert decision.checks["last_sampled_physical_volume_change"] is False


def test_peak_gate_remains_required_even_if_integral_is_stable():
    samples = list(_passing_samples())
    last = samples[-1]
    samples[-1] = FixedNeighborhoodRefinementSample(
        **{**last.__dict__, "local_ip_peak_mpa": 6.30}
    )
    decision = evaluate_fixed_neighborhood_convergence(samples)
    assert decision.passed is False
    assert decision.checks["last_peak_change"] is False


def test_non_strict_measured_refinement_fails_closed():
    samples = list(_passing_samples())
    third = samples[2]
    samples[2] = FixedNeighborhoodRefinementSample(
        **{**third.__dict__, "local_mean_max_corner_edge_mm": samples[1].local_mean_max_corner_edge_mm}
    )
    decision = evaluate_fixed_neighborhood_convergence(samples)
    assert decision.passed is False
    assert decision.checks["strict_local_metric_refinement"] is False


def test_target_sequence_must_be_strictly_decreasing():
    samples = list(_passing_samples())
    third = samples[2]
    samples[2] = FixedNeighborhoodRefinementSample(**{**third.__dict__, "local_target_size_mm": 1.8})
    with pytest.raises(FixedNeighborhoodConvergenceError, match="strictly decreasing"):
        evaluate_fixed_neighborhood_convergence(samples)


def test_decision_hash_is_deterministic():
    a = evaluate_fixed_neighborhood_convergence(_passing_samples())
    b = evaluate_fixed_neighborhood_convergence(_passing_samples())
    assert a.decision_sha256 == b.decision_sha256
