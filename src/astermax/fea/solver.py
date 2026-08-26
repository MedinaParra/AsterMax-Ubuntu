from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.linalg import spsolve

from .tet10 import tet10_integration_point_results, tet10_stiffness
from .tet4 import IsotropicMaterial, tet4_B_matrix, tet4_stiffness, von_mises


@dataclass
class LinearStaticResult:
    displacement_mm: np.ndarray
    reactions_n: np.ndarray
    element_stress_mpa: np.ndarray
    element_von_mises_mpa: np.ndarray


@dataclass
class Tet10LinearStaticResult:
    displacement_mm: np.ndarray
    reactions_n: np.ndarray
    integration_point_stress_mpa: np.ndarray
    integration_point_von_mises_mpa: np.ndarray


def assemble_global_stiffness_sparse(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    material: IsotropicMaterial,
) -> csr_matrix:
    """Assemble the global TET4 stiffness matrix directly as sparse CSR.

    Explicit numerical zeros are removed after COO->CSR conversion so ``nnz``
    reflects actually stored stiffness coefficients rather than the dense 12x12
    element insertion pattern. This matters for both memory telemetry and the
    practical scalability envelope of the PMV.
    """
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=int)
    if nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("nodes_mm must have shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 4:
        raise ValueError("elements must have shape (m, 4)")
    if elems.size and (np.any(elems < 0) or np.any(elems >= nodes.shape[0])):
        raise ValueError("elements contains an out-of-range node index")

    ndof = nodes.shape[0] * 3
    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []

    for conn in elems:
        dofs = np.array([[3*n, 3*n+1, 3*n+2] for n in conn], dtype=int).reshape(-1)
        ke = tet4_stiffness(nodes[conn], material)
        rr, cc = np.meshgrid(dofs, dofs, indexing="ij")
        rows.extend(rr.ravel().tolist())
        cols.extend(cc.ravel().tolist())
        data.extend(ke.ravel().tolist())

    stiffness = coo_matrix(
        (data, (rows, cols)), shape=(ndof, ndof), dtype=float
    ).tocsr()
    stiffness.eliminate_zeros()
    return stiffness


def _assert_straight_sided_tet10(coords_mm: np.ndarray) -> None:
    coords = np.asarray(coords_mm, dtype=float)
    if coords.shape != (10, 3):
        raise ValueError("TET10 coordinates must have shape (10, 3)")
    expected = np.asarray(
        [
            0.5 * (coords[0] + coords[1]),
            0.5 * (coords[1] + coords[2]),
            0.5 * (coords[2] + coords[0]),
            0.5 * (coords[0] + coords[3]),
            0.5 * (coords[1] + coords[3]),
            0.5 * (coords[2] + coords[3]),
        ]
    )
    scale = max(float(np.linalg.norm(coords[:4].max(axis=0) - coords[:4].min(axis=0))), 1.0)
    if not np.allclose(coords[4:], expected, rtol=0.0, atol=scale * 1.0e-10):
        raise ValueError(
            "curved TET10 geometry is outside the T10-B four-point integration verification scope"
        )


def assemble_global_stiffness_sparse_tet10(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    material: IsotropicMaterial,
) -> csr_matrix:
    """Assemble straight-sided quadratic TET10 elements into sparse CSR."""
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=int)
    if nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("nodes_mm must have shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("TET10 elements must have shape (m, 10)")
    if elems.size and (np.any(elems < 0) or np.any(elems >= nodes.shape[0])):
        raise ValueError("elements contains an out-of-range node index")

    ndof = nodes.shape[0] * 3
    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []
    for conn in elems:
        coords = nodes[conn]
        _assert_straight_sided_tet10(coords)
        dofs = np.array([[3*n, 3*n+1, 3*n+2] for n in conn], dtype=int).reshape(-1)
        ke = tet10_stiffness(coords, material)
        rr, cc = np.meshgrid(dofs, dofs, indexing="ij")
        rows.extend(rr.ravel().tolist())
        cols.extend(cc.ravel().tolist())
        data.extend(ke.ravel().tolist())

    stiffness = coo_matrix(
        (data, (rows, cols)), shape=(ndof, ndof), dtype=float
    ).tocsr()
    stiffness.eliminate_zeros()
    return stiffness


def _solve_sparse_system(
    k: csr_matrix,
    loads: np.ndarray,
    fixed_dofs: list[int] | np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    ndof = int(k.shape[0])
    fixed = np.unique(np.asarray(fixed_dofs, dtype=int))
    if np.any(fixed < 0) or np.any(fixed >= ndof):
        raise ValueError("fixed_dofs contains an out-of-range DOF")
    free = np.setdiff1d(np.arange(ndof), fixed)
    if free.size == 0:
        raise ValueError("No free DOFs remain")

    u = np.zeros(ndof, dtype=float)
    kff = k[free][:, free]
    ff = loads[free]
    solved = np.asarray(spsolve(kff, ff), dtype=float).reshape(-1)
    if solved.size != free.size or not np.all(np.isfinite(solved)):
        raise np.linalg.LinAlgError("Sparse solve did not return a finite displacement field")
    u[free] = solved
    reactions = np.asarray(k @ u - loads, dtype=float).reshape(-1)
    return u, reactions


def solve_linear_static(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    material: IsotropicMaterial,
    loads_n: np.ndarray,
    fixed_dofs: list[int] | np.ndarray,
) -> LinearStaticResult:
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=int)
    loads = np.asarray(loads_n, dtype=float).reshape(-1)
    ndof = nodes.shape[0] * 3
    if nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("nodes_mm must have shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 4:
        raise ValueError("elements must have shape (m, 4)")
    if loads.size != ndof:
        raise ValueError("loads_n must contain 3 DOFs per node")
    if not np.all(np.isfinite(loads)):
        raise ValueError("loads_n must be finite")

    k = assemble_global_stiffness_sparse(nodes, elems, material)
    u, reactions = _solve_sparse_system(k, loads, fixed_dofs)

    stresses = []
    mises = []
    d = material.constitutive_matrix()
    for conn in elems:
        dofs = np.array([[3*n, 3*n+1, 3*n+2] for n in conn], dtype=int).reshape(-1)
        b, _ = tet4_B_matrix(nodes[conn])
        stress = d @ (b @ u[dofs])
        stresses.append(stress)
        mises.append(von_mises(stress))

    return LinearStaticResult(
        displacement_mm=u.reshape((-1, 3)),
        reactions_n=reactions.reshape((-1, 3)),
        element_stress_mpa=np.asarray(stresses),
        element_von_mises_mpa=np.asarray(mises),
    )


def solve_linear_static_tet10(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    material: IsotropicMaterial,
    loads_n: np.ndarray,
    fixed_dofs: list[int] | np.ndarray,
) -> Tet10LinearStaticResult:
    """Solve a straight-sided quadratic TET10 linear-static model.

    Stress is preserved at the four integration points per element. No nodal
    averaging or peak smoothing is performed in this numerical gate.
    """
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=int)
    loads = np.asarray(loads_n, dtype=float).reshape(-1)
    ndof = nodes.shape[0] * 3
    if nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("nodes_mm must have shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("TET10 elements must have shape (m, 10)")
    if loads.size != ndof:
        raise ValueError("loads_n must contain 3 DOFs per node")
    if not np.all(np.isfinite(loads)):
        raise ValueError("loads_n must be finite")

    k = assemble_global_stiffness_sparse_tet10(nodes, elems, material)
    u, reactions = _solve_sparse_system(k, loads, fixed_dofs)
    displacement = u.reshape((-1, 3))

    ip_stress = []
    ip_mises = []
    for conn in elems:
        points = tet10_integration_point_results(nodes[conn], displacement[conn], material)
        ip_stress.append([point.stress_mpa for point in points])
        ip_mises.append([point.von_mises_mpa for point in points])

    return Tet10LinearStaticResult(
        displacement_mm=displacement,
        reactions_n=reactions.reshape((-1, 3)),
        integration_point_stress_mpa=np.asarray(ip_stress, dtype=float),
        integration_point_von_mises_mpa=np.asarray(ip_mises, dtype=float),
    )
