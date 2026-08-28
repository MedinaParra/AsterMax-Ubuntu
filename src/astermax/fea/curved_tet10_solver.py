from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix

from .solver import _solve_sparse_system
from .tet10 import tet10_B_matrix, tet10_shape_derivatives
from .tet10_isoparametric import duffy_tetra_gauss_rule
from .tet4 import IsotropicMaterial, von_mises


CURVED_TET10_VOLUME_QUADRATURE_ORDER = 4


@dataclass(frozen=True)
class CurvedTet10MeshJacobianAudit:
    quadrature_method: str
    quadrature_order: int
    point_count_per_element: int
    element_count: int
    minimum_det_jacobian: float
    maximum_det_jacobian: float
    minimum_element_det_over_maximum_ratio: float | None
    invalid_element_count: int
    nonpositive_point_count: int
    first_invalid_element_indices: tuple[int, ...]
    all_positive: bool


@dataclass(frozen=True)
class CurvedTet10LinearStaticResult:
    displacement_mm: np.ndarray
    reactions_n: np.ndarray
    integration_point_natural_coordinates: np.ndarray
    integration_point_weights: np.ndarray
    integration_point_stress_mpa: np.ndarray
    integration_point_von_mises_mpa: np.ndarray
    volume_quadrature_method: str
    volume_quadrature_order: int
    minimum_production_det_jacobian: float
    stiffness_nnz: int


def _validate_mesh(nodes_mm: np.ndarray, elements: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise ValueError("nodes_mm must be finite with shape (n,3)")
    if elems.ndim != 2 or elems.shape[1] != 10 or elems.shape[0] == 0:
        raise ValueError("elements must have shape (m,10) with m>0")
    if np.any(elems < 0) or np.any(elems >= nodes.shape[0]):
        raise ValueError("elements contains an out-of-range node index")
    return nodes, elems


def audit_curved_tet10_mesh_jacobians(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    *,
    quadrature_order: int = 5,
) -> CurvedTet10MeshJacobianAudit:
    """Dense fail-closed det(J) diagnostic independent of the stiffness loop."""
    nodes, elems = _validate_mesh(nodes_mm, elements)
    rule = duffy_tetra_gauss_rule(quadrature_order)
    derivatives = tuple(tet10_shape_derivatives(point) for point in rule.points)
    minimum = float("inf")
    maximum = -float("inf")
    minimum_ratio: float | None = None
    invalid: list[int] = []
    nonpositive = 0
    for element_index, conn in enumerate(elems):
        coords = nodes[conn]
        dets = np.asarray([np.linalg.det(coords.T @ dndr) for dndr in derivatives], dtype=float)
        if not np.all(np.isfinite(dets)):
            raise ValueError(f"non-finite TET10 Jacobian determinant in element {element_index}")
        local_min = float(np.min(dets))
        local_max = float(np.max(dets))
        minimum = min(minimum, local_min)
        maximum = max(maximum, local_max)
        bad = int(np.count_nonzero(dets <= 0.0))
        nonpositive += bad
        if bad:
            invalid.append(element_index)
        elif local_max > 0.0:
            ratio = local_min / local_max
            minimum_ratio = ratio if minimum_ratio is None else min(minimum_ratio, ratio)
    return CurvedTet10MeshJacobianAudit(
        quadrature_method=rule.method,
        quadrature_order=rule.order,
        point_count_per_element=int(rule.points.shape[0]),
        element_count=int(elems.shape[0]),
        minimum_det_jacobian=minimum,
        maximum_det_jacobian=maximum,
        minimum_element_det_over_maximum_ratio=minimum_ratio,
        invalid_element_count=len(invalid),
        nonpositive_point_count=nonpositive,
        first_invalid_element_indices=tuple(int(i) for i in invalid[:20]),
        all_positive=len(invalid) == 0,
    )


def assemble_global_stiffness_sparse_curved_tet10(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    material: IsotropicMaterial,
    *,
    quadrature_order: int = CURVED_TET10_VOLUME_QUADRATURE_ORDER,
) -> tuple[csr_matrix, float]:
    """Assemble a general isoparametric TET10 stiffness with Duffy quadrature."""
    nodes, elems = _validate_mesh(nodes_mm, elements)
    if int(quadrature_order) != CURVED_TET10_VOLUME_QUADRATURE_ORDER:
        raise ValueError(
            f"C11 curved solver volume quadrature is frozen at order {CURVED_TET10_VOLUME_QUADRATURE_ORDER}"
        )
    rule = duffy_tetra_gauss_rule(CURVED_TET10_VOLUME_QUADRATURE_ORDER)
    d = material.constitutive_matrix()
    element_entries = 30 * 30
    total_entries = int(elems.shape[0]) * element_entries
    rows = np.empty(total_entries, dtype=np.int64)
    cols = np.empty(total_entries, dtype=np.int64)
    data = np.empty(total_entries, dtype=float)
    minimum_det_j = float("inf")
    offset = 0

    for conn in elems:
        coords = nodes[conn]
        dofs = (3 * conn[:, None] + np.asarray([0, 1, 2], dtype=np.int64)[None, :]).reshape(30)
        ke = np.zeros((30, 30), dtype=float)
        for point, weight in zip(rule.points, rule.weights):
            b, det_j = tet10_B_matrix(coords, point)
            minimum_det_j = min(minimum_det_j, float(det_j))
            ke += b.T @ d @ b * float(det_j) * float(weight)
        end = offset + element_entries
        rows[offset:end] = np.repeat(dofs, 30)
        cols[offset:end] = np.tile(dofs, 30)
        data[offset:end] = ke.reshape(-1)
        offset = end

    ndof = nodes.shape[0] * 3
    stiffness = coo_matrix((data, (rows, cols)), shape=(ndof, ndof), dtype=float).tocsr()
    stiffness.eliminate_zeros()
    if not np.all(np.isfinite(stiffness.data)):
        raise ValueError("curved TET10 stiffness contains non-finite values")
    return stiffness, minimum_det_j


def solve_linear_static_curved_tet10(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    material: IsotropicMaterial,
    loads_n: np.ndarray,
    fixed_dofs: list[int] | np.ndarray,
) -> CurvedTet10LinearStaticResult:
    """C11 verification solver for valid curved isoparametric TET10 meshes.

    This is intentionally separate from the historical straight-sided solver.
    It uses independently verified Duffy GL4 integration (64 points/element),
    preserves stresses at every integration point and performs no nodal stress
    extrapolation, averaging or smoothing.
    """
    nodes, elems = _validate_mesh(nodes_mm, elements)
    loads = np.asarray(loads_n, dtype=float).reshape(-1)
    ndof = nodes.shape[0] * 3
    if loads.size != ndof or not np.all(np.isfinite(loads)):
        raise ValueError("loads_n must contain finite 3 DOFs per node")

    stiffness, minimum_det_j = assemble_global_stiffness_sparse_curved_tet10(
        nodes, elems, material
    )
    u, reactions = _solve_sparse_system(stiffness, loads, fixed_dofs)
    displacement = u.reshape((-1, 3))

    rule = duffy_tetra_gauss_rule(CURVED_TET10_VOLUME_QUADRATURE_ORDER)
    d = material.constitutive_matrix()
    stress = np.empty((elems.shape[0], rule.points.shape[0], 6), dtype=float)
    mises = np.empty((elems.shape[0], rule.points.shape[0]), dtype=float)
    for element_index, conn in enumerate(elems):
        coords = nodes[conn]
        ue = displacement[conn].reshape(30)
        for point_index, point in enumerate(rule.points):
            b, det_j = tet10_B_matrix(coords, point)
            minimum_det_j = min(minimum_det_j, float(det_j))
            sigma = d @ (b @ ue)
            stress[element_index, point_index] = sigma
            mises[element_index, point_index] = von_mises(sigma)

    if not np.all(np.isfinite(displacement)) or not np.all(np.isfinite(reactions)):
        raise ValueError("curved TET10 solve produced non-finite displacement or reactions")
    if not np.all(np.isfinite(stress)) or not np.all(np.isfinite(mises)):
        raise ValueError("curved TET10 solve produced non-finite integration-point stress")
    return CurvedTet10LinearStaticResult(
        displacement_mm=displacement,
        reactions_n=reactions.reshape((-1, 3)),
        integration_point_natural_coordinates=rule.points.copy(),
        integration_point_weights=rule.weights.copy(),
        integration_point_stress_mpa=stress,
        integration_point_von_mises_mpa=mises,
        volume_quadrature_method=rule.method,
        volume_quadrature_order=rule.order,
        minimum_production_det_jacobian=float(minimum_det_j),
        stiffness_nnz=int(stiffness.nnz),
    )
