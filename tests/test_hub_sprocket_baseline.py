import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from astermax.domain.hub_sprocket import (
    CadUnitNormalizationStatus,
    DiameterReferenceRole,
    DiameterReferenceV1,
    EvidenceStatus,
    EvidenceValueV1,
    HubSprocketBaselineV1,
    SourceReferenceV1,
)
from astermax.domain.hub_sprocket_readiness import (
    HubSprocketSolveBlocked,
    SolveReadinessStatus,
    evaluate_critical_solve_readiness,
    require_ready_for_solver,
)

BASELINE_PATH = Path(__file__).parents[1] / "examples" / "hub_sprocket" / "ot1613_baseline.json"


def load_baseline() -> HubSprocketBaselineV1:
    return HubSprocketBaselineV1.model_validate_json(BASELINE_PATH.read_text(encoding="utf-8"))


def authentic(value, *, unit=None) -> EvidenceValueV1:
    return EvidenceValueV1(value=value, status=EvidenceStatus.KNOWN_FACT, unit=unit, source_ids=["test_confirmation"])


def derived(value, derivation: str, *, unit=None) -> EvidenceValueV1:
    return EvidenceValueV1(value=value, status=EvidenceStatus.DERIVED, unit=unit, source_ids=["test_confirmation"], derivation=derivation)


def make_ready_baseline() -> HubSprocketBaselineV1:
    baseline = load_baseline().model_copy(deep=True)
    baseline.sources["test_confirmation"] = SourceReferenceV1(source_id="test_confirmation", title="Test-only confirmed engineering inputs", source_kind="test_fixture_only", notes="Structural test fixture; not OT1613 engineering evidence.")
    baseline.identifiers.confirmed_value = "OT-SKM-1613"
    baseline.identifiers.confirmation_source_ids = ["test_confirmation"]
    baseline.geometry.unit_normalization_status = CadUnitNormalizationStatus.CONFIRMED_MM_FROM_DRAWING
    baseline.geometry.human_confirmation_source_ids = ["test_confirmation"]
    for key in baseline.required_inputs:
        baseline.required_inputs[key] = authentic({"confirmed": True, "input_id": key})
    baseline.model_intent.friction_coefficient = derived(0.15, "test-only derivation from confirmed contact/material/lubricant evidence")
    baseline.model_intent.nominal_bolt_preload_n = derived(100000.0, "test-only derivation from confirmed tightening data", unit="N")
    baseline.model_intent.minimum_probable_bolt_preload_n = derived(80000.0, "test-only lower-bound derivation from confirmed tightening data", unit="N")
    return HubSprocketBaselineV1.model_validate(baseline.model_dump())


def test_current_ot1613_baseline_is_blocked_fail_closed() -> None:
    report = evaluate_critical_solve_readiness(load_baseline())
    assert report.status == SolveReadinessStatus.BLOCKED
    assert "required_input:jam_torque_knm" in report.blockers
    assert "required_input:hub_material_and_properties" in report.blockers
    assert "model_input:friction_coefficient" in report.blockers
    assert "model_input:minimum_probable_bolt_preload_n" in report.blockers
    assert "geometry:unit_normalization_unconfirmed" in report.blockers
    assert "identity:ot_identifier_unconfirmed" in report.blockers
    assert any("cad_geometry_is_nominal_touching" in warning for warning in report.warnings)


def test_blocked_baseline_cannot_be_promoted_to_solver() -> None:
    with pytest.raises(HubSprocketSolveBlocked):
        require_ready_for_solver(load_baseline())


def test_all_confirmed_inputs_can_transition_measured_gap_case_to_ready() -> None:
    report = require_ready_for_solver(make_ready_baseline())
    assert report.status == SolveReadinessStatus.READY
    assert report.blockers == []
    assert any("optimized_seating_diameter_pending_metrology" in warning for warning in report.warnings)


def test_generic_or_proposed_friction_is_not_authentic_ready_evidence() -> None:
    baseline = make_ready_baseline()
    baseline.model_intent.friction_coefficient = EvidenceValueV1(value=0.2, status=EvidenceStatus.PROPOSED_MODELING_ASSUMPTION, source_ids=["test_confirmation"])
    report = evaluate_critical_solve_readiness(HubSprocketBaselineV1.model_validate(baseline.model_dump()))
    assert report.status == SolveReadinessStatus.BLOCKED
    assert "model_input:friction_coefficient" in report.blockers


def test_reported_diameters_cannot_be_relabelled_as_oem_posterior_seat() -> None:
    baseline = load_baseline()
    baseline.diameter_references.append(DiameterReferenceV1(diameter_mm=795.0, role=DiameterReferenceRole.OEM_POSTERIOR_SEAT, status=EvidenceStatus.KNOWN_FACT, source_ids=["report_rev3_p5"]))
    with pytest.raises(ValidationError):
        HubSprocketBaselineV1.model_validate(baseline.model_dump())


def test_measured_gap_midpoint_cannot_replace_reported_range() -> None:
    payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    payload["measured_gap"]["minimum_mm"] = 0.25
    payload["measured_gap"]["maximum_mm"] = 0.25
    with pytest.raises(ValidationError):
        HubSprocketBaselineV1.model_validate(payload)


def test_step_unit_conflict_remains_explicit_until_human_confirmation() -> None:
    baseline = load_baseline()
    assert baseline.geometry.declared_length_unit == "METRE"
    assert baseline.geometry.intended_analysis_length_unit == "mm"
    assert baseline.geometry.unit_normalization_status == CadUnitNormalizationStatus.UNRESOLVED
    assert baseline.geometry.hub_bbox_numeric.y_length == pytest.approx(795.0000002)
    assert baseline.geometry.solid_count == 6
    assert baseline.geometry.segment_count_with_identical_volume == 5
