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
from .surface_qoi_convergence import SurfaceAxialQOIRefinementSample


class SurfaceAxialQOIFineExtensionError(ValueError):
    pass


@dataclass(frozen=True)
class SurfaceAxialQOIFineExtensionPolicy:
    min_samples: int = 6
    max_each_last_two_qoi_relative_change: float = 0.03
    max_final_three_qoi_band_relative_span: float = 0.03
    max_each_last_two_displacement_relative_change: float = 0.01
    max_force_residual_n: float = 1.0e-6
    max_moment_residual_nmm: float = 1.0e-4
    max_each_last_two_meridional_shift_over_finer_local_metric: float = 1.0
    require_strict_local_metric_refinement: bool = True


@dataclass(frozen=True)
class SurfaceAxialQOIFineExtensionDecision:
    passed: bool
    classification: str
    checks: dict[str, bool]
    metrics: dict[str, Any]
    policy: SurfaceAxialQOIFineExtensionPolicy
    samples: tuple[SurfaceAxialQOIRefinementSample, ...]
    c20_failure_preserved: bool
    continuous_surface_peak_convergence_claim: bool
    decision_sha256: str


def _relative_change(a: float, b: float) -> float:
    return abs(float(b) - float(a)) / max(abs(float(a)), abs(float(b)), 1.0e-12)


def _meridional(point_mm: tuple[float, float, float]) -> np.ndarray:
    p = np.asarray(point_mm, dtype=float)
    if p.shape != (3,) or not np.all(np.isfinite(p)):
        raise SurfaceAxialQOIFineExtensionError("maximum point must contain three finite coordinates")
    return np.asarray((p[0], float(np.hypot(p[1], p[2]))), dtype=float)


def evaluate_surface_axial_qoi_fine_extension(
    samples: Iterable[SurfaceAxialQOIRefinementSample],
    *,
    policy: SurfaceAxialQOIFineExtensionPolicy | None = None,
) -> SurfaceAxialQOIFineExtensionDecision:
    values = tuple(samples)
    p = policy or SurfaceAxialQOIFineExtensionPolicy()
    if len(values) < 3:
        raise SurfaceAxialQOIFineExtensionError("at least three samples are required")
    if p.min_samples < 3:
        raise SurfaceAxialQOIFineExtensionError("policy min_samples must be >= 3")
    thresholds = (
        p.max_each_last_two_qoi_relative_change,
        p.max_final_three_qoi_band_relative_span,
        p.max_each_last_two_displacement_relative_change,
        p.max_force_residual_n,
        p.max_moment_residual_nmm,
        p.max_each_last_two_meridional_shift_over_finer_local_metric,
    )
    if any(not math.isfinite(v) or v <= 0.0 for v in thresholds):
        raise SurfaceAxialQOIFineExtensionError("all policy thresholds must be finite and positive")

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
            raise SurfaceAxialQOIFineExtensionError("samples contain invalid numeric values")
        if sample.local_target_size_mm <= 0.0 or sample.local_mean_max_corner_edge_mm <= 0.0:
            raise SurfaceAxialQOIFineExtensionError("mesh metrics must be positive")
        if sample.node_count <= 0 or sample.tet10_count <= 0:
            raise SurfaceAxialQOIFineExtensionError("mesh counts must be positive")
        if sample.transition_tri6_count <= 0 or sample.surface_sample_count != 4 * sample.transition_tri6_count:
            raise SurfaceAxialQOIFineExtensionError("frozen four-point-per-TRI6 rule was not preserved")
        if sample.sampled_max_axial_normal_stress_mpa <= 0.0:
            raise SurfaceAxialQOIFineExtensionError("sampled maximum stress must be positive")
        for digest in (sample.mesh_sha256, sample.measurement_sha256, sample.equilibrium_sha256):
            if len(str(digest)) != 64:
                raise SurfaceAxialQOIFineExtensionError("sample evidence digests must be SHA-256 values")
        _meridional(sample.maximum_point_mm)

    strict_target = all(b.local_target_size_mm < a.local_target_size_mm for a, b in zip(values, values[1:]))
    if not strict_target:
        raise SurfaceAxialQOIFineExtensionError("local target sizes must be strictly decreasing")
    strict_metric = all(
        b.local_mean_max_corner_edge_mm < a.local_mean_max_corner_edge_mm
        for a, b in zip(values, values[1:])
    )

    qoi_changes = tuple(
        _relative_change(a.sampled_max_axial_normal_stress_mpa, b.sampled_max_axial_normal_stress_mpa)
        for a, b in zip(values, values[1:])
    )
    displacement_changes = tuple(
        _relative_change(a.max_displacement_mm, b.max_displacement_mm)
        for a, b in zip(values, values[1:])
    )
    last_two_qoi = qoi_changes[-2:]
    last_two_disp = displacement_changes[-2:]
    final_three = np.asarray([s.sampled_max_axial_normal_stress_mpa for s in values[-3:]], dtype=float)
    final_three_band = float((np.max(final_three) - np.min(final_three)) / max(np.max(np.abs(final_three)), 1.0e-12))

    last_two_shift = []
    last_two_shift_ratio = []
    for a, b in zip(values[-3:-1], values[-2:]):
        shift = float(np.linalg.norm(_meridional(b.maximum_point_mm) - _meridional(a.maximum_point_mm)))
        last_two_shift.append(shift)
        last_two_shift_ratio.append(shift / b.local_mean_max_corner_edge_mm)

    max_force = max(s.force_residual_n for s in values)
    max_moment = max(s.moment_residual_nmm for s in values)
    checks = {
        "minimum_sample_count": len(values) >= p.min_samples,
        "strict_target_refinement": strict_target,
        "strict_local_metric_refinement": strict_metric if p.require_strict_local_metric_refinement else True,
        "each_last_two_qoi_changes": all(v <= p.max_each_last_two_qoi_relative_change for v in last_two_qoi),
        "final_three_qoi_band": final_three_band <= p.max_final_three_qoi_band_relative_span,
        "each_last_two_displacement_changes": all(v <= p.max_each_last_two_displacement_relative_change for v in last_two_disp),
        "global_force_balance": max_force <= p.max_force_residual_n,
        "global_moment_balance": max_moment <= p.max_moment_residual_nmm,
        "each_last_two_maximum_meridional_locations": all(
            v <= p.max_each_last_two_meridional_shift_over_finer_local_metric for v in last_two_shift_ratio
        ),
    }
    passed = all(checks.values())
    classification = (
        "SURFACE_SAMPLED_AXIAL_QOI_FINE_EXTENSION_CONVERGED"
        if passed
        else "SURFACE_SAMPLED_AXIAL_QOI_FINE_EXTENSION_NOT_CONVERGED"
    )
    metrics: dict[str, Any] = {
        "sample_count": len(values),
        "all_qoi_relative_changes": list(qoi_changes),
        "last_two_qoi_relative_changes": list(last_two_qoi),
        "final_three_qoi_band_relative_span": final_three_band,
        "last_two_displacement_relative_changes": list(last_two_disp),
        "last_two_meridional_shift_mm": last_two_shift,
        "last_two_meridional_shift_over_finer_local_metric": last_two_shift_ratio,
        "max_force_residual_n": max_force,
        "max_moment_residual_nmm": max_moment,
        "qoi_growth_factor_first_to_last": (
            values[-1].sampled_max_axial_normal_stress_mpa / values[0].sampled_max_axial_normal_stress_mpa
        ),
    }
    payload = {
        "schema": "AsterMaxSurfaceAxialQOIFineExtensionDecisionV1",
        "passed": passed,
        "classification": classification,
        "checks": checks,
        "metrics": metrics,
        "policy": asdict(p),
        "samples": [asdict(s) for s in values],
        "c20_failure_preserved": True,
        "continuous_surface_peak_convergence_claim": False,
    }
    return SurfaceAxialQOIFineExtensionDecision(
        passed=passed,
        classification=classification,
        checks=checks,
        metrics=metrics,
        policy=p,
        samples=values,
        c20_failure_preserved=True,
        continuous_surface_peak_convergence_claim=False,
        decision_sha256=canonical_sha256(payload),
    )


def surface_axial_qoi_fine_extension_evidence(decision: SurfaceAxialQOIFineExtensionDecision) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"SURFACE_AXIAL_QOI_FINE_EXTENSION:{decision.decision_sha256[:16]}",
        kind="SURFACE_AXIAL_QOI_FINE_EXTENSION_CONVERGENCE",
        status=EvidenceStatus.VERIFIED if decision.passed else EvidenceStatus.UNKNOWN,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description="Finer 1.2/1.0 mm extension of the sampled fillet-surface axial-normal stress QOI convergence study; prior C20 non-convergence remains preserved.",
        payload_sha256=decision.decision_sha256,
        metadata={
            "classification": decision.classification,
            "checks": decision.checks,
            "metrics": decision.metrics,
            "policy": asdict(decision.policy),
            "c20_failure_preserved": True,
            "continuous_surface_peak_convergence_claim": False,
        },
    )


def surface_sampled_axial_qoi_fine_converged_claim(context_id: str) -> ClaimDefinition:
    return ClaimDefinition(
        claim_id="CLAIM_SURFACE_SAMPLED_AXIAL_QOI_FINE_EXTENSION_CONVERGED",
        context_id=context_id,
        statement="After preserving the failed C20 gate and adding the predeclared 1.2 and 1.0 mm levels, the declared discrete sampled fillet-surface axial-normal stress QOI satisfies the frozen finer-tail convergence gates.",
        requirements=(
            ClaimRequirement("TET10_SURFACE_STRESS_AFFINE_VERIFICATION", allowed_sources=(EvidenceSource.DOCUMENT, EvidenceSource.DETERMINISTIC_CHECK)),
            ClaimRequirement("C20_NONCONVERGENCE_PROVENANCE", allowed_sources=(EvidenceSource.DOCUMENT,)),
            ClaimRequirement("SURFACE_AXIAL_QOI_FINE_EXTENSION_CONVERGENCE", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
        ),
    )
