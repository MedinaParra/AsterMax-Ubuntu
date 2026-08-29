from dataclasses import replace

import pytest

from astermax.fea.surface_qoi_convergence import SurfaceAxialQOIRefinementSample
from astermax.fea.surface_qoi_fine_extension import (
    SurfaceAxialQOIFineExtensionError,
    evaluate_surface_axial_qoi_fine_extension,
)


DIGEST = "b" * 64


def _sample(size, metric, qoi, point, disp=0.001, force=1e-10, moment=1e-8, faces=100):
    return SurfaceAxialQOIRefinementSample(
        local_target_size_mm=size,
        local_mean_max_corner_edge_mm=metric,
        node_count=int(20000 / size),
        tet10_count=int(14000 / size),
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


def _passing_history():
    # Deliberately preserve a historical 1.6 -> 1.4 change above 3%.
    # C20b is allowed to establish a later fine-tail convergence claim only if
    # BOTH newly added steps and the full final three-value band satisfy 3%.
    return (
        _sample(2.0, 3.3, 6.15, (38.46, 0.0, 10.05), faces=140),
        _sample(1.8, 3.0, 6.24, (38.48, 7.1, 7.1), faces=150),
        _sample(1.6, 2.7, 6.245, (38.48, 6.0, 8.1), faces=195),
        _sample(1.4, 2.32, 6.45, (38.49, 1.0, 10.0), faces=305),
        _sample(1.2, 2.00, 6.50, (38.50, 9.9, 1.5), disp=0.001002, faces=390),
        _sample(1.0, 1.68, 6.54, (38.51, 0.5, 10.05), disp=0.001004, faces=520),
    )


def test_fine_extension_can_pass_without_erasing_prior_c20_failure():
    d = evaluate_surface_axial_qoi_fine_extension(_passing_history())
    assert d.passed
    assert d.c20_failure_preserved is True
    assert d.continuous_surface_peak_convergence_claim is False
    assert d.classification == "SURFACE_SAMPLED_AXIAL_QOI_FINE_EXTENSION_CONVERGED"
    assert max(d.metrics["last_two_qoi_relative_changes"]) <= 0.03
    assert d.metrics["final_three_qoi_band_relative_span"] <= 0.03


def test_one_new_fine_step_above_three_percent_blocks():
    samples = list(_passing_history())
    samples[-2] = replace(samples[-2], sampled_max_axial_normal_stress_mpa=6.70)
    d = evaluate_surface_axial_qoi_fine_extension(samples)
    assert not d.passed
    assert not d.checks["each_last_two_qoi_changes"]


def test_final_three_band_blocks_cumulative_drift_even_when_adjacent_steps_pass():
    samples = list(_passing_history())
    samples[-2] = replace(samples[-2], sampled_max_axial_normal_stress_mpa=6.63)
    samples[-1] = replace(samples[-1], sampled_max_axial_normal_stress_mpa=6.80)
    d = evaluate_surface_axial_qoi_fine_extension(samples)
    assert all(v <= 0.03 for v in d.metrics["last_two_qoi_relative_changes"])
    assert not d.checks["final_three_qoi_band"]
    assert not d.passed


def test_azimuth_rotation_does_not_block_stable_meridional_tail():
    d = evaluate_surface_axial_qoi_fine_extension(_passing_history())
    assert d.checks["each_last_two_maximum_meridional_locations"]


def test_fine_tail_meridional_jump_blocks():
    samples = list(_passing_history())
    samples[-1] = replace(samples[-1], maximum_point_mm=(42.0, 14.0, 0.0))
    d = evaluate_surface_axial_qoi_fine_extension(samples)
    assert not d.checks["each_last_two_maximum_meridional_locations"]
    assert not d.passed


def test_equilibrium_failure_in_historical_or_new_level_blocks():
    samples = list(_passing_history())
    samples[0] = replace(samples[0], moment_residual_nmm=1e-2)
    d = evaluate_surface_axial_qoi_fine_extension(samples)
    assert not d.checks["global_moment_balance"]
    assert not d.passed


def test_requires_six_total_levels_for_fine_extension_claim():
    d = evaluate_surface_axial_qoi_fine_extension(_passing_history()[:5])
    assert not d.checks["minimum_sample_count"]
    assert not d.passed


def test_rule_mutation_fails_closed():
    samples = list(_passing_history())
    samples[-1] = replace(samples[-1], surface_sample_count=2079)
    with pytest.raises(SurfaceAxialQOIFineExtensionError, match="four-point"):
        evaluate_surface_axial_qoi_fine_extension(samples)


def test_nonrefining_target_sequence_fails_closed():
    samples = list(_passing_history())
    samples[-1] = replace(samples[-1], local_target_size_mm=1.2)
    with pytest.raises(SurfaceAxialQOIFineExtensionError, match="strictly decreasing"):
        evaluate_surface_axial_qoi_fine_extension(samples)
