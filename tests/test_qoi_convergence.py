from dataclasses import replace

import pytest

from astermax.credibility import canonical_sha256
from astermax.fea.qoi_convergence import (
    QoiConvergenceCriteriaV1,
    assess_qoi_convergence,
    build_local_refinement_review,
    make_qoi_observation,
    verify_qoi_convergence_boundary,
)
from astermax.fea.worst_element_inspector import WorstElementQualitySnapshot


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64


def _observation(*, mesh_sha: str, solve_sha: str, size: float, elements: int, value: float, route: str = SHA_B):
    return make_qoi_observation(
        source_step_sha256=SHA_A,
        route_sha256=route,
        solve_evidence_sha256=solve_sha,
        mesh_identity_sha256=mesh_sha,
        mesh_target_size_mm=size,
        element_count=elements,
        qoi_name="U_MAG_MAX",
        qoi_unit="mm",
        qoi_value=value,
    )


def test_qoi_convergence_pass_is_narrow_and_deterministic():
    coarse = _observation(mesh_sha=SHA_C, solve_sha=SHA_D, size=10.0, elements=100, value=1.000)
    fine = _observation(mesh_sha=SHA_E, solve_sha="1" * 64, size=7.0, elements=180, value=1.015)
    criteria = QoiConvergenceCriteriaV1(maximum_relative_change=0.02)
    a = assess_qoi_convergence(coarse, fine, criteria)
    b = assess_qoi_convergence(coarse, fine, criteria)
    assert a == b
    assert a.status == "PASS"
    assert a.claims["qoi_discretization_converged"] is True
    assert a.claims["global_analysis_converged"] is False
    assert a.claims["industrial_validation"] is False
    assert a.claims["ansys_equivalence"] is False
    verify_qoi_convergence_boundary(a)


def test_qoi_change_above_explicit_criterion_fails():
    coarse = _observation(mesh_sha=SHA_C, solve_sha=SHA_D, size=10.0, elements=100, value=1.0)
    fine = _observation(mesh_sha=SHA_E, solve_sha="1" * 64, size=5.0, elements=240, value=1.1)
    report = assess_qoi_convergence(coarse, fine, QoiConvergenceCriteriaV1(0.05))
    assert report.status == "FAIL"
    assert "QOI_RELATIVE_CHANGE_ABOVE_EXPLICIT_CRITERION" in report.blockers
    assert report.claims["qoi_discretization_converged"] is False


def test_qoi_rejects_changed_physical_route_even_when_numbers_are_close():
    coarse = _observation(mesh_sha=SHA_C, solve_sha=SHA_D, size=10.0, elements=100, value=1.0)
    fine = _observation(mesh_sha=SHA_E, solve_sha="1" * 64, size=5.0, elements=220, value=1.001, route="2" * 64)
    report = assess_qoi_convergence(coarse, fine, QoiConvergenceCriteriaV1(0.01))
    assert report.status == "FAIL"
    assert "QOI_PHYSICAL_MODEL_PROVENANCE_MISMATCH" in report.blockers


def test_qoi_requires_verified_refinement_order():
    coarse = _observation(mesh_sha=SHA_C, solve_sha=SHA_D, size=10.0, elements=100, value=1.0)
    fine = _observation(mesh_sha=SHA_E, solve_sha="1" * 64, size=12.0, elements=80, value=1.001)
    report = assess_qoi_convergence(coarse, fine, QoiConvergenceCriteriaV1(0.01))
    assert report.status == "FAIL"
    assert "QOI_REFINEMENT_ORDER_NOT_VERIFIED" in report.blockers


def test_qoi_rejects_nonfinite_values_and_fake_sha():
    with pytest.raises(ValueError, match="QOI_VALUE_NONFINITE"):
        make_qoi_observation(
            source_step_sha256=SHA_A,
            route_sha256=SHA_B,
            solve_evidence_sha256=SHA_C,
            mesh_identity_sha256=SHA_D,
            mesh_target_size_mm=10.0,
            element_count=10,
            qoi_name="U_MAG_MAX",
            qoi_unit="mm",
            qoi_value=float("nan"),
        )
    with pytest.raises(ValueError, match="QOI_SOURCE_STEP_SHA"):
        make_qoi_observation(
            source_step_sha256="not-a-sha",
            route_sha256=SHA_B,
            solve_evidence_sha256=SHA_C,
            mesh_identity_sha256=SHA_D,
            mesh_target_size_mm=10.0,
            element_count=10,
            qoi_name="U_MAG_MAX",
            qoi_unit="mm",
            qoi_value=1.0,
        )


def test_boundary_rejects_global_or_ansys_overclaim():
    coarse = _observation(mesh_sha=SHA_C, solve_sha=SHA_D, size=10.0, elements=100, value=1.0)
    fine = _observation(mesh_sha=SHA_E, solve_sha="1" * 64, size=5.0, elements=200, value=1.001)
    report = assess_qoi_convergence(coarse, fine, QoiConvergenceCriteriaV1(0.01))
    with pytest.raises(ValueError, match="QOI_GLOBAL_CONVERGENCE_OVERCLAIM"):
        verify_qoi_convergence_boundary(replace(report, claims={**report.claims, "global_analysis_converged": True}))
    with pytest.raises(ValueError, match="QOI_ANSYS_EQUIVALENCE_OVERCLAIM"):
        verify_qoi_convergence_boundary(replace(report, claims={**report.claims, "ansys_equivalence": True}))


def _inspector() -> WorstElementQualitySnapshot:
    rows = (
        {"rank": 1, "element_index": 7, "quality": 0.12, "crosscheck_quality": 0.12, "centroid_mm": [1.0, 2.0, 3.0], "projected_centroid": [0.2, 0.3], "projected_corners": [[0.0, 0.0]] * 4},
        {"rank": 2, "element_index": 9, "quality": 0.20, "crosscheck_quality": 0.20, "centroid_mm": [4.0, 5.0, 6.0], "projected_centroid": [0.4, 0.5], "projected_corners": [[0.0, 0.0]] * 4},
    )
    core = {
        "schema": "AsterMaxWorstElementQualityInspectorV1",
        "metric": "tetra_mean_ratio",
        "element_count": 20,
        "quality_minimum": 0.12,
        "quality_p10": 0.25,
        "quality_median": 0.60,
        "quality_maximum": 0.95,
        "histogram_edges": tuple(i / 10.0 for i in range(11)),
        "histogram_counts": (0, 1, 1, 2, 2, 3, 3, 3, 3, 2),
        "worst_elements": rows,
        "crosscheck_max_abs_delta": 0.0,
        "crosscheck_tolerance": 1.0e-10,
        "crosscheck_verified": True,
        "ansys_metric_equivalence": False,
        "industrial_acceptance_threshold_declared": False,
    }
    return WorstElementQualitySnapshot(**core, snapshot_sha256=canonical_sha256(core))


def test_local_refinement_review_localizes_without_auto_execution():
    review = build_local_refinement_review(_inspector(), maximum_candidates=2)
    assert review.candidate_element_indices == (7, 9)
    assert review.candidate_centroids_mm == ((1.0, 2.0, 3.0), (4.0, 5.0, 6.0))
    assert review.requires_human_approval is True
    assert review.auto_execution_allowed is False
    assert review.changes_physics is False


def test_local_refinement_review_rejects_ansys_metric_overclaim():
    inspector = replace(_inspector(), ansys_metric_equivalence=True)
    with pytest.raises(ValueError, match="LOCAL_REFINEMENT_ANSYS_METRIC_OVERCLAIM"):
        build_local_refinement_review(inspector)
