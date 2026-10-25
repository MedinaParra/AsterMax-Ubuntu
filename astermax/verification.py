"""Numerical verification benchmarks for the AsterMax solver harness.

This module intentionally implements only a 1D linear-elastic axial bar. It is not
AsterMax's production solver. Its purpose is to provide a transparent golden problem
with a closed-form solution so future solver backends can be checked against known
physics before their results are trusted.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose


@dataclass(frozen=True)
class AxialBarResult:
    node_displacements_mm: tuple[float, ...]
    element_stress_MPa: tuple[float, ...]
    reaction_N: float
    free_end_displacement_mm: float
    analytical_displacement_mm: float
    analytical_stress_MPa: float
    displacement_relative_error: float
    stress_relative_error: float
    equilibrium_error_N: float

    def verified(self, *, rtol: float = 1e-10, equilibrium_tol_N: float = 1e-8) -> bool:
        return (
            self.displacement_relative_error <= rtol
            and self.stress_relative_error <= rtol
            and self.equilibrium_error_N <= equilibrium_tol_N
        )


def _solve_dense(a: list[list[float]], b: list[float]) -> list[float]:
    """Solve Ax=b with Gaussian elimination and partial pivoting, stdlib only."""
    n = len(b)
    aug = [row[:] + [rhs] for row, rhs in zip(a, b)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if isclose(aug[pivot][col], 0.0, abs_tol=1e-18):
            raise ValueError("Singular stiffness matrix")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        scale = aug[col][col]
        aug[col] = [value / scale for value in aug[col]]
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            if factor == 0.0:
                continue
            aug[row] = [rv - factor * cv for rv, cv in zip(aug[row], aug[col])]
    return [aug[i][-1] for i in range(n)]


def solve_axial_bar(
    *,
    length_mm: float,
    area_mm2: float,
    youngs_modulus_MPa: float,
    end_force_N: float,
    elements: int = 2,
) -> AxialBarResult:
    """Solve a fixed-free uniform axial bar using linear 2-node finite elements.

    Units are the AsterMax PMV basis: mm, N and MPa (= N/mm²).
    """
    if min(length_mm, area_mm2, youngs_modulus_MPa) <= 0:
        raise ValueError("Geometry and modulus must be positive")
    if elements < 1:
        raise ValueError("At least one finite element is required")

    nodes = elements + 1
    le = length_mm / elements
    ke = youngs_modulus_MPa * area_mm2 / le
    k = [[0.0 for _ in range(nodes)] for _ in range(nodes)]
    for e in range(elements):
        i, j = e, e + 1
        k[i][i] += ke
        k[i][j] -= ke
        k[j][i] -= ke
        k[j][j] += ke

    # Node 0 fixed. Solve the reduced system for nodes 1..n.
    kred = [row[1:] for row in k[1:]]
    f = [0.0 for _ in range(elements)]
    f[-1] = end_force_N
    ufree = _solve_dense(kred, f)
    u = [0.0] + ufree

    stress = tuple(
        youngs_modulus_MPa * (u[e + 1] - u[e]) / le for e in range(elements)
    )
    reaction = sum(k[0][j] * u[j] for j in range(nodes))

    analytical_u = end_force_N * length_mm / (youngs_modulus_MPa * area_mm2)
    analytical_stress = end_force_N / area_mm2
    uerr = abs(u[-1] - analytical_u) / max(abs(analytical_u), 1e-30)
    serr = max(abs(s - analytical_stress) for s in stress) / max(
        abs(analytical_stress), 1e-30
    )
    equilibrium_error = abs(reaction + end_force_N)

    return AxialBarResult(
        node_displacements_mm=tuple(u),
        element_stress_MPa=stress,
        reaction_N=reaction,
        free_end_displacement_mm=u[-1],
        analytical_displacement_mm=analytical_u,
        analytical_stress_MPa=analytical_stress,
        displacement_relative_error=uerr,
        stress_relative_error=serr,
        equilibrium_error_N=equilibrium_error,
    )
