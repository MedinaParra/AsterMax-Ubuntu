import pytest
from pydantic import ValidationError

from astermax.solver.reaction_target_closure import (
    ClosureControllerStatus,
    ReactionTargetClosurePlanV1,
    ReactionTrialV1,
    evaluate_reaction_target_closure,
)


def plan() -> ReactionTargetClosurePlanV1:
    return ReactionTargetClosurePlanV1(
        gap_mm=0.25,
        target_reaction_n=1_192_200.0,
        lower_displacement_mm=0.25,
        upper_displacement_mm=0.30,
        reaction_tolerance_fraction=0.02,
        max_trials=12,
    )


def test_initial_trial_is_lower_bracket() -> None:
    decision = evaluate_reaction_target_closure(plan(), [])
    assert decision.status == ClosureControllerStatus.NEED_TRIAL
    assert decision.next_displacement_mm == pytest.approx(0.25)


def test_upper_bracket_requested_after_low_reaction() -> None:
    decision = evaluate_reaction_target_closure(
        plan(),
        [ReactionTrialV1(displacement_mm=0.25, reaction_n=0.0)],
    )
    assert decision.status == ClosureControllerStatus.NEED_TRIAL
    assert decision.next_displacement_mm == pytest.approx(0.30)


def test_bisection_after_target_is_bracketed() -> None:
    decision = evaluate_reaction_target_closure(
        plan(),
        [
            ReactionTrialV1(displacement_mm=0.25, reaction_n=0.0),
            ReactionTrialV1(displacement_mm=0.30, reaction_n=2_000_000.0),
        ],
    )
    assert decision.status == ClosureControllerStatus.NEED_TRIAL
    assert decision.next_displacement_mm == pytest.approx(0.275)
    assert decision.reason == "bisect_reaction_bracket"


def test_reaction_target_converges_within_tolerance() -> None:
    decision = evaluate_reaction_target_closure(
        plan(),
        [
            ReactionTrialV1(displacement_mm=0.25, reaction_n=0.0),
            ReactionTrialV1(
                displacement_mm=0.262,
                reaction_n=1_180_000.0,
                contact_active_fraction=0.82,
            ),
            ReactionTrialV1(displacement_mm=0.30, reaction_n=2_000_000.0),
        ],
    )
    assert decision.status == ClosureControllerStatus.CONVERGED
    assert decision.achieved_displacement_mm == pytest.approx(0.262)
    assert decision.achieved_contact_active_fraction == pytest.approx(0.82)


def test_target_above_frozen_upper_bracket_fails_closed() -> None:
    decision = evaluate_reaction_target_closure(
        plan(),
        [
            ReactionTrialV1(displacement_mm=0.25, reaction_n=0.0),
            ReactionTrialV1(displacement_mm=0.30, reaction_n=500_000.0),
        ],
    )
    assert decision.status == ClosureControllerStatus.BLOCKED
    assert decision.reason == "target_above_upper_bracket_reaction"


def test_non_monotone_reaction_history_fails_closed() -> None:
    decision = evaluate_reaction_target_closure(
        plan(),
        [
            ReactionTrialV1(displacement_mm=0.25, reaction_n=100_000.0),
            ReactionTrialV1(displacement_mm=0.27, reaction_n=800_000.0),
            ReactionTrialV1(displacement_mm=0.29, reaction_n=700_000.0),
        ],
    )
    assert decision.status == ClosureControllerStatus.BLOCKED
    assert decision.reason == "non_monotone_reaction_history"


def test_nonconverged_solver_trial_fails_closed() -> None:
    decision = evaluate_reaction_target_closure(
        plan(),
        [
            ReactionTrialV1(
                displacement_mm=0.25,
                reaction_n=0.0,
                solver_converged=False,
            )
        ],
    )
    assert decision.status == ClosureControllerStatus.BLOCKED
    assert decision.reason == "nonconverged_solver_trial_present"


def test_duplicate_displacement_trial_fails_closed() -> None:
    decision = evaluate_reaction_target_closure(
        plan(),
        [
            ReactionTrialV1(displacement_mm=0.25, reaction_n=0.0),
            ReactionTrialV1(displacement_mm=0.25, reaction_n=100.0),
        ],
    )
    assert decision.status == ClosureControllerStatus.BLOCKED
    assert decision.reason == "duplicate_displacement_trial"


def test_authoritative_promotion_is_rejected_by_contract() -> None:
    with pytest.raises(ValidationError):
        ReactionTrialV1(
            displacement_mm=0.262,
            reaction_n=1_192_200.0,
            result_class="SOLVER_RESULT",
        )


def test_lower_bound_cannot_be_below_preserved_gap() -> None:
    with pytest.raises(ValidationError):
        ReactionTargetClosurePlanV1(
            gap_mm=0.25,
            target_reaction_n=1_192_200.0,
            lower_displacement_mm=0.20,
            upper_displacement_mm=0.30,
        )
