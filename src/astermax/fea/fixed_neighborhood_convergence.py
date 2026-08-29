from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Iterable

from astermax.credibility import canonical_sha256


class FixedNeighborhoodConvergenceError(ValueError):
    pass


@dataclass(frozen=True)
class FixedNeighborhoodRefinementSample:
    local_target_size_mm: float
    local_mean_max_corner_edge_mm: float
    node_count: int
    tet10_count: int
    local_ip_peak_mpa: float
    fixed_neighborhood_mean_mpa: float
    fixed_neighborhood_rms_mpa: float
    sampled_physical_volume_mm3: float
    max_displacement_mm: float
    force_residual_n: float
    moment_residual_nmm: float


@dataclass(frozen=True)
class FixedNeighborhoodConvergencePolicy:
    min_samples: int = 4
    max_last_peak_relative_change: float = 0.05
    max_last_fixed_mean_relative_change: float = 0.03
    max_last_fixed_rms_relative_change: float = 0.03
    max_last_sampled_volume_relative_change: float = 0.05
    max_last_displacement_relative_change: float = 0.01
    max_force_residual_n: float = 1.0e-5
    max_moment_residual_nmm: float = 1.0e-3
    require_strict_local_metric_refinement: bool = True


@dataclass(frozen=True)
class FixedNeighborhoodConvergenceDecision:
    passed: bool
    classification: str
    checks: dict[str, bool]
    metrics: dict[str, float]
    policy: FixedNeighborhoodConvergencePolicy
    samples: tuple[FixedNeighborhoodRefinementSample, ...]
    decision_sha256: str


def _relative_change(a: float, b: float) -> float:
    return abs(float(b) - float(a)) / max(abs(float(a)), abs(float(b)), 1.0e-12)


def evaluate_fixed_neighborhood_convergence(
    samples: Iterable[FixedNeighborhoodRefinementSample],
    *,
    policy: FixedNeighborhoodConvergencePolicy | None = None,
) -> FixedNeighborhoodConvergenceDecision:
    values = tuple(samples)
    p = policy or FixedNeighborhoodConvergencePolicy()
    if len(values) < 2:
        raise FixedNeighborhoodConvergenceError("at least two refinement samples are required")
    if p.min_samples < 2:
        raise FixedNeighborhoodConvergenceError("policy min_samples must be >= 2")

    thresholds = (
        p.max_last_peak_relative_change,
        p.max_last_fixed_mean_relative_change,
        p.max_last_fixed_rms_relative_change,
        p.max_last_sampled_volume_relative_change,
        p.max_last_displacement_relative_change,
        p.max_force_residual_n,
        p.max_moment_residual_nmm,
    )
    if any(not math.isfinite(value) or value <= 0.0 for value in thresholds):
        raise FixedNeighborhoodConvergenceError("all numeric policy thresholds must be finite and positive")

    for sample in values:
        numeric = (
            sample.local_target_size_mm,
            sample.local_mean_max_corner_edge_mm,
            sample.local_ip_peak_mpa,
            sample.fixed_neighborhood_mean_mpa,
            sample.fixed_neighborhood_rms_mpa,
            sample.sampled_physical_volume_mm3,
            sample.max_displacement_mm,
            sample.force_residual_n,
            sample.moment_residual_nmm,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in numeric):
            raise FixedNeighborhoodConvergenceError("refinement samples must contain finite non-negative metrics")
        if sample.local_target_size_mm <= 0.0 or sample.local_mean_max_corner_edge_mm <= 0.0:
            raise FixedNeighborhoodConvergenceError("mesh size metrics must be positive")
        if sample.fixed_neighborhood_mean_mpa <= 0.0 or sample.fixed_neighborhood_rms_mpa <= 0.0:
            raise FixedNeighborhoodConvergenceError("fixed-neighborhood stress witnesses must be positive")
        if sample.sampled_physical_volume_mm3 <= 0.0:
            raise FixedNeighborhoodConvergenceError("sampled physical volume must be positive")
        if sample.node_count <= 0 or sample.tet10_count <= 0:
            raise FixedNeighborhoodConvergenceError("mesh counts must be positive")

    strict_target = all(b.local_target_size_mm < a.local_target_size_mm for a, b in zip(values, values[1:]))
    if not strict_target:
        raise FixedNeighborhoodConvergenceError("local target sizes must be strictly decreasing coarse-to-fine")
    strict_metric = all(
        b.local_mean_max_corner_edge_mm < a.local_mean_max_corner_edge_mm
        for a, b in zip(values, values[1:])
    )

    last_peak = _relative_change(values[-2].local_ip_peak_mpa, values[-1].local_ip_peak_mpa)
    last_mean = _relative_change(
        values[-2].fixed_neighborhood_mean_mpa,
        values[-1].fixed_neighborhood_mean_mpa,
    )
    last_rms = _relative_change(
        values[-2].fixed_neighborhood_rms_mpa,
        values[-1].fixed_neighborhood_rms_mpa,
    )
    last_volume = _relative_change(
        values[-2].sampled_physical_volume_mm3,
        values[-1].sampled_physical_volume_mm3,
    )
    last_disp = _relative_change(values[-2].max_displacement_mm, values[-1].max_displacement_mm)
    max_force = max(sample.force_residual_n for sample in values)
    max_moment = max(sample.moment_residual_nmm for sample in values)

    checks = {
        "minimum_sample_count": len(values) >= p.min_samples,
        "strict_target_refinement": strict_target,
        "strict_local_metric_refinement": strict_metric if p.require_strict_local_metric_refinement else True,
        "last_peak_change": last_peak <= p.max_last_peak_relative_change,
        "last_fixed_neighborhood_mean_change": last_mean <= p.max_last_fixed_mean_relative_change,
        "last_fixed_neighborhood_rms_change": last_rms <= p.max_last_fixed_rms_relative_change,
        "last_sampled_physical_volume_change": last_volume <= p.max_last_sampled_volume_relative_change,
        "last_displacement_change": last_disp <= p.max_last_displacement_relative_change,
        "global_force_balance": max_force <= p.max_force_residual_n,
        "global_moment_balance": max_moment <= p.max_moment_residual_nmm,
    }
    passed = all(checks.values())
    classification = (
        "FIXED_NEIGHBORHOOD_LOCAL_STRESS_CONVERGED"
        if passed
        else "FIXED_NEIGHBORHOOD_LOCAL_STRESS_NOT_CONVERGED"
    )
    metrics = {
        "sample_count": float(len(values)),
        "last_peak_relative_change": last_peak,
        "last_fixed_neighborhood_mean_relative_change": last_mean,
        "last_fixed_neighborhood_rms_relative_change": last_rms,
        "last_sampled_physical_volume_relative_change": last_volume,
        "last_displacement_relative_change": last_disp,
        "max_force_residual_n": max_force,
        "max_moment_residual_nmm": max_moment,
        "peak_growth_factor_first_to_last": values[-1].local_ip_peak_mpa / max(values[0].local_ip_peak_mpa, 1.0e-12),
    }
    payload: dict[str, Any] = {
        "schema": "AsterMaxFixedNeighborhoodConvergenceDecisionV1",
        "passed": passed,
        "classification": classification,
        "checks": checks,
        "metrics": metrics,
        "policy": asdict(p),
        "samples": [asdict(sample) for sample in values],
    }
    return FixedNeighborhoodConvergenceDecision(
        passed=passed,
        classification=classification,
        checks=checks,
        metrics=metrics,
        policy=p,
        samples=values,
        decision_sha256=canonical_sha256(payload),
    )
