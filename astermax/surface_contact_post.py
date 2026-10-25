"""Postprocess coupled node-to-TRI3 contact without inventing field data.

Pressure is recovered only on the named slave surface from tributary TRI3 area:

    A_i = sum(A_tri / 3)
    p_i = F_n,i / A_i

With the AsterMax mm-N-MPa unit convention, N/mm^2 is numerically MPa. Nodes that
are not members of the slave contact surface receive NaN gap/pressure and zero force
so downstream visualization can distinguish 'not defined' from a true zero value.
"""

from math import isfinite, sqrt
from pathlib import Path

from .gmsh_ascii import GmshImportError, TetraMesh
from .global_surface_contact import GlobalSurfaceContactResult


class SurfaceContactPostError(ValueError):
    """Raised when a contact result cannot be postprocessed consistently."""


def _triangle_area(a, b, c) -> float:
    ab = tuple(float(b[i]) - float(a[i]) for i in range(3))
    ac = tuple(float(c[i]) - float(a[i]) for i in range(3))
    cross = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    return 0.5 * sqrt(sum(value * value for value in cross))


def slave_tributary_area_mm2(
    mesh: TetraMesh,
    *,
    slave_group: str = "CONTACT_SLAVE",
) -> tuple[float, ...]:
    """Return nodal tributary area for the named TRI3 slave surface."""
    try:
        group = mesh.surface_group(slave_group)
    except GmshImportError as exc:
        raise SurfaceContactPostError(str(exc)) from exc
    if not group.triangles:
        raise SurfaceContactPostError("slave contact surface contains no TRI3 elements")
    area = [0.0] * len(mesh.nodes)
    for triangle in group.triangles:
        if len(triangle) != 3 or any(node < 0 or node >= len(mesh.nodes) for node in triangle):
            raise SurfaceContactPostError("slave surface contains invalid TRI3 connectivity")
        value = _triangle_area(*(mesh.nodes[node] for node in triangle))
        if not isfinite(value) or value <= 0.0:
            raise SurfaceContactPostError("slave surface contains a degenerate TRI3")
        share = value / 3.0
        for node in triangle:
            area[node] += share
    for node in group.node_indices:
        if area[node] <= 0.0:
            raise SurfaceContactPostError("slave contact node has zero tributary area")
    return tuple(area)


def surface_contact_nodal_fields(
    mesh: TetraMesh,
    result: GlobalSurfaceContactResult,
    *,
    slave_group: str = "CONTACT_SLAVE",
) -> dict[str, tuple]:
    """Expand global surface-contact states into dense auditable nodal fields."""
    node_count = len(mesh.nodes)
    if node_count <= 0:
        raise SurfaceContactPostError("mesh contains no nodes")
    if len(result.displacements) != 3 * node_count:
        raise SurfaceContactPostError("contact displacement vector does not match mesh")
    tributary = slave_tributary_area_mm2(mesh, slave_group=slave_group)
    try:
        slave_nodes = set(mesh.surface_group(slave_group).node_indices)
    except GmshImportError as exc:
        raise SurfaceContactPostError(str(exc)) from exc

    gap = [float("nan")] * node_count
    penetration = [0.0] * node_count
    normal_force = [0.0] * node_count
    pressure = [float("nan")] * node_count
    active = [0.0] * node_count
    force_vector = [(0.0, 0.0, 0.0)] * node_count
    seen = set()

    for state in result.contact_states:
        node = int(state.slave_node)
        if node < 0 or node >= node_count:
            raise SurfaceContactPostError("contact state references an unknown slave node")
        if node not in slave_nodes:
            raise SurfaceContactPostError("contact state references a node outside the named slave surface")
        if node in seen:
            raise SurfaceContactPostError("duplicate contact state for one slave node")
        seen.add(node)
        values = (
            float(state.signed_gap_mm),
            float(state.penetration_mm),
            float(state.normal_force_n),
            *(float(value) for value in state.slave_force_n),
        )
        if not all(isfinite(value) for value in values):
            raise SurfaceContactPostError("contact state contains non-finite values")
        if state.penetration_mm < 0.0 or state.normal_force_n < 0.0:
            raise SurfaceContactPostError("contact penetration/normal force cannot be negative")
        gap[node] = float(state.signed_gap_mm)
        penetration[node] = float(state.penetration_mm)
        normal_force[node] = float(state.normal_force_n)
        active[node] = 1.0 if state.active else 0.0
        force_vector[node] = tuple(float(value) for value in state.slave_force_n)
        pressure[node] = float(state.normal_force_n) / tributary[node]

    missing = sorted(slave_nodes.difference(seen))
    if missing:
        raise SurfaceContactPostError(f"contact result is missing slave nodes: {missing}")

    return {
        "contact_gap_mm": tuple(gap),
        "contact_penetration_mm": tuple(penetration),
        "contact_normal_force_N": tuple(normal_force),
        "contact_pressure_MPa": tuple(pressure),
        "contact_active": tuple(active),
        "contact_force_N": tuple(force_vector),
        "contact_tributary_area_mm2": tuple(tributary),
    }


def write_surface_contact_legacy_vtk(
    path: str | Path,
    mesh: TetraMesh,
    result: GlobalSurfaceContactResult,
    *,
    slave_group: str = "CONTACT_SLAVE",
) -> Path:
    """Write TET4 displacement and verified node/TRI3 contact fields to legacy VTK."""
    fields = surface_contact_nodal_fields(mesh, result, slave_group=slave_group)
    node_count = len(mesh.nodes)
    for element in mesh.elements:
        if len(element) != 4 or any(node < 0 or node >= node_count for node in element):
            raise SurfaceContactPostError("VTK export requires valid TET4 connectivity")

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# vtk DataFile Version 3.0",
        "AsterMax small-sliding node-to-TRI3 contact result",
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
    for name in (
        "contact_gap_mm",
        "contact_penetration_mm",
        "contact_normal_force_N",
        "contact_pressure_MPa",
        "contact_active",
        "contact_tributary_area_mm2",
    ):
        lines.append(f"SCALARS {name} double 1")
        lines.append("LOOKUP_TABLE default")
        lines.extend(f"{float(value):.17g}" for value in fields[name])
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination
