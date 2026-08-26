from __future__ import annotations

from dataclasses import asdict, dataclass
import math


@dataclass(frozen=True)
class AccuracyBudgetSample:
    element_family: str
    mesh_size_mm: float
    node_count: int
    element_count: int
    dofs: int
    tip_displacement_y_mm: float
    tip_error_percent: float


@dataclass(frozen=True)
class ComparableDofPair:
    tet4: AccuracyBudgetSample
    tet10: AccuracyBudgetSample
    dof_ratio: float
    tet10_error_improvement_factor: float


@dataclass(frozen=True)
class AccuracyEfficiencyPolicy:
    min_pairs: int = 3
    max_pair_dof_ratio: float = 1.50
    min_geometric_mean_error_improvement: float = 2.0
    require_tet10_lower_error_each_pair: bool = True


@dataclass(frozen=True)
class AccuracyEfficiencyDecision:
    passed: bool
    checks: dict[str, bool]
    metrics: dict[str, float | int | None]
    policy: dict[str, float | int | bool]


def _validate_samples(samples: list[AccuracyBudgetSample], family: str) -> list[AccuracyBudgetSample]:
    if not samples:
        return []
    ordered = sorted(samples, key=lambda sample: sample.dofs)
    seen = set()
    for sample in ordered:
        if sample.element_family != family:
            raise ValueError(f"expected {family} sample, got {sample.element_family}")
        if sample.dofs <= 0 or sample.node_count <= 0 or sample.element_count <= 0:
            raise ValueError("sample counts and DOFs must be positive")
        if sample.dofs != sample.node_count * 3:
            raise ValueError("sample DOFs must equal 3 * node_count")
        if sample.dofs in seen:
            raise ValueError("duplicate DOF budgets are not allowed within an element family")
        seen.add(sample.dofs)
        if not math.isfinite(sample.tip_error_percent) or sample.tip_error_percent < 0.0:
            raise ValueError("tip error must be finite and non-negative")
        if not math.isfinite(sample.tip_displacement_y_mm):
            raise ValueError("tip displacement must be finite")
    return ordered


def match_comparable_dofs(
    tet4_samples: list[AccuracyBudgetSample],
    tet10_samples: list[AccuracyBudgetSample],
    *,
    max_dof_ratio: float = 1.50,
) -> list[ComparableDofPair]:
    """Return a deterministic one-to-one monotonic matching of comparable DOF budgets.

    The dynamic program maximizes the number of valid pairs first and then minimizes
    total absolute log(DOF ratio).  A sample can be used at most once.  This avoids
    hand-picking favorable pairs after numerical errors are known: matching depends
    only on DOF counts and the predeclared comparability ratio.
    """
    if max_dof_ratio < 1.0 or not math.isfinite(max_dof_ratio):
        raise ValueError("max_dof_ratio must be finite and >= 1")
    a = _validate_samples(tet4_samples, "TET4")
    b = _validate_samples(tet10_samples, "TET10")
    n, m = len(a), len(b)

    # state -> (pair_count, total_log_mismatch, list[(i,j)])
    dp: list[list[tuple[int, float, list[tuple[int, int]]]]] = [
        [(0, 0.0, []) for _ in range(m + 1)] for _ in range(n + 1)
    ]

    def better(
        left: tuple[int, float, list[tuple[int, int]]],
        right: tuple[int, float, list[tuple[int, int]]],
    ) -> tuple[int, float, list[tuple[int, int]]]:
        if left[0] != right[0]:
            return left if left[0] > right[0] else right
        if abs(left[1] - right[1]) > 1.0e-15:
            return left if left[1] < right[1] else right
        return left if left[2] <= right[2] else right

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            best = better(dp[i - 1][j], dp[i][j - 1])
            low = min(a[i - 1].dofs, b[j - 1].dofs)
            high = max(a[i - 1].dofs, b[j - 1].dofs)
            ratio = high / low
            if ratio <= max_dof_ratio:
                prev = dp[i - 1][j - 1]
                paired = (
                    prev[0] + 1,
                    prev[1] + abs(math.log(a[i - 1].dofs / b[j - 1].dofs)),
                    prev[2] + [(i - 1, j - 1)],
                )
                best = better(best, paired)
            dp[i][j] = best

    pairs: list[ComparableDofPair] = []
    for i, j in dp[n][m][2]:
        t4 = a[i]
        t10 = b[j]
        ratio = max(t4.dofs, t10.dofs) / min(t4.dofs, t10.dofs)
        if t10.tip_error_percent == 0.0:
            improvement = math.inf if t4.tip_error_percent > 0.0 else 1.0
        else:
            improvement = t4.tip_error_percent / t10.tip_error_percent
        pairs.append(
            ComparableDofPair(
                tet4=t4,
                tet10=t10,
                dof_ratio=float(ratio),
                tet10_error_improvement_factor=float(improvement),
            )
        )
    return pairs


def evaluate_accuracy_efficiency(
    pairs: list[ComparableDofPair],
    policy: AccuracyEfficiencyPolicy = AccuracyEfficiencyPolicy(),
) -> AccuracyEfficiencyDecision:
    if policy.min_pairs < 1:
        raise ValueError("min_pairs must be >= 1")
    if policy.max_pair_dof_ratio < 1.0:
        raise ValueError("max_pair_dof_ratio must be >= 1")
    if policy.min_geometric_mean_error_improvement <= 0.0:
        raise ValueError("minimum improvement factor must be positive")

    finite = all(
        math.isfinite(pair.dof_ratio)
        and math.isfinite(pair.tet4.tip_error_percent)
        and math.isfinite(pair.tet10.tip_error_percent)
        and pair.tet4.tip_error_percent >= 0.0
        and pair.tet10.tip_error_percent >= 0.0
        for pair in pairs
    )
    comparable = all(pair.dof_ratio <= policy.max_pair_dof_ratio for pair in pairs)
    lower_each = all(
        pair.tet10.tip_error_percent < pair.tet4.tip_error_percent for pair in pairs
    )
    improvements = [pair.tet10_error_improvement_factor for pair in pairs]
    finite_positive_improvements = [value for value in improvements if math.isfinite(value) and value > 0.0]
    geometric_mean = None
    if len(finite_positive_improvements) == len(pairs) and pairs:
        geometric_mean = math.exp(
            sum(math.log(value) for value in finite_positive_improvements) / len(finite_positive_improvements)
        )

    checks = {
        "minimum_pair_count": len(pairs) >= policy.min_pairs,
        "finite_metrics": finite,
        "comparable_dof_budget": comparable,
        "tet10_lower_error_each_pair": lower_each or not policy.require_tet10_lower_error_each_pair,
        "geometric_mean_error_improvement": bool(
            geometric_mean is not None
            and geometric_mean >= policy.min_geometric_mean_error_improvement
        ),
    }
    return AccuracyEfficiencyDecision(
        passed=all(checks.values()),
        checks=checks,
        metrics={
            "pair_count": len(pairs),
            "max_observed_dof_ratio": max((pair.dof_ratio for pair in pairs), default=None),
            "geometric_mean_tet10_error_improvement_factor": geometric_mean,
            "minimum_pair_improvement_factor": min(improvements, default=None),
        },
        policy=asdict(policy),
    )
