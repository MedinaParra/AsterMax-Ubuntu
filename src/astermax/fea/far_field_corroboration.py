from __future__ import annotations

from typing import Iterable

from astermax.credibility import (
    ClaimDefinition,
    ClaimRequirement,
    EvidenceRecord,
    EvidenceSource,
    EvidenceStatus,
    canonical_sha256,
)
from .curved_far_field_stress import CurvedFarFieldStressTensor


class FarFieldCorroborationError(ValueError):
    pass


def far_field_uniformity_evidence(
    result: CurvedFarFieldStressTensor,
    *,
    reference_stress_mpa: float,
    max_sigma_x_std_over_reference: float = 0.05,
) -> EvidenceRecord:
    reference = abs(float(reference_stress_mpa))
    limit = float(max_sigma_x_std_over_reference)
    if reference <= 0.0 or limit <= 0.0:
        raise FarFieldCorroborationError("FAR_FIELD_UNIFORMITY_REFERENCE_AND_LIMIT_MUST_BE_POSITIVE")
    ratio = abs(float(result.weighted_std_stress_mpa[0])) / reference
    passed = ratio <= limit
    payload = {
        "schema": "AsterMaxFarFieldUniformityAssessmentV1",
        "fea_evidence_sha256": result.evidence_sha256,
        "reference_stress_mpa": reference,
        "sigma_x_weighted_std_mpa": result.weighted_std_stress_mpa[0],
        "sigma_x_std_over_reference": ratio,
        "max_sigma_x_std_over_reference": limit,
        "passed": passed,
    }
    payload_sha = canonical_sha256(payload)
    return EvidenceRecord(
        evidence_id=f"FEA_FAR_FIELD_UNIFORMITY:{payload_sha[:16]}",
        kind="FEA_FAR_FIELD_UNIFORMITY",
        status=EvidenceStatus.VERIFIED if passed else EvidenceStatus.CONTRADICTED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description="Weighted sigma_x variation in the declared far-field region is checked against the analytical stress scale.",
        payload_sha256=payload_sha,
        metadata=payload,
    )


def analytical_fea_corroboration_chain(
    *,
    analytical_section_chain: EvidenceRecord,
    analytical_witness: EvidenceRecord,
    fea_far_field: EvidenceRecord,
    uniformity: EvidenceRecord,
    comparisons: Iterable[EvidenceRecord],
    required_qoi_ids: Iterable[str],
) -> EvidenceRecord:
    comparisons_tuple = tuple(comparisons)
    required = tuple(str(q).strip() for q in required_qoi_ids)
    if not required or any(not q for q in required) or len(set(required)) != len(required):
        raise FarFieldCorroborationError("REQUIRED_QOI_IDS_INVALID")
    if analytical_section_chain.kind != "ANALYTICAL_SECTION_CHAIN" or not analytical_section_chain.claim_grade:
        raise FarFieldCorroborationError("ANALYTICAL_SECTION_CHAIN_NOT_CLAIM_GRADE")
    if analytical_witness.kind != "ANALYTICAL_SECTION_WITNESS" or not analytical_witness.claim_grade:
        raise FarFieldCorroborationError("ANALYTICAL_WITNESS_NOT_CLAIM_GRADE")
    if fea_far_field.kind != "FEA_FAR_FIELD_STRESS_TENSOR" or not fea_far_field.claim_grade:
        raise FarFieldCorroborationError("FEA_FAR_FIELD_NOT_CLAIM_GRADE")
    if uniformity.kind != "FEA_FAR_FIELD_UNIFORMITY" or not uniformity.claim_grade:
        raise FarFieldCorroborationError("FEA_FAR_FIELD_UNIFORMITY_NOT_CLAIM_GRADE")
    if analytical_witness.payload_sha256 is None or fea_far_field.payload_sha256 is None:
        raise FarFieldCorroborationError("CORROBORATION_PARENT_SHA_MISSING")
    if str(analytical_section_chain.metadata.get("witness_payload_sha256", "")) != analytical_witness.payload_sha256:
        raise FarFieldCorroborationError("ANALYTICAL_SECTION_CHAIN_WITNESS_MISMATCH")
    if str(uniformity.metadata.get("fea_evidence_sha256", "")) != fea_far_field.payload_sha256:
        raise FarFieldCorroborationError("FAR_FIELD_UNIFORMITY_FEA_MISMATCH")

    by_qoi: dict[str, EvidenceRecord] = {}
    for record in comparisons_tuple:
        if record.kind != "ANALYTICAL_FEA_QOI_COMPARISON" or not record.claim_grade:
            raise FarFieldCorroborationError("QOI_COMPARISON_NOT_CLAIM_GRADE")
        qoi = str(record.metadata.get("qoi_id", ""))
        if not qoi or qoi in by_qoi:
            raise FarFieldCorroborationError("QOI_COMPARISON_ID_DUPLICATE_OR_EMPTY")
        if str(record.metadata.get("analytical_evidence_sha256", "")) != analytical_witness.payload_sha256:
            raise FarFieldCorroborationError(f"QOI_ANALYTICAL_SHA_MISMATCH:{qoi}")
        if str(record.metadata.get("fea_evidence_sha256", "")) != fea_far_field.payload_sha256:
            raise FarFieldCorroborationError(f"QOI_FEA_SHA_MISMATCH:{qoi}")
        by_qoi[qoi] = record

    if set(by_qoi) != set(required):
        missing = sorted(set(required) - set(by_qoi)); extra = sorted(set(by_qoi) - set(required))
        raise FarFieldCorroborationError(f"QOI_SET_MISMATCH:missing={missing}:extra={extra}")

    payload = {
        "schema": "AsterMaxAnalyticalFeaFarFieldCorroborationChainV1",
        "analytical_section_chain_sha256": analytical_section_chain.payload_sha256,
        "analytical_witness_sha256": analytical_witness.payload_sha256,
        "fea_far_field_sha256": fea_far_field.payload_sha256,
        "uniformity_sha256": uniformity.payload_sha256,
        "qoi_comparisons": {qoi: by_qoi[qoi].payload_sha256 for qoi in sorted(by_qoi)},
        "required_qoi_ids": sorted(required),
    }
    chain_sha = canonical_sha256(payload)
    return EvidenceRecord(
        evidence_id=f"ANALYTICAL_FEA_CHAIN:{chain_sha[:16]}",
        kind="ANALYTICAL_FEA_CORROBORATION_CHAIN",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Exact CAD analytical witness, curved-TET10 far-field tensor, uniformity gate and all declared QOI comparisons are hash-bound."
        ),
        payload_sha256=chain_sha,
        metadata=payload,
    )


def far_field_analytical_corroboration_claim(context_id: str, *, qoi_count: int) -> ClaimDefinition:
    if int(qoi_count) < 1:
        raise FarFieldCorroborationError("qoi_count must be positive")
    return ClaimDefinition(
        claim_id="CLAIM_CURVED_FEA_FAR_FIELD_ANALYTICALLY_CORROBORATED",
        context_id=context_id,
        statement=(
            "For the declared verification fixture, the converged curved-TET10 far-field stress tensor agrees with the hash-bound CAD analytical axial-stress witness within predeclared limits."
        ),
        requirements=(
            ClaimRequirement("ANALYTICAL_SECTION_CHAIN", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
            ClaimRequirement("ANALYTICAL_SECTION_WITNESS", allowed_sources=(EvidenceSource.ANALYTICAL_WITNESS,)),
            ClaimRequirement("FEA_FAR_FIELD_STRESS_TENSOR", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
            ClaimRequirement("FEA_FAR_FIELD_UNIFORMITY", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
            ClaimRequirement(
                "ANALYTICAL_FEA_QOI_COMPARISON",
                min_count=int(qoi_count),
                allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,),
            ),
            ClaimRequirement("ANALYTICAL_FEA_CORROBORATION_CHAIN", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
        ),
    )
