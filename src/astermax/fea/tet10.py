from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .tet4 import IsotropicMaterial, von_mises


# Four-point symmetric tetrahedral rule. The weights sum to the volume 1/6
# of the reference tetrahedron. This rule integrates quadratic polynomials
# exactly and is appropriate for the straight-sided quadratic TET10 PMV gate.
_GAUSS_A = 0.5854101966249685
_GAUSS_B = 0.1381966011250105
TET10_GAUSS_POINTS = np.asarray(
    [
        [_GAUSS_B, _GAUSS_B, _GAUSS_B],
        [_GAUSS_A, _GAUSS_B, _GAUSS_B],
        [_GAUSS_B, _GAUSS_A, _GAUSS_B],
        [_GAUSS_B, _GAUSS_B, _GAUSS_A],
    ],
    dtype=float,
)
TET10_GAUSS_WEIGHTS = np.full(4, 1.0 / 24.0, dtype=float)


@dataclass(frozen=True)
class Tet10IntegrationPointResult:
    natural_coordinates: np.ndarray
    det_jacobian: float
    strain: np.ndarray
    stress_mpa: np.ndarray
    von_mises_mpa: float


def tet10_shape_functions(natural_coordinates: np.ndarray) -> np.ndarray:
    """Quadratic tetrahedral shape functions in Gmsh TET10 node order.

    Natural coordinates are ``(r, s, t)`` with barycentric coordinates
    ``L1=1-r-s-t, L2=r, L3=s, L4=t``. Gmsh element type 11 uses vertices
    1..4 followed by edges (1-2, 2-3, 3-1, 1-4, 3-4, 2-4).

    The final two edge nodes are intentionally ordered 3-4 then 2-4 to match
    Gmsh's Tetrahedron10 node-numbering convention exactly.
    """
    r, s, t = np.asarray(natural_coordinates, dtype=float)
    l = np.asarray([1.0 - r - s - t, r, s, t], dtype=float)
    l1, l2, l3, l4 = l
    return np.asarray(
        [
            l1 * (2.0 * l1 - 1.0),
            l2 * (2.0 * l2 - 1.0),
            l3 * (2.0 * l3 - 1.0),
            l4 * (2.0 * l4 - 1.0),
            4.0 * l1 * l2,
            4.0 * l2 * l3,
            4.0 * l3 * l1,
            4.0 * l1 * l4,
            4.0 * l3 * l4,
            4.0 * l2 * l4,
        ],
        dtype=float,
    )


def tet10_shape_derivatives(natural_coordinates: np.ndarray) -> np.ndarray:
    """Return ``dN/d(r,s,t)`` with shape ``(10, 3)`` in Gmsh order."""
    r, s, t = np.asarray(natural_coordinates, dtype=float)
    l = np.asarray([1.0 - r - s - t, r, s, t], dtype=float)
    # Rows are barycentric coordinates L1..L4; columns are r,s,t.
    dl = np.asarray(
        [
            [-1.0, -1.0, -1.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=float,
    )
    out = np.empty((10, 3), dtype=float)
    for i in range(4):
        out[i] = (4.0 * l[i] - 1.0) * dl[i]
    edge_pairs = ((0, 1), (1, 2), (2, 0), (0, 3), (2, 3), (1, 3))
    for row, (i, j) in enumerate(edge_pairs, start=4):
        out[row] = 4.0 * (dl[i] * l[j] + l[i] * dl[j])
    return out


def tet10_B_matrix(
    coords_mm: np.ndarray,
    natural_coordinates: np.ndarray,
) -> tuple[np.ndarray, float]:
    coords = np.asarray(coords_mm, dtype=float)
    if coords.shape != (10, 3):
        raise ValueError("TET10 coordinates must have shape (10, 3)")
    dndr = tet10_shape_derivatives(natural_coordinates)
    jacobian = coords.T @ dndr
    det_j = float(np.linalg.det(jacobian))
    scale = max(float(np.linalg.norm(coords.max(axis=0) - coords.min(axis=0))), 1.0)
    if not np.isfinite(det_j) or det_j <= scale**3 * 1.0e-12:
        raise ValueError("Degenerate or inverted TET10 Jacobian")
    dndx = dndr @ np.linalg.inv(jacobian)
    b = np.zeros((6, 30), dtype=float)
    for i, (dx, dy, dz) in enumerate(dndx):
        j = 3 * i
        b[0, j] = dx
        b[1, j + 1] = dy
        b[2, j + 2] = dz
        b[3, j] = dy
        b[3, j + 1] = dx
        b[4, j + 1] = dz
        b[4, j + 2] = dy
        b[5, j] = dz
        b[5, j + 2] = dx
    return b, det_j


def tet10_stiffness(coords_mm: np.ndarray, material: IsotropicMaterial) -> np.ndarray:
    coords = np.asarray(coords_mm, dtype=float)
    if coords.shape != (10, 3):
        raise ValueError("TET10 coordinates must have shape (10, 3)")
    d = material.constitutive_matrix()
    ke = np.zeros((30, 30), dtype=float)
    for point, weight in zip(TET10_GAUSS_POINTS, TET10_GAUSS_WEIGHTS):
        b, det_j = tet10_B_matrix(coords, point)
        ke += b.T @ d @ b * det_j * weight
    if not np.all(np.isfinite(ke)):
        raise ValueError("TET10 stiffness contains non-finite values")
    return ke


def tet10_integration_point_results(
    coords_mm: np.ndarray,
    displacement_mm: np.ndarray,
    material: IsotropicMaterial,
) -> list[Tet10IntegrationPointResult]:
    coords = np.asarray(coords_mm, dtype=float)
    disp = np.asarray(displacement_mm, dtype=float)
    if coords.shape != (10, 3):
        raise ValueError("TET10 coordinates must have shape (10, 3)")
    if disp.shape != (10, 3):
        raise ValueError("TET10 displacement must have shape (10, 3)")
    ue = disp.reshape(30)
    d = material.constitutive_matrix()
    results: list[Tet10IntegrationPointResult] = []
    for point in TET10_GAUSS_POINTS:
        b, det_j = tet10_B_matrix(coords, point)
        strain = b @ ue
        stress = d @ strain
        results.append(
            Tet10IntegrationPointResult(
                natural_coordinates=np.asarray(point, dtype=float).copy(),
                det_jacobian=det_j,
                strain=np.asarray(strain, dtype=float),
                stress_mpa=np.asarray(stress, dtype=float),
                von_mises_mpa=von_mises(stress),
            )
        )
    return results


def straight_sided_tet10_from_vertices(vertices_mm: np.ndarray) -> np.ndarray:
    """Construct a straight-sided TET10 geometry in Gmsh node order.

    This helper is intentionally limited to verification fixtures. Industrial
    curved-edge geometry must come from the CAD/mesher and must not be rebuilt
    from corner nodes.
    """
    v = np.asarray(vertices_mm, dtype=float)
    if v.shape != (4, 3):
        raise ValueError("vertices_mm must have shape (4, 3)")
    v1, v2, v3, v4 = v
    return np.vstack(
        [
            v1,
            v2,
            v3,
            v4,
            0.5 * (v1 + v2),
            0.5 * (v2 + v3),
            0.5 * (v3 + v1),
            0.5 * (v1 + v4),
            0.5 * (v3 + v4),
            0.5 * (v2 + v4),
        ]
    )
