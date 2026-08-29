from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

from astermax.credibility import canonical_sha256
from .bounded_stress_concentration import StressConcentrationGrid
from .shaft_shoulder import ShaftShoulderGeometry
from .stress_concentration_applicability import StressConcentrationApplicabilityAssessment


class EmpiricalKtEvaluationError(ValueError):
    pass


@dataclass(frozen=True)
class DomainBoundStressConcentrationEvaluation:
    schema: str
    dataset_sha256: str
    geometry_sha256: str
    applicability_assessment_sha256: str
    actual_diameter_ratio: float
    evaluated_diameter_ratio: float
    diameter_ratio_snap_absolute: float
    actual_radius_ratio: float
    radius_bracket: tuple[float, float]
    radius_interpolation_fraction: float
    factor: float
    interpolation: str
    evaluation_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("evaluation_sha256")
        return payload


def evaluate_domain_bound_stress_concentration(
    grid: StressConcentrationGrid,
    applicability: StressConcentrationApplicabilityAssessment,
    geometry: ShaftShoulderGeometry,
) -> DomainBoundStressConcentrationEvaluation:
    if not applicability.applicable:
        raise EmpiricalKtEvaluationError("EMPIRICAL_SOURCE_OUTSIDE_GEOMETRY_DOMAIN")
    if applicability.geometry_sha256 != geometry.geometry_sha256:
        raise EmpiricalKtEvaluationError("EMPIRICAL_APPLICABILITY_GEOMETRY_SHA_MISMATCH")
    if applicability.source_provenance_sha256 != grid.source_provenance_sha256:
        raise EmpiricalKtEvaluationError("EMPIRICAL_APPLICABILITY_GRID_SOURCE_SHA_MISMATCH")
    if applicability.matched_diameter_ratio is None:
        raise EmpiricalKtEvaluationError("EMPIRICAL_DIAMETER_RATIO_NOT_RESOLVED_TO_DECLARED_CURVE")
    if applicability.requested_load_mode != grid.load_mode.strip().upper():
        raise EmpiricalKtEvaluationError("EMPIRICAL_LOAD_MODE_GRID_MISMATCH")

    matched_d = float(applicability.matched_diameter_ratio)
    candidates = [i for i, value in enumerate(grid.diameter_ratios) if abs(float(value) - matched_d) <= 1.0e-12]
    if len(candidates) != 1:
        raise EmpiricalKtEvaluationError("EMPIRICAL_MATCHED_DIAMETER_CURVE_NOT_IN_DATASET")
    row_index = candidates[0]

    r = float(geometry.radius_ratio)
    r_axis = tuple(float(v) for v in grid.radius_ratios)
    if r < r_axis[0] or r > r_axis[-1]:
        raise EmpiricalKtEvaluationError("EMPIRICAL_RADIUS_RATIO_OUTSIDE_DATASET")
    if r == r_axis[-1]:
        j0, j1, t = len(r_axis) - 2, len(r_axis) - 1, 1.0
    else:
        found = None
        for j in range(len(r_axis) - 1):
            if r_axis[j] <= r <= r_axis[j + 1]:
                span = r_axis[j + 1] - r_axis[j]
                found = (j, j + 1, (r - r_axis[j]) / span)
                break
        if found is None:
            raise EmpiricalKtEvaluationError("EMPIRICAL_RADIUS_RATIO_BRACKET_NOT_FOUND")
        j0, j1, t = found

    f0 = float(grid.factors[row_index][j0])
    f1 = float(grid.factors[row_index][j1])
    factor = (1.0 - t) * f0 + t * f1
    if not math.isfinite(factor) or factor <= 0.0:
        raise EmpiricalKtEvaluationError("EMPIRICAL_INTERPOLATED_FACTOR_INVALID")

    payload = {
        "schema": "AsterMaxDomainBoundStressConcentrationEvaluationV1",
        "dataset_sha256": grid.dataset_sha256,
        "geometry_sha256": geometry.geometry_sha256,
        "applicability_assessment_sha256": applicability.assessment_sha256,
        "actual_diameter_ratio": float(geometry.diameter_ratio),
        "evaluated_diameter_ratio": matched_d,
        "diameter_ratio_snap_absolute": abs(float(geometry.diameter_ratio) - matched_d),
        "actual_radius_ratio": r,
        "radius_bracket": (r_axis[j0], r_axis[j1]),
        "radius_interpolation_fraction": float(t),
        "factor": factor,
        "interpolation": "DECLARED_D_OVER_D_CURVE_IDENTITY_PLUS_BOUNDED_LINEAR_R_OVER_D_NO_EXTRAPOLATION",
    }
    return DomainBoundStressConcentrationEvaluation(
        **payload,
        evaluation_sha256=canonical_sha256(payload),
    )
