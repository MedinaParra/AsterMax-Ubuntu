import hashlib
import math

import pytest

from astermax.geometry.step_intake import (
    CylindricalFaceCandidateV1,
    GapScenarioKind,
    GapScenarioV1,
    GeometryPreparationStatus,
    InterfaceSelectionV1,
    StepEvidenceError,
    StepInspectionV1,
    build_gap_sensitivity,
    build_segment_radial_frames,
    evaluate_geometry_preparation,
    validate_gap_sensitivity_plan,
    verify_local_step,
)

SEGMENTS = [1, 2, 4, 5, 6]


def synthetic_inspection(segment_radius_mm: float = 399.0) -> StepInspectionV1:
    frames, deviation = build_segment_radial_frames(
        [
            (2, 398.0, 0.0),
            (1, 398.0 * math.cos(math.radians(72)), 398.0 * math.sin(math.radians(72))),
            (4, 398.0 * math.cos(math.radians(144)), 398.0 * math.sin(math.radians(144))),
            (5, 398.0 * math.cos(math.radians(216)), 398.0 * math.sin(math.radians(216))),
            (6, 398.0 * math.cos(math.radians(288)), 398.0 * math.sin(math.radians(288))),
        ]
    )
    segment_candidates = []
    for index in SEGMENTS:
        for offset in (0, 100):
            segment_candidates.append(
                CylindricalFaceCandidateV1(
                    solid_index_1based=index,
                    face_index_1based=20 + index + offset,
                    radius_mm=segment_radius_mm,
                    area_mm2=100.0,
                    axis_alignment_x_abs=1.0,
                    x_min_mm=-951.0,
                    x_max_mm=-922.0,
                )
            )
    return StepInspectionV1(
        sha256="a" * 64,
        byte_size=100,
        solid_count=6,
        hub_solid_index_1based=3,
        segment_solid_indices_1based=SEGMENTS,
        segment_frames=frames,
        hub_cylindrical_candidates=[
            CylindricalFaceCandidateV1(
                solid_index_1based=3,
                face_index_1based=10,
                radius_mm=397.5,
                area_mm2=1000.0,
                axis_alignment_x_abs=1.0,
                x_min_mm=-951.0,
                x_max_mm=-926.0,
            )
        ],
        segment_cylindrical_candidates=segment_candidates,
        spacing_deviation_max_deg=deviation,
    )


def complete_selection() -> InterfaceSelectionV1:
    return InterfaceSelectionV1(
        hub_face_index_1based=10,
        segment_face_indices_1based={
            index: [20 + index, 120 + index] for index in SEGMENTS
        },
        source_ids=["human_review"],
    )


def test_gap_sensitivity_preserves_measured_endpoints_and_derived_midpoint() -> None:
    plan = build_gap_sensitivity(0.10, 0.40, source_id="report_rev3_p5")
    assert [(item.gap_mm, item.kind) for item in plan] == [
        (0.10, GapScenarioKind.MEASURED_ENDPOINT),
        (0.25, GapScenarioKind.DERIVED_SENSITIVITY),
        (0.40, GapScenarioKind.MEASURED_ENDPOINT),
    ]
    assert "not measured evidence" in plan[1].derivation


def test_midpoint_cannot_be_smuggled_in_as_measured_evidence() -> None:
    malicious_plan = [
        GapScenarioV1(scenario_id="min", gap_mm=0.10, kind=GapScenarioKind.MEASURED_ENDPOINT, source_ids=["report"]),
        GapScenarioV1(scenario_id="mid", gap_mm=0.25, kind=GapScenarioKind.MEASURED_ENDPOINT, source_ids=["report"]),
        GapScenarioV1(scenario_id="max", gap_mm=0.40, kind=GapScenarioKind.MEASURED_ENDPOINT, source_ids=["report"]),
    ]
    with pytest.raises(ValueError, match="reported range endpoints"):
        validate_gap_sensitivity_plan(malicious_plan, minimum_mm=0.10, maximum_mm=0.40)


def test_local_step_wrong_hash_fails_before_cad_backend(tmp_path) -> None:
    step = tmp_path / "model.stp"
    step.write_bytes(b"confidential-step-fixture")
    with pytest.raises(StepEvidenceError, match="SHA-256 mismatch"):
        verify_local_step(step, expected_sha256="0" * 64, expected_byte_size=step.stat().st_size)


def test_local_step_wrong_size_fails_before_cad_backend(tmp_path) -> None:
    step = tmp_path / "model.stp"
    step.write_bytes(b"confidential-step-fixture")
    digest = hashlib.sha256(step.read_bytes()).hexdigest()
    with pytest.raises(StepEvidenceError, match="byte size mismatch"):
        verify_local_step(step, expected_sha256=digest, expected_byte_size=step.stat().st_size + 1)


def test_five_segment_radial_frames_are_72_degree_periodic() -> None:
    inspection = synthetic_inspection()
    assert inspection.spacing_deviation_max_deg == pytest.approx(0.0, abs=1e-10)
    assert len(inspection.segment_frames) == 5
    assert [round(item.angle_deg) for item in inspection.segment_frames] == [0, 72, 144, 216, 288]


def test_current_geometry_preparation_blocks_unconfirmed_interface() -> None:
    plan = build_gap_sensitivity(0.10, 0.40, source_id="report_rev3_p5")
    result = evaluate_geometry_preparation(synthetic_inspection(), plan, test_flange_diameter_mm=796.87)
    assert result.status == GeometryPreparationStatus.BLOCKED_INTERFACE_SELECTION
    assert result.blockers == ["interface:seat_faces_unconfirmed"]


def test_incomplete_or_non_candidate_face_selection_remains_blocked() -> None:
    plan = build_gap_sensitivity(0.10, 0.40, source_id="report_rev3_p5")
    selection = InterfaceSelectionV1(
        hub_face_index_1based=999,
        segment_face_indices_1based={1: [21]},
        source_ids=["human_review"],
    )
    result = evaluate_geometry_preparation(synthetic_inspection(), plan, selection, test_flange_diameter_mm=796.87)
    assert result.status == GeometryPreparationStatus.BLOCKED_INTERFACE_SELECTION
    assert "interface:selected_hub_face_not_candidate" in result.blockers
    assert "interface:segment_2_faces_missing" in result.blockers


def test_multiple_pad_faces_per_segment_can_be_selected() -> None:
    inspection = synthetic_inspection(segment_radius_mm=399.0)
    plan = build_gap_sensitivity(0.10, 0.40, source_id="report_rev3_p5")
    result = evaluate_geometry_preparation(
        inspection,
        plan,
        complete_selection(),
        test_flange_diameter_mm=796.87,
    )
    assert result.status == GeometryPreparationStatus.READY_FOR_PARAMETERIZATION
    assert result.blockers == []


def test_selected_cylindrical_pad_smaller_than_physical_test_flange_is_blocked() -> None:
    inspection = synthetic_inspection(segment_radius_mm=398.05)
    plan = build_gap_sensitivity(0.10, 0.40, source_id="report_rev3_p5")
    result = evaluate_geometry_preparation(
        inspection,
        plan,
        complete_selection(),
        test_flange_diameter_mm=796.87,
    )
    assert result.status == GeometryPreparationStatus.BLOCKED_INTERFACE_SELECTION
    assert any("diameter_below_test_flange" in blocker for blocker in result.blockers)


def test_candidate_axial_extent_requires_both_bounds() -> None:
    with pytest.raises(ValueError, match="both x_min_mm and x_max_mm"):
        CylindricalFaceCandidateV1(
            solid_index_1based=1,
            face_index_1based=1,
            radius_mm=400.0,
            area_mm2=10.0,
            axis_alignment_x_abs=1.0,
            x_min_mm=-10.0,
        )
