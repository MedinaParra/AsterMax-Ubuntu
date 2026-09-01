"""Feature-aware persistent surface selection for AsterMax verification workflows.

This module extends semantic boundary intent beyond planar model extremes.  It
re-identifies cylindrical engineering features from a complete triangulated boundary
without relying on OpenCASCADE/Gmsh face IDs.  The intended use cases are bolt holes,
shaft/seal seats and cylindrical contact interfaces that must survive remeshing.

The mechanism is deliberately auditable and verification-level: it uses triangle
centroids/normals, a declared cylinder axis, normalized transverse center and either
an absolute or normalized radius.  It is not a full commercial persistent-topology
kernel and fails closed when no feature is found.  Units are mm when radius_mm is used.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Sequence

from .gmsh_ascii import SurfaceGroup, TetraMesh
from .semantic_surface import SemanticSurfaceError, _triangle_geometry


class FeatureSurfaceError(ValueError):
    """Raised when a feature-aware surface cannot be resolved safely."""


@dataclass(frozen=True)
class CylindricalSurfaceIntent:
    name: str
    axis: str
    center_fraction: tuple[float, float] = (0.5, 0.5)
    radius_mm: float | None = None
    radius_fraction: float | None = None
    radial_tolerance_fraction: float = 0.03
    maximum_axis_normal_component: float = 0.20

    def __post_init__(self) -> None:
        if not self.name or '"' in self.name or "\n" in self.name:
            raise FeatureSurfaceError("feature surface name must be a non-empty simple string")
        if self.axis not in ("x", "y", "z"):
            raise FeatureSurfaceError("cylindrical feature axis must be x, y, or z")
        if len(self.center_fraction) != 2:
            raise FeatureSurfaceError("center_fraction must contain two transverse coordinates")
        if any((not math.isfinite(float(v))) or not (0.0 <= float(v) <= 1.0) for v in self.center_fraction):
            raise FeatureSurfaceError("center_fraction values must lie within [0, 1]")
        if (self.radius_mm is None) == (self.radius_fraction is None):
            raise FeatureSurfaceError("define exactly one of radius_mm or radius_fraction")
        if self.radius_mm is not None and ((not math.isfinite(float(self.radius_mm))) or float(self.radius_mm) <= 0.0):
            raise FeatureSurfaceError("radius_mm must be finite and positive")
        if self.radius_fraction is not None and ((not math.isfinite(float(self.radius_fraction))) or float(self.radius_fraction) <= 0.0):
            raise FeatureSurfaceError("radius_fraction must be finite and positive")
        if (not math.isfinite(float(self.radial_tolerance_fraction))) or not (0.0 < float(self.radial_tolerance_fraction) < 0.5):
            raise FeatureSurfaceError("radial_tolerance_fraction must satisfy 0 < value < 0.5")
        if (not math.isfinite(float(self.maximum_axis_normal_component))) or not (0.0 <= float(self.maximum_axis_normal_component) < 1.0):
            raise FeatureSurfaceError("maximum_axis_normal_component must satisfy 0 <= value < 1")


@dataclass(frozen=True)
class CylindricalSurfaceResolution:
    intent: CylindricalSurfaceIntent
    group: SurfaceGroup
    axis_index: int
    transverse_axes: tuple[int, int]
    center_mm: tuple[float, float]
    resolved_radius_mm: float
    radial_tolerance_mm: float
    selected_area_mm2: float
    selected_triangle_count: int
    mean_centroid_radius_mm: float
    max_centroid_radius_error_mm: float


def resolve_cylindrical_surface(
    mesh: TetraMesh,
    intent: CylindricalSurfaceIntent,
    *,
    boundary_group: str = "ALL_BOUNDARY",
    physical_tag: int = 0,
) -> CylindricalSurfaceResolution:
    """Resolve a cylindrical boundary feature from a complete surface triangulation."""
    if not mesh.nodes:
        raise FeatureSurfaceError("mesh contains no nodes")
    try:
        boundary = mesh.surface_group(boundary_group)
    except ValueError as exc:
        raise FeatureSurfaceError(str(exc)) from exc

    axis = {"x": 0, "y": 1, "z": 2}[intent.axis]
    transverse = tuple(i for i in range(3) if i != axis)
    mins = tuple(min(float(p[i]) for p in mesh.nodes) for i in range(3))
    maxs = tuple(max(float(p[i]) for p in mesh.nodes) for i in range(3))
    spans = tuple(maxs[i] - mins[i] for i in range(3))
    if any((not math.isfinite(v)) or v <= 0.0 for v in (spans[axis], spans[transverse[0]], spans[transverse[1]])):
        raise FeatureSurfaceError("model bounding box must have positive 3D spans")

    center = tuple(
        mins[t] + float(intent.center_fraction[j]) * spans[t]
        for j, t in enumerate(transverse)
    )
    transverse_reference = min(spans[t] for t in transverse)
    radius = float(intent.radius_mm) if intent.radius_mm is not None else float(intent.radius_fraction) * transverse_reference
    tolerance = max(radius * float(intent.radial_tolerance_fraction), transverse_reference * 1e-12)

    selected = []
    area = 0.0
    radii = []
    errors = []
    for tri in boundary.triangles:
        try:
            centroid, normal, tri_area = _triangle_geometry(mesh.nodes, tri)
        except SemanticSurfaceError as exc:
            raise FeatureSurfaceError(str(exc)) from exc
        du = centroid[transverse[0]] - center[0]
        dv = centroid[transverse[1]] - center[1]
        centroid_radius = math.sqrt(du*du + dv*dv)
        radial_error = abs(centroid_radius - radius)
        orientation_ok = abs(float(normal[axis])) <= float(intent.maximum_axis_normal_component)
        if radial_error <= tolerance and orientation_ok:
            selected.append(tuple(int(i) for i in tri))
            area += tri_area
            radii.append(centroid_radius)
            errors.append(radial_error)

    if not selected:
        raise FeatureSurfaceError(
            f"cylindrical feature {intent.name} matched no boundary triangles on axis {intent.axis}"
        )
    mean_radius = sum(radii) / len(radii)
    group = SurfaceGroup(intent.name, int(physical_tag), tuple(selected))
    return CylindricalSurfaceResolution(
        intent=intent,
        group=group,
        axis_index=axis,
        transverse_axes=transverse,
        center_mm=center,
        resolved_radius_mm=radius,
        radial_tolerance_mm=tolerance,
        selected_area_mm2=area,
        selected_triangle_count=len(selected),
        mean_centroid_radius_mm=mean_radius,
        max_centroid_radius_error_mm=max(errors),
    )


def apply_feature_surfaces(
    mesh: TetraMesh,
    intents: Sequence[CylindricalSurfaceIntent],
    *,
    boundary_group: str = "ALL_BOUNDARY",
) -> tuple[TetraMesh, tuple[CylindricalSurfaceResolution, ...]]:
    """Add deterministic feature-aware groups while preserving boundary evidence."""
    intents = tuple(intents)
    if not intents:
        raise FeatureSurfaceError("at least one feature surface intent is required")
    names = [intent.name for intent in intents]
    if len(set(names)) != len(names):
        raise FeatureSurfaceError("feature surface names must be unique")
    existing = {group.name for group in mesh.surface_groups}
    collisions = sorted(existing.intersection(names))
    if collisions:
        raise FeatureSurfaceError(f"feature surface names collide with existing groups: {collisions}")
    resolutions = tuple(
        resolve_cylindrical_surface(mesh, intent, boundary_group=boundary_group, physical_tag=2000+i)
        for i, intent in enumerate(intents)
    )
    updated = replace(mesh, surface_groups=mesh.surface_groups + tuple(r.group for r in resolutions))
    return updated, resolutions
