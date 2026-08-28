from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

from astermax.credibility import EvidenceRecord, EvidenceSource, EvidenceStatus, canonical_sha256
from .neighborhood_verification import NeighborhoodComparison
from .singularity_diagnostic import SingularityDiagnostic


class PhysicsGuidedRefinementError(ValueError):
    pass


@dataclass(frozen=True)
class PhysicsGuidedRefinementPolicy:
    target_size_factor: float = 0.5
    maximum_additional_cycles: int = 3
    stop_when_neighborhood_passes: bool = True

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.target_size_factor)
            or self.target_size_factor <= 0.0
            or self.target_size_factor >= 1.0
        ):
            raise PhysicsGuidedRefinementError("target_size_factor must be between zero and one")
        if int(self.maximum_additional_cycles) < 1:
            raise PhysicsGuidedRefinementError("maximum_additional_cycles must be positive")


@dataclass(frozen=True)
class RefinementRecommendation:
    schema: str
    recommendation_id: str
    action: str
    reason: str
    target_size_factor: float | None
    maximum_additional_cycles: int
    neighborhood_sha256: str
    singularity_sha256: str
    recommendation_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("recommendation_sha256")
        return payload


def recommend_local_refinement(
    *,
    recommendation_id: str,
    neighborhood: NeighborhoodComparison,
    singularity: SingularityDiagnostic,
    policy: PhysicsGuidedRefinementPolicy = PhysicsGuidedRefinementPolicy(),
) -> RefinementRecommendation:
    recommendation_id = str(recommendation_id).strip()
    if not recommendation_id:
        raise PhysicsGuidedRefinementError("recommendation_id must be non-empty")

    if singularity.classification == "LIKELY_SINGULARITY":
        action = "REFINE_NEIGHBORHOOD_DO_NOT_CHASE_PEAK"
        reason = (
            "Peak remains mesh-sensitive while the neighboring field is stabilizing; "
            "refine only to characterize the surrounding field and keep the core peak non-claimable."
        )
        factor = policy.target_size_factor
    elif neighborhood.passed and singularity.classification == "LOCALLY_CONVERGED_FIELD":
        action = "NO_REFINEMENT_REQUIRED"
        reason = "Neighborhood agrees with its witness and local peak/neighborhood trends are stable."
        factor = None
    elif not neighborhood.passed:
        action = "REFINE_LOCAL_NEIGHBORHOOD"
        reason = "FEA neighborhood does not yet agree with the independent witness within declared tolerance."
        factor = policy.target_size_factor
    else:
        action = "REFINE_FOR_STABILITY"
        reason = "Neighborhood agreement is acceptable but refinement trend remains inconclusive."
        factor = policy.target_size_factor

    payload = {
        "schema": "AsterMaxPhysicsGuidedRefinementRecommendationV1",
        "recommendation_id": recommendation_id,
        "action": action,
        "reason": reason,
        "target_size_factor": factor,
        "maximum_additional_cycles": int(policy.maximum_additional_cycles),
        "neighborhood_sha256": neighborhood.comparison_sha256,
        "singularity_sha256": singularity.diagnostic_sha256,
    }
    return RefinementRecommendation(**payload, recommendation_sha256=canonical_sha256(payload))


def refinement_recommendation_evidence(
    recommendation: RefinementRecommendation,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"REFINEMENT:{recommendation.recommendation_id}:{recommendation.recommendation_sha256[:16]}",
        kind="PHYSICS_GUIDED_REFINEMENT_RECOMMENDATION",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Deterministic local refinement recommendation derived from neighborhood discrepancy and singularity trend. "
            "It is not itself a solution-verification claim."
        ),
        payload_sha256=recommendation.recommendation_sha256,
        metadata=recommendation.canonical_without_hash(),
    )
