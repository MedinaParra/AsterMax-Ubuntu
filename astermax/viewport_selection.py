"""Deterministic screen-space picking helpers for the AsterMax CAD preview.

This module deliberately operates on preview TRI3 geometry only. A pick is a
model-authoring proposal anchor, not solver evidence and not a persistent CAD
face identity. Solver selections must still pass the engineering preparation
and approval gates.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Sequence


Vec3 = tuple[float, float, float]
Tri3 = tuple[int, int, int]


@dataclass(frozen=True)
class SurfacePick:
    triangle_index: int
    node_indices: Tri3
    centroid_mm: Vec3
    unit_normal: Vec3
    screen_depth: float


@dataclass(frozen=True)
class ForceCommand:
    magnitude_n: float
    direction: Vec3

    @property
    def vector_n(self) -> Vec3:
        return tuple(self.magnitude_n * v for v in self.direction)  # type: ignore[return-value]


def _rotate(p: Vec3, yaw: float, pitch: float) -> Vec3:
    x, y, z = p
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    x1, z1 = cy * x + sy * z, -sy * x + cy * z
    y2, z2 = cp * y - sp * z1, sp * y + cp * z1
    return (x1, y2, z2)


def project_nodes(
    nodes: Sequence[Vec3], *, width: float, height: float, yaw: float, pitch: float, zoom: float
) -> tuple[tuple[float, float, float], ...]:
    if not nodes:
        return ()
    if width <= 0 or height <= 0 or zoom <= 0 or not all(math.isfinite(v) for v in (width, height, yaw, pitch, zoom)):
        raise ValueError("viewport projection parameters must be finite and positive")
    cx = sum(p[0] for p in nodes) / len(nodes)
    cy = sum(p[1] for p in nodes) / len(nodes)
    cz = sum(p[2] for p in nodes) / len(nodes)
    centered = [(p[0] - cx, p[1] - cy, p[2] - cz) for p in nodes]
    rotated = [_rotate(p, yaw, pitch) for p in centered]
    span = max(max(abs(q[i]) for q in rotated) for i in range(3)) or 1.0
    scale = 0.42 * min(width, height) / span * zoom
    return tuple((width / 2 + q[0] * scale, height / 2 - q[1] * scale, q[2]) for q in rotated)


def _inside_triangle(px: float, py: float, a, b, c, tol: float = 1e-9) -> bool:
    def cross(u, v, p):
        return (p[0] - u[0]) * (v[1] - u[1]) - (p[1] - u[1]) * (v[0] - u[0])
    p = (px, py)
    d1 = cross(a, b, p)
    d2 = cross(b, c, p)
    d3 = cross(c, a, p)
    has_neg = d1 < -tol or d2 < -tol or d3 < -tol
    has_pos = d1 > tol or d2 > tol or d3 > tol
    return not (has_neg and has_pos)


def _normal(a: Vec3, b: Vec3, c: Vec3) -> Vec3:
    ux, uy, uz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
    vx, vy, vz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
    nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
    mag = math.sqrt(nx*nx + ny*ny + nz*nz)
    if mag <= 1e-15:
        raise ValueError("cannot pick a degenerate TRI3")
    return (nx/mag, ny/mag, nz/mag)


def pick_triangle(
    nodes: Sequence[Vec3], triangles: Sequence[Tri3], *, x: float, y: float,
    width: float, height: float, yaw: float, pitch: float, zoom: float,
) -> SurfacePick | None:
    """Return the front-most TRI3 under a screen point using the same projection as the PMV viewport."""
    if not triangles or not nodes:
        return None
    screen = project_nodes(nodes, width=width, height=height, yaw=yaw, pitch=pitch, zoom=zoom)
    hits: list[tuple[float, int, Tri3]] = []
    for index, tri in enumerate(triangles):
        if len(tri) != 3 or any(i < 0 or i >= len(nodes) for i in tri):
            raise ValueError("triangle connectivity is outside preview node range")
        a, b, c = (screen[i] for i in tri)
        if _inside_triangle(x, y, a, b, c):
            hits.append(((a[2]+b[2]+c[2])/3.0, index, tri))
    if not hits:
        return None
    depth, index, tri = max(hits, key=lambda item: (item[0], -item[1]))
    a3, b3, c3 = (nodes[i] for i in tri)
    centroid = tuple((a3[i]+b3[i]+c3[i])/3.0 for i in range(3))
    return SurfacePick(index, tri, centroid, _normal(a3, b3, c3), depth)  # type: ignore[arg-type]


_FORCE_RE = re.compile(r"(?P<value>[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+))\s*(?P<unit>kn|n)\b", re.IGNORECASE)
_AXIS_RE = re.compile(r"(?P<sign>[+-])?\s*(?P<axis>[xyz])\b", re.IGNORECASE)


def parse_force_command(text: str) -> ForceCommand | None:
    """Parse simple engineering commands such as 'aplica 25 kN aqui en -Z'."""
    match = _FORCE_RE.search(text)
    axis = _AXIS_RE.search(text)
    if not match or not axis:
        return None
    value = float(match.group("value").replace(",", "."))
    if not math.isfinite(value) or value == 0.0:
        return None
    if match.group("unit").lower() == "kn":
        value *= 1000.0
    sign = -1.0 if axis.group("sign") == "-" else 1.0
    axis_name = axis.group("axis").lower()
    direction = {
        "x": (sign, 0.0, 0.0),
        "y": (0.0, sign, 0.0),
        "z": (0.0, 0.0, sign),
    }[axis_name]
    return ForceCommand(abs(value), direction)
