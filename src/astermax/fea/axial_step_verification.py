from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from astermax.credibility import canonical_sha256


class AxialStepVerificationError(ValueError):
    pass


@dataclass(frozen=True)
class AxialRefinementLevel:
    mesh_size_mm: float
    node_count: int
    tet10_count: int
    interior_sample_count: int
    mean_sigma_xx_mpa: float
    rms_error_mpa: float
    maximum_relative_error: float

    def validate(self) -> None:
        if not np.isfinite(self.mesh_size_mm) or self.mesh_size_mm <= 0.0:
            raise AxialStepVerificationError("mesh_size_mm must be finite and positive")
        if self.node_count <= 0 or self.tet10_count <= 0 or self.interior_sample_count <= 0:
            raise AxialStepVerificationError("mesh/refinement counts must be positive")
        for name in ("mean_sigma_xx_mpa", "rms_error_mpa", "maximum_relative_error"):
            value = float(getattr(self, name))
            if not np.isfinite(value) or (name != "mean_sigma_xx_mpa" and value < 0.0):
                raise AxialStepVerificationError(f"{name} must be finite and nonnegative where applicable")


@dataclass(frozen=True)
class AxialRefinementPolicy:
    expected_level_count: int = 3
    final_rms_relative_limit: float = 0.03
    final_max_relative_limit: float = 0.08
    required_rms_improvement_ratio: float = 0.90
    schema: str = "ASTERMAX_AXIAL_STEP_REFINEMENT_POLICY_V1"

    def validate(self) -> None:
        if self.expected_level_count < 3:
            raise AxialStepVerificationError("at least three refinement levels are required")
        for name in ("final_rms_relative_limit", "final_max_relative_limit", "required_rms_improvement_ratio"):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value <= 0.0:
                raise AxialStepVerificationError(f"{name} must be finite and positive")
        if self.required_rms_improvement_ratio > 1.0:
            raise AxialStepVerificationError("required_rms_improvement_ratio must be <= 1")
        if self.schema != "ASTERMAX_AXIAL_STEP_REFINEMENT_POLICY_V1":
            raise AxialStepVerificationError("unsupported axial refinement policy schema")


DEFAULT_AXIAL_REFINEMENT_POLICY = AxialRefinementPolicy()


@dataclass(frozen=True)
class AxialRefinementAssessment:
    schema: str
    level_count: int
    mesh_sizes_mm: tuple[float, ...]
    rms_errors_mpa: tuple[float, ...]
    max_relative_errors: tuple[float, ...]
    rms_relative_errors: tuple[float, ...]
    coarse_to_fine_rms_ratio: float
    final_rms_relative_error: float
    final_max_relative_error: float
    stress_convergence_claim: bool
    decision: str
    policy: dict
    evidence_boundary: str
    assessment_sha256: str


def assess_axial_refinement(
    levels: list[AxialRefinementLevel] | tuple[AxialRefinementLevel, ...],
    reference_sigma_mpa: float,
    *,
    policy: AxialRefinementPolicy = DEFAULT_AXIAL_REFINEMENT_POLICY,
) -> AxialRefinementAssessment:
    policy.validate()
    reference = float(reference_sigma_mpa)
    if not np.isfinite(reference) or abs(reference) <= 1.0e-12:
        raise AxialStepVerificationError("reference_sigma_mpa must be finite and nonzero")
    items = tuple(levels)
    if len(items) != policy.expected_level_count:
        raise AxialStepVerificationError(
            f"expected exactly {policy.expected_level_count} refinement levels, got {len(items)}"
        )
    for item in items:
        item.validate()
    sizes = np.asarray([item.mesh_size_mm for item in items], dtype=float)
    if not np.all(np.diff(sizes) < 0.0):
        raise AxialStepVerificationError("refinement levels must be ordered coarse-to-fine by decreasing mesh size")
    rms = np.asarray([item.rms_error_mpa for item in items], dtype=float)
    max_rel = np.asarray([item.maximum_relative_error for item in items], dtype=float)
    rms_rel = rms / abs(reference)
    coarse_to_fine = float(rms[-1] / max(rms[0], 1.0e-30))
    final_rms_rel = float(rms_rel[-1])
    final_max_rel = float(max_rel[-1])
    claim = bool(
        final_rms_rel <= policy.final_rms_relative_limit
        and final_max_rel <= policy.final_max_relative_limit
        and coarse_to_fine <= policy.required_rms_improvement_ratio
    )
    decision = "STRESS_REFINEMENT_CRITERIA_MET" if claim else "STRESS_REFINEMENT_CLAIM_BLOCKED"
    payload = {
        "schema": "AsterMaxAxialStepRefinementAssessmentV1",
        "level_count": len(items),
        "mesh_sizes_mm": [float(v) for v in sizes],
        "rms_errors_mpa": [float(v) for v in rms],
        "max_relative_errors": [float(v) for v in max_rel],
        "rms_relative_errors": [float(v) for v in rms_rel],
        "coarse_to_fine_rms_ratio": coarse_to_fine,
        "final_rms_relative_error": final_rms_rel,
        "final_max_relative_error": final_max_rel,
        "stress_convergence_claim": claim,
        "decision": decision,
        "policy": asdict(policy),
        "evidence_boundary": (
            "AXIAL_STEP_INTERIOR_SIGMA_XX_REFINEMENT_ONLY_NOT_ARBITRARY_MODEL_CONVERGENCE_"
            "NOT_INDUSTRIAL_VALIDATION_NOT_ANSYS_EQUIVALENCE"
        ),
    }
    return AxialRefinementAssessment(
        schema=payload["schema"],
        level_count=payload["level_count"],
        mesh_sizes_mm=tuple(payload["mesh_sizes_mm"]),
        rms_errors_mpa=tuple(payload["rms_errors_mpa"]),
        max_relative_errors=tuple(payload["max_relative_errors"]),
        rms_relative_errors=tuple(payload["rms_relative_errors"]),
        coarse_to_fine_rms_ratio=coarse_to_fine,
        final_rms_relative_error=final_rms_rel,
        final_max_relative_error=final_max_rel,
        stress_convergence_claim=claim,
        decision=decision,
        policy=payload["policy"],
        evidence_boundary=payload["evidence_boundary"],
        assessment_sha256=canonical_sha256(payload),
    )
