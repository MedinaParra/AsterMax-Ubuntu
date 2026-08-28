from __future__ import annotations

from astermax.credibility import (
    ClaimDefinition,
    ClaimRequirement,
    EvidenceRecord,
    EvidenceSource,
    EvidenceStatus,
    canonical_sha256,
)
from .analytical_load_case import AnalyticalLoadCase
from .analytical_witness import LinearNormalStressWitness
from .circular_section import CircularSectionApplicability
from .circular_torsion import CircularTorsionWitness
from .stress_envelope import CircularCombinedStressEnvelope


class CombinedEvidenceError(ValueError):
    pass


def analytical_load_case_evidence(load_case: AnalyticalLoadCase) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"ANALYTICAL_LOAD_CASE:{load_case.load_case_id}",
        kind="ANALYTICAL_LOAD_CASE",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description="Immutable analytical section load case bound to one exact section hash.",
        payload_sha256=load_case.load_case_sha256,
        metadata={
            "load_case_id": load_case.load_case_id,
            "selection_id": load_case.selection_id,
            "section_sha256": load_case.section_sha256,
            "axial_force_n": load_case.axial_force_n,
            "moment_u_nmm": load_case.moment_u_nmm,
            "moment_v_nmm": load_case.moment_v_nmm,
            "torque_nmm": load_case.torque_nmm,
        },
    )


def combined_envelope_evidence(envelope: CircularCombinedStressEnvelope) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"COMBINED_ENVELOPE:{envelope.selection_id}:{envelope.envelope_sha256[:16]}",
        kind="ANALYTICAL_COMBINED_ENVELOPE",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.ANALYTICAL_WITNESS,
        description="Exact circular-section axial/biaxial-bending/torsion von Mises envelope.",
        payload_sha256=envelope.envelope_sha256,
        metadata={
            "selection_id": envelope.selection_id,
            "section_sha256": envelope.section_sha256,
            "critical_u_mm": envelope.critical_u_mm,
            "critical_v_mm": envelope.critical_v_mm,
            "max_von_mises_mpa": envelope.max_von_mises_mpa,
            "method": envelope.method,
        },
    )


def combined_analytical_chain_evidence(
    load_case: AnalyticalLoadCase,
    applicability: CircularSectionApplicability,
    normal: LinearNormalStressWitness,
    torsion: CircularTorsionWitness,
    envelope: CircularCombinedStressEnvelope,
) -> EvidenceRecord:
    selection_ids = {
        load_case.selection_id,
        applicability.selection_id,
        normal.selection_id,
        torsion.selection_id,
        envelope.selection_id,
    }
    if len(selection_ids) != 1:
        raise CombinedEvidenceError("COMBINED_CHAIN_SELECTION_MISMATCH")
    section_hashes = {
        load_case.section_sha256,
        applicability.section_sha256,
        normal.section_sha256,
        torsion.section_sha256,
        envelope.section_sha256,
    }
    if len(section_hashes) != 1:
        raise CombinedEvidenceError("COMBINED_CHAIN_SECTION_SHA_MISMATCH")
    if torsion.applicability_sha256 != applicability.applicability_sha256:
        raise CombinedEvidenceError("COMBINED_CHAIN_APPLICABILITY_SHA_MISMATCH")

    payload = {
        "schema": "AsterMaxCombinedAnalyticalChainV1",
        "selection_id": load_case.selection_id,
        "section_sha256": load_case.section_sha256,
        "load_case_sha256": load_case.load_case_sha256,
        "applicability_sha256": applicability.applicability_sha256,
        "normal_witness_sha256": normal.witness_sha256,
        "torsion_witness_sha256": torsion.witness_sha256,
        "envelope_sha256": envelope.envelope_sha256,
    }
    digest = canonical_sha256(payload)
    return EvidenceRecord(
        evidence_id=f"COMBINED_CHAIN:{load_case.load_case_id}:{digest[:16]}",
        kind="ANALYTICAL_COMBINED_CHAIN",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description="Deterministic hash binding of one section, load case and all combined analytical witnesses.",
        payload_sha256=digest,
        metadata=payload,
    )


def combined_analytical_claim(context_id: str) -> ClaimDefinition:
    return ClaimDefinition(
        claim_id="CLAIM_CIRCULAR_SECTION_COMBINED_STRESS_RECONSTRUCTED",
        context_id=context_id,
        statement=(
            "For the exact declared solid circular CAD section and immutable load case, "
            "axial force, biaxial bending and torque have compatible independent analytical witnesses "
            "and an exact combined von Mises envelope."
        ),
        requirements=(
            ClaimRequirement("CAD_SECTION_PROPERTIES", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
            ClaimRequirement("CIRCULAR_SECTION_APPLICABILITY", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
            ClaimRequirement("ANALYTICAL_LOAD_CASE", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
            ClaimRequirement("ANALYTICAL_SECTION_WITNESS", allowed_sources=(EvidenceSource.ANALYTICAL_WITNESS,)),
            ClaimRequirement("ANALYTICAL_TORSION_WITNESS", allowed_sources=(EvidenceSource.ANALYTICAL_WITNESS,)),
            ClaimRequirement("ANALYTICAL_COMBINED_ENVELOPE", allowed_sources=(EvidenceSource.ANALYTICAL_WITNESS,)),
            ClaimRequirement("ANALYTICAL_COMBINED_CHAIN", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
        ),
    )
