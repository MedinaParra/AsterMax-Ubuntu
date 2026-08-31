"""Prepare geometric contact directly from named Gmsh physical surfaces.

This bridges preserved CAD/mesh semantics into the verified node-to-rigid-plane
contact kernel.  Contact definitions are generated deterministically from the unique
nodes of a named TRI3 surface.  The helper also converts solved contact states into
full-length nodal fields suitable for VTK/GUI visualization.
"""

from math import isfinite
from typing import Sequence

from .geometric_contact import GeometricContactResult, NodePlaneContact
from .gmsh_ascii import GmshImportError, TetraMesh


class ContactPreparationError(ValueError):
    """Raised when mesh semantics cannot produce a valid contact definition/field."""


def surface_to_rigid_plane_contacts(
    mesh: TetraMesh,
    group_name: str,
    *,
    plane_point_mm: Sequence[float],
    normal: Sequence[float],
    penalty_stiffness_n_per_mm: float,
) -> tuple[NodePlaneContact, ...]:
    """Create one node-to-plane contact for every unique node of a physical surface."""
    if len(plane_point_mm) != 3 or len(normal) != 3:
        raise ContactPreparationError("plane point and normal must contain three components")
    point = tuple(float(value) for value in plane_point_mm)
    direction = tuple(float(value) for value in normal)
    penalty = float(penalty_stiffness_n_per_mm)
    if not all(isfinite(value) for value in (*point, *direction, penalty)):
        raise ContactPreparationError("contact plane and penalty values must be finite")
    if penalty <= 0.0:
        raise ContactPreparationError("contact penalty stiffness must be positive")
    if sum(value * value for value in direction) <= 0.0:
        raise ContactPreparationError("contact normal must be non-zero")
    try:
        group = mesh.surface_group(group_name)
    except GmshImportError as exc:
        raise ContactPreparationError(str(exc)) from exc
    if not group.triangles or not group.node_indices:
        raise ContactPreparationError("contact surface contains no TRI3 nodes")
    return tuple(
        NodePlaneContact(
            node=node,
            plane_point_mm=point,
            normal=direction,
            penalty_stiffness_n_per_mm=penalty,
        )
        for node in group.node_indices
    )


def contact_nodal_fields(
    node_count: int,
    result: GeometricContactResult,
) -> dict[str, tuple]:
    """Return dense nodal contact fields for visualization/postprocessing.

    Nodes without a contact definition receive zero force/penetration, ``active=0``,
    and NaN gap so an external viewer can distinguish non-contact nodes from a true
    zero gap.  Duplicate states for one node are rejected because the current contact
    kernel supports only one rigid-plane contact per node.
    """
    if node_count <= 0:
        raise ContactPreparationError("node_count must be positive")
    gap = [float("nan")] * node_count
    penetration = [0.0] * node_count
    normal_force = [0.0] * node_count
    active = [0.0] * node_count
    force_vector = [(0.0, 0.0, 0.0)] * node_count
    seen = set()
    for state in result.contacts:
        node = int(state.node)
        if node < 0 or node >= node_count:
            raise ContactPreparationError("contact result references an unknown node")
        if node in seen:
            raise ContactPreparationError("duplicate contact state for one node")
        seen.add(node)
        gap[node] = float(state.signed_gap_mm)
        penetration[node] = float(state.penetration_mm)
        normal_force[node] = float(state.normal_force_n)
        active[node] = 1.0 if state.active else 0.0
        force_vector[node] = tuple(float(value) for value in state.force_vector_n)
    return {
        "contact_gap_mm": tuple(gap),
        "contact_penetration_mm": tuple(penetration),
        "contact_normal_force_N": tuple(normal_force),
        "contact_active": tuple(active),
        "contact_force_N": tuple(force_vector),
    }
