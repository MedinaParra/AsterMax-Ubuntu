"""Mesh-semantic preparation for small-sliding surface contact.

This module converts named Gmsh Physical Surface groups into explicit
NodeTriangleContactPair definitions. Master TRI3 orientation is aligned to a caller-
supplied normal hint; no implicit CAD normal convention is assumed.
"""

from dataclasses import dataclass
import math
from typing import Sequence

from .gmsh_ascii import GmshImportError, TetraMesh
from .global_surface_contact import NodeTriangleContactPair
from .surface_contact import SurfaceContactError, project_point_to_triangle, triangle_unit_normal


class MeshSurfaceContactError(ValueError):
    """Raised when named mesh surfaces cannot form auditable contact pairs."""


@dataclass(frozen=True)
class MeshContactPairingReport:
    slave_group: str
    master_group: str
    slave_node_count: int
    master_triangle_count: int
    pair_count: int
    max_reference_distance_mm: float


def _unit(values: Sequence[float]) -> tuple[float, float, float]:
    if len(values) != 3:
        raise MeshSurfaceContactError("master normal hint must contain three components")
    vector = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in vector):
        raise MeshSurfaceContactError("master normal hint must be finite")
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude <= 0.0:
        raise MeshSurfaceContactError("master normal hint must be non-zero")
    return tuple(value / magnitude for value in vector)


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _oriented_triangle(mesh: TetraMesh, triangle, normal_hint):
    tri = tuple(int(value) for value in triangle)
    try:
        normal = triangle_unit_normal(*(mesh.nodes[index] for index in tri))
    except (SurfaceContactError, IndexError) as exc:
        raise MeshSurfaceContactError(str(exc)) from exc
    if _dot(normal, normal_hint) < 0.0:
        tri = (tri[0], tri[2], tri[1])
    return tri


def build_named_surface_contact_pairs(
    mesh: TetraMesh,
    *,
    slave_group: str = "CONTACT_SLAVE",
    master_group: str = "CONTACT_MASTER",
    master_normal_hint: Sequence[float],
    penalty_stiffness_n_per_mm: float,
    search_distance_mm: float,
) -> tuple[tuple[NodeTriangleContactPair, ...], MeshContactPairingReport]:
    """Pair every unique slave node to its nearest valid projected master TRI3.

    The current PMV intentionally uses exhaustive search for transparency. A candidate
    must have an orthogonal projection inside the finite master TRI3 and absolute
    reference gap <= search_distance_mm. Ties are resolved deterministically by the
    TRI3 connectivity tuple. Failure to pair any slave node is fatal.
    """
    penalty = float(penalty_stiffness_n_per_mm)
    distance = float(search_distance_mm)
    if not math.isfinite(penalty) or penalty <= 0.0:
        raise MeshSurfaceContactError("contact penalty stiffness must be finite and positive")
    if not math.isfinite(distance) or distance < 0.0:
        raise MeshSurfaceContactError("contact search distance must be finite and non-negative")
    normal_hint = _unit(master_normal_hint)
    try:
        slaves = mesh.surface_group(slave_group)
        masters = mesh.surface_group(master_group)
    except GmshImportError as exc:
        raise MeshSurfaceContactError(str(exc)) from exc
    if not slaves.node_indices:
        raise MeshSurfaceContactError("slave surface contains no nodes")
    if not masters.triangles:
        raise MeshSurfaceContactError("master surface contains no TRI3 elements")

    oriented = tuple(sorted(_oriented_triangle(mesh, tri, normal_hint) for tri in masters.triangles))
    pairs = []
    distances = []
    for slave in slaves.node_indices:
        candidates = []
        for tri in oriented:
            if slave in tri:
                continue
            try:
                projection = project_point_to_triangle(
                    mesh.nodes[slave], *(mesh.nodes[index] for index in tri)
                )
            except SurfaceContactError as exc:
                raise MeshSurfaceContactError(str(exc)) from exc
            reference_distance = abs(projection.signed_gap_mm)
            if projection.inside_triangle and reference_distance <= distance:
                candidates.append((reference_distance, tri))
        if not candidates:
            raise MeshSurfaceContactError(
                f"slave node {slave} has no master TRI3 projection within {distance:g} mm"
            )
        reference_distance, tri = min(candidates, key=lambda item: (item[0], item[1]))
        pairs.append(NodeTriangleContactPair(slave, tri, penalty))
        distances.append(reference_distance)

    return tuple(pairs), MeshContactPairingReport(
        slave_group=slave_group,
        master_group=master_group,
        slave_node_count=len(slaves.node_indices),
        master_triangle_count=len(oriented),
        pair_count=len(pairs),
        max_reference_distance_mm=max(distances, default=0.0),
    )
