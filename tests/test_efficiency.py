from __future__ import annotations

from astermax.fea.efficiency import (
    AccuracyBudgetSample,
    AccuracyEfficiencyPolicy,
    evaluate_accuracy_efficiency,
    match_comparable_dofs,
)


def _sample(family: str, nodes: int, error: float) -> AccuracyBudgetSample:
    return AccuracyBudgetSample(
        element_family=family,
        mesh_size_mm=1.0,
        node_count=nodes,
        element_count=max(1, nodes * 2),
        dofs=nodes * 3,
        tip_displacement_y_mm=-0.25,
        tip_error_percent=error,
    )


def test_matching_is_one_to_one_and_uses_only_dof_budget() -> None:
    tet4 = [_sample("TET4", 100, 20.0), _sample("TET4", 200, 12.0), _sample("TET4", 400, 8.0)]
    tet10 = [_sample("TET10", 110, 2.0), _sample("TET10", 190, 1.5), _sample("TET10", 390, 1.0)]
    pairs = match_comparable_dofs(tet4, tet10, max_dof_ratio=1.20)
    assert len(pairs) == 3
    assert len({pair.tet4.dofs for pair in pairs}) == 3
    assert len({pair.tet10.dofs for pair in pairs}) == 3
    assert [(pair.tet4.node_count, pair.tet10.node_count) for pair in pairs] == [
        (100, 110),
        (200, 190),
        (400, 390),
    ]


def test_efficiency_gate_passes_only_when_tet10_is_materially_better() -> None:
    pairs = match_comparable_dofs(
        [_sample("TET4", 100, 16.0), _sample("TET4", 200, 10.0), _sample("TET4", 400, 6.0)],
        [_sample("TET10", 105, 2.0), _sample("TET10", 210, 1.5), _sample("TET10", 390, 1.0)],
        max_dof_ratio=1.20,
    )
    decision = evaluate_accuracy_efficiency(
        pairs,
        AccuracyEfficiencyPolicy(
            min_pairs=3,
            max_pair_dof_ratio=1.20,
            min_geometric_mean_error_improvement=2.0,
        ),
    )
    assert decision.passed is True
    assert decision.checks["tet10_lower_error_each_pair"] is True
    assert decision.metrics["geometric_mean_tet10_error_improvement_factor"] > 2.0


def test_efficiency_gate_fails_if_one_comparable_pair_favors_tet4() -> None:
    pairs = match_comparable_dofs(
        [_sample("TET4", 100, 5.0), _sample("TET4", 200, 1.0), _sample("TET4", 400, 4.0)],
        [_sample("TET10", 100, 2.0), _sample("TET10", 200, 2.0), _sample("TET10", 400, 1.0)],
        max_dof_ratio=1.01,
    )
    decision = evaluate_accuracy_efficiency(pairs)
    assert decision.passed is False
    assert decision.checks["tet10_lower_error_each_pair"] is False
