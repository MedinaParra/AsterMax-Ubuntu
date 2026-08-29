from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import re
from typing import Any

from astermax.credibility import (
    ClaimDefinition,
    ClaimRequirement,
    EvidenceRecord,
    EvidenceSource,
    EvidenceStatus,
    canonical_sha256,
)
from .authorized_empirical_dataset import AuthorizedStressConcentrationDataset
from .empirical_local_stress import EmpiricalLocalStressPrediction
from .shaft_shoulder import ShaftShoulderGeometry


class EmpiricalFeaCorroborationError(ValueError):
    pass


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EMPIRICAL_QOI = "SURFACE_PEAK_AXIAL_NORMAL_STRESS_MPA"


@dataclass(frozen=True)
class FeaLocalStressVerificationSummary:
    schema: str
    upstream_benchmark_sha256: str
    upstream_decision_sha256: str
    upstream_singularity_diagnostic_sha256: str
    small_diameter_mm: float
    large_diameter_mm: float
    fillet_radius_mm: float
    axial_force_n: float
    local_stress_convergence_claim: bool
    singularity_classification: str
    qoi_id: str
    qoi_location: str
    qoi_stress_measure: str
    measurement_operator: str
    nodal_recovery: bool
    surface_extrapolation: bool
    summary_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("summary_sha256")
        return payload


@dataclass(frozen=True)
class EmpiricalFeaCorroborationEligibility:
    schema: str
    empirical_prediction_sha256: str
    intake_sha256: str
    empirical_geometry_sha256: str
    fea_summary_sha256: str
    empirical_qoi_id: str
    fea_qoi_id: str
    geometry_match: bool
    axial_load_scale_match: bool
    fea_converged: bool
    fea_locally_converged_field: bool
    empirical_data_non_synthetic: bool
    qoi_compatible: bool
    eligible: bool
    classification: str
    blockers: tuple[str, ...]
    assessment_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("assessment_sha256")
        return payload


def _sha(name: str, value: str) -> str:
    clean = str(value).strip().lower()
    if not _SHA256_RE.fullmatch(clean):
        raise EmpiricalFeaCorroborationError(f"{name} must be SHA-256")
    return clean


def _positive(name: str, value: float) -> float:
    x = float(value)
    if not math.isfinite(x) or x <= 0.0:
        raise EmpiricalFeaCorroborationError(f"{name} must be finite and positive")
    return x


def _relative(a: float, b: float) -> float:
    return abs(float(a) - float(b)) / max(abs(float(a)), abs(float(b)), 1.0e-30)


def build_fea_local_stress_verification_summary(
    *,
    upstream_benchmark_sha256: str,
    upstream_decision_sha256: str,
    upstream_singularity_diagnostic_sha256: str,
    small_diameter_mm: float,
    large_diameter_mm: float,
    fillet_radius_mm: float,
    axial_force_n: float,
    local_stress_convergence_claim: bool,
    singularity_classification: str,
    qoi_id: str,
    qoi_location: str,
    qoi_stress_measure: str,
    measurement_operator: str,
    nodal_recovery: bool,
    surface_extrapolation: bool,
) -> FeaLocalStressVerificationSummary:
    payload = {
        "schema": "AsterMaxFeaLocalStressVerificationSummaryV1",
        "upstream_benchmark_sha256": _sha("upstream_benchmark_sha256", upstream_benchmark_sha256),
        "upstream_decision_sha256": _sha("upstream_decision_sha256", upstream_decision_sha256),
        "upstream_singularity_diagnostic_sha256": _sha(
            "upstream_singularity_diagnostic_sha256", upstream_singularity_diagnostic_sha256
        ),
        "small_diameter_mm": _positive("small_diameter_mm", small_diameter_mm),
        "large_diameter_mm": _positive("large_diameter_mm", large_diameter_mm),
        "fillet_radius_mm": _positive("fillet_radius_mm", fillet_radius_mm),
        "axial_force_n": _positive("axial_force_n", axial_force_n),
        "local_stress_convergence_claim": bool(local_stress_convergence_claim),
        "singularity_classification": str(singularity_classification).strip(),
        "qoi_id": str(qoi_id).strip(),
        "qoi_location": str(qoi_location).strip(),
        "qoi_stress_measure": str(qoi_stress_measure).strip(),
        "measurement_operator": str(measurement_operator).strip(),
        "nodal_recovery": bool(nodal_recovery),
        "surface_extrapolation": bool(surface_extrapolation),
    }
    if any(not payload[key] for key in (
        "singularity_classification", "qoi_id", "qoi_location", "qoi_stress_measure", "measurement_operator"
    )):
        raise EmpiricalFeaCorroborationError("FEA_LOCAL_STRESS_SUMMARY_TEXT_FIELDS_MUST_BE_NONEMPTY")
    if payload["large_diameter_mm"] <= payload["small_diameter_mm"]:
        raise EmpiricalFeaCorroborationError("FEA_LOCAL_STRESS_SUMMARY_DIAMETERS_INVALID")
    return FeaLocalStressVerificationSummary(
        **payload,
        summary_sha256=canonical_sha256(payload),
    )


def assess_empirical_fea_corroboration_eligibility(
    prediction: EmpiricalLocalStressPrediction,
    intake: AuthorizedStressConcentrationDataset,
    geometry: ShaftShoulderGeometry,
    fea: FeaLocalStressVerificationSummary,
    *,
    max_geometry_relative_mismatch: float = 1.0e-6,
    max_nominal_stress_scale_relative_mismatch: float = 1.0e-6,
) -> EmpiricalFeaCorroborationEligibility:
    geom_tol = float(max_geometry_relative_mismatch)
    scale_tol = float(max_nominal_stress_scale_relative_mismatch)
    if not all(math.isfinite(x) and x >= 0.0 for x in (geom_tol, scale_tol)):
        raise EmpiricalFeaCorroborationError("CORROBORATION_ELIGIBILITY_TOLERANCE_INVALID")

    if prediction.intake_sha256 != intake.intake_sha256:
        raise EmpiricalFeaCorroborationError("CORROBORATION_PREDICTION_INTAKE_SHA_MISMATCH")
    if prediction.geometry_sha256 != geometry.geometry_sha256:
        raise EmpiricalFeaCorroborationError("CORROBORATION_PREDICTION_GEOMETRY_SHA_MISMATCH")
    if prediction.uses_non_synthetic_authorized_data == intake.synthetic_verification_only:
        # Expected logical relation is uses_non_synthetic == not synthetic.
        raise EmpiricalFeaCorroborationError("CORROBORATION_SYNTHETIC_FLAG_INCONSISTENT")

    geometry_match = all(
        _relative(a, b) <= geom_tol
        for a, b in (
            (geometry.small_diameter_mm, fea.small_diameter_mm),
            (geometry.large_diameter_mm, fea.large_diameter_mm),
            (geometry.fillet_radius_mm, fea.fillet_radius_mm),
        )
    )
    empirical_nominal = float(prediction.nominal_axial_stress_mpa)
    fea_nominal = fea.axial_force_n / (math.pi * fea.small_diameter_mm**2 / 4.0)
    load_scale_match = _relative(empirical_nominal, fea_nominal) <= scale_tol
    fea_converged = bool(fea.local_stress_convergence_claim)
    locally_converged = fea.singularity_classification == "LOCALLY_CONVERGED_FIELD"
    non_synthetic = bool(prediction.uses_non_synthetic_authorized_data and not intake.synthetic_verification_only)

    qoi_compatible = (
        fea.qoi_id == _EMPIRICAL_QOI
        and fea.qoi_location == "CAD_SURFACE_FILLET_PEAK"
        and fea.qoi_stress_measure == "AXIAL_NORMAL_STRESS"
        and fea.surface_extrapolation is False
    )

    blockers: list[str] = []
    if not non_synthetic:
        blockers.append("EMPIRICAL_DATASET_SYNTHETIC_NOT_PHYSICAL")
    if not geometry_match:
        blockers.append("EMPIRICAL_FEA_GEOMETRY_MISMATCH")
    if not load_scale_match:
        blockers.append("EMPIRICAL_FEA_NOMINAL_STRESS_SCALE_MISMATCH")
    if not fea_converged:
        blockers.append("FEA_LOCAL_STRESS_NOT_CONVERGED")
    if not locally_converged:
        blockers.append("FEA_LOCAL_FIELD_SINGULARITY_STATUS_NOT_CONVERGED")
    if not qoi_compatible:
        blockers.append("FEA_QOI_NOT_COMPATIBLE_WITH_EMPIRICAL_SURFACE_PEAK_AXIAL_STRESS")

    eligible = not blockers
    if eligible:
        classification = "ELIGIBLE_FOR_EMPIRICAL_FEA_CORROBORATION_STUDY"
    elif "EMPIRICAL_DATASET_SYNTHETIC_NOT_PHYSICAL" in blockers:
        classification = "BLOCKED_SYNTHETIC_EMPIRICAL_DATA_NOT_PHYSICAL"
    elif "FEA_QOI_NOT_COMPATIBLE_WITH_EMPIRICAL_SURFACE_PEAK_AXIAL_STRESS" in blockers:
        classification = "BLOCKED_QOI_NOT_COMPARABLE"
    elif "FEA_LOCAL_STRESS_NOT_CONVERGED" in blockers or "FEA_LOCAL_FIELD_SINGULARITY_STATUS_NOT_CONVERGED" in blockers:
        classification = "BLOCKED_FEA_LOCAL_STRESS_VERIFICATION"
    elif "EMPIRICAL_FEA_GEOMETRY_MISMATCH" in blockers:
        classification = "BLOCKED_GEOMETRY_MISMATCH"
    else:
        classification = "BLOCKED_NOMINAL_STRESS_SCALE_MISMATCH"

    payload = {
        "schema": "AsterMaxEmpiricalFeaCorroborationEligibilityV1",
        "empirical_prediction_sha256": prediction.prediction_sha256,
        "intake_sha256": intake.intake_sha256,
        "empirical_geometry_sha256": geometry.geometry_sha256,
        "fea_summary_sha256": fea.summary_sha256,
        "empirical_qoi_id": _EMPIRICAL_QOI,
        "fea_qoi_id": fea.qoi_id,
        "geometry_match": geometry_match,
        "axial_load_scale_match": load_scale_match,
        "fea_converged": fea_converged,
        "fea_locally_converged_field": locally_converged,
        "empirical_data_non_synthetic": non_synthetic,
        "qoi_compatible": qoi_compatible,
        "eligible": eligible,
        "classification": classification,
        "blockers": tuple(blockers),
    }
    return EmpiricalFeaCorroborationEligibility(
        **payload,
        assessment_sha256=canonical_sha256(payload),
    )


def fea_local_stress_verification_summary_evidence(
    summary: FeaLocalStressVerificationSummary,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"FEA_LOCAL_VERIFY:{summary.summary_sha256[:16]}",
        kind="FEA_LOCAL_STRESS_VERIFICATION_SUMMARY",
        status=(
            EvidenceStatus.VERIFIED
            if summary.local_stress_convergence_claim and summary.singularity_classification == "LOCALLY_CONVERGED_FIELD"
            else EvidenceStatus.CONTRADICTED
        ),
        source=EvidenceSource.DOCUMENT,
        description=(
            "Hash-bound summary of an upstream FEA local-stress verification result. "
            "The summary preserves the upstream benchmark/decision/diagnostic hashes and QOI semantics."
        ),
        payload_sha256=summary.summary_sha256,
        metadata=summary.canonical_without_hash(),
    )


def empirical_fea_corroboration_eligibility_evidence(
    eligibility: EmpiricalFeaCorroborationEligibility,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"EMPIRICAL_FEA_ELIG:{eligibility.assessment_sha256[:16]}",
        kind="EMPIRICAL_FEA_CORROBORATION_ELIGIBILITY",
        status=EvidenceStatus.VERIFIED if eligibility.eligible else EvidenceStatus.CONTRADICTED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Empirical and FEA local-stress evidence are semantically eligible for a future numerical comparison."
            if eligibility.eligible
            else "Empirical and FEA evidence must not be numerically compared as corroboration because one or more eligibility gates failed."
        ),
        payload_sha256=eligibility.assessment_sha256,
        metadata=eligibility.canonical_without_hash(),
    )


def empirical_fea_corroboration_eligibility_claim(context_id: str) -> ClaimDefinition:
    return ClaimDefinition(
        claim_id="CLAIM_EMPIRICAL_FEA_CORROBORATION_ELIGIBLE",
        context_id=context_id,
        statement=(
            "The empirical local-stress prediction and verified FEA result are eligible for a separately governed corroboration comparison."
        ),
        requirements=(
            ClaimRequirement("AUTHORIZED_EMPIRICAL_DATASET_INTAKE", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
            ClaimRequirement("EMPIRICAL_LOCAL_STRESS_PREDICTION", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
            ClaimRequirement("FEA_LOCAL_STRESS_VERIFICATION_SUMMARY", allowed_sources=(EvidenceSource.DOCUMENT, EvidenceSource.DETERMINISTIC_CHECK)),
            ClaimRequirement("EMPIRICAL_FEA_CORROBORATION_ELIGIBILITY", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
        ),
    )
