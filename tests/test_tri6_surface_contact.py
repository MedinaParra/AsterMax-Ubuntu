from __future__ import annotations

import numpy as np
import pytest

from astermax.contact import (
    TRI6_GAUSS_BARYCENTRIC,
    solve_tet10_tri6_surface_pressure_contact,
    tri6_shape_functions,
    tri6_surface_operator,
    tri6_surface_pressure_generalized_force,
)
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet4 import IsotropicMaterial


MATERIAL = IsotropicMaterial(young_modulus_mpa=200_000.0, poisson_ratio=0.30)
FACE_NODES = np.asarray([0, 1, 2, 4, 5, 6], dtype=int)
SUPPORT_NODES = np.asarray([3, 7, 8, 9], dtype=int)
FIXED_DOFS = np.asarray(
    [3 * node + component for node in SUPPORT_NODES for component in range(3)],
    dtype=int,
)
NORMAL = np.asarray([0.0, 0.0, 1.0], dtype=float)


def fixture() -> tuple[np.ndarray, np.ndarray]:
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
    return nodes, np.arange(10, dtype=int).reshape(1, 10)


def test_tri6_shape_partition_and_surface_weights() -> None:
    nodes, _ = fixture()
    operator, barycentric, weights = tri6_surface_operator(
        nodes_mm=nodes,
        face_nodes=FACE_NODES,
        contact_normal=NORMAL,
    )
    assert operator.shape == (3, nodes.shape[0] * 3)
    assert np.allclose(barycentric, TRI6_GAUSS_BARYCENTRIC)
    assert np.allclose([np.sum(tri6_shape_functions(point)) for point in barycentric], 1.0)
    assert np.isclose(np.sum(weights), 50.0)
    assert np.allclose(weights, 50.0 / 3.0)


def test_uniform_10_mpa_is_primary_contact_solution() -> None:
    nodes, elements = fixture()
    target_pressure = np.full(3, 10.0, dtype=float)
    loads = tri6_surface_pressure_generalized_force(
        nodes_mm=nodes,
        face_nodes=FACE_NODES,
        contact_normal=NORMAL,
        pressure_mpa=target_pressure,
    )
    result = solve_tet10_tri6_surface_pressure_contact(
        nodes_mm=nodes,
        elements=elements,
        material=MATERIAL,
        loads_n=loads,
        fixed_dofs=FIXED_DOFS,
        face_nodes=FACE_NODES,
        contact_normal=NORMAL,
        initial_gaps_mm=np.zeros(3),
    )

    assert result.pressure_is_primary_contact_unknown is True
    assert result.contact_pressure_recovered_from_nodal_reactions is False
    assert result.penalty_method_used is False
    assert result.surface_integration_contact_executed is True
    assert np.allclose(result.contact_pressure_mpa, target_pressure, rtol=0.0, atol=1.0e-8)
    assert np.allclose(result.integration_displacements_mm, 0.0, atol=1.0e-10)
    assert np.allclose(result.signed_gaps_mm, 0.0, atol=1.0e-10)
    assert np.all(result.contact_point_forces_n > 0.0)
    assert result.free_equilibrium_residual_norm_n <= 1.0e-6
    assert result.exact_no_penetration is True
    assert result.active_contact_indices == (0, 1, 2)
    assert np.allclose(result.displacement_mm, 0.0, atol=1.0e-10)


def test_opening_load_keeps_surface_pressure_zero() -> None:
    nodes, elements = fixture()
    opening = -tri6_surface_pressure_generalized_force(
        nodes_mm=nodes,
        face_nodes=FACE_NODES,
        contact_normal=NORMAL,
        pressure_mpa=np.full(3, 4.0),
    )
    result = solve_tet10_tri6_surface_pressure_contact(
        nodes_mm=nodes,
        elements=elements,
        material=MATERIAL,
        loads_n=opening,
        fixed_dofs=FIXED_DOFS,
        face_nodes=FACE_NODES,
        contact_normal=NORMAL,
        initial_gaps_mm=np.zeros(3),
    )
    assert np.allclose(result.contact_pressure_mpa, 0.0)
    assert all(state.value == "OPEN" for state in result.states)
    assert np.all(result.signed_gaps_mm > 0.0)
    assert result.active_contact_indices == ()


def test_curved_tri6_face_fails_closed() -> None:
    nodes, elements = fixture()
    nodes = nodes.copy()
    nodes[FACE_NODES[3], 2] += 0.1
    with pytest.raises(ValueError, match="straight-sided TRI6"):
        solve_tet10_tri6_surface_pressure_contact(
            nodes_mm=nodes,
            elements=elements,
            material=MATERIAL,
            loads_n=np.zeros(nodes.shape[0] * 3),
            fixed_dofs=FIXED_DOFS,
            face_nodes=FACE_NODES,
            contact_normal=NORMAL,
            initial_gaps_mm=np.zeros(3),
        )
