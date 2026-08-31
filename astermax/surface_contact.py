"""Auditable frictionless node-to-TRI3 contact geometry for AsterMax PMV.

This module is intentionally geometry-first. It verifies the local kinematics and
force transfer required for later surface-to-surface contact without yet claiming a
production nonlinear contact solver.

For a slave point x and a master TRI3 (a,b,c), the point is orthogonally projected
onto the triangle plane. Barycentric coordinates determine whether the projection is
inside the finite triangle. The triangle normal defines signed gap; negative gap means
penetration when the normal points into the admissible slave half-space.

An active penalty contact produces slave force +Fn*n and an equal/opposite master
reaction distributed to the three master nodes by the barycentric projection weights.
This preserves force and moment for the local contact pair.
"""

from dataclasses import dataclass
import math
from typing import Sequence


class SurfaceContactError(ValueError):
    """Raised for invalid TRI3 contact geometry or contact parameters."""


@dataclass(frozen=True)
class TriangleProjection:
    projected_point_mm: tuple[float, float, float]
    barycentric: tuple[float, float, float]
    normal: tuple[float, float, float]
    signed_gap_mm: float
    inside_triangle: bool


@dataclass(frozen=True)
class NodeTriangleContactState:
    signed_gap_mm: float
    penetration_mm: float
    normal_force_n: float
    active: bool
    barycentric: tuple[float, float, float]
    slave_force_n: tuple[float, float, float]
    master_nodal_forces_n: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]


def _vec3(values: Sequence[float], name: str) -> tuple[float, float, float]:
    if len(values) != 3:
        raise SurfaceContactError(f"{name} must contain three components")
    result = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in result):
        raise SurfaceContactError(f"{name} components must be finite")
    return result


def _sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _add(a, b):
    return tuple(a[i] + b[i] for i in range(3))


def _scale(a, factor):
    return tuple(factor * a[i] for i in range(3))


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(a):
    return math.sqrt(_dot(a, a))


def triangle_unit_normal(
    a_mm: Sequence[float], b_mm: Sequence[float], c_mm: Sequence[float]
) -> tuple[float, float, float]:
    """Return the oriented unit normal of a non-degenerate TRI3."""
    a = _vec3(a_mm, "triangle node a")
    b = _vec3(b_mm, "triangle node b")
    c = _vec3(c_mm, "triangle node c")
    raw = _cross(_sub(b, a), _sub(c, a))
    magnitude = _norm(raw)
    if magnitude <= 0.0:
        raise SurfaceContactError("master triangle is degenerate")
    return _scale(raw, 1.0 / magnitude)


def project_point_to_triangle(
    point_mm: Sequence[float],
    a_mm: Sequence[float],
    b_mm: Sequence[float],
    c_mm: Sequence[float],
    *,
    barycentric_tolerance: float = 1e-10,
) -> TriangleProjection:
    """Orthogonally project a point to a TRI3 plane and recover barycentric weights."""
    if not math.isfinite(barycentric_tolerance) or barycentric_tolerance < 0.0:
        raise SurfaceContactError("barycentric tolerance must be finite and non-negative")
    p = _vec3(point_mm, "slave point")
    a = _vec3(a_mm, "triangle node a")
    b = _vec3(b_mm, "triangle node b")
    c = _vec3(c_mm, "triangle node c")
    normal = triangle_unit_normal(a, b, c)
    gap = _dot(normal, _sub(p, a))
    projected = _sub(p, _scale(normal, gap))

    v0 = _sub(b, a)
    v1 = _sub(c, a)
    v2 = _sub(projected, a)
    d00 = _dot(v0, v0)
    d01 = _dot(v0, v1)
    d11 = _dot(v1, v1)
    d20 = _dot(v2, v0)
    d21 = _dot(v2, v1)
    denominator = d00 * d11 - d01 * d01
    scale = max(d00 * d11, 1.0)
    if abs(denominator) <= 1e-14 * scale:
        raise SurfaceContactError("master triangle is numerically degenerate")
    beta = (d11 * d20 - d01 * d21) / denominator
    gamma = (d00 * d21 - d01 * d20) / denominator
    alpha = 1.0 - beta - gamma
    barycentric = (alpha, beta, gamma)
    inside = all(value >= -barycentric_tolerance for value in barycentric) and all(
        value <= 1.0 + barycentric_tolerance for value in barycentric
    )
    return TriangleProjection(projected, barycentric, normal, gap, inside)


def evaluate_node_triangle_penalty_contact(
    slave_point_mm: Sequence[float],
    a_mm: Sequence[float],
    b_mm: Sequence[float],
    c_mm: Sequence[float],
    *,
    penalty_stiffness_n_per_mm: float,
    activation_tolerance_mm: float = 1e-10,
) -> NodeTriangleContactState:
    """Evaluate one frictionless slave-node/master-TRI3 penalty contact pair.

    A pair is active only if the orthogonal projection lies inside the finite master
    triangle and the signed gap is more negative than the activation tolerance.
    """
    penalty = float(penalty_stiffness_n_per_mm)
    if not math.isfinite(penalty) or penalty <= 0.0:
        raise SurfaceContactError("contact penalty stiffness must be finite and positive")
    if not math.isfinite(activation_tolerance_mm) or activation_tolerance_mm < 0.0:
        raise SurfaceContactError("activation tolerance must be finite and non-negative")
    projection = project_point_to_triangle(slave_point_mm, a_mm, b_mm, c_mm)
    active = projection.inside_triangle and projection.signed_gap_mm < -activation_tolerance_mm
    penetration = max(0.0, -projection.signed_gap_mm) if active else 0.0
    normal_force = penalty * penetration
    slave_force = _scale(projection.normal, normal_force)
    master_total = _scale(slave_force, -1.0)
    master_forces = tuple(
        _scale(master_total, weight) for weight in projection.barycentric
    )
    return NodeTriangleContactState(
        signed_gap_mm=projection.signed_gap_mm,
        penetration_mm=penetration,
        normal_force_n=normal_force,
        active=active,
        barycentric=projection.barycentric,
        slave_force_n=slave_force,
        master_nodal_forces_n=master_forces,
    )


def resultant_and_moment_about_origin(
    slave_point_mm: Sequence[float],
    slave_force_n: Sequence[float],
    master_points_mm: Sequence[Sequence[float]],
    master_forces_n: Sequence[Sequence[float]],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Recover net force and moment of a local slave/master contact pair."""
    if len(master_points_mm) != 3 or len(master_forces_n) != 3:
        raise SurfaceContactError("TRI3 force recovery requires three master nodes/forces")
    points = [_vec3(slave_point_mm, "slave point")] + [
        _vec3(point, "master point") for point in master_points_mm
    ]
    forces = [_vec3(slave_force_n, "slave force")] + [
        _vec3(force, "master force") for force in master_forces_n
    ]
    resultant = [0.0, 0.0, 0.0]
    moment = [0.0, 0.0, 0.0]
    for point, force in zip(points, forces):
        cross = _cross(point, force)
        for i in range(3):
            resultant[i] += force[i]
            moment[i] += cross[i]
    return tuple(resultant), tuple(moment)
