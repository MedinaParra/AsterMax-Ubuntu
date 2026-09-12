"""Auditable Gmsh v2 ASCII importer for the AsterMax PMV.

The verified kernel consumes first-order tetrahedra (Gmsh type 4).  Triangular
surface elements (type 2) are also retained when they belong to named physical
groups so CAD/meshing intent can survive into boundary-condition preparation.
Coordinates are accepted only when the caller explicitly resolves the source to mm.
"""

from dataclasses import dataclass
from pathlib import Path


class GmshImportError(ValueError):
    """Raised when a mesh cannot be represented by the verified AsterMax kernel."""


@dataclass(frozen=True)
class SurfaceGroup:
    """Named triangular surface group using compact zero-based node indices."""

    name: str
    physical_tag: int
    triangles: tuple[tuple[int, int, int], ...]

    @property
    def node_indices(self) -> tuple[int, ...]:
        return tuple(sorted({node for tri in self.triangles for node in tri}))


@dataclass(frozen=True)
class TetraMesh:
    nodes: tuple[tuple[float, float, float], ...]
    elements: tuple[tuple[int, int, int, int], ...]
    source_unit: str
    surface_groups: tuple[SurfaceGroup, ...] = ()

    def surface_group(self, name: str) -> SurfaceGroup:
        matches = [group for group in self.surface_groups if group.name == name]
        if not matches:
            raise GmshImportError(f"unknown physical surface group: {name}")
        if len(matches) != 1:
            raise GmshImportError(f"physical surface group name is ambiguous: {name}")
        return matches[0]


def _section(lines: list[str], name: str, *, required: bool = True) -> list[str]:
    start_token = f"${name}"
    end_token = f"$End{name}"
    try:
        start = lines.index(start_token) + 1
        end = lines.index(end_token, start)
    except ValueError as exc:
        if required:
            raise GmshImportError(f"missing Gmsh section: {name}") from exc
        return []
    return lines[start:end]


def _physical_names(lines: list[str]) -> dict[tuple[int, int], str]:
    section = _section(lines, "PhysicalNames", required=False)
    if not section:
        return {}
    try:
        expected = int(section[0])
    except (IndexError, ValueError) as exc:
        raise GmshImportError("invalid PhysicalNames count") from exc
    if len(section[1:]) != expected:
        raise GmshImportError("physical-name count does not match section")

    names: dict[tuple[int, int], str] = {}
    for line in section[1:]:
        parts = line.split(maxsplit=2)
        if len(parts) != 3:
            raise GmshImportError("malformed physical-name record")
        dimension = int(parts[0])
        tag = int(parts[1])
        raw_name = parts[2].strip()
        if len(raw_name) < 2 or raw_name[0] != '"' or raw_name[-1] != '"':
            raise GmshImportError("physical group names must be quoted")
        name = raw_name[1:-1]
        key = (dimension, tag)
        if key in names:
            raise GmshImportError("duplicate physical-name tag")
        names[key] = name
    return names


def parse_gmsh_v2_ascii(text: str, *, declared_unit: str) -> TetraMesh:
    """Parse first-order TET4 plus named triangular surface groups in Gmsh v2 ASCII."""
    if declared_unit != "mm":
        raise GmshImportError("mesh length unit must be explicitly resolved to mm")

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    mesh_format = _section(lines, "MeshFormat")
    if not mesh_format:
        raise GmshImportError("empty MeshFormat section")
    tokens = mesh_format[0].split()
    if len(tokens) < 3 or not tokens[0].startswith("2.") or tokens[1] != "0":
        raise GmshImportError("only Gmsh v2 ASCII meshes are supported")

    physical_names = _physical_names(lines)

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
    surface_by_tag: dict[int, list[tuple[int, int, int]]] = {}
    for line in element_lines[1:]:
        parts = line.split()
        if len(parts) < 3:
            raise GmshImportError("malformed element record")
        element_type = int(parts[1])
        tag_count = int(parts[2])
        if tag_count < 0 or len(parts) < 3 + tag_count:
            raise GmshImportError("malformed element tags")
        tags = [int(value) for value in parts[3 : 3 + tag_count]]
        connectivity = parts[3 + tag_count :]
        if element_type == 4:
            if len(connectivity) != 4:
                raise GmshImportError("TET4 element must reference four nodes")
            ids = tuple(int(value) for value in connectivity)
            if len(set(ids)) != 4:
                raise GmshImportError("TET4 connectivity contains duplicate nodes")
            tetra_node_ids.append(ids)  # type: ignore[arg-type]
        elif element_type == 2 and tags:
            if len(connectivity) != 3:
                raise GmshImportError("TRI3 surface element must reference three nodes")
            physical_tag = tags[0]
            if (2, physical_tag) in physical_names:
                ids = tuple(int(value) for value in connectivity)
                if len(set(ids)) != 3:
                    raise GmshImportError("TRI3 connectivity contains duplicate nodes")
                surface_by_tag.setdefault(physical_tag, []).append(ids)  # type: ignore[arg-type]

    if not tetra_node_ids:
        raise GmshImportError("mesh contains no first-order tetrahedra")

    referenced = {node_id for tet in tetra_node_ids for node_id in tet}
    missing = sorted(referenced.difference(node_by_id))
    if missing:
        raise GmshImportError(f"elements reference unknown node ids: {missing}")

    # Surface groups must be genuine boundary entities of the supported volume mesh;
    # retaining an orphan surface node would create an invalid BC-to-volume mapping.
    surface_nodes = {node_id for tris in surface_by_tag.values() for tri in tris for node_id in tri}
    orphan_surface_nodes = sorted(surface_nodes.difference(referenced))
    if orphan_surface_nodes:
        raise GmshImportError(
            f"physical surfaces reference nodes outside TET4 volume mesh: {orphan_surface_nodes}"
        )

    ordered_ids = sorted(referenced)
    compact = {node_id: index for index, node_id in enumerate(ordered_ids)}
    nodes = tuple(node_by_id[node_id] for node_id in ordered_ids)
    elements = tuple(tuple(compact[node_id] for node_id in tet) for tet in tetra_node_ids)

    groups = []
    for physical_tag, tris in sorted(surface_by_tag.items()):
        groups.append(
            SurfaceGroup(
                name=physical_names[(2, physical_tag)],
                physical_tag=physical_tag,
                triangles=tuple(tuple(compact[node] for node in tri) for tri in tris),
            )
        )

    return TetraMesh(
        nodes=nodes,
        elements=elements,
        source_unit="mm",
        surface_groups=tuple(groups),
    )


def read_gmsh_v2_ascii(path: str | Path, *, declared_unit: str) -> TetraMesh:
    return parse_gmsh_v2_ascii(Path(path).read_text(encoding="utf-8"), declared_unit=declared_unit)
