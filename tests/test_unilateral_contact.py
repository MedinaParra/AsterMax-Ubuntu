from __future__ import annotations

import math

import pytest

from astermax.contact.unilateral import (
    ContactState,
    UnilateralSpringContactProblem,
    solve_unilateral_spring_contact,
    solve_unilateral_spring_contact_sweep,
)


K = 10000.0
G0 = 0.20
ACTIVATION = K * G0


def _solve(load_n: float):
    return solve_unilateral_spring_contact(
        UnilateralSpringContactProblem(K, G0, load_n)
    )


def test_open_contact_matches_unconstrained_elastic_solution():
    result = _solve(1000.0)
    assert result.state == ContactState.OPEN
    assert result.displacement_mm == pytest.approx(0.10, abs=1.0e-15)
    assert result.signed_gap_mm == pytest.approx(0.10, abs=1.0e-15)
    assert result.contact_reaction_n == 0.0
    assert result.spring_force_n == pytest.approx(1000.0, abs=1.0e-10)
    assert result.force_residual_n == 0.0
    assert result.complementarity_n_mm == 0.0
    assert result.penetration_mm == 0.0
    assert result.exact_no_penetration is True


def test_exact_activation_is_touching_with_zero_reaction():
    result = _solve(ACTIVATION)
    assert result.state == ContactState.TOUCHING_ZERO_REACTION
    assert result.displacement_mm == pytest.approx(G0, abs=1.0e-15)
    assert result.signed_gap_mm == 0.0
    assert result.contact_reaction_n == 0.0
    assert result.spring_force_n == pytest.approx(ACTIVATION, abs=1.0e-10)
    assert result.force_residual_n == 0.0
    assert result.complementarity_n_mm == 0.0


def test_active_contact_enforces_exact_no_penetration_and_equilibrium():
    result = _solve(5000.0)
    assert result.state == ContactState.ACTIVE
    assert result.displacement_mm == pytest.approx(G0, abs=1.0e-15)
    assert result.signed_gap_mm == 0.0
    assert result.contact_reaction_n == pytest.approx(3000.0, abs=1.0e-10)
    assert result.spring_force_n == pytest.approx(2000.0, abs=1.0e-10)
    assert result.spring_force_n + result.contact_reaction_n == pytest.approx(5000.0, abs=1.0e-10)
    assert result.force_residual_n == 0.0
    assert result.complementarity_n_mm == 0.0
    assert result.penetration_mm == 0.0
    assert result.exact_no_penetration is True
    assert result.friction_solved is False
    assert result.contact_fea_executed is False
    assert result.industrial_validation_claimed is False


def test_opening_load_never_creates_tensile_contact_reaction():
    result = _solve(-1500.0)
    assert result.state == ContactState.OPEN
    assert result.displacement_mm == pytest.approx(-0.15, abs=1.0e-15)
    assert result.signed_gap_mm == pytest.approx(0.35, abs=1.0e-15)
    assert result.contact_reaction_n == 0.0
    assert result.contact_reaction_n >= 0.0
    assert result.force_residual_n == 0.0


def test_zero_initial_gap_opens_under_tension_and_activates_under_compression():
    opening = solve_unilateral_spring_contact(
        UnilateralSpringContactProblem(2500.0, 0.0, -100.0)
    )
    touching = solve_unilateral_spring_contact(
        UnilateralSpringContactProblem(2500.0, 0.0, 0.0)
    )
    active = solve_unilateral_spring_contact(
        UnilateralSpringContactProblem(2500.0, 0.0, 100.0)
    )
    assert opening.state == ContactState.OPEN
    assert opening.signed_gap_mm > 0.0
    assert opening.contact_reaction_n == 0.0
    assert touching.state == ContactState.TOUCHING_ZERO_REACTION
    assert touching.signed_gap_mm == 0.0
    assert active.state == ContactState.ACTIVE
    assert active.displacement_mm == 0.0
    assert active.contact_reaction_n == pytest.approx(100.0, abs=1.0e-12)


def test_load_sweep_crosses_activation_monotonically_without_penetration():
    loads = (-1000.0, 0.0, 1000.0, 2000.0, 3000.0, 5000.0)
    results = solve_unilateral_spring_contact_sweep(
        stiffness_n_per_mm=K,
        initial_gap_mm=G0,
        applied_loads_n=loads,
    )
    assert [result.state for result in results] == [
        ContactState.OPEN,
        ContactState.OPEN,
        ContactState.OPEN,
        ContactState.TOUCHING_ZERO_REACTION,
        ContactState.ACTIVE,
        ContactState.ACTIVE,
    ]
    assert [result.displacement_mm for result in results] == pytest.approx(
        [-0.10, 0.0, 0.10, 0.20, 0.20, 0.20], abs=1.0e-15
    )
    assert [result.contact_reaction_n for result in results] == pytest.approx(
        [0.0, 0.0, 0.0, 0.0, 1000.0, 3000.0], abs=1.0e-10
    )
    assert all(result.signed_gap_mm >= 0.0 for result in results)
    assert all(result.contact_reaction_n >= 0.0 for result in results)
    assert all(result.complementarity_n_mm == 0.0 for result in results)
    assert all(result.force_residual_n == 0.0 for result in results)
    assert all(result.exact_no_penetration for result in results)


def test_force_tolerance_is_dimensional_and_does_not_mix_with_gap_tolerance():
    result = solve_unilateral_spring_contact(
        UnilateralSpringContactProblem(K, G0, ACTIVATION + 5.0e-10),
        force_tolerance_n=1.0e-9,
        gap_tolerance_mm=1.0e-15,
    )
    assert result.state == ContactState.TOUCHING_ZERO_REACTION
    assert result.signed_gap_mm == 0.0
    assert result.contact_reaction_n == 0.0
    assert abs(result.force_residual_n) <= 1.0e-9


def test_problem_validation_fails_closed():
    with pytest.raises(ValueError, match="stiffness"):
        UnilateralSpringContactProblem(0.0, 0.2, 100.0)
    with pytest.raises(ValueError, match="gap"):
        UnilateralSpringContactProblem(1000.0, -0.1, 100.0)
    with pytest.raises(ValueError, match="finite"):
        UnilateralSpringContactProblem(1000.0, 0.1, math.inf)
    with pytest.raises(ValueError, match="at least one"):
        solve_unilateral_spring_contact_sweep(
            stiffness_n_per_mm=1000.0,
            initial_gap_mm=0.1,
            applied_loads_n=(),
        )
    with pytest.raises(ValueError, match="force_tolerance"):
        solve_unilateral_spring_contact(
            UnilateralSpringContactProblem(1000.0, 0.1, 100.0),
            force_tolerance_n=-1.0,
        )
