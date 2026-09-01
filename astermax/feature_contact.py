"""Feature-aware cylindrical contact pairing for persistent AsterMax workflows.

This module closes an important limitation of the planar contact bridge: a cylinder
cannot be represented by one global normal hint because its surface normal varies
with circumferential position.  Here each master TRI3 is oriented from a declared
cylindrical feature axis/center using its own local radial direction, then every
slave node is paired to the nearest finite master triangle projection.

The routine adds no contact constitutive physics.  It only prepares deterministic
``NodeTriangleContactPair`` objects for the already verified contact solvers. Units
are mm and N.  The implementation remains verification-level and deliberately uses
exhaustive search rather than a spatial acceleration structure.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

from .feature_surface import CylindricalSurfaceResolution
from .global_surface_contact import NodeTriangleContactPair
from .gmsh_ascii import TetraMesh
from .surface_contact import SurfaceContactError, project_point_to_triangle, triangle_unit_normal


class FeatureContactError(ValueError):
    """Raised when cylindrical feature contact cannot be prepared safely."""


@dataclass(frozen=True)
class CylindricalFeatureContactReport:
    slave_group: str
    master_group: str
    slave_node_count: int
    master_triangle_count: int
    pair_count: int
    max_reference_distance_mm: float
    mean_reference_distance_mm: float
    minimum_master_radial_alignment: float
    master_normal_direction: str


def _dot(a, b) -> float:
    return sum(float(a[i]) * float(b[i]) for i in range(3))


def _unit(v):
    norm = math.sqrt(sum(float(x) * float(x) for x in v))
    if not math.isfinite(norm) or norm <= 0.0:
        raise FeatureContactError("local cylindrical radial direction is undefined")
    return tuple(float(x) / norm for x in v)


def _local_radial_direction(mesh: TetraMesh, tri, resolution: CylindricalSurfaceResolution):
    centroid = tuple(
        sum(float(mesh.nodes[int(node)][i]) for node in tri) / 3.0 for i in range(3)
    )
    radial = [0.0, 0.0, 0.0]
    for j, axis in enumerate(resolution.transverse_axes):
        radial[axis] = centroid[axis] - float(resolution.center_mm[j])
    return _unit(radial)


def _oriented_master_triangles(
    mesh: TetraMesh,
    master: CylindricalSurfaceResolution,
    direction: Literal["outward", "inward"],
):
    oriented = []
    alignments = []
    sign = 1.0 if direction == "outward" else -1.0
    for triangle in master.group.triangles:
        tri = tuple(int(v) for v in triangle)
        try:
            normal = triangle_unit_normal(*(mesh.nodes[node] for node in tri))
        except (SurfaceContactError, IndexError) as exc:
            raise FeatureContactError(str(exc)) from exc
        target = tuple(sign * x for x in _local_radial_direction(mesh, tri, master))
        if _dot(normal, target) < 0.0:
            tri = (tri[0], tri[2], tri[1])
            normal = tuple(-float(x) for x in normal)
        alignment = _dot(normal, target)
        if not math.isfinite(alignment) or alignment <= 0.0:
            raise FeatureContactError("master TRI3 cannot be aligned to local cylindrical normal")
        oriented.append(tri)
        alignments.append(alignment)
    if not oriented:
        raise FeatureContactError("cylindrical master feature contains no TRI3 elements")
    return tuple(sorted(oriented)), tuple(alignments)


def build_cylindrical_feature_contact_pairs(
    mesh: TetraMesh,
    slave: CylindricalSurfaceResolution,
    master: CylindricalSurfaceResolution,
    *,
    penalty_stiffness_n_per_mm: float,
    search_distance_mm: float,
    master_normal_direction: Literal["outward", "inward"] = "outward",
) -> tuple[tuple[NodeTriangleContactPair, ...], CylindricalFeatureContactReport]:
    """Build persistent node-to-TRI3 pairs using local cylindrical master normals.

    The slave/master resolutions must refer to the same cylinder axis and center.
    Every slave node must project inside a finite master TRI3 within the declared
    search distance.  A missing projection fails closed instead of silently dropping
    contact.  Ties are resolved deterministically by triangle connectivity.
    """
    penalty = float(penalty_stiffness_n_per_mm)
    distance = float(search_distance_mm)
    if not math.isfinite(penalty) or penalty <= 0.0:
        raise FeatureContactError("contact penalty stiffness must be finite and positive")
    if not math.isfinite(distance) or distance < 0.0:
        raise FeatureContactError("contact search distance must be finite and non-negative")
    if master_normal_direction not in ("outward", "inward"):
        raise FeatureContactError("master_normal_direction must be outward or inward")
    if slave.axis_index != master.axis_index or slave.transverse_axes != master.transverse_axes:
        raise FeatureContactError("slave and master cylindrical features must use the same axis")
    center_delta = math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(slave.center_mm, master.center_mm)))
    scale = max(float(slave.resolved_radius_mm), float(master.resolved_radius_mm), 1.0)
    if center_delta > scale * 1e-9:
        raise FeatureContactError("slave and master cylindrical features must be concentric")
    slave_nodes = tuple(slave.group.node_indices)
    if not slave_nodes:
        raise FeatureContactError("cylindrical slave feature contains no nodes")

    masters, alignments = _oriented_master_triangles(mesh, master, master_normal_direction)
    pairs = []
    distances = []
    for slave_node in slave_nodes:
        candidates = []
        for tri in masters:
            if slave_node in tri:
                continue
            try:
                projection = project_point_to_triangle(
                    mesh.nodes[slave_node], *(mesh.nodes[index] for index in tri)
                )
            except SurfaceContactError as exc:
                raise FeatureContactError(str(exc)) from exc
            reference_distance = abs(float(projection.signed_gap_mm))
            if projection.inside_triangle and reference_distance <= distance:
                candidates.append((reference_distance, tri))
        if not candidates:
            raise FeatureContactError(
                f"slave node {slave_node} has no cylindrical master projection within {distance:g} mm"
            )
        reference_distance, tri = min(candidates, key=lambda item: (item[0], item[1]))
        pairs.append(NodeTriangleContactPair(int(slave_node), tri, penalty))
        distances.append(reference_distance)

    return tuple(pairs), CylindricalFeatureContactReport(
        slave_group=slave.group.name,
        master_group=master.group.name,
        slave_node_count=len(slave_nodes),
        master_triangle_count=len(masters),
        pair_count=len(pairs),
        max_reference_distance_mm=max(distances),
        mean_reference_distance_mm=sum(distances) / len(distances),
        minimum_master_radial_alignment=min(alignments),
        master_normal_direction=master_normal_direction,
    )
