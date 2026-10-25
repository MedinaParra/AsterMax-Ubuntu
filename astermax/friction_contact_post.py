"""Auditable postprocessing for updated node-to-TRI3 Coulomb contact.

Only quantities present in the verified contact state are exported. Slave nodal
pressure/traction use TRI3 tributary area, preserving the AsterMax mm-N-MPa
convention where N/mm^2 == MPa. Nodes outside CONTACT_SLAVE receive NaN for
surface-only scalar fields so visualization does not confuse 'undefined' with zero.

Regime encoding for VTK is deterministic:
    OPEN=0, STICK=1, SLIP=2
"""

from math import isfinite
from pathlib import Path

from .gmsh_ascii import GmshImportError, TetraMesh
from .surface_contact_post import SurfaceContactPostError, slave_tributary_area_mm2
from .updated_surface_friction import UpdatedSurfaceFrictionResult


class FrictionContactPostError(ValueError):
    """Raised when frictional contact fields cannot be recovered consistently."""


_REGIME_CODE = {"OPEN": 0.0, "STICK": 1.0, "SLIP": 2.0}


def friction_contact_nodal_fields(
    mesh: TetraMesh,
    result: UpdatedSurfaceFrictionResult,
    *,
    slave_group: str = "CONTACT_SLAVE",
) -> dict[str, tuple]:
    """Expand updated Coulomb states into dense, visualization-ready nodal fields."""
    node_count = len(mesh.nodes)
    if node_count <= 0:
        raise FrictionContactPostError("mesh contains no nodes")
    if len(result.displacements) != 3 * node_count:
        raise FrictionContactPostError("contact displacement vector does not match mesh")
    try:
        slave_nodes = set(mesh.surface_group(slave_group).node_indices)
        tributary = slave_tributary_area_mm2(mesh, slave_group=slave_group)
    except (GmshImportError, SurfaceContactPostError) as exc:
        raise FrictionContactPostError(str(exc)) from exc

    nan = float("nan")
    gap = [nan] * node_count
    penetration = [0.0] * node_count
    normal_force = [0.0] * node_count
    pressure = [nan] * node_count
    tangential_force = [(0.0, 0.0, 0.0)] * node_count
    tangential_force_mag = [0.0] * node_count
    friction_traction = [nan] * node_count
    friction_limit = [nan] * node_count
    friction_utilization = [nan] * node_count
    regime_code = [nan] * node_count
    active = [0.0] * node_count
    seen = set()

    for state in result.contact_states:
        node = int(state.slave_node)
        if node < 0 or node >= node_count:
            raise FrictionContactPostError("contact state references an unknown slave node")
        if node not in slave_nodes:
            raise FrictionContactPostError("contact state references a node outside the named slave surface")
        if node in seen:
            raise FrictionContactPostError("duplicate contact state for one slave node")
        seen.add(node)
        regime = str(state.regime).upper()
        if regime not in _REGIME_CODE:
            raise FrictionContactPostError(f"unknown friction regime: {state.regime}")
        ft = tuple(float(value) for value in state.tangential_force_n)
        if len(ft) != 3:
            raise FrictionContactPostError("tangential force vector must contain three components")
        values = (
            float(state.signed_gap_mm), float(state.penetration_mm),
            float(state.normal_force_n), float(state.tangential_force_magnitude_n),
            float(state.friction_limit_n), *ft,
        )
        if not all(isfinite(value) for value in values):
            raise FrictionContactPostError("contact state contains non-finite values")
        if state.penetration_mm < 0.0 or state.normal_force_n < 0.0:
            raise FrictionContactPostError("penetration/normal force cannot be negative")
        if state.tangential_force_magnitude_n < 0.0 or state.friction_limit_n < 0.0:
            raise FrictionContactPostError("friction magnitude/limit cannot be negative")
        vector_mag2 = sum(value * value for value in ft)
        declared_mag2 = float(state.tangential_force_magnitude_n) ** 2
        scale = max(1.0, vector_mag2, declared_mag2)
        if abs(vector_mag2 - declared_mag2) > 1e-9 * scale:
            raise FrictionContactPostError("tangential force vector disagrees with its declared magnitude")
        if state.tangential_force_magnitude_n > state.friction_limit_n + 1e-9 * max(1.0, state.friction_limit_n):
            raise FrictionContactPostError("tangential force exceeds Coulomb limit")
        if regime == "OPEN" and (state.active or state.normal_force_n > 1e-12 or state.tangential_force_magnitude_n > 1e-12):
            raise FrictionContactPostError("OPEN state cannot carry contact force")
        if regime != "OPEN" and not state.active:
            raise FrictionContactPostError("STICK/SLIP state must be active")

        area = tributary[node]
        gap[node] = float(state.signed_gap_mm)
        penetration[node] = float(state.penetration_mm)
        normal_force[node] = float(state.normal_force_n)
        pressure[node] = float(state.normal_force_n) / area
        tangential_force[node] = ft
        tangential_force_mag[node] = float(state.tangential_force_magnitude_n)
        friction_traction[node] = float(state.tangential_force_magnitude_n) / area
        friction_limit[node] = float(state.friction_limit_n)
        regime_code[node] = _REGIME_CODE[regime]
        active[node] = 1.0 if state.active else 0.0
        if state.friction_limit_n > 0.0:
            friction_utilization[node] = float(state.tangential_force_magnitude_n) / float(state.friction_limit_n)
        else:
            friction_utilization[node] = 0.0

    missing = sorted(slave_nodes.difference(seen))
    if missing:
        raise FrictionContactPostError(f"contact result is missing slave nodes: {missing}")

    return {
        "contact_gap_mm": tuple(gap),
        "contact_penetration_mm": tuple(penetration),
        "contact_normal_force_N": tuple(normal_force),
        "contact_pressure_MPa": tuple(pressure),
        "friction_force_N": tuple(tangential_force),
        "friction_force_magnitude_N": tuple(tangential_force_mag),
        "friction_traction_MPa": tuple(friction_traction),
        "friction_limit_N": tuple(friction_limit),
        "friction_utilization": tuple(friction_utilization),
        "friction_regime": tuple(regime_code),
        "contact_active": tuple(active),
        "contact_tributary_area_mm2": tuple(tributary),
    }


def write_friction_contact_legacy_vtk(
    path: str | Path,
    mesh: TetraMesh,
    result: UpdatedSurfaceFrictionResult,
    *,
    slave_group: str = "CONTACT_SLAVE",
) -> Path:
    """Write verified displacement/contact/friction fields to legacy VTK."""
    fields = friction_contact_nodal_fields(mesh, result, slave_group=slave_group)
    node_count = len(mesh.nodes)
    for element in mesh.elements:
        if len(element) != 4 or any(node < 0 or node >= node_count for node in element):
            raise FrictionContactPostError("VTK export requires valid TET4 connectivity")

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# vtk DataFile Version 3.0",
        "AsterMax updated node-to-TRI3 Coulomb contact result",
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
    lines.append("VECTORS friction_force_N double")
    lines.extend(" ".join(f"{value:.17g}" for value in vector) for vector in fields["friction_force_N"])
    for name in (
        "contact_gap_mm", "contact_penetration_mm", "contact_normal_force_N",
        "contact_pressure_MPa", "friction_force_magnitude_N", "friction_traction_MPa",
        "friction_limit_N", "friction_utilization", "friction_regime", "contact_active",
        "contact_tributary_area_mm2",
    ):
        lines.append(f"SCALARS {name} double 1")
        lines.append("LOOKUP_TABLE default")
        lines.extend(f"{float(value):.17g}" for value in fields[name])
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination
