from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

from astermax.credibility import (
    ClaimDefinition,
    ClaimRequirement,
    EvidenceRecord,
    EvidenceSource,
    EvidenceStatus,
    canonical_sha256,
)
from .analytical_witness import LinearNormalStressWitness
from .authorized_empirical_dataset import AuthorizedStressConcentrationDataset
from .bounded_stress_concentration import StressConcentrationEvaluation, StressConcentrationGrid
from .shaft_shoulder import ShaftShoulderGeometry
from .stress_concentration_applicability import StressConcentrationApplicabilityAssessment


class EmpiricalLocalStressError(ValueError):
    pass


@dataclass(frozen=True)
class EmpiricalLocalStressPrediction:
    schema: str
    intake_sha256: str
    grid_dataset_sha256: str
    applicability_assessment_sha256: str
    geometry_sha256: str
    analytical_witness_sha256: str
    evaluation_sha256: str
    load_mode: str
    kt_factor: float
    nominal_axial_stress_mpa: float
    predicted_local_axial_stress_mpa: float
    implied_nominal_area_mm2: float
    expected_small_section_area_mm2: float
    nominal_area_relative_mismatch: float
    uses_non_synthetic_authorized_data: bool
    interpretation: str
    prediction_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("prediction_sha256")
        return payload


def _relative(a: float, b: float) -> float:
    return abs(float(a) - float(b)) / max(abs(float(a)), abs(float(b)), 1.0e-30)


def build_empirical_local_stress_prediction(
    intake: AuthorizedStressConcentrationDataset,
    grid: StressConcentrationGrid,
    applicability: StressConcentrationApplicabilityAssessment,
    geometry: ShaftShoulderGeometry,
    witness: LinearNormalStressWitness,
    evaluation: StressConcentrationEvaluation,
    *,
    max_nominal_area_relative_mismatch: float = 1.0e-6,
    zero_moment_tolerance_nmm: float = 1.0e-9,
    zero_gradient_tolerance_mpa_per_mm: float = 1.0e-12,
) -> EmpiricalLocalStressPrediction:
    area_tol = float(max_nominal_area_relative_mismatch)
    moment_tol = float(zero_moment_tolerance_nmm)
    gradient_tol = float(zero_gradient_tolerance_mpa_per_mm)
    if not all(math.isfinite(x) and x >= 0.0 for x in (area_tol, moment_tol, gradient_tol)):
        raise EmpiricalLocalStressError("EMPIRICAL_LOCAL_STRESS_TOLERANCE_INVALID")

    if intake.grid_dataset_sha256 != grid.dataset_sha256:
        raise EmpiricalLocalStressError("EMPIRICAL_GRID_INTAKE_SHA_MISMATCH")
    if evaluation.dataset_sha256 != grid.dataset_sha256:
        raise EmpiricalLocalStressError("EMPIRICAL_EVALUATION_GRID_SHA_MISMATCH")
    if evaluation.geometry_sha256 != geometry.geometry_sha256:
        raise EmpiricalLocalStressError("EMPIRICAL_EVALUATION_GEOMETRY_SHA_MISMATCH")
    if applicability.geometry_sha256 != geometry.geometry_sha256:
        raise EmpiricalLocalStressError("EMPIRICAL_APPLICABILITY_GEOMETRY_SHA_MISMATCH")
    if applicability.source_provenance_sha256 != intake.source_provenance_sha256:
        raise EmpiricalLocalStressError("EMPIRICAL_APPLICABILITY_SOURCE_SHA_MISMATCH")
    if not applicability.applicable:
        raise EmpiricalLocalStressError("EMPIRICAL_SOURCE_OUTSIDE_GEOMETRY_DOMAIN")
    if grid.load_mode.strip().upper() != "AXIAL_TENSION" or applicability.requested_load_mode != "AXIAL_TENSION":
        raise EmpiricalLocalStressError("EMPIRICAL_LOCAL_STRESS_REQUIRES_AXIAL_TENSION")

    if witness.axial_force_n <= 0.0 or witness.sigma0_mpa <= 0.0:
        raise EmpiricalLocalStressError("EMPIRICAL_LOCAL_STRESS_REQUIRES_POSITIVE_AXIAL_TENSION")
    if abs(witness.moment_u_nmm) > moment_tol or abs(witness.moment_v_nmm) > moment_tol:
        raise EmpiricalLocalStressError("EMPIRICAL_LOCAL_STRESS_REQUIRES_ZERO_BENDING_MOMENT")
    if (
        abs(witness.gradient_u_mpa_per_mm) > gradient_tol
        or abs(witness.gradient_v_mpa_per_mm) > gradient_tol
    ):
        raise EmpiricalLocalStressError("EMPIRICAL_LOCAL_STRESS_REQUIRES_UNIFORM_NOMINAL_STRESS")

    implied_area = float(witness.axial_force_n / witness.sigma0_mpa)
    expected_area = math.pi * float(geometry.small_diameter_mm) ** 2 / 4.0
    area_mismatch = _relative(implied_area, expected_area)
    if area_mismatch > area_tol:
        raise EmpiricalLocalStressError(
            f"EMPIRICAL_NOMINAL_SECTION_GEOMETRY_MISMATCH:{area_mismatch:.17g}"
        )

    kt = float(evaluation.factor)
    if not math.isfinite(kt) or kt < 1.0:
        raise EmpiricalLocalStressError("EMPIRICAL_KT_FACTOR_INVALID")
    nominal = float(witness.sigma0_mpa)
    predicted = kt * nominal

    payload = {
        "schema": "AsterMaxEmpiricalLocalStressPredictionV1",
        "intake_sha256": intake.intake_sha256,
        "grid_dataset_sha256": grid.dataset_sha256,
        "applicability_assessment_sha256": applicability.assessment_sha256,
        "geometry_sha256": geometry.geometry_sha256,
        "analytical_witness_sha256": witness.witness_sha256,
        "evaluation_sha256": evaluation.evaluation_sha256,
        "load_mode": "AXIAL_TENSION",
        "kt_factor": kt,
        "nominal_axial_stress_mpa": nominal,
        "predicted_local_axial_stress_mpa": predicted,
        "implied_nominal_area_mm2": implied_area,
        "expected_small_section_area_mm2": expected_area,
        "nominal_area_relative_mismatch": area_mismatch,
        "uses_non_synthetic_authorized_data": not intake.synthetic_verification_only,
        "interpretation": "EMPIRICAL_CORRELATION_OUTPUT_NOT_PHYSICAL_VALIDATION",
    }
    return EmpiricalLocalStressPrediction(**payload, prediction_sha256=canonical_sha256(payload))


def empirical_evaluation_evidence(
    intake: AuthorizedStressConcentrationDataset,
    evaluation: StressConcentrationEvaluation,
) -> EvidenceRecord:
    if intake.grid_dataset_sha256 != evaluation.dataset_sha256:
        raise EmpiricalLocalStressError("EMPIRICAL_EVALUATION_INTAKE_SHA_MISMATCH")
    payload = {
        "intake_sha256": intake.intake_sha256,
        "dataset_sha256": evaluation.dataset_sha256,
        "geometry_sha256": evaluation.geometry_sha256,
        "evaluation_sha256": evaluation.evaluation_sha256,
        "factor": evaluation.factor,
        "synthetic_verification_only": intake.synthetic_verification_only,
    }
    return EvidenceRecord(
        evidence_id=f"EMPIRICAL_EVAL:{evaluation.evaluation_sha256[:16]}",
        kind="EMPIRICAL_STRESS_CONCENTRATION_EVALUATION",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description="Bounded stress-concentration grid evaluation tied to the exact authorized dataset intake and geometry.",
        payload_sha256=canonical_sha256(payload),
        metadata=payload,
    )


def empirical_local_prediction_evidence(prediction: EmpiricalLocalStressPrediction) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"EMPIRICAL_LOCAL_STRESS:{prediction.prediction_sha256[:16]}",
        kind="EMPIRICAL_LOCAL_STRESS_PREDICTION",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description=(
            "Kt multiplied by an independently bound pure-axial nominal section witness after geometry, domain and dataset checks."
        ),
        payload_sha256=prediction.prediction_sha256,
        metadata=prediction.canonical_without_hash(),
    )


def empirical_local_stress_chain_evidence(
    intake: AuthorizedStressConcentrationDataset,
    applicability: StressConcentrationApplicabilityAssessment,
    witness: LinearNormalStressWitness,
    evaluation: StressConcentrationEvaluation,
    prediction: EmpiricalLocalStressPrediction,
) -> EvidenceRecord:
    checks = (
        prediction.intake_sha256 == intake.intake_sha256,
        prediction.grid_dataset_sha256 == intake.grid_dataset_sha256,
        prediction.applicability_assessment_sha256 == applicability.assessment_sha256,
        prediction.geometry_sha256 == applicability.geometry_sha256 == evaluation.geometry_sha256,
        prediction.analytical_witness_sha256 == witness.witness_sha256,
        prediction.evaluation_sha256 == evaluation.evaluation_sha256,
        evaluation.dataset_sha256 == intake.grid_dataset_sha256,
        applicability.applicable,
    )
    if not all(checks):
        raise EmpiricalLocalStressError("EMPIRICAL_LOCAL_STRESS_CHAIN_BINDING_MISMATCH")
    payload = {
        "schema": "AsterMaxEmpiricalLocalStressChainV1",
        "intake_sha256": intake.intake_sha256,
        "applicability_assessment_sha256": applicability.assessment_sha256,
        "analytical_witness_sha256": witness.witness_sha256,
        "evaluation_sha256": evaluation.evaluation_sha256,
        "prediction_sha256": prediction.prediction_sha256,
        "synthetic_verification_only": intake.synthetic_verification_only,
    }
    chain_sha = canonical_sha256(payload)
    return EvidenceRecord(
        evidence_id=f"EMPIRICAL_LOCAL_CHAIN:{chain_sha[:16]}",
        kind="EMPIRICAL_LOCAL_STRESS_CHAIN",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description="Exact authorized dataset, applicability, nominal analytical witness, Kt evaluation and local-stress prediction are hash-bound.",
        payload_sha256=chain_sha,
        metadata=payload,
    )


def empirical_local_stress_computation_claim(context_id: str) -> ClaimDefinition:
    return ClaimDefinition(
        claim_id="CLAIM_EMPIRICAL_LOCAL_STRESS_CHAIN_COMPUTED",
        context_id=context_id,
        statement=(
            "An empirical local axial stress was computed from an authorized bounded Kt dataset and the matching pure-axial nominal CAD-section witness."
        ),
        requirements=(
            ClaimRequirement("AUTHORIZED_EMPIRICAL_DATASET_INTAKE", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
            ClaimRequirement("STRESS_CONCENTRATION_DOMAIN_APPLICABILITY", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
            ClaimRequirement("ANALYTICAL_SECTION_WITNESS", allowed_sources=(EvidenceSource.ANALYTICAL_WITNESS,)),
            ClaimRequirement("EMPIRICAL_STRESS_CONCENTRATION_EVALUATION", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
            ClaimRequirement("EMPIRICAL_LOCAL_STRESS_PREDICTION", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
            ClaimRequirement("EMPIRICAL_LOCAL_STRESS_CHAIN", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
        ),
    )
