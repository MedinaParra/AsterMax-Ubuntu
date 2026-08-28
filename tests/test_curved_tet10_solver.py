from __future__ import annotations

import numpy as np
import pytest

from astermax.fea.curved_tet10_solver import (
    audit_curved_tet10_mesh_jacobians,
    solve_linear_static_curved_tet10,
)
from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet4 import IsotropicMaterial


MATERIAL = IsotropicMaterial(young_modulus_mpa=200000.0, poisson_ratio=0.3)


def _valid_curved_single_tet() -> tuple[np.ndarray, np.ndarray]:
    vertices = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [0.0, 10.0, 0.0],
            [0.0, 0.0, 10.0],
        ]
    )
    nodes = straight_sided_tet10_from_vertices(vertices)
    nodes[4] += np.asarray([0.0, 0.25, 0.10])
    nodes[5] += np.asarray([0.10, 0.0, 0.15])
    nodes[7] += np.asarray([0.15, 0.10, 0.0])
    return nodes, np.arange(10, dtype=np.int64).reshape((1, 10))


def test_historical_straight_solver_still_rejects_curved_tet10():
    nodes, elements = _valid_curved_single_tet()
    loads = np.zeros((nodes.shape[0], 3), dtype=float)
    loads[3, 0] = 1.0
    fixed = np.asarray([0, 1, 2, 3, 4, 5, 6, 7, 8], dtype=np.int64)
    with pytest.raises(ValueError, match="curved TET10 geometry is outside"):
        solve_linear_static_tet10(nodes, elements, MATERIAL, loads, fixed)


def test_curved_solver_returns_finite_fields_on_valid_curved_element():
    nodes, elements = _valid_curved_single_tet()
    audit = audit_curved_tet10_mesh_jacobians(nodes, elements, quadrature_order=5)
    assert audit.all_positive is True
    assert audit.invalid_element_count == 0
    assert audit.minimum_det_jacobian > 0.0

    loads = np.zeros((nodes.shape[0], 3), dtype=float)
    loads[3, 0] = 10.0
    # Three non-collinear corner nodes fixed; this is deliberately a small
    # solver-integrity fixture, not a physical engineering benchmark.
    fixed_nodes = (0, 1, 2)
    fixed = np.asarray(
        [dof for node in fixed_nodes for dof in (3 * node, 3 * node + 1, 3 * node + 2)],
        dtype=np.int64,
    )
    result = solve_linear_static_curved_tet10(nodes, elements, MATERIAL, loads, fixed)
    assert result.integration_point_natural_coordinates.shape == (64, 3)
    assert result.integration_point_weights.shape == (64,)
    assert result.integration_point_stress_mpa.shape == (1, 64, 6)
    assert result.integration_point_von_mises_mpa.shape == (1, 64)
    assert result.minimum_production_det_jacobian > 0.0
    assert result.stiffness_nnz > 0
    assert np.all(np.isfinite(result.displacement_mm))
    assert np.all(np.isfinite(result.reactions_n))
    assert np.all(np.isfinite(result.integration_point_stress_mpa))
    assert np.all(np.isfinite(result.integration_point_von_mises_mpa))
    force_residual = np.linalg.norm(np.sum(result.reactions_n, axis=0) + np.sum(loads, axis=0))
    assert force_residual < 1.0e-8


def test_curved_mesh_audit_records_inversion_and_solver_remains_fail_closed():
    nodes, elements = _valid_curved_single_tet()
    nodes = nodes.copy()
    nodes[[0, 1]] = nodes[[1, 0]]
    audit = audit_curved_tet10_mesh_jacobians(nodes, elements, quadrature_order=5)
    assert audit.all_positive is False
    assert audit.invalid_element_count == 1
    assert audit.nonpositive_point_count > 0

    loads = np.zeros((nodes.shape[0], 3), dtype=float)
    loads[3, 0] = 1.0
    fixed = np.asarray([0, 1, 2, 3, 4, 5, 6, 7, 8], dtype=np.int64)
    with pytest.raises(ValueError, match="Degenerate or inverted TET10 Jacobian"):
        solve_linear_static_curved_tet10(nodes, elements, MATERIAL, loads, fixed)
