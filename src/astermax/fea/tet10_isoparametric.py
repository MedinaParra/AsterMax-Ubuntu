from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from numpy.polynomial.legendre import leggauss

from .tet10 import tet10_B_matrix
from .tet4 import IsotropicMaterial


@dataclass(frozen=True)
class TetraQuadratureRule:
    method: str
    order: int
    points: np.ndarray
    weights: np.ndarray


@dataclass(frozen=True)
class Tet10JacobianAudit:
    quadrature_method: str
    quadrature_order: int
    point_count: int
    minimum_det_jacobian: float
    maximum_det_jacobian: float
    minimum_over_maximum_ratio: float


def duffy_tetra_gauss_rule(order: int) -> TetraQuadratureRule:
    """Independent tensor Gauss-Legendre rule mapped onto the reference tetrahedron.

    The Duffy map from the unit cube is
      r = u,
      s = (1-u) v,
      t = (1-u) (1-v) w,
    with determinant ``(1-u)^2 (1-v)``.  This rule is intentionally separate
    from the four-point symmetric production gate so it can act as an
    integration reference during curved-isoparametric code verification.
    """
    n = int(order)
    if n < 2 or n > 12:
        raise ValueError("order must be between 2 and 12")
    abscissae, weights_1d = leggauss(n)
    abscissae = 0.5 * (abscissae + 1.0)
    weights_1d = 0.5 * weights_1d
    points: list[tuple[float, float, float]] = []
    weights: list[float] = []
    for i, u in enumerate(abscissae):
        one_minus_u = 1.0 - float(u)
        for j, v in enumerate(abscissae):
            one_minus_v = 1.0 - float(v)
            for k, w in enumerate(abscissae):
                r = float(u)
                s = one_minus_u * float(v)
                t = one_minus_u * one_minus_v * float(w)
                jacobian = one_minus_u * one_minus_u * one_minus_v
                weight = float(weights_1d[i] * weights_1d[j] * weights_1d[k] * jacobian)
                points.append((r, s, t))
                weights.append(weight)
    p = np.asarray(points, dtype=float)
    q = np.asarray(weights, dtype=float)
    if p.shape != (n**3, 3) or q.shape != (n**3,):
        raise RuntimeError("unexpected Duffy quadrature shape")
    if not np.all(np.isfinite(p)) or not np.all(np.isfinite(q)) or np.any(q <= 0.0):
        raise RuntimeError("Duffy quadrature contains invalid values")
    if not np.isclose(float(np.sum(q)), 1.0 / 6.0, rtol=0.0, atol=5.0e-15):
        raise RuntimeError("Duffy quadrature does not integrate reference volume")
    return TetraQuadratureRule(
        method="DUFFY_TENSOR_GAUSS_LEGENDRE_REFERENCE",
        order=n,
        points=p,
        weights=q,
    )


def simplex_monomial_integral(i: int, j: int, k: int) -> float:
    """Exact integral of r^i s^j t^k over the unit reference tetrahedron."""
    powers = (int(i), int(j), int(k))
    if any(value < 0 for value in powers):
        raise ValueError("monomial powers must be non-negative")
    return float(
        math.factorial(powers[0])
        * math.factorial(powers[1])
        * math.factorial(powers[2])
        / math.factorial(sum(powers) + 3)
    )


def tet10_isoparametric_jacobian_audit(
    coords_mm: np.ndarray,
    *,
    quadrature_order: int = 4,
) -> Tet10JacobianAudit:
    coords = np.asarray(coords_mm, dtype=float)
    if coords.shape != (10, 3) or not np.all(np.isfinite(coords)):
        raise ValueError("coords_mm must be finite with shape (10,3)")
    rule = duffy_tetra_gauss_rule(quadrature_order)
    dets = np.asarray([tet10_B_matrix(coords, point)[1] for point in rule.points], dtype=float)
    minimum = float(np.min(dets))
    maximum = float(np.max(dets))
    if minimum <= 0.0 or not np.isfinite(maximum):
        raise ValueError("curved TET10 has non-positive or non-finite Jacobian")
    return Tet10JacobianAudit(
        quadrature_method=rule.method,
        quadrature_order=rule.order,
        point_count=int(rule.points.shape[0]),
        minimum_det_jacobian=minimum,
        maximum_det_jacobian=maximum,
        minimum_over_maximum_ratio=minimum / maximum,
    )


def tet10_stiffness_isoparametric_reference(
    coords_mm: np.ndarray,
    material: IsotropicMaterial,
    *,
    quadrature_order: int = 4,
) -> np.ndarray:
    """High-order reference integration for a general isoparametric TET10.

    This is a **verification reference**, not yet the production curved-element
    integration contract.  It intentionally uses many positive-weight Duffy
    points so the current four-point straight-sided rule can be audited without
    reusing the same quadrature assumption.
    """
    coords = np.asarray(coords_mm, dtype=float)
    if coords.shape != (10, 3) or not np.all(np.isfinite(coords)):
        raise ValueError("coords_mm must be finite with shape (10,3)")
    d = material.constitutive_matrix()
    rule = duffy_tetra_gauss_rule(quadrature_order)
    ke = np.zeros((30, 30), dtype=float)
    for point, weight in zip(rule.points, rule.weights):
        b, det_j = tet10_B_matrix(coords, point)
        ke += b.T @ d @ b * det_j * float(weight)
    if not np.all(np.isfinite(ke)):
        raise ValueError("isoparametric reference stiffness contains non-finite values")
    return ke


def relative_matrix_difference(a: np.ndarray, b: np.ndarray) -> float:
    left = np.asarray(a, dtype=float)
    right = np.asarray(b, dtype=float)
    if left.shape != right.shape or left.ndim != 2:
        raise ValueError("matrix shapes must match")
    denominator = max(float(np.linalg.norm(right)), np.finfo(float).tiny)
    return float(np.linalg.norm(left - right) / denominator)
