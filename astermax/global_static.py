"""Small auditable 3D linear-static assembler for AsterMax verification cases.

This is a verification kernel, not a production sparse solver. It assembles dense
multi-TET4 stiffness matrices in the PMV unit system (mm, N, MPa), applies explicit
Dirichlet constraints and nodal loads, solves the reduced system, recovers reactions
and evaluates element strain/stress using the verified TET4 element implementation.
"""

from dataclasses import dataclass
from typing import Mapping, Sequence

from .tet4 import Tet4Result, evaluate, stiffness_matrix


class GlobalStaticError(ValueError):
    """Raised when a global finite-element model is invalid or singular."""


@dataclass(frozen=True)
class GlobalStaticResult:
    displacements: tuple[float, ...]
    reactions: tuple[float, ...]
    residual: tuple[float, ...]
    element_results: tuple[Tet4Result, ...]
    total_strain_energy: float


def _solve_dense(a: Sequence[Sequence[float]], b: Sequence[float]) -> list[float]:
    """Solve Ax=b with pivoted Gaussian elimination for small verification systems."""
    n = len(a)
    if n == 0 or len(b) != n or any(len(row) != n for row in a):
        raise GlobalStaticError("reduced stiffness system must be non-empty and square")
    matrix_scale = max(abs(value) for row in a for value in row)
    if matrix_scale == 0.0:
        raise GlobalStaticError("singular reduced stiffness matrix; check constraints")
    # A relative threshold is essential for stiffness matrices: an absolute pivot
    # threshold can mistake floating-point remnants of rigid-body modes for rank.
    pivot_tolerance = max(1e-14, matrix_scale * 1e-12)
    aug = [list(map(float, row)) + [float(b[i])] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(aug[row][col]))
        if abs(aug[pivot][col]) <= pivot_tolerance:
            raise GlobalStaticError("singular reduced stiffness matrix; check constraints")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        scale = aug[col][col]
        for j in range(col, n + 1):
            aug[col][j] /= scale
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            if factor == 0.0:
                continue
            for j in range(col, n + 1):
                aug[row][j] -= factor * aug[col][j]
    return [aug[i][n] for i in range(n)]


def assemble_stiffness(
    nodes: Sequence[Sequence[float]],
    elements: Sequence[Sequence[int]],
    young: float,
    poisson: float,
) -> list[list[float]]:
    """Assemble dense global K from linear four-node tetrahedra."""
    if not nodes or any(len(node) != 3 for node in nodes):
        raise GlobalStaticError("nodes must contain 3D coordinates")
    if not elements:
        raise GlobalStaticError("at least one TET4 element is required")
    ndof = 3 * len(nodes)
    k_global = [[0.0] * ndof for _ in range(ndof)]
    for element in elements:
        if len(element) != 4 or len(set(element)) != 4:
            raise GlobalStaticError("each TET4 must reference four distinct nodes")
        if any(index < 0 or index >= len(nodes) for index in element):
            raise GlobalStaticError("element references an unknown node")
        element_nodes = [nodes[index] for index in element]
        k_element = stiffness_matrix(element_nodes, young, poisson)
        dofs = [3 * index + component for index in element for component in range(3)]
        for local_i, global_i in enumerate(dofs):
            for local_j, global_j in enumerate(dofs):
                k_global[global_i][global_j] += k_element[local_i][local_j]
    return k_global


def solve_linear_static(
    nodes: Sequence[Sequence[float]],
    elements: Sequence[Sequence[int]],
    young: float,
    poisson: float,
    constraints: Mapping[int, float],
    loads: Mapping[int, float],
) -> GlobalStaticResult:
    """Assemble and solve a small linear-static multi-TET4 model.

    Constraint/load keys are zero-based global DOF indices: 3*node + {0:x,1:y,2:z}.
    Reactions are reported as K*u-f and therefore should be non-zero only at
    constrained DOFs within numerical tolerance.
    """
    k_global = assemble_stiffness(nodes, elements, young, poisson)
    ndof = len(k_global)
    if not constraints:
        raise GlobalStaticError("at least one Dirichlet constraint is required")
    for dof in (*constraints.keys(), *loads.keys()):
        if dof < 0 or dof >= ndof:
            raise GlobalStaticError("constraint/load references an unknown DOF")

    fixed = {int(dof): float(value) for dof, value in constraints.items()}
    force = [0.0] * ndof
    for dof, value in loads.items():
        force[int(dof)] += float(value)

    free = [dof for dof in range(ndof) if dof not in fixed]
    if not free:
        raise GlobalStaticError("model has no free DOFs to solve")
    reduced_k = [[k_global[i][j] for j in free] for i in free]
    reduced_f = [
        force[i] - sum(k_global[i][j] * value for j, value in fixed.items())
        for i in free
    ]
    solved = _solve_dense(reduced_k, reduced_f)

    displacement = [0.0] * ndof
    for dof, value in fixed.items():
        displacement[dof] = value
    for dof, value in zip(free, solved):
        displacement[dof] = value

    ku = [sum(row[j] * displacement[j] for j in range(ndof)) for row in k_global]
    residual = [ku[i] - force[i] for i in range(ndof)]
    reactions = [residual[i] if i in fixed else 0.0 for i in range(ndof)]

    element_results = []
    for element in elements:
        element_nodes = [nodes[index] for index in element]
        element_u = [
            displacement[3 * index + component]
            for index in element
            for component in range(3)
        ]
        element_results.append(evaluate(element_nodes, element_u, young, poisson))

    return GlobalStaticResult(
        displacements=tuple(displacement),
        reactions=tuple(reactions),
        residual=tuple(residual),
        element_results=tuple(element_results),
        total_strain_energy=sum(result.strain_energy for result in element_results),
    )
