from __future__ import annotations

import numpy as np
import pytest

from astermax.contact import (
    ContactState,
    solve_tet10_single_dof_unilateral_contact,
)
from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet4 import IsotropicMaterial


MATERIAL = IsotropicMaterial(young_modulus_mpa=200_000.0, poisson_ratio=0.30)
INITIAL_GAP_MM = 0.01
CONTACT_DOF = 3 * 3 + 2  # apex node 3, +Z closing direction
BASE_NODES = np.asarray([0, 1, 2, 4, 5, 6], dtype=int)
FIXED_DOFS = np.asarray(
    [3 * node + component for node in BASE_NODES for component in range(3)],
    dtype=int,
)


def _fixture() -> tuple[np.ndarray, np.ndarray]:
    vertices = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [0.0, 10.0, 0.0],
            [0.0, 0.0, 10.0],
        ],
        dtype=float,
    )
    nodes = straight_sided_tet10_from_vertices(vertices)
    elements = np.arange(10, dtype=int).reshape(1, 10)
    return nodes, elements


def _loads(force_n: float) -> np.ndarray:
    nodes, _ = _fixture()
    loads = np.zeros(nodes.shape[0] * 3, dtype=float)
    loads[CONTACT_DOF] = force_n
    return loads


def _activation_load_n() -> float:
    nodes, elements = _fixture()
    unit = solve_linear_static_tet10(
        nodes,
        elements,
        MATERIAL,
        _loads(1.0),
        FIXED_DOFS,
    )
    compliance_mm_per_n = float(unit.displacement_mm.reshape(-1)[CONTACT_DOF])
    assert compliance_mm_per_n > 0.0
    return INITIAL_GAP_MM / compliance_mm_per_n


def _solve(force_n: float):
    nodes, elements = _fixture()
    return solve_tet10_single_dof_unilateral_contact(
        nodes_mm=nodes,
        elements=elements,
        material=MATERIAL,
        loads_n=_loads(force_n),
        fixed_dofs=FIXED_DOFS,
        contact_dof=CONTACT_DOF,
        initial_gap_mm=INITIAL_GAP_MM,
        force_tolerance_n=1.0e-6,
        gap_tolerance_mm=1.0e-9,
    )


def test_open_contact_matches_unconstrained_tet10_solution() -> None:
    activation = _activation_load_n()
    force = 0.5 * activation
    result = _solve(force)
    nodes, elements = _fixture()
    baseline = solve_linear_static_tet10(
        nodes,
        elements,
        MATERIAL,
        _loads(force),
        FIXED_DOFS,
    )

    assert result.state == ContactState.OPEN
    assert result.contact_reaction_n == 0.0
    assert result.signed_gap_mm > 0.0
    assert result.exact_no_penetration is True
    assert np.allclose(result.displacement_mm, baseline.displacement_mm, rtol=1.0e-10, atol=1.0e-12)
    assert result.integration_point_stress_mpa.shape == (1, 4, 6)
    assert result.integration_point_von_mises_mpa.shape == (1, 4)
    assert np.isfinite(result.integration_point_stress_mpa).all()


def test_exact_condensed_activation_is_touching_with_zero_reaction() -> None:
    activation = _activation_load_n()
    result = _solve(activation)

    assert result.state == ContactState.TOUCHING_ZERO_REACTION
    assert result.displacement_mm.reshape(-1)[CONTACT_DOF] == pytest.approx(INITIAL_GAP_MM, abs=1.0e-9)
    assert result.signed_gap_mm == 0.0
    assert result.contact_reaction_n == 0.0
    assert result.penetration_mm == 0.0
    assert result.complementarity_n_mm == 0.0


def test_active_contact_clamps_dof_and_matches_condensed_reaction() -> None:
    activation = _activation_load_n()
    force = 1.5 * activation
    result = _solve(force)

    assert result.state == ContactState.ACTIVE
    assert result.displacement_mm.reshape(-1)[CONTACT_DOF] == pytest.approx(INITIAL_GAP_MM, abs=1.0e-10)
    assert result.signed_gap_mm == 0.0
    assert result.contact_reaction_n == pytest.approx(force - activation, rel=1.0e-9, abs=1.0e-6)
    assert result.raw_constraint_reaction_n == pytest.approx(-(force - activation), rel=1.0e-9, abs=1.0e-6)
    assert result.complementarity_n_mm == 0.0
    assert result.penetration_mm == 0.0
    assert result.free_equilibrium_residual_norm_n <= 1.0e-6
    assert result.finite_element_contact_executed is True
    assert result.deformable_tet10_contact is True
    assert result.contact_pressure_recovered is False
    assert result.friction_solved is False
    assert result.industrial_validation_claimed is False
    assert result.ot1613_result_claimed is False
    assert result.ansys_equivalence_claimed is False


def test_opening_load_never_generates_tensile_contact() -> None:
    activation = _activation_load_n()
    result = _solve(-0.5 * activation)

    assert result.state == ContactState.OPEN
    assert result.contact_reaction_n == 0.0
    assert result.free_trial_contact_displacement_mm < 0.0
    assert result.signed_gap_mm > INITIAL_GAP_MM


def test_active_stress_field_is_real_tet10_recovery_not_scalar_proxy() -> None:
    activation = _activation_load_n()
    result = _solve(2.0 * activation)

    assert result.state == ContactState.ACTIVE
    assert result.integration_point_stress_mpa.shape == (1, 4, 6)
    assert result.integration_point_von_mises_mpa.shape == (1, 4)
    assert np.isfinite(result.integration_point_stress_mpa).all()
    assert np.isfinite(result.integration_point_von_mises_mpa).all()
    assert float(np.max(result.integration_point_von_mises_mpa)) > 0.0


def test_contact_dof_cannot_be_an_existing_fixed_support() -> None:
    nodes, elements = _fixture()
    with pytest.raises(ValueError, match="contact_dof cannot already be"):
        solve_tet10_single_dof_unilateral_contact(
            nodes_mm=nodes,
            elements=elements,
            material=MATERIAL,
            loads_n=_loads(1.0),
            fixed_dofs=FIXED_DOFS,
            contact_dof=int(FIXED_DOFS[0]),
            initial_gap_mm=INITIAL_GAP_MM,
        )


def test_invalid_contact_inputs_fail_closed() -> None:
    nodes, elements = _fixture()
    with pytest.raises(ValueError, match="initial_gap_mm"):
        solve_tet10_single_dof_unilateral_contact(
            nodes_mm=nodes,
            elements=elements,
            material=MATERIAL,
            loads_n=_loads(1.0),
            fixed_dofs=FIXED_DOFS,
            contact_dof=CONTACT_DOF,
            initial_gap_mm=-0.1,
        )
    with pytest.raises(ValueError, match="contact_dof is out of range"):
        solve_tet10_single_dof_unilateral_contact(
            nodes_mm=nodes,
            elements=elements,
            material=MATERIAL,
            loads_n=_loads(1.0),
            fixed_dofs=FIXED_DOFS,
            contact_dof=nodes.shape[0] * 3,
            initial_gap_mm=INITIAL_GAP_MM,
        )
