from __future__ import annotations

import pytest

from astermax.fea.axial_step_verification import (
    AxialRefinementLevel,
    AxialRefinementPolicy,
    AxialStepVerificationError,
    assess_axial_refinement,
)


def _level(size: float, rms: float, max_rel: float) -> AxialRefinementLevel:
    return AxialRefinementLevel(
        mesh_size_mm=size,
        node_count=100,
        tet10_count=50,
        interior_sample_count=80,
        mean_sigma_xx_mpa=100.0,
        rms_error_mpa=rms,
        maximum_relative_error=max_rel,
    )


def test_refinement_claim_is_permitted_only_when_declared_criteria_are_met() -> None:
    assessment = assess_axial_refinement(
        [_level(20.0, 6.0, 0.10), _level(14.0, 4.0, 0.07), _level(10.0, 2.0, 0.05)],
        100.0,
    )
    assert assessment.stress_convergence_claim is True
    assert assessment.decision == "STRESS_REFINEMENT_CRITERIA_MET"
    assert assessment.final_rms_relative_error == pytest.approx(0.02)
    assert assessment.coarse_to_fine_rms_ratio == pytest.approx(1.0 / 3.0)
    assert "NOT_ARBITRARY_MODEL_CONVERGENCE" in assessment.evidence_boundary


def test_refinement_claim_stays_blocked_when_final_error_is_too_large() -> None:
    assessment = assess_axial_refinement(
        [_level(20.0, 8.0, 0.12), _level(14.0, 6.0, 0.10), _level(10.0, 4.0, 0.09)],
        100.0,
    )
    assert assessment.stress_convergence_claim is False
    assert assessment.decision == "STRESS_REFINEMENT_CLAIM_BLOCKED"


def test_refinement_levels_must_be_coarse_to_fine_and_complete() -> None:
    with pytest.raises(AxialStepVerificationError, match="coarse-to-fine"):
        assess_axial_refinement(
            [_level(10.0, 5.0, 0.1), _level(14.0, 4.0, 0.08), _level(8.0, 3.0, 0.06)],
            100.0,
        )
    with pytest.raises(AxialStepVerificationError, match="exactly 3"):
        assess_axial_refinement([_level(20.0, 6.0, 0.1), _level(10.0, 3.0, 0.05)], 100.0)


def test_policy_rejects_less_than_three_levels() -> None:
    with pytest.raises(AxialStepVerificationError, match="at least three"):
        AxialRefinementPolicy(expected_level_count=2).validate()
