"""Minimal, auditable 4-node tetrahedral linear-elastic element.

Scope: element-level verification only. Units are caller-defined but must be
consistent; AsterMax PMV uses mm, N and MPa (N/mm^2).
"""

from dataclasses import dataclass
from math import fabs
from typing import Iterable, Sequence


class Tet4Error(ValueError):
    """Raised when a tetrahedral element is physically/numerically invalid."""


@dataclass(frozen=True)
class Tet4Result:
    volume: float
    strain: tuple[float, ...]
    stress: tuple[float, ...]
    strain_energy: float
    internal_force: tuple[float, ...]


def _inverse(matrix: Sequence[Sequence[float]]) -> list[list[float]]:
    n = len(matrix)
    if n == 0 or any(len(row) != n for row in matrix):
        raise Tet4Error("matrix must be square")
    aug = [list(map(float, row)) + [1.0 if i == j else 0.0 for j in range(n)]
           for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-14:
            raise Tet4Error("singular matrix")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        scale = aug[col][col]
        aug[col] = [value / scale for value in aug[col]]
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            aug[row] = [aug[row][j] - factor * aug[col][j] for j in range(2 * n)]
    return [row[n:] for row in aug]


def _det3(a: Sequence[Sequence[float]]) -> float:
    return (
        a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
        - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
        + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0])
    )


def isotropic_elasticity_matrix(young: float, poisson: float) -> list[list[float]]:
    if young <= 0:
        raise Tet4Error("Young's modulus must be positive")
    if not (-1.0 < poisson < 0.5):
        raise Tet4Error("Poisson ratio must satisfy -1 < nu < 0.5")
    c = young / ((1.0 + poisson) * (1.0 - 2.0 * poisson))
    lam = poisson * c
    mu = young / (2.0 * (1.0 + poisson))
    d = [[0.0] * 6 for _ in range(6)]
    for i in range(3):
        for j in range(3):
            d[i][j] = lam
        d[i][i] += 2.0 * mu
    d[3][3] = d[4][4] = d[5][5] = mu
    return d


def geometry(nodes: Sequence[Sequence[float]]) -> tuple[float, list[list[float]]]:
    if len(nodes) != 4 or any(len(node) != 3 for node in nodes):
        raise Tet4Error("TET4 requires exactly four 3D nodes")
    x0, x1, x2, x3 = [tuple(map(float, node)) for node in nodes]
    jac = [
        [x1[0]-x0[0], x2[0]-x0[0], x3[0]-x0[0]],
        [x1[1]-x0[1], x2[1]-x0[1], x3[1]-x0[1]],
        [x1[2]-x0[2], x2[2]-x0[2], x3[2]-x0[2]],
    ]
    signed_six_volume = _det3(jac)
    volume = fabs(signed_six_volume) / 6.0
    if volume <= 1e-14:
        raise Tet4Error("degenerate tetrahedron")

    m = [[1.0, *map(float, node)] for node in nodes]
    inv_m = _inverse(m)
    # N_i = inv_m[0][i] + inv_m[1][i] x + inv_m[2][i] y + inv_m[3][i] z
    gradients = [[inv_m[1][i], inv_m[2][i], inv_m[3][i]] for i in range(4)]
    return volume, gradients


def strain_displacement_matrix(nodes: Sequence[Sequence[float]]) -> tuple[float, list[list[float]]]:
    volume, gradients = geometry(nodes)
    b = [[0.0] * 12 for _ in range(6)]
    for i, (dx, dy, dz) in enumerate(gradients):
        c = 3 * i
        b[0][c] = dx
        b[1][c+1] = dy
        b[2][c+2] = dz
        b[3][c] = dy; b[3][c+1] = dx
        b[4][c+1] = dz; b[4][c+2] = dy
        b[5][c] = dz; b[5][c+2] = dx
    return volume, b


def _matvec(a: Sequence[Sequence[float]], x: Sequence[float]) -> list[float]:
    return [sum(row[j] * x[j] for j in range(len(x))) for row in a]


def stiffness_matrix(nodes: Sequence[Sequence[float]], young: float, poisson: float) -> list[list[float]]:
    volume, b = strain_displacement_matrix(nodes)
    d = isotropic_elasticity_matrix(young, poisson)
    db = [[sum(d[i][k] * b[k][j] for k in range(6)) for j in range(12)] for i in range(6)]
    return [[volume * sum(b[k][i] * db[k][j] for k in range(6)) for j in range(12)] for i in range(12)]


def evaluate(nodes: Sequence[Sequence[float]], displacements: Iterable[float], young: float, poisson: float) -> Tet4Result:
    u = tuple(map(float, displacements))
    if len(u) != 12:
        raise Tet4Error("TET4 requires 12 displacement DOFs")
    volume, b = strain_displacement_matrix(nodes)
    d = isotropic_elasticity_matrix(young, poisson)
    strain = tuple(_matvec(b, u))
    stress = tuple(_matvec(d, strain))
    k = stiffness_matrix(nodes, young, poisson)
    fint = tuple(_matvec(k, u))
    energy = 0.5 * sum(u[i] * fint[i] for i in range(12))
    return Tet4Result(volume, strain, stress, energy, fint)
