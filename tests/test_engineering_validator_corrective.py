from __future__ import annotations

from dataclasses import replace

import pytest

from astermax.fea.corrective_action import (
    propose_corrective_action,
    verify_corrective_action_boundary,
)
from astermax.fea.engineering_validator import (
    EngineeringValidationCriteriaV1,
    validate_mesh_and_equilibrium,
    verify_validation_contract,
)
from astermax.fea.tet_quality import TetQualitySnapshot


def quality(minimum: float) -> TetQualitySnapshot:
    return TetQualitySnapshot(
        schema="AsterMaxTetMeanRatioQualityV1",
        metric="TETRA_MEAN_RATIO_12_TIMES_3V_TO_2_OVER_3_DIV_SUM_EDGE_SQUARED",
        element_count=10,
        minimum=minimum,
        percentile_10=max(minimum, 0.5),
        median=0.8,
        maximum=0.95,
        crosscheck_max_abs_delta=0.0,
        crosscheck_tolerance=1.0e-10,
        crosscheck_verified=True,
        ansys_metric_equivalence=False,
        snapshot_sha256="1" * 64,
    )


def solve(force: float, moment: float) -> dict:
    return {
        "force_residual_n": force,
        "moment_residual_nmm": moment,
        "solve_evidence_sha256": "2" * 64,
    }


def criteria() -> EngineeringValidationCriteriaV1:
    return EngineeringValidationCriteriaV1(
        minimum_tet_mean_ratio=0.20,
        maximum_force_residual_n=1.0e-6,
        maximum_moment_residual_nmm=1.0e-4,
    )


def test_validator_passes_only_explicit_mesh_and_equilibrium_criteria():
    report = validate_mesh_and_equilibrium(quality(0.35), solve(1.0e-8, 1.0e-6), criteria())
    assert report.status == "PASS"
    assert report.blockers == ()
    assert report.mesh_quality_pass
    assert report.force_equilibrium_pass
    assert report.moment_equilibrium_pass
    assert report.claims == {
        "converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    verify_validation_contract(report)


def test_mesh_failure_yields_review_only_refinement_candidate():
    report = validate_mesh_and_equilibrium(quality(0.10), solve(0.0, 0.0), criteria())
    assert report.status == "FAIL"
    assert "MESH_QUALITY_BELOW_EXPLICIT_CRITERION" in report.blockers
    candidate = propose_corrective_action(report)
    assert candidate.action_type == "LOCAL_MESH_REFINEMENT_REVIEW"
    assert candidate.requires_element_localization is True
    assert candidate.requires_human_approval is True
    assert candidate.auto_execution_allowed is False
    assert candidate.modifies_physics is False
    verify_corrective_action_boundary(candidate)


def test_equilibrium_failure_never_auto_changes_boundary_conditions():
    report = validate_mesh_and_equilibrium(quality(0.40), solve(2.0e-3, 3.0), criteria())
    candidate = propose_corrective_action(report)
    assert report.status == "FAIL"
    assert candidate.action_type == "EQUILIBRIUM_AND_BC_REVIEW"
    assert candidate.auto_execution_allowed is False
    assert candidate.modifies_physics is False
    assert candidate.requires_human_approval is True


def test_pass_report_does_not_create_synthetic_correction_or_convergence_claim():
    report = validate_mesh_and_equilibrium(quality(0.40), solve(0.0, 0.0), criteria())
    candidate = propose_corrective_action(report)
    assert candidate.action_type == "NONE"
    assert candidate.requires_human_approval is False
    assert report.claims["converged"] is False


def test_validator_rejects_nonfinite_residual_and_ansys_metric_overclaim():
    with pytest.raises(ValueError, match="ENGINEERING_VALIDATOR_NONFINITE_RESIDUAL"):
        validate_mesh_and_equilibrium(quality(0.4), solve(float("nan"), 0.0), criteria())
    with pytest.raises(ValueError, match="ENGINEERING_VALIDATOR_ANSYS_METRIC_OVERCLAIM"):
        validate_mesh_and_equilibrium(replace(quality(0.4), ansys_metric_equivalence=True), solve(0.0, 0.0), criteria())


def test_validator_rejects_implicit_or_invalid_acceptance_thresholds():
    with pytest.raises(ValueError, match="ENGINEERING_VALIDATOR_QUALITY_CRITERION"):
        validate_mesh_and_equilibrium(
            quality(0.4),
            solve(0.0, 0.0),
            EngineeringValidationCriteriaV1(0.0, 1.0, 1.0),
        )


def test_contract_verifiers_fail_closed_on_overclaim_or_auto_execution():
    report = validate_mesh_and_equilibrium(quality(0.4), solve(0.0, 0.0), criteria())
    with pytest.raises(ValueError, match="ENGINEERING_VALIDATOR_CLAIM_BOUNDARY"):
        verify_validation_contract(replace(report, claims={**report.claims, "converged": True}))
    candidate = propose_corrective_action(validate_mesh_and_equilibrium(quality(0.1), solve(0.0, 0.0), criteria()))
    with pytest.raises(ValueError, match="CORRECTIVE_ACTION_AUTO_EXECUTION_FORBIDDEN"):
        verify_corrective_action_boundary(replace(candidate, auto_execution_allowed=True))
