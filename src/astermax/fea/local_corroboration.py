from __future__ import annotations

import re
from typing import Iterable

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
            "Exact binding of one result hash, one independent analytical/empirical witness "
            "and one spatial neighborhood comparison."
        ),
        payload_sha256=digest,
        metadata=payload,
    )


def synthetic_dataset_authorization_evidence(
    source_evidence: EvidenceRecord,
    dataset_evidence: EvidenceRecord,
) -> EvidenceRecord:
    """Authorize only explicitly synthetic software-verification SCF data.

    Published/copyrighted empirical data intentionally has no deterministic
    authorization path here. Such a dataset must later enter through an explicit
    document/human authorization record with exact source locator and rights basis.
    """
    if (
        source_evidence.kind != "STRESS_CONCENTRATION_SOURCE_PROVENANCE"
        or source_evidence.source is not EvidenceSource.DETERMINISTIC_CHECK
        or not source_evidence.claim_grade
        or source_evidence.payload_sha256 is None
    ):
        raise LocalCorroborationError("INVALID_STRESS_CONCENTRATION_SOURCE_EVIDENCE")
    if (
        dataset_evidence.kind != "STRESS_CONCENTRATION_DATASET"
        or dataset_evidence.source is not EvidenceSource.DETERMINISTIC_CHECK
        or not dataset_evidence.claim_grade
        or dataset_evidence.payload_sha256 is None
    ):
        raise LocalCorroborationError("INVALID_STRESS_CONCENTRATION_DATASET_EVIDENCE")

    rights_note = str(source_evidence.metadata.get("rights_note", ""))
    if "SYNTHETIC_SOFTWARE_VERIFICATION_DATA" not in rights_note:
        raise LocalCorroborationError("PUBLISHED_EMPIRICAL_DATA_REQUIRES_EXPLICIT_AUTHORIZATION")
    dataset_source_sha = str(dataset_evidence.metadata.get("source_provenance_sha256", ""))
    if dataset_source_sha != source_evidence.payload_sha256:
        raise LocalCorroborationError("DATASET_SOURCE_PROVENANCE_MISMATCH")

    payload = {
        "schema": "AsterMaxSyntheticSCFDatasetAuthorizationV1",
        "classification": "SYNTHETIC_SOFTWARE_VERIFICATION_DATA",
        "source_evidence_id": source_evidence.evidence_id,
        "source_provenance_sha256": source_evidence.payload_sha256,
        "dataset_evidence_id": dataset_evidence.evidence_id,
        "dataset_sha256": dataset_evidence.payload_sha256,
        "authorization_basis": "EXPLICIT_SYNTHETIC_VERIFICATION_RIGHTS_NOTE",
    }
    digest = canonical_sha256(payload)
    return EvidenceRecord(
        evidence_id=f"SCF_AUTH:{dataset_evidence.evidence_id}:{digest[:12]}",
        kind="STRESS_CONCENTRATION_DATASET_AUTHORIZATION",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Authorization binding for explicitly synthetic software-verification stress-concentration data only."
        ),
        payload_sha256=digest,
        metadata=payload,
    )


def empirical_local_chain_evidence(
    *,
    chain_id: str,
    source_evidence: EvidenceRecord,
    geometry_evidence: EvidenceRecord,
    dataset_evidences: Iterable[EvidenceRecord],
    authorization_evidences: Iterable[EvidenceRecord],
    witness_evidence: EvidenceRecord,
    binding_evidence: EvidenceRecord,
) -> EvidenceRecord:
    """Prove exact source→datasets→geometry→witness→local-result binding.

    Categorical ClaimEngine requirements alone cannot prove that otherwise valid
    records belong to the same calculation. This deterministic chain closes that
    cross-mixing failure mode.
    """
    chain_id = str(chain_id).strip()
    if not chain_id:
        raise LocalCorroborationError("chain_id must be non-empty")
    if (
        source_evidence.kind != "STRESS_CONCENTRATION_SOURCE_PROVENANCE"
        or not source_evidence.claim_grade
        or source_evidence.payload_sha256 is None
    ):
        raise LocalCorroborationError("EMPIRICAL_CHAIN_INVALID_SOURCE")
    if (
        geometry_evidence.kind != "SHAFT_SHOULDER_GEOMETRY"
        or not geometry_evidence.claim_grade
        or geometry_evidence.payload_sha256 is None
    ):
        raise LocalCorroborationError("EMPIRICAL_CHAIN_INVALID_GEOMETRY")
    datasets = tuple(dataset_evidences)
    if len(datasets) != 2:
        raise LocalCorroborationError("EMPIRICAL_CHAIN_REQUIRES_EXACTLY_TWO_DATASETS")
    if any(
        record.kind != "STRESS_CONCENTRATION_DATASET"
        or not record.claim_grade
        or record.payload_sha256 is None
        for record in datasets
    ):
        raise LocalCorroborationError("EMPIRICAL_CHAIN_INVALID_DATASET")
    if len({record.payload_sha256 for record in datasets}) != 2:
        raise LocalCorroborationError("EMPIRICAL_CHAIN_DATASETS_MUST_BE_DISTINCT")
    if any(
        str(record.metadata.get("source_provenance_sha256", ""))
        != source_evidence.payload_sha256
        for record in datasets
    ):
        raise LocalCorroborationError("EMPIRICAL_CHAIN_DATASET_SOURCE_MISMATCH")

    authorizations = tuple(authorization_evidences)
    if len(authorizations) != 2 or any(
        record.kind != "STRESS_CONCENTRATION_DATASET_AUTHORIZATION"
        or not record.claim_grade
        or record.payload_sha256 is None
        for record in authorizations
    ):
        raise LocalCorroborationError("EMPIRICAL_CHAIN_REQUIRES_TWO_DATASET_AUTHORIZATIONS")
    authorized_dataset_hashes = {
        str(record.metadata.get("dataset_sha256", "")) for record in authorizations
    }
    dataset_hashes = {str(record.payload_sha256) for record in datasets}
    if authorized_dataset_hashes != dataset_hashes:
        raise LocalCorroborationError("EMPIRICAL_CHAIN_DATASET_AUTHORIZATION_MISMATCH")
    if any(
        str(record.metadata.get("source_provenance_sha256", ""))
        != source_evidence.payload_sha256
        for record in authorizations
    ):
        raise LocalCorroborationError("EMPIRICAL_CHAIN_AUTHORIZATION_SOURCE_MISMATCH")

    if (
        witness_evidence.kind != "STRESS_CONCENTRATION_WITNESS"
        or witness_evidence.source is not EvidenceSource.ANALYTICAL_WITNESS
        or not witness_evidence.claim_grade
        or witness_evidence.payload_sha256 is None
    ):
        raise LocalCorroborationError("EMPIRICAL_CHAIN_INVALID_WITNESS")
    if str(witness_evidence.metadata.get("geometry_sha256", "")) != geometry_evidence.payload_sha256:
        raise LocalCorroborationError("EMPIRICAL_CHAIN_WITNESS_GEOMETRY_MISMATCH")
    witness_dataset_hashes = {
        str(witness_evidence.metadata.get("bending_dataset_sha256", "")),
        str(witness_evidence.metadata.get("torsion_dataset_sha256", "")),
    }
    if witness_dataset_hashes != dataset_hashes:
        raise LocalCorroborationError("EMPIRICAL_CHAIN_WITNESS_DATASET_MISMATCH")

    if (
        binding_evidence.kind != "LOCAL_NEIGHBORHOOD_BINDING"
        or not binding_evidence.claim_grade
        or binding_evidence.payload_sha256 is None
    ):
        raise LocalCorroborationError("EMPIRICAL_CHAIN_INVALID_LOCAL_BINDING")
    if (
        str(binding_evidence.metadata.get("witness_payload_sha256", ""))
        != witness_evidence.payload_sha256
    ):
        raise LocalCorroborationError("EMPIRICAL_CHAIN_LOCAL_BINDING_WITNESS_MISMATCH")

    payload = {
        "schema": "AsterMaxEmpiricalLocalEvidenceChainV1",
        "chain_id": chain_id,
        "source_provenance_sha256": source_evidence.payload_sha256,
        "geometry_sha256": geometry_evidence.payload_sha256,
        "dataset_sha256s": sorted(dataset_hashes),
        "authorization_sha256s": sorted(
            str(record.payload_sha256) for record in authorizations
        ),
        "witness_sha256": witness_evidence.payload_sha256,
        "local_binding_sha256": binding_evidence.payload_sha256,
        "result_sha256": str(binding_evidence.metadata.get("fea_result_sha256", "")),
    }
    digest = canonical_sha256(payload)
    return EvidenceRecord(
        evidence_id=f"LOCAL_EMPIRICAL_CHAIN:{chain_id}:{digest[:16]}",
        kind="LOCAL_EMPIRICAL_CHAIN",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Deterministic binding of exact source provenance, authorized datasets, shaft geometry, notch witness and local result comparison."
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
            "For the declared shaft-shoulder geometry and explicitly authorized bounded empirical "
            "stress-concentration datasets, the local result neighborhood agrees with the exact "
            "hash-bound witness within the declared tolerance."
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
                "STRESS_CONCENTRATION_DATASET_AUTHORIZATION",
                min_count=2,
                allowed_sources=(
                    EvidenceSource.DETERMINISTIC_CHECK,
                    EvidenceSource.DOCUMENT,
                    EvidenceSource.HUMAN_CONFIRMED,
                ),
            ),
            ClaimRequirement(
                "STRESS_CONCENTRATION_WITNESS",
                allowed_sources=(EvidenceSource.ANALYTICAL_WITNESS,),
            ),
            ClaimRequirement(
                "LOCAL_NEIGHBORHOOD_BINDING",
                allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,),
            ),
            ClaimRequirement(
                "LOCAL_EMPIRICAL_CHAIN",
                allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,),
            ),
        ),
    )


def analytical_local_neighborhood_claim(context_id: str) -> ClaimDefinition:
    return ClaimDefinition(
        claim_id="CLAIM_ANALYTICAL_LOCAL_NEIGHBORHOOD_CORROBORATED",
        context_id=context_id,
        statement=(
            "For the declared analytical verification witness, the hash-bound local result neighborhood "
            "agrees with the independent field within the declared tolerance."
        ),
        requirements=(
            ClaimRequirement(
                "KIRSCH_HOLE_WITNESS",
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
