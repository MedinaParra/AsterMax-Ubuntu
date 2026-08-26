from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


EXPLORATORY_RESULT_CLASS = "EXPLORATORY_NOT_FOR_ACCEPTANCE"


class ClosureControllerStatus(StrEnum):
    NEED_TRIAL = "NEED_TRIAL"
    CONVERGED = "CONVERGED"
    BLOCKED = "BLOCKED"


class ReactionTargetClosurePlanV1(BaseModel):
    """Fail-closed controller plan for exploratory displacement-controlled closure.

    The imposed displacement is a numerical control variable. It is not bolt elongation,
    nut advance, or an authenticated assembly displacement.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="ReactionTargetClosurePlanV1",
        pattern=r"^ReactionTargetClosurePlanV1$",
    )
    result_class: str = Field(
        default=EXPLORATORY_RESULT_CLASS,
        pattern=r"^EXPLORATORY_NOT_FOR_ACCEPTANCE$",
    )
    gap_mm: float = Field(ge=0)
    target_reaction_n: float = Field(gt=0)
    lower_displacement_mm: float = Field(ge=0)
    upper_displacement_mm: float = Field(gt=0)
    reaction_tolerance_fraction: float = Field(default=0.02, gt=0, le=0.25)
    max_trials: int = Field(default=12, ge=2, le=64)

    @model_validator(mode="after")
    def validate_bracket(self) -> "ReactionTargetClosurePlanV1":
        if self.lower_displacement_mm < self.gap_mm:
            raise ValueError("lower displacement cannot be below the preserved geometric GAP")
        if self.upper_displacement_mm <= self.lower_displacement_mm:
            raise ValueError("upper displacement must exceed lower displacement")
        return self


class ReactionTrialV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    displacement_mm: float = Field(ge=0)
    reaction_n: float = Field(ge=0)
    solver_converged: bool = True
    contact_active_fraction: float | None = Field(default=None, ge=0, le=1)
    result_class: str = Field(
        default=EXPLORATORY_RESULT_CLASS,
        pattern=r"^EXPLORATORY_NOT_FOR_ACCEPTANCE$",
    )


class ReactionTargetClosureDecisionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="ReactionTargetClosureDecisionV1",
        pattern=r"^ReactionTargetClosureDecisionV1$",
    )
    status: ClosureControllerStatus
    result_class: str = Field(
        default=EXPLORATORY_RESULT_CLASS,
        pattern=r"^EXPLORATORY_NOT_FOR_ACCEPTANCE$",
    )
    target_reaction_n: float = Field(gt=0)
    next_displacement_mm: float | None = Field(default=None, ge=0)
    achieved_reaction_n: float | None = Field(default=None, ge=0)
    achieved_displacement_mm: float | None = Field(default=None, ge=0)
    achieved_contact_active_fraction: float | None = Field(default=None, ge=0, le=1)
    reason: str = Field(min_length=1)


def _reaction_error_fraction(target: float, reaction: float) -> float:
    return abs(reaction - target) / target


def evaluate_reaction_target_closure(
    plan: ReactionTargetClosurePlanV1,
    trials: list[ReactionTrialV1],
) -> ReactionTargetClosureDecisionV1:
    """Return the next displacement trial or a fail-closed terminal decision.

    The controller assumes a monotone relationship between imposed closure and total
    compressive reaction. If solver evidence violates that assumption, the controller
    blocks instead of inventing a continuation strategy.
    """

    if len(trials) >= plan.max_trials:
        return ReactionTargetClosureDecisionV1(
            status=ClosureControllerStatus.BLOCKED,
            target_reaction_n=plan.target_reaction_n,
            reason="maximum_trial_budget_exhausted",
        )

    if any(not trial.solver_converged for trial in trials):
        return ReactionTargetClosureDecisionV1(
            status=ClosureControllerStatus.BLOCKED,
            target_reaction_n=plan.target_reaction_n,
            reason="nonconverged_solver_trial_present",
        )

    if not trials:
        return ReactionTargetClosureDecisionV1(
            status=ClosureControllerStatus.NEED_TRIAL,
            target_reaction_n=plan.target_reaction_n,
            next_displacement_mm=plan.lower_displacement_mm,
            reason="evaluate_lower_bracket",
        )

    ordered = sorted(trials, key=lambda trial: trial.displacement_mm)
    displacements = [trial.displacement_mm for trial in ordered]
    if len(displacements) != len(set(displacements)):
        return ReactionTargetClosureDecisionV1(
            status=ClosureControllerStatus.BLOCKED,
            target_reaction_n=plan.target_reaction_n,
            reason="duplicate_displacement_trial",
        )

    if displacements[0] < plan.lower_displacement_mm - 1e-12 or displacements[-1] > plan.upper_displacement_mm + 1e-12:
        return ReactionTargetClosureDecisionV1(
            status=ClosureControllerStatus.BLOCKED,
            target_reaction_n=plan.target_reaction_n,
            reason="trial_outside_frozen_displacement_bracket",
        )

    monotonic_tol = max(1e-6, plan.target_reaction_n * 1e-6)
    for left, right in zip(ordered, ordered[1:]):
        if right.reaction_n + monotonic_tol < left.reaction_n:
            return ReactionTargetClosureDecisionV1(
                status=ClosureControllerStatus.BLOCKED,
                target_reaction_n=plan.target_reaction_n,
                reason="non_monotone_reaction_history",
            )

    best = min(
        ordered,
        key=lambda trial: _reaction_error_fraction(plan.target_reaction_n, trial.reaction_n),
    )
    if _reaction_error_fraction(plan.target_reaction_n, best.reaction_n) <= plan.reaction_tolerance_fraction:
        return ReactionTargetClosureDecisionV1(
            status=ClosureControllerStatus.CONVERGED,
            target_reaction_n=plan.target_reaction_n,
            achieved_reaction_n=best.reaction_n,
            achieved_displacement_mm=best.displacement_mm,
            achieved_contact_active_fraction=best.contact_active_fraction,
            reason="target_reaction_within_tolerance",
        )

    below = [trial for trial in ordered if trial.reaction_n < plan.target_reaction_n]
    above = [trial for trial in ordered if trial.reaction_n > plan.target_reaction_n]

    lower_trial = max(below, key=lambda trial: trial.displacement_mm) if below else None
    upper_trial = min(above, key=lambda trial: trial.displacement_mm) if above else None

    lower_was_tested = any(abs(t.displacement_mm - plan.lower_displacement_mm) <= 1e-12 for t in ordered)
    upper_was_tested = any(abs(t.displacement_mm - plan.upper_displacement_mm) <= 1e-12 for t in ordered)

    if not lower_was_tested:
        return ReactionTargetClosureDecisionV1(
            status=ClosureControllerStatus.NEED_TRIAL,
            target_reaction_n=plan.target_reaction_n,
            next_displacement_mm=plan.lower_displacement_mm,
            reason="evaluate_lower_bracket",
        )

    lower_bracket_trial = min(ordered, key=lambda t: abs(t.displacement_mm - plan.lower_displacement_mm))
    if lower_bracket_trial.reaction_n > plan.target_reaction_n:
        return ReactionTargetClosureDecisionV1(
            status=ClosureControllerStatus.BLOCKED,
            target_reaction_n=plan.target_reaction_n,
            reason="target_below_lower_bracket_reaction",
        )

    if not upper_was_tested:
        return ReactionTargetClosureDecisionV1(
            status=ClosureControllerStatus.NEED_TRIAL,
            target_reaction_n=plan.target_reaction_n,
            next_displacement_mm=plan.upper_displacement_mm,
            reason="evaluate_upper_bracket",
        )

    upper_bracket_trial = min(ordered, key=lambda t: abs(t.displacement_mm - plan.upper_displacement_mm))
    if upper_bracket_trial.reaction_n < plan.target_reaction_n:
        return ReactionTargetClosureDecisionV1(
            status=ClosureControllerStatus.BLOCKED,
            target_reaction_n=plan.target_reaction_n,
            reason="target_above_upper_bracket_reaction",
        )

    if lower_trial is None or upper_trial is None:
        return ReactionTargetClosureDecisionV1(
            status=ClosureControllerStatus.BLOCKED,
            target_reaction_n=plan.target_reaction_n,
            reason="reaction_target_not_bracketed",
        )

    next_displacement = 0.5 * (lower_trial.displacement_mm + upper_trial.displacement_mm)
    if any(abs(next_displacement - trial.displacement_mm) <= 1e-12 for trial in ordered):
        return ReactionTargetClosureDecisionV1(
            status=ClosureControllerStatus.BLOCKED,
            target_reaction_n=plan.target_reaction_n,
            reason="displacement_bisection_stalled",
        )

    return ReactionTargetClosureDecisionV1(
        status=ClosureControllerStatus.NEED_TRIAL,
        target_reaction_n=plan.target_reaction_n,
        next_displacement_mm=next_displacement,
        reason="bisect_reaction_bracket",
    )
