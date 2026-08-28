from __future__ import annotations

import re

from astermax.credibility import (
    ClaimDefinition,
    ClaimRequirement,
    EvidenceRecord,
    EvidenceSource,
    EvidenceStatus,
    canonical_sha256,
)
from .neighborhood_verification import NeighborhoodComparison
from .singularity_diagnostic import SingularityDiagnostic


class LocalCorroborationError(ValueError):
    pass


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def local_neighborhood_binding_evidence(
    *,
    binding_id: str,
    comparison: NeighborhoodComparison,
    witness_evidence: EvidenceRecord,
    fea_result_sha256: str,
) -> EvidenceRecord:
    binding_id = str(binding_id).strip()
    fea_sha = str(fea_result_sha256).lower().strip()
    if not binding_id:
        raise LocalCorroborationError("binding_id must be non-empty")
    if not _SHA256_RE.fullmatch(fea_sha):
        raise LocalCorroborationError("fea_result_sha256 must be a lowercase SHA-256 digest")
    if witness_evidence.kind not in {"STRESS_CONCENTRATION_WITNESS", "KIRSCH_HOLE_WITNESS"}:
        raise LocalCorroborationError("unsupported local analytical witness kind")
    if not witness_evidence.claim_grade or witness_evidence.payload_sha256 is None:
        raise LocalCorroborationError("local analytical witness must be claim-grade and hash-bound")

    payload = {
        "schema": "AsterMaxLocalNeighborhoodBindingV1",
        "binding_id": binding_id,
        "comparison_sha256": comparison.comparison_sha256,
        "witness_evidence_id": witness_evidence.evidence_id,
        "witness_payload_sha256": witness_evidence.payload_sha256,
        "fea_result_sha256": fea_sha,
        "comparison_passed": comparison.passed,
        "core_exclusion_mm": comparison.core_exclusion_mm,
        "max_relative_error": comparison.max_relative_error,
        "max_allowed_relative_error": comparison.max_allowed_relative_error,
    }
    digest = canonical_sha256(payload)
    return EvidenceRecord(
        evidence_id=f"LOCAL_BINDING:{binding_id}:{digest[:16]}",
        kind="LOCAL_NEIGHBORHOOD_BINDING",
        status=EvidenceStatus.VERIFIED if comparison.passed else EvidenceStatus.CONTRADICTED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Exact binding of one FEA result hash, one independent analytical/empirical witness and one spatial neighborhood comparison."
        ),
        payload_sha256=digest,
        metadata=payload,
    )


def local_peak_convergence_evidence(diagnostic: SingularityDiagnostic) -> EvidenceRecord:
    if diagnostic.classification == "LOCALLY_CONVERGED_FIELD":
        status = EvidenceStatus.VERIFIED
    elif diagnostic.classification == "LIKELY_SINGULARITY":
        status = EvidenceStatus.OUT_OF_DOMAIN
    else:
        status = EvidenceStatus.NOT_ASSESSED
    return EvidenceRecord(
        evidence_id=f"LOCAL_PEAK:{diagnostic.diagnostic_id}:{diagnostic.diagnostic_sha256[:16]}",
        kind="LOCAL_PEAK_CONVERGENCE",
        status=status,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Claim gate for interpreting the local FEA peak as mesh-stable. A likely singularity is explicitly out of domain for a finite peak claim."
        ),
        payload_sha256=diagnostic.diagnostic_sha256,
        metadata={
            "diagnostic_sha256": diagnostic.diagnostic_sha256,
            "classification": diagnostic.classification,
            "peak_last_change": diagnostic.peak_last_change,
            "neighborhood_last_change": diagnostic.neighborhood_last_change,
        },
    )


def empirical_local_neighborhood_claim(context_id: str) -> ClaimDefinition:
    return ClaimDefinition(
        claim_id="CLAIM_EMPIRICAL_LOCAL_NEIGHBORHOOD_CORROBORATED",
        context_id=context_id,
        statement=(
            "For the declared shaft-shoulder geometry and bounded empirical stress-concentration datasets, "
            "the local FEA neighborhood agrees with the exact hash-bound witness within the declared tolerance."
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
                "STRESS_CONCENTRATION_DATASET",
                min_count=2,
                allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,),
            ),
            ClaimRequirement(
                "STRESS_CONCENTRATION_WITNESS",
                allowed_sources=(EvidenceSource.ANALYTICAL_WITNESS,),
            ),
            ClaimRequirement(
                "LOCAL_NEIGHBORHOOD_BINDING",
                allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,),
            ),
        ),
    )


def local_peak_reliability_claim(context_id: str) -> ClaimDefinition:
    return ClaimDefinition(
        claim_id="CLAIM_LOCAL_FEA_PEAK_MESH_STABLE",
        context_id=context_id,
        statement=(
            "The local FEA peak is mesh-stable under the declared refinement diagnostic and may be reported as a finite local peak for this verification context."
        ),
        requirements=(
            ClaimRequirement(
                "LOCAL_PEAK_CONVERGENCE",
                allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,),
            ),
        ),
    )
