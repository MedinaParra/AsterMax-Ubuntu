"""Prepare geometric contact directly from named Gmsh physical surfaces.

This bridges preserved CAD/mesh semantics into the verified node-to-rigid-plane
contact kernel. Contact definitions are generated deterministically from the unique
nodes of a named TRI3 surface. Solved contact states can be expanded to dense nodal
fields and exported as an auditable legacy-VTK artifact for ParaView.
"""

from math import isfinite
from pathlib import Path
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
    zero gap. Duplicate states for one node are rejected because the current contact
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


def write_contact_legacy_vtk(
    path: str | Path,
    mesh: TetraMesh,
    result: GeometricContactResult,
) -> Path:
    """Write TET4 geometry plus displacement/contact nodal fields to ASCII VTK.

    This contact artifact intentionally does not invent stresses: the current
    geometric-contact result does not yet carry element stress recovery. Geometry is
    undeformed and displacement is exported as POINT_DATA for ParaView Warp By Vector.
    """
    node_count = len(mesh.nodes)
    if node_count < 1 or len(result.displacements) != 3 * node_count:
        raise ContactPreparationError("contact displacement vector does not match mesh")
    for element in mesh.elements:
        if len(element) != 4 or any(node < 0 or node >= node_count for node in element):
            raise ContactPreparationError("VTK contact export requires valid TET4 connectivity")
    fields = contact_nodal_fields(node_count, result)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# vtk DataFile Version 3.0",
        "AsterMax frictionless node-plane contact result",
        "ASCII",
        "DATASET UNSTRUCTURED_GRID",
        f"POINTS {node_count} double",
    ]
    lines.extend(" ".join(f"{float(value):.17g}" for value in node) for node in mesh.nodes)
    lines.append(f"CELLS {len(mesh.elements)} {5 * len(mesh.elements)}")
    lines.extend("4 " + " ".join(str(int(node)) for node in element) for element in mesh.elements)
    lines.append(f"CELL_TYPES {len(mesh.elements)}")
    lines.extend("10" for _ in mesh.elements)
    lines.append(f"POINT_DATA {node_count}")
    lines.append("VECTORS displacement_mm double")
    for node in range(node_count):
        base = 3 * node
        lines.append(" ".join(f"{float(result.displacements[base+i]):.17g}" for i in range(3)))
    lines.append("VECTORS contact_force_N double")
    lines.extend(" ".join(f"{value:.17g}" for value in vector) for vector in fields["contact_force_N"])
    for name in ("contact_gap_mm", "contact_penetration_mm", "contact_normal_force_N", "contact_active"):
        lines.append(f"SCALARS {name} double 1")
        lines.append("LOOKUP_TABLE default")
        lines.extend(f"{float(value):.17g}" for value in fields[name])
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination
