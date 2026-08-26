from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math

import numpy as np


class Tri6PressureRecoveryStatus(StrEnum):
    VALID_CONSISTENT_COMPRESSIVE_PRESSURE = "VALID_CONSISTENT_COMPRESSIVE_PRESSURE"
    BLOCKED_NEGATIVE_PRESSURE = "BLOCKED_NEGATIVE_PRESSURE"


@dataclass(frozen=True)
class Tri6PressureRecoveryResult:
    schema_version: str
    result_class: str
    status: Tri6PressureRecoveryStatus
    area_mm2: float
    nodal_reactions_n: np.ndarray
    consistent_matrix_mm2: np.ndarray
    projected_nodal_pressure_mpa: np.ndarray
    reproduced_nodal_reactions_n: np.ndarray
    max_reaction_reproduction_error_n: float
    nodal_reaction_resultant_n: float
    projected_pressure_resultant_n: float
    resultant_error_n: float
    minimum_pressure_mpa: float
    minimum_pressure_barycentric: np.ndarray
    maximum_pressure_mpa: float
    maximum_pressure_barycentric: np.ndarray
    contact_pressure_claim_authorized: bool
    nodal_contact_reactions_remain_valid: bool
    pressure_field_source: str
    industrial_validation_claimed: bool
    ot1613_pressure_claimed: bool
    ansys_equivalence_claimed: bool


def triangle_area_mm2(vertices_mm: np.ndarray) -> float:
    vertices = np.asarray(vertices_mm, dtype=float)
    if vertices.shape != (3, 3) or not np.all(np.isfinite(vertices)):
        raise ValueError("vertices_mm must be a finite (3, 3) array")
    area = 0.5 * float(np.linalg.norm(np.cross(vertices[1] - vertices[0], vertices[2] - vertices[0])))
    if not math.isfinite(area) or area <= 0.0:
        raise ValueError("TRI6 corner vertices must define a positive triangle area")
    return area


def tri6_consistent_pressure_matrix_mm2(area_mm2: float) -> np.ndarray:
    """Exact planar TRI6 matrix M_ij = integral_A N_i N_j dA.

    Node order is the standard quadratic triangle order:
    corners 1,2,3 followed by edge nodes 1-2, 2-3, 3-1.
    The matrix is exact for a straight-sided planar triangle and therefore avoids
    quadrature/order ambiguity in the pressure-provenance gate.
    """

    area = float(area_mm2)
    if not math.isfinite(area) or area <= 0.0:
        raise ValueError("area_mm2 must be finite and positive")
    integer_matrix = np.asarray(
        [
            [6, -1, -1, 0, -4, 0],
            [-1, 6, -1, 0, 0, -4],
            [-1, -1, 6, -4, 0, 0],
            [0, 0, -4, 32, 16, 16],
            [-4, 0, 0, 16, 32, 16],
            [0, -4, 0, 16, 16, 32],
        ],
        dtype=float,
    )
    return (area / 180.0) * integer_matrix


def tri6_pressure_value_mpa(
    projected_nodal_pressure_mpa: np.ndarray,
    barycentric: np.ndarray,
) -> float:
    pressure = np.asarray(projected_nodal_pressure_mpa, dtype=float).reshape(-1)
    l = np.asarray(barycentric, dtype=float).reshape(-1)
    if pressure.size != 6 or not np.all(np.isfinite(pressure)):
        raise ValueError("projected_nodal_pressure_mpa must contain six finite values")
    if l.size != 3 or not np.all(np.isfinite(l)):
        raise ValueError("barycentric must contain three finite values")
    if np.any(l < -1.0e-12) or abs(float(np.sum(l)) - 1.0) > 1.0e-10:
        raise ValueError("barycentric coordinates must be inside the triangle and sum to one")
    l1, l2, l3 = l
    shape = np.asarray(
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
    return float(shape @ pressure)


def _edge_stationary_candidate(a: float, b: float, c: float) -> float | None:
    # Quadratic q(t)=a*t^2+b*t+c. Return the interior stationary point only.
    if abs(a) <= 1.0e-15:
        return None
    t = -b / (2.0 * a)
    return float(t) if 0.0 < t < 1.0 else None


def tri6_quadratic_pressure_extrema(
    projected_nodal_pressure_mpa: np.ndarray,
) -> tuple[float, np.ndarray, float, np.ndarray]:
    """Find global extrema of the quadratic TRI6 interpolant on the triangle.

    A quadratic reaches its extrema at a vertex, an edge stationary point, or an
    interior stationary point. All such candidates are evaluated analytically;
    no sampling grid is used for the acceptance decision.
    """

    p = np.asarray(projected_nodal_pressure_mpa, dtype=float).reshape(-1)
    if p.size != 6 or not np.all(np.isfinite(p)):
        raise ValueError("projected_nodal_pressure_mpa must contain six finite values")
    p1, p2, p3, p4, p5, p6 = (float(value) for value in p)

    candidates: list[np.ndarray] = [
        np.asarray([1.0, 0.0, 0.0]),
        np.asarray([0.0, 1.0, 0.0]),
        np.asarray([0.0, 0.0, 1.0]),
    ]

    # Edge 1-2: t=L2, pressure values p1, p4, p2 at t=0,.5,1.
    edge_specs = (
        (p1, p4, p2, lambda t: np.asarray([1.0 - t, t, 0.0])),
        (p2, p5, p3, lambda t: np.asarray([0.0, 1.0 - t, t])),
        (p3, p6, p1, lambda t: np.asarray([t, 0.0, 1.0 - t])),
    )
    for q0, qmid, q1, mapper in edge_specs:
        a = 2.0 * (q0 + q1 - 2.0 * qmid)
        b = 4.0 * qmid - 3.0 * q0 - q1
        t = _edge_stationary_candidate(a, b, q0)
        if t is not None:
            candidates.append(mapper(t))

    # With x=L1, y=L2, L3=1-x-y:
    # p = ax*x^2 + axy*x*y + ay*y^2 + bx*x + by*y + c.
    ax = 2.0 * p1 + 2.0 * p3 - 4.0 * p6
    axy = 4.0 * p3 + 4.0 * p4 - 4.0 * p5 - 4.0 * p6
    ay = 2.0 * p2 + 2.0 * p3 - 4.0 * p5
    bx = -p1 - 3.0 * p3 + 4.0 * p6
    by = -p2 - 3.0 * p3 + 4.0 * p5
    hessian = np.asarray([[2.0 * ax, axy], [axy, 2.0 * ay]], dtype=float)
    gradient_offset = np.asarray([bx, by], dtype=float)
    if abs(float(np.linalg.det(hessian))) > 1.0e-15:
        xy = np.linalg.solve(hessian, -gradient_offset)
        x, y = float(xy[0]), float(xy[1])
        z = 1.0 - x - y
        if x > 0.0 and y > 0.0 and z > 0.0:
            candidates.append(np.asarray([x, y, z], dtype=float))

    evaluated = [
        (tri6_pressure_value_mpa(p, bary), bary)
        for bary in candidates
    ]
    minimum = min(evaluated, key=lambda item: item[0])
    maximum = max(evaluated, key=lambda item: item[0])
    return minimum[0], minimum[1], maximum[0], maximum[1]


def recover_consistent_tri6_pressure(
    *,
    corner_vertices_mm: np.ndarray,
    nodal_reactions_n: np.ndarray,
    reaction_tolerance_n: float = 1.0e-8,
    pressure_tolerance_mpa: float = 1.0e-10,
) -> Tri6PressureRecoveryResult:
    """Project six TRI6 nodal normal reactions to a quadratic pressure field.

    The generalized nodal force relation is solved exactly:
        r_i = integral_A N_i p dA = sum_j M_ij p_j.

    A pressure claim is authorized only if the reconstructed quadratic field is
    non-negative over the entire triangle. Otherwise the nodal reactions remain
    valid contact forces but pressure provenance is blocked.
    """

    reactions = np.asarray(nodal_reactions_n, dtype=float).reshape(-1)
    if reactions.size != 6 or not np.all(np.isfinite(reactions)):
        raise ValueError("nodal_reactions_n must contain six finite values")
    if np.any(reactions < -reaction_tolerance_n):
        raise ValueError("nodal contact reactions must be non-negative within tolerance")
    if reaction_tolerance_n < 0.0 or pressure_tolerance_mpa < 0.0:
        raise ValueError("tolerances must be non-negative")

    area = triangle_area_mm2(corner_vertices_mm)
    matrix = tri6_consistent_pressure_matrix_mm2(area)
    pressure = np.linalg.solve(matrix, reactions)
    reproduced = matrix @ pressure
    reproduction_error = float(np.max(np.abs(reproduced - reactions)))
    resultant_reactions = float(np.sum(reactions))

    # Integral N1=N2=N3=0 and integral N4=N5=N6=A/3 for a straight TRI6.
    resultant_pressure = float((area / 3.0) * np.sum(pressure[3:6]))
    resultant_error = abs(resultant_pressure - resultant_reactions)
    pmin, xmin, pmax, xmax = tri6_quadratic_pressure_extrema(pressure)
    authorized = (
        reproduction_error <= reaction_tolerance_n
        and resultant_error <= reaction_tolerance_n * max(1.0, reactions.size)
        and pmin >= -pressure_tolerance_mpa
    )
    status = (
        Tri6PressureRecoveryStatus.VALID_CONSISTENT_COMPRESSIVE_PRESSURE
        if authorized
        else Tri6PressureRecoveryStatus.BLOCKED_NEGATIVE_PRESSURE
    )

    return Tri6PressureRecoveryResult(
        schema_version="AsterMaxTri6PressureRecoveryV1",
        result_class="TRI6_CONTACT_PRESSURE_PROVENANCE_GATE",
        status=status,
        area_mm2=area,
        nodal_reactions_n=reactions.copy(),
        consistent_matrix_mm2=matrix,
        projected_nodal_pressure_mpa=pressure,
        reproduced_nodal_reactions_n=reproduced,
        max_reaction_reproduction_error_n=reproduction_error,
        nodal_reaction_resultant_n=resultant_reactions,
        projected_pressure_resultant_n=resultant_pressure,
        resultant_error_n=resultant_error,
        minimum_pressure_mpa=pmin,
        minimum_pressure_barycentric=xmin,
        maximum_pressure_mpa=pmax,
        maximum_pressure_barycentric=xmax,
        contact_pressure_claim_authorized=authorized,
        nodal_contact_reactions_remain_valid=True,
        pressure_field_source="CONSISTENT_QUADRATIC_TRI6_PROJECTION_FROM_NODAL_NORMAL_REACTIONS",
        industrial_validation_claimed=False,
        ot1613_pressure_claimed=False,
        ansys_equivalence_claimed=False,
    )
