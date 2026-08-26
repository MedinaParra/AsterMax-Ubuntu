from __future__ import annotations

import itertools

import numpy as np
import pytest

from astermax.contact import ContactState, solve_tet10_multipoint_unilateral_contact
from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet4 import IsotropicMaterial


MATERIAL = IsotropicMaterial(young_modulus_mpa=200_000.0, poisson_ratio=0.30)
CONTACT_NODES = np.asarray([0, 1, 2, 4, 5, 6], dtype=int)  # complete top TRI6 face
CONTACT_DOFS = 3 * CONTACT_NODES + 2
SUPPORT_NODES = np.asarray([3, 7, 8, 9], dtype=int)
FIXED_DOFS = np.asarray(
    [3 * node + component for node in SUPPORT_NODES for component in range(3)],
    dtype=int,
)
CONTACT_LOADS_N = np.asarray([420.0, 520.0, 610.0, 470.0, 560.0, 650.0], dtype=float)
GAP_FACTORS = np.asarray([0.55, 1.40, 0.75, 1.25, 0.65, 1.50], dtype=float)


def _fixture() -> tuple[np.ndarray, np.ndarray]:
    # Vertex order is deliberately positive for the TET10 Jacobian while the
    # complete quadratic face 0-1-2/4-5-6 remains on the z=10 contact plane.
    vertices = np.asarray(
        [
            [-5.0, -5.0, 10.0],
            [0.0, 5.0, 10.0],
            [5.0, -5.0, 10.0],
            [0.0, 0.0, 0.0],
        ],
        dtype=float,
    )
    nodes = straight_sided_tet10_from_vertices(vertices)
    elements = np.arange(10, dtype=int).reshape(1, 10)
    assert np.allclose(nodes[CONTACT_NODES, 2], 10.0)
    return nodes, elements


def _load_vector(contact_loads_n: np.ndarray = CONTACT_LOADS_N) -> np.ndarray:
    nodes, _ = _fixture()
    loads = np.zeros(nodes.shape[0] * 3, dtype=float)
    loads[CONTACT_DOFS] = np.asarray(contact_loads_n, dtype=float)
    return loads


def _contact_compliance() -> np.ndarray:
    nodes, elements = _fixture()
    compliance = np.zeros((CONTACT_DOFS.size, CONTACT_DOFS.size), dtype=float)
    for column, dof in enumerate(CONTACT_DOFS):
        loads = np.zeros(nodes.shape[0] * 3, dtype=float)
        loads[int(dof)] = 1.0
        result = solve_linear_static_tet10(
            nodes,
            elements,
            MATERIAL,
            loads,
            FIXED_DOFS,
        )
        compliance[:, column] = result.displacement_mm.reshape(-1)[CONTACT_DOFS]
    assert np.all(np.isfinite(compliance))
    assert np.allclose(compliance, compliance.T, rtol=1.0e-9, atol=1.0e-12)
    return compliance


def _designed_gaps() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    compliance = _contact_compliance()
    free_u = compliance @ CONTACT_LOADS_N
    assert np.all(free_u > 0.0)
    gaps = free_u * GAP_FACTORS
    assert np.all(gaps > 0.0)
    return compliance, free_u, gaps


def _enumerate_condensed_reference(
    compliance: np.ndarray,
    loads_n: np.ndarray,
    gaps_mm: np.ndarray,
    *,
    force_tolerance_n: float = 1.0e-7,
    gap_tolerance_mm: float = 1.0e-10,
) -> tuple[np.ndarray, np.ndarray, tuple[int, ...]]:
    """Independent small-LCP reference by exhaustive active-set enumeration."""
    free_u = compliance @ loads_n
    n = gaps_mm.size
    valid: list[tuple[np.ndarray, np.ndarray, tuple[int, ...]]] = []

    for mask_bits in itertools.product((False, True), repeat=n):
        active = np.flatnonzero(np.asarray(mask_bits, dtype=bool))
        reaction = np.zeros(n, dtype=float)
        if active.size:
            caa = compliance[np.ix_(active, active)]
            rhs = free_u[active] - gaps_mm[active]
            try:
                reaction_active = np.linalg.solve(caa, rhs)
            except np.linalg.LinAlgError:
                continue
            reaction[active] = reaction_active

        displacement = free_u - compliance @ reaction
        inactive = np.setdiff1d(np.arange(n, dtype=int), active)
        if active.size and np.any(reaction[active] < -force_tolerance_n):
            continue
        if active.size and np.any(np.abs(displacement[active] - gaps_mm[active]) > gap_tolerance_mm):
            continue
        if inactive.size and np.any(displacement[inactive] > gaps_mm[inactive] + gap_tolerance_mm):
            continue
        if np.any((gaps_mm - displacement) * np.maximum(reaction, 0.0) > 1.0e-8):
            continue

        reaction[np.abs(reaction) <= force_tolerance_n] = 0.0
        canonical = tuple(int(i) for i in np.flatnonzero(reaction > force_tolerance_n))
        valid.append((displacement, reaction, canonical))

    canonical_sets = {entry[2] for entry in valid}
    assert len(canonical_sets) == 1, f"expected unique physical active set, got {canonical_sets}"
    canonical = next(iter(canonical_sets))
    candidates = [entry for entry in valid if entry[2] == canonical]
    displacement, reaction, _ = candidates[0]
    return displacement, reaction, canonical


def test_multipoint_contact_matches_independent_condensed_lcp_reference() -> None:
    compliance, _, gaps = _designed_gaps()
    reference_u, reference_r, reference_active = _enumerate_condensed_reference(
        compliance,
        CONTACT_LOADS_N,
        gaps,
    )
    nodes, elements = _fixture()
    result = solve_tet10_multipoint_unilateral_contact(
        nodes_mm=nodes,
        elements=elements,
        material=MATERIAL,
        loads_n=_load_vector(),
        fixed_dofs=FIXED_DOFS,
        contact_dofs=CONTACT_DOFS,
        initial_gaps_mm=gaps,
        force_tolerance_n=1.0e-7,
        gap_tolerance_mm=1.0e-10,
    )

    actual_u = result.displacement_mm.reshape(-1)[CONTACT_DOFS]
    assert result.converged is True
    assert result.active_contact_indices == reference_active
    assert np.allclose(actual_u, reference_u, rtol=1.0e-9, atol=1.0e-10)
    assert np.allclose(result.contact_reactions_n, reference_r, rtol=1.0e-9, atol=1.0e-7)
    assert len(reference_active) >= 2
    assert len(reference_active) < CONTACT_DOFS.size
    assert result.exact_no_penetration is True
    assert np.all(result.signed_gaps_mm >= -1.0e-10)
    assert np.all(result.contact_reactions_n >= -1.0e-7)
    assert np.all(np.abs(result.complementarity_n_mm) <= 1.0e-8)
    assert result.free_equilibrium_residual_norm_n <= 1.0e-5


def test_open_patch_matches_linear_tet10_when_all_gaps_are_large() -> None:
    compliance, free_u, _ = _designed_gaps()
    gaps = np.maximum(free_u * 2.0, 1.0e-6)
    nodes, elements = _fixture()
    result = solve_tet10_multipoint_unilateral_contact(
        nodes_mm=nodes,
        elements=elements,
        material=MATERIAL,
        loads_n=_load_vector(),
        fixed_dofs=FIXED_DOFS,
        contact_dofs=CONTACT_DOFS,
        initial_gaps_mm=gaps,
    )
    baseline = solve_linear_static_tet10(
        nodes,
        elements,
        MATERIAL,
        _load_vector(),
        FIXED_DOFS,
    )

    assert result.active_contact_indices == ()
    assert all(state == ContactState.OPEN for state in result.states)
    assert np.allclose(result.displacement_mm, baseline.displacement_mm, rtol=1.0e-10, atol=1.0e-12)
    assert np.all(result.contact_reactions_n == 0.0)
    assert np.allclose(compliance @ CONTACT_LOADS_N, free_u)


def test_multipoint_patch_recovers_real_tet10_stress_but_not_pressure() -> None:
    _, _, gaps = _designed_gaps()
    nodes, elements = _fixture()
    result = solve_tet10_multipoint_unilateral_contact(
        nodes_mm=nodes,
        elements=elements,
        material=MATERIAL,
        loads_n=_load_vector(),
        fixed_dofs=FIXED_DOFS,
        contact_dofs=CONTACT_DOFS,
        initial_gaps_mm=gaps,
    )

    assert result.integration_point_stress_mpa.shape == (1, 4, 6)
    assert result.integration_point_von_mises_mpa.shape == (1, 4)
    assert np.isfinite(result.integration_point_stress_mpa).all()
    assert float(np.max(result.integration_point_von_mises_mpa)) > 0.0
    assert result.multipoint_contact is True
    assert result.surface_patch_constraint_set is True
    assert result.contact_pressure_recovered is False
    assert result.friction_solved is False
    assert result.industrial_validation_claimed is False
    assert result.ot1613_result_claimed is False
    assert result.ansys_equivalence_claimed is False


def test_multipoint_contact_input_contract_fails_closed() -> None:
    nodes, elements = _fixture()
    loads = _load_vector()
    with pytest.raises(ValueError, match="at least two"):
        solve_tet10_multipoint_unilateral_contact(
            nodes_mm=nodes,
            elements=elements,
            material=MATERIAL,
            loads_n=loads,
            fixed_dofs=FIXED_DOFS,
            contact_dofs=[int(CONTACT_DOFS[0])],
            initial_gaps_mm=[0.01],
        )
    with pytest.raises(ValueError, match="unique"):
        solve_tet10_multipoint_unilateral_contact(
            nodes_mm=nodes,
            elements=elements,
            material=MATERIAL,
            loads_n=loads,
            fixed_dofs=FIXED_DOFS,
            contact_dofs=[int(CONTACT_DOFS[0]), int(CONTACT_DOFS[0])],
            initial_gaps_mm=[0.01, 0.01],
        )
    with pytest.raises(ValueError, match="match contact_dofs"):
        solve_tet10_multipoint_unilateral_contact(
            nodes_mm=nodes,
            elements=elements,
            material=MATERIAL,
            loads_n=loads,
            fixed_dofs=FIXED_DOFS,
            contact_dofs=CONTACT_DOFS,
            initial_gaps_mm=[0.01, 0.02],
        )
    with pytest.raises(ValueError, match="overlap fixed"):
        solve_tet10_multipoint_unilateral_contact(
            nodes_mm=nodes,
            elements=elements,
            material=MATERIAL,
            loads_n=loads,
            fixed_dofs=FIXED_DOFS,
            contact_dofs=[int(FIXED_DOFS[0]), int(CONTACT_DOFS[1])],
            initial_gaps_mm=[0.01, 0.01],
        )
