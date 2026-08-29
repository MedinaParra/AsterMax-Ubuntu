from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import re
from typing import Any, Iterable

from astermax.credibility import (
    ClaimDefinition,
    ClaimRequirement,
    EvidenceRecord,
    EvidenceSource,
    EvidenceStatus,
    canonical_sha256,
)
from .shaft_shoulder import ShaftShoulderGeometry
from .stress_concentration_source import StressConcentrationSource


class StressConcentrationApplicabilityError(ValueError):
    pass


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class StressConcentrationApplicabilityDomain:
    schema: str
    domain_id: str
    source_provenance_sha256: str
    load_mode: str
    allowed_diameter_ratios: tuple[float, ...]
    diameter_ratio_absolute_tolerance: float
    radius_ratio_min: float
    radius_ratio_max: float
    interpolation_policy: str
    source_locator: str
    domain_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("domain_sha256")
        return payload


@dataclass(frozen=True)
class StressConcentrationApplicabilityAssessment:
    schema: str
    domain_sha256: str
    source_provenance_sha256: str
    geometry_sha256: str
    requested_load_mode: str
    actual_diameter_ratio: float
    actual_radius_ratio: float
    matched_diameter_ratio: float | None
    diameter_ratio_match: bool
    radius_ratio_within_bounds: bool
    load_mode_match: bool
    applicable: bool
    classification: str
    blockers: tuple[str, ...]
    assessment_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("assessment_sha256")
        return payload


def _positive(name: str, value: float) -> float:
    x = float(value)
    if not math.isfinite(x) or x <= 0.0:
        raise StressConcentrationApplicabilityError(f"{name} must be finite and positive")
    return x


def build_stress_concentration_applicability_domain(
    *,
    domain_id: str,
    source_provenance_sha256: str,
    load_mode: str,
    allowed_diameter_ratios: Iterable[float],
    radius_ratio_min: float,
    radius_ratio_max: float,
    source_locator: str,
    diameter_ratio_absolute_tolerance: float = 1.0e-6,
    interpolation_policy: str = "EXACT_DECLARED_DIAMETER_RATIO_ONLY_NO_EXTRAPOLATION",
) -> StressConcentrationApplicabilityDomain:
    """Declare an empirical source domain without granting interpolation/extrapolation.

    `diameter_ratio_absolute_tolerance` resolves floating-point/CAD import identity
    around one explicitly published D/d curve. It is not an empirical interpolation
    band and must stay tiny relative to spacing between declared source curves.
    """
    clean_id = str(domain_id).strip()
    clean_sha = str(source_provenance_sha256).strip().lower()
    clean_mode = str(load_mode).strip().upper()
    clean_locator = str(source_locator).strip()
    clean_policy = str(interpolation_policy).strip().upper()
    if not clean_id or not clean_mode or not clean_locator or not clean_policy:
        raise StressConcentrationApplicabilityError("domain identifiers must be non-empty")
    if not _SHA256_RE.fullmatch(clean_sha):
        raise StressConcentrationApplicabilityError("source_provenance_sha256 must be SHA-256")

    ratios = tuple(float(v) for v in allowed_diameter_ratios)
    if not ratios or any(not math.isfinite(v) or v <= 1.0 for v in ratios):
        raise StressConcentrationApplicabilityError("allowed_diameter_ratios must be finite and > 1")
    if tuple(sorted(set(ratios))) != ratios:
        raise StressConcentrationApplicabilityError("allowed_diameter_ratios must be strictly increasing and unique")

    r_min = _positive("radius_ratio_min", radius_ratio_min)
    r_max = _positive("radius_ratio_max", radius_ratio_max)
    tol = _positive("diameter_ratio_absolute_tolerance", diameter_ratio_absolute_tolerance)
    if r_max < r_min:
        raise StressConcentrationApplicabilityError("radius_ratio_max must be >= radius_ratio_min")
    if tol >= 1.0e-3:
        raise StressConcentrationApplicabilityError("diameter_ratio_absolute_tolerance is too large for identity matching")

    payload = {
        "schema": "AsterMaxStressConcentrationApplicabilityDomainV1",
        "domain_id": clean_id,
        "source_provenance_sha256": clean_sha,
        "load_mode": clean_mode,
        "allowed_diameter_ratios": ratios,
        "diameter_ratio_absolute_tolerance": tol,
        "radius_ratio_min": r_min,
        "radius_ratio_max": r_max,
        "interpolation_policy": clean_policy,
        "source_locator": clean_locator,
    }
    return StressConcentrationApplicabilityDomain(
        **payload,
        domain_sha256=canonical_sha256(payload),
    )


def assess_stress_concentration_applicability(
    source: StressConcentrationSource,
    domain: StressConcentrationApplicabilityDomain,
    geometry: ShaftShoulderGeometry,
    *,
    requested_load_mode: str,
) -> StressConcentrationApplicabilityAssessment:
    if domain.source_provenance_sha256 != source.provenance_sha256:
        raise StressConcentrationApplicabilityError("SCF_DOMAIN_SOURCE_PROVENANCE_MISMATCH")

    requested = str(requested_load_mode).strip().upper()
    if not requested:
        raise StressConcentrationApplicabilityError("requested_load_mode must be non-empty")

    d_ratio = float(geometry.diameter_ratio)
    r_ratio = float(geometry.radius_ratio)
    candidates = [
        value
        for value in domain.allowed_diameter_ratios
        if abs(d_ratio - value) <= domain.diameter_ratio_absolute_tolerance
    ]
    diameter_match = len(candidates) == 1
    matched = float(candidates[0]) if diameter_match else None
    radius_ok = domain.radius_ratio_min <= r_ratio <= domain.radius_ratio_max
    load_ok = requested == domain.load_mode

    blockers: list[str] = []
    if not load_ok:
        blockers.append("LOAD_MODE_OUTSIDE_EMPIRICAL_DOMAIN")
    if not diameter_match:
        blockers.append("DIAMETER_RATIO_OUTSIDE_EMPIRICAL_DOMAIN")
    if not radius_ok:
        blockers.append("RADIUS_RATIO_OUTSIDE_EMPIRICAL_DOMAIN")

    applicable = not blockers
    classification = "APPLICABLE" if applicable else "OUTSIDE_EMPIRICAL_DOMAIN"
    payload = {
        "schema": "AsterMaxStressConcentrationApplicabilityAssessmentV1",
        "domain_sha256": domain.domain_sha256,
        "source_provenance_sha256": source.provenance_sha256,
        "geometry_sha256": geometry.geometry_sha256,
        "requested_load_mode": requested,
        "actual_diameter_ratio": d_ratio,
        "actual_radius_ratio": r_ratio,
        "matched_diameter_ratio": matched,
        "diameter_ratio_match": diameter_match,
        "radius_ratio_within_bounds": radius_ok,
        "load_mode_match": load_ok,
        "applicable": applicable,
        "classification": classification,
        "blockers": tuple(blockers),
    }
    return StressConcentrationApplicabilityAssessment(
        **payload,
        assessment_sha256=canonical_sha256(payload),
    )


def applicability_domain_evidence(domain: StressConcentrationApplicabilityDomain) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"SCF_DOMAIN:{domain.domain_id}",
        kind="STRESS_CONCENTRATION_APPLICABILITY_DOMAIN",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description="Hash-bound empirical stress-concentration applicability domain; no extrapolation permitted.",
        payload_sha256=domain.domain_sha256,
        metadata=domain.canonical_without_hash(),
    )


def applicability_assessment_evidence(
    assessment: StressConcentrationApplicabilityAssessment,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"SCF_APPLICABILITY:{assessment.assessment_sha256[:16]}",
        kind="STRESS_CONCENTRATION_DOMAIN_APPLICABILITY",
        status=EvidenceStatus.VERIFIED if assessment.applicable else EvidenceStatus.CONTRADICTED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Empirical stress-concentration source domain is applicable to the exact hashed geometry and load mode."
            if assessment.applicable
            else "Exact hashed geometry/load mode lies outside the declared empirical source domain; extrapolation is blocked."
        ),
        payload_sha256=assessment.assessment_sha256,
        metadata=assessment.canonical_without_hash(),
    )


def empirical_kt_source_applicability_claim(context_id: str) -> ClaimDefinition:
    return ClaimDefinition(
        claim_id="CLAIM_EMPIRICAL_KT_SOURCE_APPLICABLE",
        context_id=context_id,
        statement=(
            "The declared empirical stress-concentration source domain is applicable to the exact shaft-shoulder geometry and load mode."
        ),
        requirements=(
            ClaimRequirement(
                "STRESS_CONCENTRATION_SOURCE_PROVENANCE",
                allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,),
            ),
            ClaimRequirement(
                "SHAFT_SHOULDER_GEOMETRY",
                allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,),
            ),
            ClaimRequirement(
                "STRESS_CONCENTRATION_APPLICABILITY_DOMAIN",
                allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,),
            ),
            ClaimRequirement(
                "STRESS_CONCENTRATION_DOMAIN_APPLICABILITY",
                allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,),
            ),
        ),
    )
