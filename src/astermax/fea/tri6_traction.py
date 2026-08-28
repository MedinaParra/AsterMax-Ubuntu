from __future__ import annotations

from dataclasses import dataclass

import numpy as np


_TRI3_GAUSS = np.asarray(
    [
        [1.0 / 6.0, 1.0 / 6.0],
        [2.0 / 3.0, 1.0 / 6.0],
        [1.0 / 6.0, 2.0 / 3.0],
    ],
    dtype=float,
)
_TRI3_WEIGHTS = np.full(3, 1.0 / 6.0, dtype=float)


@dataclass(frozen=True)
class ConsistentSurfaceLoad:
    loads_n: np.ndarray
    surface_area_mm2: float
    requested_resultant_n: tuple[float, float, float]
    integrated_resultant_n: tuple[float, float, float]
    integrated_moment_about_origin_nmm: tuple[float, float, float]
    relative_resultant_error: float


def tri6_shape_functions(rs: np.ndarray) -> np.ndarray:
    r, s = np.asarray(rs, dtype=float)
    l1, l2, l3 = 1.0 - r - s, r, s
    return np.asarray(
        [
            l1 * (2.0 * l1 - 1.0),
            l2 * (2.0 * l2 - 1.0),
            l3 * (2.0 * l3 - 1.0),
            4.0 * l1 * l2,
            4.0 * l2 * l3,
            4.0 * l3 * l1,
        ],
        dtype=float,
    )


def tri6_shape_derivatives(rs: np.ndarray) -> np.ndarray:
    r, s = np.asarray(rs, dtype=float)
    l = np.asarray([1.0 - r - s, r, s], dtype=float)
    dl = np.asarray([[-1.0, -1.0], [1.0, 0.0], [0.0, 1.0]], dtype=float)
    out = np.empty((6, 2), dtype=float)
    for i in range(3):
        out[i] = (4.0 * l[i] - 1.0) * dl[i]
    for row, (i, j) in enumerate(((0, 1), (1, 2), (2, 0)), start=3):
        out[row] = 4.0 * (dl[i] * l[j] + l[i] * dl[j])
    return out


def consistent_tri6_resultant_load(
    nodes_mm: np.ndarray,
    tri6: np.ndarray,
    *,
    total_force_n: np.ndarray | tuple[float, float, float],
) -> ConsistentSurfaceLoad:
    """Apply a uniform surface traction whose integrated resultant is exact.

    The TRI6 consistent nodal weights are integrated with a three-point
    triangle rule. The unscaled integrated area is then used to convert the
    requested total force vector into uniform traction. This avoids equal-load-
    per-node dependence on mesh density.
    """
    nodes = np.asarray(nodes_mm, dtype=float)
    faces = np.asarray(tri6, dtype=np.int64)
    force = np.asarray(total_force_n, dtype=float).reshape(3)
    if nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("nodes_mm must have shape (n,3)")
    if faces.ndim != 2 or faces.shape[1] != 6 or faces.shape[0] == 0:
        raise ValueError("tri6 must have shape (m,6) with m>0")
    if np.any(faces < 0) or np.any(faces >= nodes.shape[0]):
        raise ValueError("tri6 contains out-of-range node indices")
    if not np.all(np.isfinite(nodes)) or not np.all(np.isfinite(force)):
        raise ValueError("nodes and total force must be finite")
    if np.linalg.norm(force) <= 0.0:
        raise ValueError("total_force_n must be non-zero")

    scalar_weights = np.zeros(nodes.shape[0], dtype=float)
    area = 0.0
    first_moment = np.zeros(3, dtype=float)
    for conn in faces:
        xyz = nodes[conn]
        for point, weight in zip(_TRI3_GAUSS, _TRI3_WEIGHTS):
            n = tri6_shape_functions(point)
            dn = tri6_shape_derivatives(point)
            tangents = xyz.T @ dn
            jac = float(np.linalg.norm(np.cross(tangents[:, 0], tangents[:, 1])))
            if not np.isfinite(jac) or jac <= 0.0:
                raise ValueError("degenerate TRI6 surface Jacobian")
            darea = jac * float(weight)
            x = n @ xyz
            area += darea
            first_moment += x * darea
            scalar_weights[conn] += n * darea

    if not np.isfinite(area) or area <= 0.0:
        raise ValueError("integrated TRI6 area is invalid")
    if not np.isclose(float(np.sum(scalar_weights)), area, rtol=1.0e-11, atol=max(area, 1.0) * 1.0e-12):
        raise RuntimeError("TRI6 partition-of-unity integration failed")

    traction = force / area
    loads = scalar_weights[:, None] * traction[None, :]
    resultant = loads.sum(axis=0)
    moment = np.sum(np.cross(nodes, loads), axis=0)
    norm = max(float(np.linalg.norm(force)), np.finfo(float).tiny)
    error = float(np.linalg.norm(resultant - force) / norm)
    if not np.all(np.isfinite(loads)) or error > 1.0e-10:
        raise RuntimeError(f"consistent TRI6 resultant check failed: relative_error={error}")

    # Cross-check nodal first moment against direct quadrature first moment.
    direct_moment = np.cross(first_moment, traction)
    if not np.allclose(moment, direct_moment, rtol=1.0e-10, atol=max(np.linalg.norm(direct_moment), 1.0) * 1.0e-10):
        raise RuntimeError("consistent TRI6 moment integration check failed")

    return ConsistentSurfaceLoad(
        loads_n=loads,
        surface_area_mm2=area,
        requested_resultant_n=tuple(float(v) for v in force),
        integrated_resultant_n=tuple(float(v) for v in resultant),
        integrated_moment_about_origin_nmm=tuple(float(v) for v in moment),
        relative_resultant_error=error,
    )


def fixed_dofs_from_tri6(tri6: np.ndarray) -> np.ndarray:
    faces = np.asarray(tri6, dtype=np.int64)
    if faces.ndim != 2 or faces.shape[1] != 6 or faces.shape[0] == 0:
        raise ValueError("tri6 must have shape (m,6) with m>0")
    nodes = np.unique(faces.reshape(-1))
    return np.asarray([[3 * n, 3 * n + 1, 3 * n + 2] for n in nodes], dtype=np.int64).reshape(-1)
