from __future__ import annotations

import numpy as np

from .tet4 import IsotropicMaterial, von_mises


# Gmsh 10-node tetrahedron ordering:
# vertices 1..4, then edges (1-2), (2-3), (3-1), (1-4), (2-4), (3-4).
_GMSH_EDGE_ORDER = ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))


def tet10_shape(local: np.ndarray | list[float] | tuple[float, float, float]) -> np.ndarray:
    """Quadratic tetrahedron shape functions at (r,s,t).

    The barycentric coordinates are L1=1-r-s-t, L2=r, L3=s, L4=t.
    Node ordering matches Gmsh element type 11.
    """
    r, s, t = np.asarray(local, dtype=float)
    l = np.array([1.0 - r - s - t, r, s, t], dtype=float)
    n = np.empty(10, dtype=float)
    n[:4] = l * (2.0 * l - 1.0)
    for i, (a, b) in enumerate(_GMSH_EDGE_ORDER, start=4):
        n[i] = 4.0 * l[a] * l[b]
    return n


def tet10_shape_grad_local(local: np.ndarray | list[float] | tuple[float, float, float]) -> np.ndarray:
    """Return dN/d(r,s,t) with shape (10,3), in Gmsh node ordering."""
    r, s, t = np.asarray(local, dtype=float)
    l = np.array([1.0 - r - s - t, r, s, t], dtype=float)
    dl = np.array(
        [
            [-1.0, -1.0, -1.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=float,
    )
    g = np.empty((10, 3), dtype=float)
    for a in range(4):
        g[a] = (4.0 * l[a] - 1.0) * dl[a]
    for i, (a, b) in enumerate(_GMSH_EDGE_ORDER, start=4):
        g[i] = 4.0 * (l[b] * dl[a] + l[a] * dl[b])
    return g


def tet10_B_matrix(coords_mm: np.ndarray, local: np.ndarray | list[float] | tuple[float, float, float]) -> tuple[np.ndarray, float]:
    """Return the small-strain B matrix and positive Jacobian determinant."""
    coords = np.asarray(coords_mm, dtype=float)
    if coords.shape != (10, 3):
        raise ValueError("coords_mm must have shape (10,3)")
    if not np.all(np.isfinite(coords)):
        raise ValueError("coords_mm must be finite")

    dlocal = tet10_shape_grad_local(local)
    jac = coords.T @ dlocal
    det_j = float(np.linalg.det(jac))
    if not np.isfinite(det_j) or det_j <= 0.0:
        raise ValueError(f"TET10 requires positive Jacobian determinant; got {det_j}")
    dxyz = dlocal @ np.linalg.inv(jac)

    b = np.zeros((6, 30), dtype=float)
    for i, (dx, dy, dz) in enumerate(dxyz):
        c = 3 * i
        b[0, c] = dx
        b[1, c + 1] = dy
        b[2, c + 2] = dz
        b[3, c] = dy
        b[3, c + 1] = dx
        b[4, c + 1] = dz
        b[4, c + 2] = dy
        b[5, c] = dz
        b[5, c + 2] = dx
    return b, det_j


def tet10_gauss_rule() -> tuple[np.ndarray, np.ndarray]:
    """Symmetric 4-point tetrahedral rule, exact for quadratic polynomials."""
    a = 0.5854101966249685
    b = 0.1381966011250105
    bary = np.array(
        [
            [a, b, b, b],
            [b, a, b, b],
            [b, b, a, b],
            [b, b, b, a],
        ],
        dtype=float,
    )
    # local coordinates are L2,L3,L4
    points = bary[:, 1:]
    weights = np.full(4, 1.0 / 24.0, dtype=float)
    return points, weights


def tet10_stiffness(coords_mm: np.ndarray, material: IsotropicMaterial) -> np.ndarray:
    """Compute the 30x30 isoparametric TET10 stiffness by 4-point integration."""
    d = material.constitutive_matrix()
    k = np.zeros((30, 30), dtype=float)
    points, weights = tet10_gauss_rule()
    for point, weight in zip(points, weights):
        b, det_j = tet10_B_matrix(coords_mm, point)
        k += (b.T @ d @ b) * det_j * weight
    # Round-off can leave minute skew terms; enforce the energy symmetry explicitly.
    return 0.5 * (k + k.T)


def tet10_stress_at_centroid(
    coords_mm: np.ndarray,
    displacement_mm: np.ndarray,
    material: IsotropicMaterial,
) -> tuple[np.ndarray, float]:
    """Evaluate element stress at the centroid for initial PMV post-processing."""
    u = np.asarray(displacement_mm, dtype=float)
    if u.shape != (10, 3):
        raise ValueError("displacement_mm must have shape (10,3)")
    b, _ = tet10_B_matrix(coords_mm, (0.25, 0.25, 0.25))
    stress = material.constitutive_matrix() @ (b @ u.reshape(-1))
    return stress, von_mises(stress)
