from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Iterable

import numpy as np

from astermax.credibility import (
    ClaimDefinition,
    ClaimRequirement,
    EvidenceRecord,
    EvidenceSource,
    EvidenceStatus,
    canonical_sha256,
)


class SurfaceAxialQOIConvergenceError(ValueError):
    pass


@dataclass(frozen=True)
class SurfaceAxialQOIRefinementSample:
    local_target_size_mm: float
    local_mean_max_corner_edge_mm: float
    node_count: int
    tet10_count: int
    transition_tri6_count: int
    surface_sample_count: int
    sampled_max_axial_normal_stress_mpa: float
    maximum_point_mm: tuple[float, float, float]
    max_displacement_mm: float
    force_residual_n: float
    moment_residual_nmm: float
    mesh_sha256: str
    measurement_sha256: str
    equilibrium_sha256: str


@dataclass(frozen=True)
class SurfaceAxialQOIConvergencePolicy:
    min_samples: int = 4
    max_penultimate_relative_change: float = 0.05
    max_last_relative_change: float = 0.03
    max_last_displacement_relative_change: float = 0.01
    max_force_residual_n: float = 1.0e-6
    max_moment_residual_nmm: float = 1.0e-4
    max_last_meridional_shift_over_final_local_metric: float = 1.0
    require_strict_local_metric_refinement: bool = True


@dataclass(frozen=True)
class SurfaceAxialQOIConvergenceDecision:
    passed: bool
    classification: str
    checks: dict[str, bool]
    metrics: dict[str, float]
    policy: SurfaceAxialQOIConvergencePolicy
    samples: tuple[SurfaceAxialQOIRefinementSample, ...]
    continuous_surface_peak_convergence_claim: bool
    decision_sha256: str


def _relative_change(a: float, b: float) -> float:
    return abs(float(b) - float(a)) / max(abs(float(a)), abs(float(b)), 1.0e-12)


def _meridional_point(point_mm: tuple[float, float, float]) -> np.ndarray:
    point = np.asarray(point_mm, dtype=float)
    if point.shape != (3,) or not np.all(np.isfinite(point)):
        raise SurfaceAxialQOIConvergenceError("maximum_point_mm must contain three finite coordinates")
    return np.asarray((point[0], float(np.hypot(point[1], point[2]))), dtype=float)


def evaluate_surface_axial_qoi_convergence(
    samples: Iterable[SurfaceAxialQOIRefinementSample],
    *,
    policy: SurfaceAxialQOIConvergencePolicy | None = None,
) -> SurfaceAxialQOIConvergenceDecision:
    values = tuple(samples)
    p = policy or SurfaceAxialQOIConvergencePolicy()
    if len(values) < 3:
        raise SurfaceAxialQOIConvergenceError("at least three samples are required to evaluate penultimate and last refinement changes")
    if p.min_samples < 3:
        raise SurfaceAxialQOIConvergenceError("policy min_samples must be >= 3")
    thresholds = (
        p.max_penultimate_relative_change,
        p.max_last_relative_change,
        p.max_last_displacement_relative_change,
        p.max_force_residual_n,
        p.max_moment_residual_nmm,
        p.max_last_meridional_shift_over_final_local_metric,
    )
    if any(not math.isfinite(v) or v <= 0.0 for v in thresholds):
        raise SurfaceAxialQOIConvergenceError("all numeric policy thresholds must be finite and positive")

    for sample in values:
        numeric = (
            sample.local_target_size_mm,
            sample.local_mean_max_corner_edge_mm,
            sample.sampled_max_axial_normal_stress_mpa,
            sample.max_displacement_mm,
            sample.force_residual_n,
            sample.moment_residual_nmm,
        )
        if any(not math.isfinite(v) or v < 0.0 for v in numeric):
            raise SurfaceAxialQOIConvergenceError("refinement samples must contain finite non-negative metrics")
        if sample.local_target_size_mm <= 0.0 or sample.local_mean_max_corner_edge_mm <= 0.0:
            raise SurfaceAxialQOIConvergenceError("mesh size metrics must be positive")
        if sample.node_count <= 0 or sample.tet10_count <= 0:
            raise SurfaceAxialQOIConvergenceError("mesh counts must be positive")
        if sample.transition_tri6_count <= 0 or sample.surface_sample_count <= 0:
            raise SurfaceAxialQOIConvergenceError("surface counts must be positive")
        if sample.surface_sample_count != 4 * sample.transition_tri6_count:
            raise SurfaceAxialQOIConvergenceError("surface sample count must preserve the frozen four-point-per-TRI6 rule")
        if sample.sampled_max_axial_normal_stress_mpa <= 0.0:
            raise SurfaceAxialQOIConvergenceError("sampled maximum axial stress must be positive")
        for digest in (sample.mesh_sha256, sample.measurement_sha256, sample.equilibrium_sha256):
            if len(str(digest)) != 64:
                raise SurfaceAxialQOIConvergenceError("sample evidence digests must be SHA-256 values")
        _meridional_point(sample.maximum_point_mm)

    strict_target = all(b.local_target_size_mm < a.local_target_size_mm for a, b in zip(values, values[1:]))
    if not strict_target:
        raise SurfaceAxialQOIConvergenceError("local target sizes must be strictly decreasing coarse-to-fine")
    strict_metric = all(
        b.local_mean_max_corner_edge_mm < a.local_mean_max_corner_edge_mm
        for a, b in zip(values, values[1:])
    )

    penultimate_change = _relative_change(
        values[-3].sampled_max_axial_normal_stress_mpa,
        values[-2].sampled_max_axial_normal_stress_mpa,
    )
    last_change = _relative_change(
        values[-2].sampled_max_axial_normal_stress_mpa,
        values[-1].sampled_max_axial_normal_stress_mpa,
    )
    last_disp_change = _relative_change(values[-2].max_displacement_mm, values[-1].max_displacement_mm)
    max_force = max(sample.force_residual_n for sample in values)
    max_moment = max(sample.moment_residual_nmm for sample in values)
    last_meridional_shift = float(
        np.linalg.norm(_meridional_point(values[-1].maximum_point_mm) - _meridional_point(values[-2].maximum_point_mm))
    )
    last_meridional_shift_ratio = last_meridional_shift / values[-1].local_mean_max_corner_edge_mm

    checks = {
        "minimum_sample_count": len(values) >= p.min_samples,
        "strict_target_refinement": strict_target,
        "strict_local_metric_refinement": strict_metric if p.require_strict_local_metric_refinement else True,
        "penultimate_qoi_change": penultimate_change <= p.max_penultimate_relative_change,
        "last_qoi_change": last_change <= p.max_last_relative_change,
        "last_displacement_change": last_disp_change <= p.max_last_displacement_relative_change,
        "global_force_balance": max_force <= p.max_force_residual_n,
        "global_moment_balance": max_moment <= p.max_moment_residual_nmm,
        "last_maximum_meridional_location_stability": (
            last_meridional_shift_ratio <= p.max_last_meridional_shift_over_final_local_metric
        ),
    }
    passed = all(checks.values())
    classification = (
        "SURFACE_SAMPLED_AXIAL_QOI_CONVERGED"
        if passed
        else "SURFACE_SAMPLED_AXIAL_QOI_NOT_CONVERGED"
    )
    metrics = {
        "sample_count": float(len(values)),
        "penultimate_qoi_relative_change": penultimate_change,
        "last_qoi_relative_change": last_change,
        "last_displacement_relative_change": last_disp_change,
        "max_force_residual_n": max_force,
        "max_moment_residual_nmm": max_moment,
        "last_maximum_meridional_shift_mm": last_meridional_shift,
        "last_maximum_meridional_shift_over_final_local_metric": last_meridional_shift_ratio,
        "qoi_growth_factor_first_to_last": (
            values[-1].sampled_max_axial_normal_stress_mpa
            / values[0].sampled_max_axial_normal_stress_mpa
        ),
    }
    payload: dict[str, Any] = {
        "schema": "AsterMaxSurfaceAxialQOIConvergenceDecisionV1",
        "passed": passed,
        "classification": classification,
        "checks": checks,
        "metrics": metrics,
        "policy": asdict(p),
        "samples": [asdict(sample) for sample in values],
        "continuous_surface_peak_convergence_claim": False,
    }
    return SurfaceAxialQOIConvergenceDecision(
        passed=passed,
        classification=classification,
        checks=checks,
        metrics=metrics,
        policy=p,
        samples=values,
        continuous_surface_peak_convergence_claim=False,
        decision_sha256=canonical_sha256(payload),
    )


def surface_axial_qoi_convergence_evidence(
    decision: SurfaceAxialQOIConvergenceDecision,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"SURFACE_AXIAL_QOI_CONVERGENCE:{decision.decision_sha256[:16]}",
        kind="SURFACE_AXIAL_QOI_CONVERGENCE",
        status=EvidenceStatus.VERIFIED if decision.passed else EvidenceStatus.UNKNOWN,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Mesh-refinement convergence assessment for the declared discrete sampled fillet-surface axial-normal stress QOI; not a continuous surface-peak claim."
        ),
        payload_sha256=decision.decision_sha256,
        metadata={
            "classification": decision.classification,
            "checks": decision.checks,
            "metrics": decision.metrics,
            "policy": asdict(decision.policy),
            "continuous_surface_peak_convergence_claim": False,
        },
    )


def surface_sampled_axial_qoi_converged_claim(context_id: str) -> ClaimDefinition:
    return ClaimDefinition(
        claim_id="CLAIM_SURFACE_SAMPLED_AXIAL_QOI_CONVERGED",
        context_id=context_id,
        statement=(
            "The declared discrete sampled axial-normal stress QOI on the persistent CAD fillet surface satisfies the frozen mesh-refinement convergence gates."
        ),
        requirements=(
            ClaimRequirement(
                "TET10_SURFACE_STRESS_AFFINE_VERIFICATION",
                allowed_sources=(EvidenceSource.DOCUMENT, EvidenceSource.DETERMINISTIC_CHECK),
            ),
            ClaimRequirement(
                "SURFACE_AXIAL_QOI_CONVERGENCE",
                allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,),
            ),
        ),
    )
