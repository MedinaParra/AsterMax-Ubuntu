from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.linalg import spsolve

from .tet4 import IsotropicMaterial, tet4_B_matrix, tet4_stiffness, von_mises


@dataclass
class LinearStaticResult:
    displacement_mm: np.ndarray
    reactions_n: np.ndarray
    element_stress_mpa: np.ndarray
    element_von_mises_mpa: np.ndarray


def assemble_global_stiffness_sparse(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    material: IsotropicMaterial,
) -> csr_matrix:
    """Assemble the global TET4 stiffness matrix directly as sparse CSR."""
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

    return coo_matrix((data, (rows, cols)), shape=(ndof, ndof), dtype=float).tocsr()


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
