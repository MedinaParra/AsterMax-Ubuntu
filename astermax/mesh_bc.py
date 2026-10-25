"""Boundary-condition preparation from named Gmsh physical surfaces.

This module is intentionally small and solver-agnostic. It converts preserved mesh
semantics into explicit global DOF maps for the verified linear-static kernel.
Uniform total surface force is distributed using TRI3 tributary areas, preserving the
requested resultant exactly (within floating-point tolerance).
"""

from math import sqrt
from typing import Iterable, Sequence

from .gmsh_ascii import GmshImportError, TetraMesh


class BoundaryPreparationError(ValueError):
    """Raised when named mesh semantics cannot produce a valid BC/load map."""


def fixed_surface_constraints(
    mesh: TetraMesh,
    group_name: str,
    *,
    components: Iterable[int] = (0, 1, 2),
    value: float = 0.0,
) -> dict[int, float]:
    """Constrain selected Cartesian components on all nodes in a named surface."""
    group = mesh.surface_group(group_name)
    selected = tuple(sorted(set(int(component) for component in components)))
    if not selected or any(component not in (0, 1, 2) for component in selected):
        raise BoundaryPreparationError("components must be a non-empty subset of {0,1,2}")
    constraints: dict[int, float] = {}
    for node in group.node_indices:
        for component in selected:
            constraints[3 * node + component] = float(value)
    return constraints


def _triangle_area(
    a: Sequence[float], b: Sequence[float], c: Sequence[float]
) -> float:
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    cross = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    return 0.5 * sqrt(sum(value * value for value in cross))


def surface_total_force_loads(
    mesh: TetraMesh,
    group_name: str,
    total_force: Sequence[float],
) -> dict[int, float]:
    """Distribute a total XYZ force across a named TRI3 surface by tributary area.

    Each triangle receives a share proportional to its area and passes one third of
    that share to each vertex. This is equivalent to integrating a uniform traction
    over first-order triangles while specifying the desired total resultant directly.
    """
    if len(total_force) != 3:
        raise BoundaryPreparationError("total_force must contain Fx, Fy, Fz")
    force = tuple(float(value) for value in total_force)
    group = mesh.surface_group(group_name)
    if not group.triangles:
        raise BoundaryPreparationError("surface group contains no TRI3 elements")

    areas = []
    for tri in group.triangles:
        area = _triangle_area(*(mesh.nodes[node] for node in tri))
        if area <= 0.0:
            raise BoundaryPreparationError("surface group contains a degenerate triangle")
        areas.append(area)
    total_area = sum(areas)
    if total_area <= 0.0:
        raise BoundaryPreparationError("surface group has zero total area")

    nodal_weights: dict[int, float] = {}
    for tri, area in zip(group.triangles, areas):
        share = area / (3.0 * total_area)
        for node in tri:
            nodal_weights[node] = nodal_weights.get(node, 0.0) + share

    loads: dict[int, float] = {}
    for node, weight in nodal_weights.items():
        for component, component_force in enumerate(force):
            value = component_force * weight
            if value != 0.0:
                loads[3 * node + component] = value
    return loads


def resultant_from_nodal_loads(loads: dict[int, float]) -> tuple[float, float, float]:
    """Recover the XYZ resultant from a global-DOF nodal-load map."""
    result = [0.0, 0.0, 0.0]
    for dof, value in loads.items():
        if dof < 0:
            raise BoundaryPreparationError("load DOF cannot be negative")
        result[dof % 3] += float(value)
    return tuple(result)  # type: ignore[return-value]
