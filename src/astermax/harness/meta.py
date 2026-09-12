from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class MetaDecision(StrEnum):
    RETAIN = "RETAIN"
    ROLLBACK = "ROLLBACK"
    INCONCLUSIVE = "INCONCLUSIVE"


class HarnessMetricsV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mandatory_pass_rate: float = Field(ge=0.0, le=1.0)
    aggregate_score: float = Field(ge=0.0)
    failed_mandatory_cases: list[str] = Field(default_factory=list)
    tool_calls: int = Field(default=0, ge=0)
    retries: int = Field(default=0, ge=0)
    wall_clock_seconds: float = Field(default=0.0, ge=0.0)


class MetaComparisonV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: MetaDecision
    reasons: list[str] = Field(default_factory=list)
    score_delta: float
    budget_ratio: float


def compare_harness_candidate(
    baseline: HarnessMetricsV1,
    candidate: HarnessMetricsV1,
    *,
    min_score_gain: float = 0.01,
    max_budget_ratio: float = 1.25,
) -> MetaComparisonV1:
    reasons: list[str] = []

    if baseline.suite_sha256 != candidate.suite_sha256:
        reasons.append("Baseline and candidate were not evaluated on the same frozen suite.")

    if candidate.failed_mandatory_cases:
        reasons.append("Candidate fails mandatory eval cases.")

    if candidate.mandatory_pass_rate < baseline.mandatory_pass_rate:
        reasons.append("Mandatory pass rate regressed.")

    score_delta = candidate.aggregate_score - baseline.aggregate_score
    baseline_budget = max(baseline.wall_clock_seconds, 1e-9)
    budget_ratio = candidate.wall_clock_seconds / baseline_budget

    if score_delta < min_score_gain:
        reasons.append(
            f"Score gain {score_delta:.6f} is below required minimum {min_score_gain:.6f}."
        )

    if budget_ratio > max_budget_ratio:
        reasons.append(
            f"Wall-clock budget ratio {budget_ratio:.3f} exceeds limit {max_budget_ratio:.3f}."
        )

    decision = MetaDecision.ROLLBACK if reasons else MetaDecision.RETAIN
    return MetaComparisonV1(
        decision=decision,
        reasons=reasons,
        score_delta=score_delta,
        budget_ratio=budget_ratio,
    )
