"""Feature-aware cylindrical contact pairing for persistent AsterMax workflows.

This module prepares deterministic node-to-TRI3 pairs for cylindrical interfaces.
Each master TRI3 uses a local radial normal. Candidate discovery can use either the
reference exhaustive route or a deterministic AABB/BVH accelerator; both feed the
same finite-triangle projection and gap calculation, so the accelerated path changes
no constitutive contact physics.

Units: mm and N.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

from .contact_spatial_index import ContactSpatialIndexError, build_triangle_aabb_tree
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
    search_strategy: str
    candidate_triangle_tests: int
    exhaustive_triangle_tests: int

    @property
    def candidate_reduction_fraction(self) -> float:
        if self.exhaustive_triangle_tests <= 0:
            return 0.0
        return 1.0 - self.candidate_triangle_tests / self.exhaustive_triangle_tests


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
    search_strategy: Literal["bvh", "exhaustive"] = "bvh",
    bvh_leaf_size: int = 8,
) -> tuple[tuple[NodeTriangleContactPair, ...], CylindricalFeatureContactReport]:
    """Build persistent node-to-TRI3 pairs using local cylindrical master normals.

    ``exhaustive`` is retained as a verification oracle. ``bvh`` only removes master
    triangles that cannot be within the declared search distance according to an exact
    point-to-AABB lower bound. Final projection, inside-TRI3 testing, gap evaluation,
    and deterministic tie-breaking are identical for both strategies.
    """
    penalty = float(penalty_stiffness_n_per_mm)
    distance = float(search_distance_mm)
    if not math.isfinite(penalty) or penalty <= 0.0:
        raise FeatureContactError("contact penalty stiffness must be finite and positive")
    if not math.isfinite(distance) or distance < 0.0:
        raise FeatureContactError("contact search distance must be finite and non-negative")
    if master_normal_direction not in ("outward", "inward"):
        raise FeatureContactError("master_normal_direction must be outward or inward")
    if search_strategy not in ("bvh", "exhaustive"):
        raise FeatureContactError("search_strategy must be bvh or exhaustive")
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
    tree = None
    if search_strategy == "bvh":
        try:
            tree = build_triangle_aabb_tree(mesh.nodes, masters, leaf_size=bvh_leaf_size)
        except ContactSpatialIndexError as exc:
            raise FeatureContactError(str(exc)) from exc

    pairs = []
    distances = []
    candidate_tests = 0
    for slave_node in slave_nodes:
        if tree is None:
            candidate_masters = masters
        else:
            try:
                candidate_masters = tree.query_point(mesh.nodes[slave_node], distance_mm=distance)
            except ContactSpatialIndexError as exc:
                raise FeatureContactError(str(exc)) from exc
        candidates = []
        for tri in candidate_masters:
            if slave_node in tri:
                continue
            candidate_tests += 1
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

    exhaustive_tests = len(slave_nodes) * len(masters)
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
        search_strategy=search_strategy,
        candidate_triangle_tests=candidate_tests,
        exhaustive_triangle_tests=exhaustive_tests,
    )
