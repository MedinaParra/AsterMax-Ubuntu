import math

import pytest

from astermax.credibility import (
    ClaimEngine,
    ClaimState,
    ConsequenceLevel,
    ContextOfUse,
    EvidenceGraph,
    EvidenceRecord,
    EvidenceSource,
    EvidenceStatus,
    canonical_sha256,
)
from astermax.fea.authorized_empirical_dataset import AuthorizedStressConcentrationDataset
from astermax.fea.empirical_fea_corroboration import (
    assess_empirical_fea_corroboration_eligibility,
    build_fea_local_stress_verification_summary,
    empirical_fea_corroboration_eligibility_claim,
    empirical_fea_corroboration_eligibility_evidence,
    fea_local_stress_verification_summary_evidence,
)
from astermax.fea.empirical_local_stress import EmpiricalLocalStressPrediction
from astermax.fea.shaft_shoulder import build_shaft_shoulder_geometry


def _intake(*, synthetic: bool) -> AuthorizedStressConcentrationDataset:
    payload = {
        "schema": "AsterMaxAuthorizedStressConcentrationDatasetV1",
        "manifest_sha256": "1" * 64,
        "source_provenance_sha256": "2" * 64,
        "raw_file_sha256": "3" * 64,
        "dataset_filename": "c17_test_dataset.json",
        "dataset_id": "C17_TEST_GRID",
        "factor_name": "Kt_TEST_ONLY_NOT_ENGINEERING_DATA",
        "load_mode": "AXIAL_TENSION",
        "grid_dataset_sha256": "4" * 64,
        "authorization_basis": "SYNTHETIC_VERIFICATION" if synthetic else "LICENSED",
        "synthetic_verification_only": synthetic,
    }
    return AuthorizedStressConcentrationDataset(
        **payload,
        intake_sha256=canonical_sha256(payload),
    )


def _geometry(*, large=30.0):
    return build_shaft_shoulder_geometry(
        geometry_id="C17_TEST_GEOMETRY",
        small_diameter_mm=20.0,
        large_diameter_mm=large,
        fillet_radius_mm=2.0,
    )


def _prediction(intake, geometry, *, non_synthetic: bool):
    nominal = 1000.0 / (math.pi * 20.0**2 / 4.0)
    payload = {
        "schema": "AsterMaxEmpiricalLocalStressPredictionV1",
        "intake_sha256": intake.intake_sha256,
        "grid_dataset_sha256": intake.grid_dataset_sha256,
        "applicability_assessment_sha256": "5" * 64,
        "geometry_sha256": geometry.geometry_sha256,
        "analytical_witness_sha256": "6" * 64,
        "evaluation_sha256": "7" * 64,
        "load_mode": "AXIAL_TENSION",
        "kt_factor": 2.0,
        "nominal_axial_stress_mpa": nominal,
        "predicted_local_axial_stress_mpa": 2.0 * nominal,
        "implied_nominal_area_mm2": math.pi * 20.0**2 / 4.0,
        "expected_small_section_area_mm2": math.pi * 20.0**2 / 4.0,
        "nominal_area_relative_mismatch": 0.0,
        "uses_non_synthetic_authorized_data": non_synthetic,
        "interpretation": "TEST_ONLY_SOFTWARE_GATE_NOT_PHYSICAL_VALIDATION",
    }
    return EmpiricalLocalStressPrediction(
        **payload,
        prediction_sha256=canonical_sha256(payload),
    )


def _fea(
    *,
    small=20.0000002,
    large=30.0000002,
    radius=1.9999998,
    force=1000.0,
    converged=True,
    singularity="LOCALLY_CONVERGED_FIELD",
    qoi_id="VON_MISES_IP_MAX_MPA",
    qoi_location="ACTUAL_DUFFY_GL4_INTERIOR_INTEGRATION_POINTS",
    stress_measure="VON_MISES",
):
    return build_fea_local_stress_verification_summary(
        upstream_benchmark_sha256="8" * 64,
        upstream_artifact_zip_sha256="9" * 64,
        upstream_decision_sha256="a" * 64,
        upstream_singularity_diagnostic_sha256="b" * 64,
        small_diameter_mm=small,
        large_diameter_mm=large,
        fillet_radius_mm=radius,
        axial_force_n=force,
        local_stress_convergence_claim=converged,
        singularity_classification=singularity,
        qoi_id=qoi_id,
        qoi_location=qoi_location,
        qoi_stress_measure=stress_measure,
        measurement_operator="FIXED_R_OVER_4_VOLUME_PLUS_ACTUAL_IP_PEAK",
        nodal_recovery=False,
        surface_extrapolation=False,
    )


def test_current_c17_shape_blocks_synthetic_and_incompatible_qoi_independently():
    intake = _intake(synthetic=True)
    geometry = _geometry()
    prediction = _prediction(intake, geometry, non_synthetic=False)
    eligibility = assess_empirical_fea_corroboration_eligibility(
        prediction,
        intake,
        geometry,
        _fea(),
    )
    assert eligibility.eligible is False
    assert eligibility.classification == "BLOCKED_SYNTHETIC_EMPIRICAL_DATA_NOT_PHYSICAL"
    assert eligibility.geometry_match is True
    assert eligibility.axial_load_scale_match is True
    assert eligibility.fea_converged is True
    assert eligibility.fea_locally_converged_field is True
    assert eligibility.empirical_data_non_synthetic is False
    assert eligibility.qoi_compatible is False
    assert eligibility.blockers == (
        "EMPIRICAL_DATASET_SYNTHETIC_NOT_PHYSICAL",
        "FEA_QOI_NOT_COMPATIBLE_WITH_EMPIRICAL_SURFACE_PEAK_AXIAL_STRESS",
    )


def test_semantically_matching_test_double_can_be_eligible_without_claiming_validation():
    intake = _intake(synthetic=False)
    geometry = _geometry()
    prediction = _prediction(intake, geometry, non_synthetic=True)
    fea = _fea(
        qoi_id="SURFACE_PEAK_AXIAL_NORMAL_STRESS_MPA",
        qoi_location="CAD_SURFACE_FILLET_PEAK",
        stress_measure="AXIAL_NORMAL_STRESS",
    )
    eligibility = assess_empirical_fea_corroboration_eligibility(
        prediction,
        intake,
        geometry,
        fea,
    )
    assert eligibility.eligible is True
    assert eligibility.classification == "ELIGIBLE_FOR_EMPIRICAL_FEA_CORROBORATION_STUDY"
    assert eligibility.blockers == ()


def test_geometry_mismatch_blocks():
    intake = _intake(synthetic=False)
    geometry = _geometry()
    prediction = _prediction(intake, geometry, non_synthetic=True)
    eligibility = assess_empirical_fea_corroboration_eligibility(
        prediction,
        intake,
        geometry,
        _fea(large=31.0, qoi_id="SURFACE_PEAK_AXIAL_NORMAL_STRESS_MPA", qoi_location="CAD_SURFACE_FILLET_PEAK", stress_measure="AXIAL_NORMAL_STRESS"),
    )
    assert eligibility.eligible is False
    assert "EMPIRICAL_FEA_GEOMETRY_MISMATCH" in eligibility.blockers


def test_nominal_stress_scale_mismatch_blocks():
    intake = _intake(synthetic=False)
    geometry = _geometry()
    prediction = _prediction(intake, geometry, non_synthetic=True)
    eligibility = assess_empirical_fea_corroboration_eligibility(
        prediction,
        intake,
        geometry,
        _fea(force=900.0, qoi_id="SURFACE_PEAK_AXIAL_NORMAL_STRESS_MPA", qoi_location="CAD_SURFACE_FILLET_PEAK", stress_measure="AXIAL_NORMAL_STRESS"),
    )
    assert eligibility.eligible is False
    assert "EMPIRICAL_FEA_NOMINAL_STRESS_SCALE_MISMATCH" in eligibility.blockers


def test_unconverged_fea_blocks():
    intake = _intake(synthetic=False)
    geometry = _geometry()
    prediction = _prediction(intake, geometry, non_synthetic=True)
    eligibility = assess_empirical_fea_corroboration_eligibility(
        prediction,
        intake,
        geometry,
        _fea(converged=False, singularity="NOT_ASSESSED", qoi_id="SURFACE_PEAK_AXIAL_NORMAL_STRESS_MPA", qoi_location="CAD_SURFACE_FILLET_PEAK", stress_measure="AXIAL_NORMAL_STRESS"),
    )
    assert eligibility.eligible is False
    assert "FEA_LOCAL_STRESS_NOT_CONVERGED" in eligibility.blockers
    assert "FEA_LOCAL_FIELD_SINGULARITY_STATUS_NOT_CONVERGED" in eligibility.blockers


def test_claim_engine_blocks_when_eligibility_record_is_contradicted():
    intake = _intake(synthetic=True)
    geometry = _geometry()
    prediction = _prediction(intake, geometry, non_synthetic=False)
    fea = _fea()
    eligibility = assess_empirical_fea_corroboration_eligibility(prediction, intake, geometry, fea)

    context = ContextOfUse(
        context_id="COU_C17_TEST",
        engineering_question="May empirical and FEA local-stress evidence be compared?",
        intended_decision="Permit only a separately governed corroboration study.",
        quantities_of_interest=("empirical surface peak axial stress", "FEA local stress QOI"),
        acceptance_criteria=("all provenance and QOI gates must pass",),
        consequence_level=ConsequenceLevel.HIGH,
        assumptions=("test-only fixtures are not physical validation",),
    )
    graph = EvidenceGraph(context)
    direct_records = (
        EvidenceRecord("INTAKE:C17", "AUTHORIZED_EMPIRICAL_DATASET_INTAKE", EvidenceStatus.VERIFIED, EvidenceSource.DETERMINISTIC_CHECK, "test intake", intake.intake_sha256),
        EvidenceRecord("APPLIC:C17", "STRESS_CONCENTRATION_DOMAIN_APPLICABILITY", EvidenceStatus.VERIFIED, EvidenceSource.DETERMINISTIC_CHECK, "test applicability", "c" * 64),
        EvidenceRecord("PREDICT:C17", "EMPIRICAL_LOCAL_STRESS_PREDICTION", EvidenceStatus.VERIFIED, EvidenceSource.DETERMINISTIC_CHECK, "test prediction", prediction.prediction_sha256),
        EvidenceRecord("CHAIN:C17", "EMPIRICAL_LOCAL_STRESS_CHAIN", EvidenceStatus.VERIFIED, EvidenceSource.DETERMINISTIC_CHECK, "test chain", "d" * 64),
        fea_local_stress_verification_summary_evidence(fea),
        empirical_fea_corroboration_eligibility_evidence(eligibility),
    )
    for record in direct_records:
        graph.add(record)
    decision = ClaimEngine.evaluate(
        empirical_fea_corroboration_eligibility_claim(context.context_id),
        graph,
    )
    assert decision.state is ClaimState.BLOCKED
    assert any("EMPIRICAL_FEA_CORROBORATION_ELIGIBILITY" in blocker for blocker in decision.blockers)


def test_prediction_synthetic_flag_inconsistency_hard_fails():
    intake = _intake(synthetic=True)
    geometry = _geometry()
    prediction = _prediction(intake, geometry, non_synthetic=True)
    with pytest.raises(Exception, match="SYNTHETIC_FLAG_INCONSISTENT"):
        assess_empirical_fea_corroboration_eligibility(prediction, intake, geometry, _fea())
