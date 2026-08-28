from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Iterable

from astermax.credibility import EvidenceRecord, EvidenceSource, EvidenceStatus, canonical_sha256


class NeighborhoodVerificationError(ValueError):
    pass


@dataclass(frozen=True)
class NeighborhoodSample:
    distance_mm: float
    fea_value_mpa: float
    witness_value_mpa: float


@dataclass(frozen=True)
class NeighborhoodComparison:
    schema: str
    comparison_id: str
    sample_count: int
    core_exclusion_mm: float
    max_allowed_relative_error: float
    max_relative_error: float
    mean_relative_error: float
    passed: bool
    method: str
    samples: tuple[NeighborhoodSample, ...]
    comparison_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("comparison_sha256")
        return payload


def _finite(name: str, value: float) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise NeighborhoodVerificationError(f"{name} must be finite")
    return result


def compare_local_neighborhood(
    *,
    comparison_id: str,
    samples: Iterable[NeighborhoodSample],
    core_exclusion_mm: float = 0.0,
    max_allowed_relative_error: float = 0.05,
    min_samples: int = 3,
    denominator_floor_mpa: float = 1.0e-9,
) -> NeighborhoodComparison:
    comparison_id = str(comparison_id).strip()
    if not comparison_id:
        raise NeighborhoodVerificationError("comparison_id must be non-empty")
    exclusion = _finite("core_exclusion_mm", core_exclusion_mm)
    tolerance = _finite("max_allowed_relative_error", max_allowed_relative_error)
    floor = _finite("denominator_floor_mpa", denominator_floor_mpa)
    if exclusion < 0.0 or tolerance <= 0.0 or floor <= 0.0 or int(min_samples) < 1:
        raise NeighborhoodVerificationError("invalid neighborhood comparison policy")

    clean: list[NeighborhoodSample] = []
    for sample in samples:
        distance = _finite("distance_mm", sample.distance_mm)
        fea = _finite("fea_value_mpa", sample.fea_value_mpa)
        witness = _finite("witness_value_mpa", sample.witness_value_mpa)
        if distance < 0.0:
            raise NeighborhoodVerificationError("distance_mm must be non-negative")
        if distance >= exclusion:
            clean.append(NeighborhoodSample(distance, fea, witness))
    clean.sort(key=lambda sample: sample.distance_mm)
    if len(clean) < int(min_samples):
        raise NeighborhoodVerificationError("INSUFFICIENT_NEIGHBORHOOD_SAMPLES")
    if len({sample.distance_mm for sample in clean}) != len(clean):
        raise NeighborhoodVerificationError("NEIGHBORHOOD_DISTANCES_MUST_BE_UNIQUE")

    errors = [
        abs(sample.fea_value_mpa - sample.witness_value_mpa)
        / max(abs(sample.witness_value_mpa), floor)
        for sample in clean
    ]
    max_error = max(errors)
    mean_error = sum(errors) / len(errors)
    passed = max_error <= tolerance
    payload = {
        "schema": "AsterMaxNeighborhoodComparisonV1",
        "comparison_id": comparison_id,
        "sample_count": len(clean),
        "core_exclusion_mm": exclusion,
        "max_allowed_relative_error": tolerance,
        "max_relative_error": max_error,
        "mean_relative_error": mean_error,
        "passed": passed,
        "method": "SPATIAL_SCALAR_PROFILE_RELATIVE_ERROR_WITH_DECLARED_CORE_EXCLUSION",
        "samples": tuple(clean),
    }
    return NeighborhoodComparison(**payload, comparison_sha256=canonical_sha256(asdict_payload(payload)))


def asdict_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["samples"] = [asdict(sample) for sample in payload["samples"]]
    return result


def neighborhood_comparison_evidence(comparison: NeighborhoodComparison) -> EvidenceRecord:
    status = EvidenceStatus.VERIFIED if comparison.passed else EvidenceStatus.CONTRADICTED
    return EvidenceRecord(
        evidence_id=f"NEIGHBORHOOD:{comparison.comparison_id}:{comparison.comparison_sha256[:16]}",
        kind="LOCAL_NEIGHBORHOOD_COMPARISON",
        status=status,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Local FEA-to-witness spatial neighborhood comparison under explicit error tolerance and core exclusion."
        ),
        payload_sha256=comparison.comparison_sha256,
        metadata=comparison.canonical_without_hash(),
    )
