from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .tet4 import IsotropicMaterial, tet4_B_matrix, tet4_stiffness, von_mises


@dataclass
class LinearStaticResult:
    displacement_mm: np.ndarray
    reactions_n: np.ndarray
    element_stress_mpa: np.ndarray
    element_von_mises_mpa: np.ndarray


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

    k = np.zeros((ndof, ndof), dtype=float)
    for conn in elems:
        dofs = np.array([[3*n, 3*n+1, 3*n+2] for n in conn], dtype=int).reshape(-1)
        ke = tet4_stiffness(nodes[conn], material)
        k[np.ix_(dofs, dofs)] += ke

    fixed = np.unique(np.asarray(fixed_dofs, dtype=int))
    if np.any(fixed < 0) or np.any(fixed >= ndof):
        raise ValueError("fixed_dofs contains an out-of-range DOF")
    free = np.setdiff1d(np.arange(ndof), fixed)
    if free.size == 0:
        raise ValueError("No free DOFs remain")

    u = np.zeros(ndof, dtype=float)
    kff = k[np.ix_(free, free)]
    ff = loads[free]
    u[free] = np.linalg.solve(kff, ff)
    reactions = k @ u - loads

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
