"""Minimal auditable Gmsh v2 ASCII importer for the AsterMax PMV.

This module intentionally supports only the subset needed by the current verified
linear-static kernel: 3D nodes plus first-order tetrahedra (Gmsh element type 4).
Geometry is assumed to have been generated in millimetres and the caller must state
that unit basis explicitly; Gmsh v2 does not encode a reliable engineering length
unit in the mesh file itself.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class GmshImportError(ValueError):
    """Raised when a mesh cannot be represented by the verified AsterMax kernel."""


@dataclass(frozen=True)
class TetraMesh:
    nodes: tuple[tuple[float, float, float], ...]
    elements: tuple[tuple[int, int, int, int], ...]
    source_unit: str


def _section(lines: list[str], name: str) -> list[str]:
    start_token = f"${name}"
    end_token = f"$End{name}"
    try:
        start = lines.index(start_token) + 1
        end = lines.index(end_token, start)
    except ValueError as exc:
        raise GmshImportError(f"missing Gmsh section: {name}") from exc
    return lines[start:end]


def parse_gmsh_v2_ascii(text: str, *, declared_unit: str) -> TetraMesh:
    """Parse a first-order tetrahedral Gmsh v2 ASCII mesh declared in mm."""
    if declared_unit != "mm":
        raise GmshImportError("mesh length unit must be explicitly resolved to mm")

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    mesh_format = _section(lines, "MeshFormat")
    if not mesh_format:
        raise GmshImportError("empty MeshFormat section")
    tokens = mesh_format[0].split()
    if len(tokens) < 3 or not tokens[0].startswith("2.") or tokens[1] != "0":
        raise GmshImportError("only Gmsh v2 ASCII meshes are supported")

    node_lines = _section(lines, "Nodes")
    try:
        expected_nodes = int(node_lines[0])
    except (IndexError, ValueError) as exc:
        raise GmshImportError("invalid node count") from exc
    if len(node_lines[1:]) != expected_nodes:
        raise GmshImportError("node count does not match Nodes section")

    node_by_id: dict[int, tuple[float, float, float]] = {}
    for line in node_lines[1:]:
        parts = line.split()
        if len(parts) != 4:
            raise GmshImportError("each v2 node must contain id x y z")
        node_id = int(parts[0])
        if node_id in node_by_id:
            raise GmshImportError("duplicate node id")
        node_by_id[node_id] = (float(parts[1]), float(parts[2]), float(parts[3]))

    element_lines = _section(lines, "Elements")
    try:
        expected_elements = int(element_lines[0])
    except (IndexError, ValueError) as exc:
        raise GmshImportError("invalid element count") from exc
    if len(element_lines[1:]) != expected_elements:
        raise GmshImportError("element count does not match Elements section")

    tetra_node_ids: list[tuple[int, int, int, int]] = []
    for line in element_lines[1:]:
        parts = line.split()
        if len(parts) < 3:
            raise GmshImportError("malformed element record")
        element_type = int(parts[1])
        tag_count = int(parts[2])
        connectivity = parts[3 + tag_count :]
        if element_type == 4:
            if len(connectivity) != 4:
                raise GmshImportError("TET4 element must reference four nodes")
            ids = tuple(int(value) for value in connectivity)
            if len(set(ids)) != 4:
                raise GmshImportError("TET4 connectivity contains duplicate nodes")
            tetra_node_ids.append(ids)  # type: ignore[arg-type]

    if not tetra_node_ids:
        raise GmshImportError("mesh contains no first-order tetrahedra")

    referenced = {node_id for tet in tetra_node_ids for node_id in tet}
    missing = sorted(referenced.difference(node_by_id))
    if missing:
        raise GmshImportError(f"elements reference unknown node ids: {missing}")

    # Compact to exactly the nodes used by supported tetrahedra. This prevents line,
    # triangle, or higher-order support entities from leaking unused DOFs into solve.
    ordered_ids = sorted(referenced)
    compact = {node_id: index for index, node_id in enumerate(ordered_ids)}
    nodes = tuple(node_by_id[node_id] for node_id in ordered_ids)
    elements = tuple(
        tuple(compact[node_id] for node_id in tet) for tet in tetra_node_ids
    )
    return TetraMesh(nodes=nodes, elements=elements, source_unit="mm")


def read_gmsh_v2_ascii(path: str | Path, *, declared_unit: str) -> TetraMesh:
    return parse_gmsh_v2_ascii(Path(path).read_text(encoding="utf-8"), declared_unit=declared_unit)
