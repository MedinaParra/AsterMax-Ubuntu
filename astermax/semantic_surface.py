"""Topology-robust semantic surface intent for AsterMax verification workflows.

This layer deliberately avoids CAD face IDs. It re-identifies engineering surfaces
from the meshed boundary using normalized position inside the model bounding box plus
triangle-plane orientation. The intent therefore survives remeshing and moderate
parametric dimension changes when the physical meaning of the face is unchanged.

It is a verification-level persistent-selection mechanism, not a full commercial CAD
topology naming system. Units are geometry-independent because position is normalized.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Sequence

from .gmsh_ascii import SurfaceGroup, TetraMesh


class SemanticSurfaceError(ValueError):
    """Raised when a semantic surface cannot be resolved unambiguously."""


@dataclass(frozen=True)
class SemanticSurfaceIntent:
    name: str
    axis: str
    side: str
    band_fraction: float = 0.02
    minimum_normal_alignment: float = 0.95

    def __post_init__(self) -> None:
        if not self.name or '"' in self.name or "\n" in self.name:
            raise SemanticSurfaceError("semantic surface name must be a non-empty simple string")
        if self.axis not in ("x", "y", "z"):
            raise SemanticSurfaceError("semantic surface axis must be x, y, or z")
        if self.side not in ("min", "max"):
            raise SemanticSurfaceError("semantic surface side must be min or max")
        if not math.isfinite(float(self.band_fraction)) or not (0.0 <= float(self.band_fraction) < 0.5):
            raise SemanticSurfaceError("band_fraction must satisfy 0 <= band < 0.5")
        if not math.isfinite(float(self.minimum_normal_alignment)) or not (0.0 < float(self.minimum_normal_alignment) <= 1.0):
            raise SemanticSurfaceError("minimum_normal_alignment must satisfy 0 < value <= 1")


@dataclass(frozen=True)
class SemanticSurfaceResolution:
    intent: SemanticSurfaceIntent
    group: SurfaceGroup
    model_minimum: tuple[float, float, float]
    model_maximum: tuple[float, float, float]
    selected_area: float
    selected_triangle_count: int


def _sub(a, b):
    return tuple(float(a[i]) - float(b[i]) for i in range(3))


def _cross(a, b):
    return (
        a[1]*b[2] - a[2]*b[1],
        a[2]*b[0] - a[0]*b[2],
        a[0]*b[1] - a[1]*b[0],
    )


def _triangle_geometry(nodes, tri):
    try:
        a, b, c = (nodes[int(i)] for i in tri)
    except (IndexError, TypeError) as exc:
        raise SemanticSurfaceError("boundary triangle references an unknown node") from exc
    ab = _sub(b, a)
    ac = _sub(c, a)
    cross = _cross(ab, ac)
    norm = math.sqrt(sum(v*v for v in cross))
    if norm <= 0.0 or not math.isfinite(norm):
        raise SemanticSurfaceError("boundary contains a degenerate triangle")
    centroid = tuple((float(a[i]) + float(b[i]) + float(c[i])) / 3.0 for i in range(3))
    unit = tuple(v / norm for v in cross)
    return centroid, unit, 0.5 * norm


def resolve_semantic_surface(
    mesh: TetraMesh,
    intent: SemanticSurfaceIntent,
    *,
    boundary_group: str = "ALL_BOUNDARY",
    physical_tag: int = 0,
) -> SemanticSurfaceResolution:
    """Resolve one engineering surface from a complete named boundary triangulation."""
    if not mesh.nodes:
        raise SemanticSurfaceError("mesh contains no nodes")
    try:
        boundary = mesh.surface_group(boundary_group)
    except ValueError as exc:
        raise SemanticSurfaceError(str(exc)) from exc
    axis = {"x": 0, "y": 1, "z": 2}[intent.axis]
    mins = tuple(min(float(p[i]) for p in mesh.nodes) for i in range(3))
    maxs = tuple(max(float(p[i]) for p in mesh.nodes) for i in range(3))
    span = maxs[axis] - mins[axis]
    if not math.isfinite(span) or span <= 0.0:
        raise SemanticSurfaceError(f"model has zero span along semantic axis {intent.axis}")
    target = mins[axis] if intent.side == "min" else maxs[axis]
    tolerance = max(span * float(intent.band_fraction), span * 1e-12)

    selected = []
    area = 0.0
    for tri in boundary.triangles:
        centroid, normal, tri_area = _triangle_geometry(mesh.nodes, tri)
        position_ok = abs(centroid[axis] - target) <= tolerance
        orientation_ok = abs(normal[axis]) >= float(intent.minimum_normal_alignment)
        if position_ok and orientation_ok:
            selected.append(tuple(int(i) for i in tri))
            area += tri_area
    if not selected:
        raise SemanticSurfaceError(
            f"semantic surface {intent.name} matched no boundary triangles on {intent.axis}-{intent.side}"
        )
    group = SurfaceGroup(intent.name, int(physical_tag), tuple(selected))
    return SemanticSurfaceResolution(
        intent=intent,
        group=group,
        model_minimum=mins,
        model_maximum=maxs,
        selected_area=area,
        selected_triangle_count=len(selected),
    )


def apply_semantic_surfaces(
    mesh: TetraMesh,
    intents: Sequence[SemanticSurfaceIntent],
    *,
    boundary_group: str = "ALL_BOUNDARY",
) -> tuple[TetraMesh, tuple[SemanticSurfaceResolution, ...]]:
    """Add deterministic semantic surface groups while preserving source boundary evidence."""
    intents = tuple(intents)
    if not intents:
        raise SemanticSurfaceError("at least one semantic surface intent is required")
    names = [intent.name for intent in intents]
    if len(set(names)) != len(names):
        raise SemanticSurfaceError("semantic surface names must be unique")
    existing = {group.name for group in mesh.surface_groups}
    collisions = sorted(existing.intersection(names))
    if collisions:
        raise SemanticSurfaceError(f"semantic surface names collide with existing groups: {collisions}")
    resolutions = tuple(
        resolve_semantic_surface(mesh, intent, boundary_group=boundary_group, physical_tag=1000+i)
        for i, intent in enumerate(intents)
    )
    updated = replace(mesh, surface_groups=mesh.surface_groups + tuple(r.group for r in resolutions))
    return updated, resolutions
