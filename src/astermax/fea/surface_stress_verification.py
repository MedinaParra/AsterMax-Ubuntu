from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Iterable

from astermax.credibility import (
    ClaimDefinition,
    ClaimRequirement,
    EvidenceRecord,
    EvidenceSource,
    EvidenceStatus,
    canonical_sha256,
)
from .tet10_surface_stress import Tet10SurfaceStressSample


class SurfaceStressVerificationError(ValueError):
    pass


@dataclass(frozen=True)
class SurfaceStressAffineVerification:
    schema: str
    verification_id: str
    sample_count: int
    expected_axial_normal_stress_mpa: float
    minimum_axial_normal_stress_mpa: float
    maximum_axial_normal_stress_mpa: float
    maximum_absolute_error_mpa: float
    maximum_relative_error: float
    minimum_det_jacobian: float
    maximum_allowed_absolute_error_mpa: float
    maximum_allowed_relative_error: float
    no_nodal_stress_recovery: bool
    no_stress_smoothing: bool
    no_integration_point_stress_extrapolation: bool
    direct_displacement_gradient_evaluation: bool
    passed: bool
    verification_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("verification_sha256")
        return payload


def verify_affine_surface_axial_stress(
    verification_id: str,
    samples: Iterable[Tet10SurfaceStressSample],
    *,
    expected_axial_normal_stress_mpa: float,
    maximum_absolute_error_mpa: float = 1.0e-8,
    maximum_relative_error: float = 1.0e-10,
) -> SurfaceStressAffineVerification:
    sid = str(verification_id).strip()
    values = tuple(samples)
    expected = float(expected_axial_normal_stress_mpa)
    abs_limit = float(maximum_absolute_error_mpa)
    rel_limit = float(maximum_relative_error)
    if not sid:
        raise SurfaceStressVerificationError("verification_id must be non-empty")
    if not values:
        raise SurfaceStressVerificationError("surface stress verification requires at least one sample")
    if not math.isfinite(expected):
        raise SurfaceStressVerificationError("expected stress must be finite")
    if not math.isfinite(abs_limit) or abs_limit < 0.0 or not math.isfinite(rel_limit) or rel_limit < 0.0:
        raise SurfaceStressVerificationError("verification tolerances must be finite and non-negative")

    measured = tuple(float(sample.axial_normal_stress_mpa) for sample in values)
    dets = tuple(float(sample.det_jacobian) for sample in values)
    if any(not math.isfinite(v) for v in (*measured, *dets)) or min(dets) <= 0.0:
        raise SurfaceStressVerificationError("samples contain invalid stress or Jacobian values")
    errors = tuple(abs(v - expected) for v in measured)
    denom = max(abs(expected), 1.0e-30)
    rel_errors = tuple(error / denom for error in errors)
    max_abs = max(errors)
    max_rel = max(rel_errors)
    passed = bool(max_abs <= abs_limit and max_rel <= rel_limit)

    payload = {
        "schema": "AsterMaxSurfaceStressAffineVerificationV1",
        "verification_id": sid,
        "sample_count": len(values),
        "expected_axial_normal_stress_mpa": expected,
        "minimum_axial_normal_stress_mpa": min(measured),
        "maximum_axial_normal_stress_mpa": max(measured),
        "maximum_absolute_error_mpa": max_abs,
        "maximum_relative_error": max_rel,
        "minimum_det_jacobian": min(dets),
        "maximum_allowed_absolute_error_mpa": abs_limit,
        "maximum_allowed_relative_error": rel_limit,
        "no_nodal_stress_recovery": True,
        "no_stress_smoothing": True,
        "no_integration_point_stress_extrapolation": True,
        "direct_displacement_gradient_evaluation": True,
        "passed": passed,
    }
    return SurfaceStressAffineVerification(
        **payload,
        verification_sha256=canonical_sha256(payload),
    )


def surface_stress_affine_verification_evidence(
    verification: SurfaceStressAffineVerification,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"SURFACE_STRESS_AFFINE:{verification.verification_sha256[:16]}",
        kind="TET10_SURFACE_STRESS_AFFINE_VERIFICATION",
        status=EvidenceStatus.VERIFIED if verification.passed else EvidenceStatus.CONTRADICTED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Direct TET10 boundary stress evaluation reproduces the declared affine reference field without nodal recovery, smoothing or IP-stress extrapolation."
            if verification.passed
            else "Direct TET10 boundary stress evaluation failed the declared affine reference-field tolerance."
        ),
        payload_sha256=verification.verification_sha256,
        metadata=verification.canonical_without_hash(),
    )


def tet10_surface_stress_affine_verification_claim(context_id: str) -> ClaimDefinition:
    return ClaimDefinition(
        claim_id="CLAIM_TET10_SURFACE_STRESS_OPERATOR_AFFINE_VERIFIED",
        context_id=context_id,
        statement=(
            "The direct TET10 surface stress operator reproduces an affine uniaxial reference field on the selected curved CAD surface within the frozen tolerance."
        ),
        requirements=(
            ClaimRequirement(
                "TET10_SURFACE_STRESS_AFFINE_VERIFICATION",
                allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,),
            ),
        ),
    )
