"""Professional visualization fields for explicit-GAP preloaded frictional joints.

The exporter is intentionally downstream-only: it never recomputes contact physics.
Every plotted quantity comes from the converged ``GappedPreloadedJointResult`` and
its verified redistribution diagnostics. Source CAD coordinates remain the VTK
geometry; GAP is exported as a scalar hypothesis field so viewers can distinguish
nominal geometry from analysis assumptions.

Units: mm, N, MPa. Regime/support encodings are deterministic:
    support_state: OPEN=0, ACTIVE=1
    friction_regime: OPEN=0, STICK=1, SLIP=2
"""

from math import isfinite
from pathlib import Path
from typing import Sequence

from .bolt_pretension import BoltPretensionConnector
from .friction_contact_post import friction_contact_nodal_fields
from .gapped_joint_diagnostics import evaluate_gapped_joint
from .gapped_preloaded_joint import GappedPreloadedJointResult
from .gmsh_ascii import GmshImportError, TetraMesh


class GappedJointVTKError(ValueError):
    """Raised when a gapped-joint result cannot be exported consistently."""


def gapped_joint_nodal_fields(
    mesh: TetraMesh,
    connectors: Sequence[BoltPretensionConnector],
    result: GappedPreloadedJointResult,
    *,
    slave_group: str = "CONTACT_SLAVE",
) -> dict[str, tuple]:
    """Return dense nodal fields for professional joint visualization.

    Surface-only and bolt-only quantities use NaN outside their semantic domain so
    ParaView (or a future Windows viewer) does not confuse 'undefined' with zero.
    """
    node_count = len(mesh.nodes)
    if tuple(tuple(float(x) for x in p) for p in mesh.nodes) != result.source_nodes:
        raise GappedJointVTKError("mesh/source CAD nodes do not match the gapped-joint source geometry")
    if len(result.joint.displacements) != 3 * node_count:
        raise GappedJointVTKError("joint displacement vector does not match mesh")
    try:
        slave_nodes = set(mesh.surface_group(slave_group).node_indices)
        contact_fields = friction_contact_nodal_fields(
            mesh, result.joint.contact_result, slave_group=slave_group
        )
        report = evaluate_gapped_joint(connectors, result)
    except (GmshImportError, ValueError) as exc:
        raise GappedJointVTKError(str(exc)) from exc

    gap_map = dict(result.gap.gap_by_slave_mm)
    if set(gap_map) != slave_nodes:
        raise GappedJointVTKError("explicit GAP field must match the named slave surface exactly")

    nan = float("nan")
    initial_gap = [nan] * node_count
    final_gap = [nan] * node_count
    gap_closure = [nan] * node_count
    support_state = [nan] * node_count
    bolt_force = [nan] * node_count
    bolt_load_share = [nan] * node_count
    bolt_preload = [nan] * node_count

    zone_by_node = {zone.slave_node: zone for zone in report.zones}
    if set(zone_by_node) != slave_nodes:
        raise GappedJointVTKError("diagnostic zones must match the named slave surface")
    for node in sorted(slave_nodes):
        zone = zone_by_node[node]
        initial_gap[node] = float(zone.initial_gap_mm)
        final_gap[node] = float(zone.final_signed_gap_mm)
        gap_closure[node] = float(zone.closure_mm)
        support_state[node] = 1.0 if zone.active else 0.0

    if len(connectors) != len(report.redistribution.bolt_states):
        raise GappedJointVTKError("bolt definitions and redistribution states disagree")
    used_bolt_nodes = set()
    for connector, state in zip(connectors, report.redistribution.bolt_states):
        node = int(connector.node_b)
        if node < 0 or node >= node_count:
            raise GappedJointVTKError("bolt visualization references an unknown node")
        if node in used_bolt_nodes:
            raise GappedJointVTKError("multiple bolt connectors map to the same visualization node")
        used_bolt_nodes.add(node)
        values = (state.preload_n, state.final_axial_force_n, state.tensile_load_share)
        if not all(isfinite(float(v)) for v in values):
            raise GappedJointVTKError("bolt visualization state contains non-finite values")
        bolt_preload[node] = float(state.preload_n)
        bolt_force[node] = float(state.final_axial_force_n)
        bolt_load_share[node] = float(state.tensile_load_share)

    return {
        "initial_gap_mm": tuple(initial_gap),
        "final_gap_mm": tuple(final_gap),
        "gap_closure_mm": tuple(gap_closure),
        "support_state": tuple(support_state),
        "bolt_preload_N": tuple(bolt_preload),
        "bolt_axial_force_N": tuple(bolt_force),
        "bolt_load_share": tuple(bolt_load_share),
        **contact_fields,
    }


def write_gapped_joint_legacy_vtk(
    path: str | Path,
    mesh: TetraMesh,
    connectors: Sequence[BoltPretensionConnector],
    result: GappedPreloadedJointResult,
    *,
    slave_group: str = "CONTACT_SLAVE",
) -> Path:
    """Write source CAD geometry plus verified GAP/contact/bolt fields to legacy VTK."""
    fields = gapped_joint_nodal_fields(mesh, connectors, result, slave_group=slave_group)
    node_count = len(mesh.nodes)
    for element in mesh.elements:
        if len(element) != 4 or any(node < 0 or node >= node_count for node in element):
            raise GappedJointVTKError("VTK export requires valid TET4 connectivity")

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# vtk DataFile Version 3.0",
        "AsterMax explicit-GAP preloaded frictional joint",
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
        lines.append(" ".join(f"{float(result.joint.displacements[base+i]):.17g}" for i in range(3)))
    lines.append("VECTORS friction_force_N double")
    lines.extend(" ".join(f"{float(v):.17g}" for v in vector) for vector in fields["friction_force_N"])

    scalar_names = (
        "initial_gap_mm", "final_gap_mm", "gap_closure_mm", "support_state",
        "bolt_preload_N", "bolt_axial_force_N", "bolt_load_share",
        "contact_gap_mm", "contact_penetration_mm", "contact_normal_force_N",
        "contact_pressure_MPa", "friction_force_magnitude_N", "friction_traction_MPa",
        "friction_limit_N", "friction_utilization", "friction_regime", "contact_active",
        "contact_tributary_area_mm2",
    )
    for name in scalar_names:
        lines.append(f"SCALARS {name} double 1")
        lines.append("LOOKUP_TABLE default")
        lines.extend(f"{float(value):.17g}" for value in fields[name])
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination
