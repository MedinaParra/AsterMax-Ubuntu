from __future__ import annotations

import pytest

from astermax.credibility import EvidenceRecord, EvidenceSource, EvidenceStatus
from astermax.fea.analytical_comparison import compare_scalar_qoi, scalar_qoi_comparison_evidence
from astermax.fea.far_field_corroboration import (
    FarFieldCorroborationError,
    analytical_fea_corroboration_chain,
)


def _record(evidence_id: str, kind: str, source: EvidenceSource, sha: str, metadata: dict) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        kind=kind,
        status=EvidenceStatus.VERIFIED,
        source=source,
        description="test evidence",
        payload_sha256=sha,
        metadata=metadata,
    )


def _parents():
    witness_sha = "a" * 64
    fea_sha = "b" * 64
    section_chain = _record(
        "CHAIN", "ANALYTICAL_SECTION_CHAIN", EvidenceSource.DETERMINISTIC_CHECK, "c" * 64,
        {"witness_payload_sha256": witness_sha},
    )
    witness = _record(
        "WITNESS", "ANALYTICAL_SECTION_WITNESS", EvidenceSource.ANALYTICAL_WITNESS, witness_sha,
        {"selection_id": "S"},
    )
    fea = _record(
        "FEA", "FEA_FAR_FIELD_STRESS_TENSOR", EvidenceSource.DETERMINISTIC_CHECK, fea_sha,
        {"mesh_sha256": "d" * 64},
    )
    uniformity = _record(
        "UNIFORM", "FEA_FAR_FIELD_UNIFORMITY", EvidenceSource.DETERMINISTIC_CHECK, "e" * 64,
        {"fea_evidence_sha256": fea_sha},
    )
    comparison = scalar_qoi_comparison_evidence(compare_scalar_qoi(
        qoi_id="SIGMA_X_MEAN",
        units="MPa",
        analytical_evidence_sha256=witness_sha,
        fea_evidence_sha256=fea_sha,
        analytical_value=10.0,
        fea_value=10.01,
        max_absolute_error=1.0,
        max_relative_error=0.02,
    ))
    return section_chain, witness, fea, uniformity, comparison


def test_valid_hash_bound_chain_is_verified():
    section_chain, witness, fea, uniformity, comparison = _parents()
    chain = analytical_fea_corroboration_chain(
        analytical_section_chain=section_chain,
        analytical_witness=witness,
        fea_far_field=fea,
        uniformity=uniformity,
        comparisons=(comparison,),
        required_qoi_ids=("SIGMA_X_MEAN",),
    )
    assert chain.status is EvidenceStatus.VERIFIED
    assert chain.kind == "ANALYTICAL_FEA_CORROBORATION_CHAIN"


def test_comparison_for_other_fea_payload_is_rejected():
    section_chain, witness, fea, uniformity, _ = _parents()
    wrong = scalar_qoi_comparison_evidence(compare_scalar_qoi(
        qoi_id="SIGMA_X_MEAN", units="MPa",
        analytical_evidence_sha256=witness.payload_sha256,
        fea_evidence_sha256="f" * 64,
        analytical_value=10.0, fea_value=10.0,
        max_absolute_error=1.0, max_relative_error=0.02,
    ))
    with pytest.raises(FarFieldCorroborationError, match="QOI_FEA_SHA_MISMATCH"):
        analytical_fea_corroboration_chain(
            analytical_section_chain=section_chain, analytical_witness=witness,
            fea_far_field=fea, uniformity=uniformity, comparisons=(wrong,),
            required_qoi_ids=("SIGMA_X_MEAN",),
        )


def test_missing_declared_qoi_is_rejected():
    section_chain, witness, fea, uniformity, comparison = _parents()
    with pytest.raises(FarFieldCorroborationError, match="QOI_SET_MISMATCH"):
        analytical_fea_corroboration_chain(
            analytical_section_chain=section_chain, analytical_witness=witness,
            fea_far_field=fea, uniformity=uniformity, comparisons=(comparison,),
            required_qoi_ids=("SIGMA_X_MEAN", "VON_MISES_MEAN"),
        )


def test_failed_qoi_comparison_cannot_enter_chain():
    section_chain, witness, fea, uniformity, _ = _parents()
    failed = scalar_qoi_comparison_evidence(compare_scalar_qoi(
        qoi_id="SIGMA_X_MEAN", units="MPa",
        analytical_evidence_sha256=witness.payload_sha256,
        fea_evidence_sha256=fea.payload_sha256,
        analytical_value=10.0, fea_value=12.0,
        max_absolute_error=0.1, max_relative_error=0.01,
    ))
    assert failed.status is EvidenceStatus.CONTRADICTED
    with pytest.raises(FarFieldCorroborationError, match="QOI_COMPARISON_NOT_CLAIM_GRADE"):
        analytical_fea_corroboration_chain(
            analytical_section_chain=section_chain, analytical_witness=witness,
            fea_far_field=fea, uniformity=uniformity, comparisons=(failed,),
            required_qoi_ids=("SIGMA_X_MEAN",),
        )
