from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.polynomial.legendre import leggauss

from .tri6_traction import tri6_shape_derivatives, tri6_shape_functions


@dataclass(frozen=True)
class TriangleQuadratureRule:
    method: str
    order: int
    points: np.ndarray
    weights: np.ndarray


@dataclass(frozen=True)
class Tri6SurfaceQuadratureComparison:
    order_a: int
    order_b: int
    area_a_mm2: float
    area_b_mm2: float
    relative_area_difference: float
    centroid_a_mm: tuple[float, float, float]
    centroid_b_mm: tuple[float, float, float]
    centroid_delta_mm: float


@dataclass(frozen=True)
class IsoparametricSurfaceLoad:
    loads_n: np.ndarray
    surface_area_mm2: float
    requested_resultant_n: tuple[float, float, float]
    integrated_resultant_n: tuple[float, float, float]
    integrated_moment_about_origin_nmm: tuple[float, float, float]
    relative_resultant_error: float
    quadrature_method: str
    quadrature_order: int


def duffy_triangle_gauss_rule(order: int) -> TriangleQuadratureRule:
    """Tensor Gauss-Legendre rule mapped from the unit square to a triangle."""
    n = int(order)
    if n < 2 or n > 16:
        raise ValueError("order must be between 2 and 16")
    xi, wi = leggauss(n)
    xi = 0.5 * (xi + 1.0)
    wi = 0.5 * wi
    points: list[tuple[float, float]] = []
    weights: list[float] = []
    for i, u in enumerate(xi):
        one_minus_u = 1.0 - float(u)
        for j, v in enumerate(xi):
            points.append((float(u), one_minus_u * float(v)))
            weights.append(float(wi[i] * wi[j] * one_minus_u))
    p = np.asarray(points, dtype=float)
    w = np.asarray(weights, dtype=float)
    if p.shape != (n * n, 2) or w.shape != (n * n,):
        raise RuntimeError("unexpected triangle Duffy quadrature shape")
    if not np.all(np.isfinite(p)) or not np.all(np.isfinite(w)) or np.any(w <= 0.0):
        raise RuntimeError("triangle Duffy quadrature contains invalid values")
    if not np.isclose(float(np.sum(w)), 0.5, rtol=0.0, atol=5.0e-15):
        raise RuntimeError("triangle Duffy quadrature does not integrate reference area")
    return TriangleQuadratureRule(
        method="DUFFY_TRIANGLE_TENSOR_GAUSS_LEGENDRE_REFERENCE",
        order=n,
        points=p,
        weights=w,
    )


def triangle_monomial_integral(i: int, j: int) -> float:
    """Exact integral of r^i s^j over r>=0,s>=0,r+s<=1."""
    ii, jj = int(i), int(j)
    if ii < 0 or jj < 0:
        raise ValueError("monomial powers must be non-negative")
    import math
    return float(math.factorial(ii) * math.factorial(jj) / math.factorial(ii + jj + 2))


def _validate_surface(nodes_mm: np.ndarray, tri6: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    nodes = np.asarray(nodes_mm, dtype=float)
    faces = np.asarray(tri6, dtype=np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise ValueError("nodes_mm must be a finite array with shape (n,3)")
    if faces.ndim != 2 or faces.shape[1] != 6 or faces.shape[0] == 0:
        raise ValueError("tri6 must have shape (m,6) with m>0")
    if np.any(faces < 0) or np.any(faces >= nodes.shape[0]):
        raise ValueError("tri6 contains out-of-range node indices")
    return nodes, faces


def _integrate_surface(
    nodes_mm: np.ndarray,
    tri6: np.ndarray,
    *,
    quadrature_order: int,
) -> tuple[float, np.ndarray, np.ndarray, TriangleQuadratureRule]:
    nodes, faces = _validate_surface(nodes_mm, tri6)
    rule = duffy_triangle_gauss_rule(quadrature_order)
    scalar_weights = np.zeros(nodes.shape[0], dtype=float)
    area = 0.0
    first_moment = np.zeros(3, dtype=float)
    for conn in faces:
        xyz = nodes[conn]
        for point, weight in zip(rule.points, rule.weights):
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
    if not np.isclose(float(np.sum(scalar_weights)), area, rtol=2.0e-12, atol=max(area, 1.0) * 2.0e-12):
        raise RuntimeError("TRI6 partition-of-unity integration failed")
    return area, first_moment, scalar_weights, rule


def compare_tri6_surface_quadrature(
    nodes_mm: np.ndarray,
    tri6: np.ndarray,
    *,
    order_a: int = 4,
    order_b: int = 5,
) -> Tri6SurfaceQuadratureComparison:
    area_a, first_a, _, _ = _integrate_surface(nodes_mm, tri6, quadrature_order=order_a)
    area_b, first_b, _, _ = _integrate_surface(nodes_mm, tri6, quadrature_order=order_b)
    centroid_a = first_a / area_a
    centroid_b = first_b / area_b
    relative = abs(area_a - area_b) / max(abs(area_b), np.finfo(float).tiny)
    delta = float(np.linalg.norm(centroid_a - centroid_b))
    return Tri6SurfaceQuadratureComparison(
        order_a=int(order_a),
        order_b=int(order_b),
        area_a_mm2=float(area_a),
        area_b_mm2=float(area_b),
        relative_area_difference=float(relative),
        centroid_a_mm=tuple(float(v) for v in centroid_a),
        centroid_b_mm=tuple(float(v) for v in centroid_b),
        centroid_delta_mm=delta,
    )


def consistent_tri6_resultant_load_isoparametric(
    nodes_mm: np.ndarray,
    tri6: np.ndarray,
    *,
    total_force_n: np.ndarray | tuple[float, float, float],
    quadrature_order: int = 4,
) -> IsoparametricSurfaceLoad:
    """Uniform traction integrated on a general curved TRI6 surface."""
    nodes, faces = _validate_surface(nodes_mm, tri6)
    force = np.asarray(total_force_n, dtype=float).reshape(3)
    if not np.all(np.isfinite(force)) or float(np.linalg.norm(force)) <= 0.0:
        raise ValueError("total_force_n must be a finite non-zero vector")
    area, first_moment, scalar_weights, rule = _integrate_surface(
        nodes, faces, quadrature_order=quadrature_order
    )
    traction = force / area
    loads = scalar_weights[:, None] * traction[None, :]
    resultant = loads.sum(axis=0)
    moment = np.sum(np.cross(nodes, loads), axis=0)
    norm = max(float(np.linalg.norm(force)), np.finfo(float).tiny)
    error = float(np.linalg.norm(resultant - force) / norm)
    direct_moment = np.cross(first_moment, traction)
    if not np.all(np.isfinite(loads)) or error > 1.0e-12:
        raise RuntimeError(f"curved TRI6 resultant check failed: relative_error={error}")
    if not np.allclose(moment, direct_moment, rtol=2.0e-11, atol=max(float(np.linalg.norm(direct_moment)), 1.0) * 2.0e-11):
        raise RuntimeError("curved TRI6 moment integration check failed")
    return IsoparametricSurfaceLoad(
        loads_n=loads,
        surface_area_mm2=float(area),
        requested_resultant_n=tuple(float(v) for v in force),
        integrated_resultant_n=tuple(float(v) for v in resultant),
        integrated_moment_about_origin_nmm=tuple(float(v) for v in moment),
        relative_resultant_error=error,
        quadrature_method=rule.method,
        quadrature_order=rule.order,
    )
