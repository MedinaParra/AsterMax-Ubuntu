from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


class GmshBridgeError(RuntimeError):
    """Raised when CAD/mesh data leaves the Windows PMV certified boundary."""


@dataclass(frozen=True)
class GmshTet4Mesh:
    nodes_mm: np.ndarray
    elements: np.ndarray
    surface_triangles: dict[str, np.ndarray]
    bbox_mm: tuple[float, float, float, float, float, float]
    dimensions_mm: tuple[float, float, float]
    gmsh_version: str


@dataclass(frozen=True)
class GmshTet10Mesh:
    nodes_mm: np.ndarray
    elements: np.ndarray
    surface_triangles: dict[str, np.ndarray]
    bbox_mm: tuple[float, float, float, float, float, float]
    dimensions_mm: tuple[float, float, float]
    gmsh_version: str


def _gmsh():
    try:
        import gmsh  # type: ignore
    except ImportError as exc:  # pragma: no cover - deployment failure path
        raise GmshBridgeError("gmsh is required for STEP meshing") from exc
    return gmsh


def _axis_surface_entities(gmsh, surfaces, bbox):
    xmin, ymin, zmin, xmax, ymax, zmax = bbox
    span = max(xmax - xmin, ymax - ymin, zmax - zmin, 1.0)
    tol = span * 1.0e-6
    targets = {
        "X_MIN": (0, xmin),
        "X_MAX": (0, xmax),
        "Y_MIN": (1, ymin),
        "Y_MAX": (1, ymax),
        "Z_MIN": (2, zmin),
        "Z_MAX": (2, zmax),
    }
    grouped: dict[str, list[int]] = {name: [] for name in targets}
    for dim, tag in surfaces:
        sb = gmsh.model.getBoundingBox(dim, tag)
        lows = sb[:3]
        highs = sb[3:]
        for name, (axis, value) in targets.items():
            if abs(lows[axis] - value) <= tol and abs(highs[axis] - value) <= tol:
                grouped[name].append(tag)
    missing = [name for name, tags in grouped.items() if not tags]
    if missing:
        raise GmshBridgeError("axis face scoping incomplete: " + ", ".join(missing))
    return grouped


def _prepare_single_step_solid(gmsh, path: Path):
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("astermax_windows_step_to_solve")
    imported = gmsh.model.occ.importShapes(str(path))
    gmsh.model.occ.synchronize()
    volumes = gmsh.model.getEntities(3)
    if len(volumes) != 1 or not any(dim == 3 for dim, _ in imported):
        raise GmshBridgeError(f"PMV requires exactly one imported 3-D solid; found {len(volumes)}")

    bbox = tuple(float(v) for v in gmsh.model.getBoundingBox(3, volumes[0][1]))
    xmin, ymin, zmin, xmax, ymax, zmax = bbox
    dimensions = (xmax - xmin, ymax - ymin, zmax - zmin)
    if not all(value > 0 for value in dimensions):
        raise GmshBridgeError(f"invalid STEP dimensions: {dimensions}")
    surface_entities = _axis_surface_entities(gmsh, gmsh.model.getEntities(2), bbox)
    return bbox, dimensions, surface_entities


def _node_table(gmsh):
    node_tags, coords, _ = gmsh.model.mesh.getNodes()
    nodes = np.asarray(coords, dtype=float).reshape((-1, 3))
    if nodes.size == 0:
        raise GmshBridgeError("Gmsh produced no nodes")
    return nodes, {int(tag): index for index, tag in enumerate(node_tags)}


def _remap_connectivity(raw_tags: np.ndarray, tag_to_index: dict[int, int]) -> np.ndarray:
    return np.vectorize(lambda tag: tag_to_index[int(tag)], otypes=[np.int64])(raw_tags)


def mesh_step_tet4(step_path: str | Path, mesh_size_mm: float) -> GmshTet4Mesh:
    """Import exactly one STEP solid in mm and expose solver-ready TET4 data."""
    path = Path(step_path)
    if path.suffix.lower() not in {".step", ".stp"} or not path.is_file():
        raise GmshBridgeError("certified input must be an existing STEP/STP file")
    if mesh_size_mm <= 0:
        raise GmshBridgeError("mesh_size_mm must be positive")

    gmsh = _gmsh()
    gmsh.initialize()
    try:
        bbox, dimensions, surface_entities = _prepare_single_step_solid(gmsh, path)

        gmsh.option.setNumber("Mesh.MeshSizeMin", float(mesh_size_mm))
        gmsh.option.setNumber("Mesh.MeshSizeMax", float(mesh_size_mm))
        gmsh.option.setNumber("Mesh.ElementOrder", 1)
        gmsh.model.mesh.generate(3)

        nodes, tag_to_index = _node_table(gmsh)

        volume_types, _, volume_nodes = gmsh.model.mesh.getElements(3)
        tetra_blocks = []
        unsupported = []
        for element_type, connectivity in zip(volume_types, volume_nodes):
            element_type = int(element_type)
            raw = np.asarray(connectivity, dtype=np.int64)
            if element_type == 4:
                tetra_blocks.append(raw.reshape((-1, 4)))
            elif raw.size:
                unsupported.append(element_type)
        if unsupported:
            raise GmshBridgeError(f"non-TET4 volume element types: {sorted(set(unsupported))}")
        if not tetra_blocks:
            raise GmshBridgeError("Gmsh produced no TET4 elements")
        tet_tags = np.vstack(tetra_blocks)
        elements = _remap_connectivity(tet_tags, tag_to_index)

        triangle_groups: dict[str, np.ndarray] = {}
        for name, entity_tags in surface_entities.items():
            blocks = []
            for entity_tag in entity_tags:
                surface_types, _, surface_nodes = gmsh.model.mesh.getElements(2, entity_tag)
                for element_type, connectivity in zip(surface_types, surface_nodes):
                    raw = np.asarray(connectivity, dtype=np.int64)
                    if int(element_type) == 2:
                        blocks.append(raw.reshape((-1, 3)))
                    elif raw.size:
                        raise GmshBridgeError(
                            f"surface {name} contains unsupported element type {int(element_type)}"
                        )
            if not blocks:
                raise GmshBridgeError(f"surface {name} contains no TRI3 elements")
            tri_tags = np.vstack(blocks)
            triangle_groups[name] = _remap_connectivity(tri_tags, tag_to_index)

        return GmshTet4Mesh(
            nodes_mm=nodes,
            elements=np.asarray(elements, dtype=np.int64),
            surface_triangles=triangle_groups,
            bbox_mm=bbox,
            dimensions_mm=tuple(float(value) for value in dimensions),
            gmsh_version=str(getattr(gmsh, "__version__", "unknown")),
        )
    finally:
        gmsh.finalize()


def mesh_step_tet10(step_path: str | Path, mesh_size_mm: float) -> GmshTet10Mesh:
    """Import one STEP solid and expose Gmsh type-11 TET10 / type-9 TRI6 data.

    This is the T10-B verification route. The current TET10 kernel is accepted
    only for straight-sided quadratic elements; the solver performs that
    fail-closed geometry check before assembly.
    """
    path = Path(step_path)
    if path.suffix.lower() not in {".step", ".stp"} or not path.is_file():
        raise GmshBridgeError("certified input must be an existing STEP/STP file")
    if mesh_size_mm <= 0:
        raise GmshBridgeError("mesh_size_mm must be positive")

    gmsh = _gmsh()
    gmsh.initialize()
    try:
        bbox, dimensions, surface_entities = _prepare_single_step_solid(gmsh, path)

        gmsh.option.setNumber("Mesh.MeshSizeMin", float(mesh_size_mm))
        gmsh.option.setNumber("Mesh.MeshSizeMax", float(mesh_size_mm))
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.model.mesh.generate(3)

        nodes, tag_to_index = _node_table(gmsh)

        volume_types, _, volume_nodes = gmsh.model.mesh.getElements(3)
        tetra_blocks = []
        unsupported = []
        for element_type, connectivity in zip(volume_types, volume_nodes):
            element_type = int(element_type)
            raw = np.asarray(connectivity, dtype=np.int64)
            if element_type == 11:
                tetra_blocks.append(raw.reshape((-1, 10)))
            elif raw.size:
                unsupported.append(element_type)
        if unsupported:
            raise GmshBridgeError(f"non-TET10 volume element types: {sorted(set(unsupported))}")
        if not tetra_blocks:
            raise GmshBridgeError("Gmsh produced no TET10 elements")
        tet_tags = np.vstack(tetra_blocks)
        elements = _remap_connectivity(tet_tags, tag_to_index)

        triangle_groups: dict[str, np.ndarray] = {}
        for name, entity_tags in surface_entities.items():
            blocks = []
            for entity_tag in entity_tags:
                surface_types, _, surface_nodes = gmsh.model.mesh.getElements(2, entity_tag)
                for element_type, connectivity in zip(surface_types, surface_nodes):
                    raw = np.asarray(connectivity, dtype=np.int64)
                    if int(element_type) == 9:
                        blocks.append(raw.reshape((-1, 6)))
                    elif raw.size:
                        raise GmshBridgeError(
                            f"surface {name} contains unsupported element type {int(element_type)}"
                        )
            if not blocks:
                raise GmshBridgeError(f"surface {name} contains no TRI6 elements")
            tri_tags = np.vstack(blocks)
            triangle_groups[name] = _remap_connectivity(tri_tags, tag_to_index)

        return GmshTet10Mesh(
            nodes_mm=nodes,
            elements=np.asarray(elements, dtype=np.int64),
            surface_triangles=triangle_groups,
            bbox_mm=bbox,
            dimensions_mm=tuple(float(value) for value in dimensions),
            gmsh_version=str(getattr(gmsh, "__version__", "unknown")),
        )
    finally:
        gmsh.finalize()


def unique_surface_nodes(triangles: np.ndarray) -> np.ndarray:
    tri = np.asarray(triangles, dtype=np.int64)
    if tri.ndim != 2 or tri.shape[1] < 3:
        raise ValueError("surface triangles must have shape (n, 3+)")
    return np.unique(tri.reshape(-1))


def fixed_dofs_for_nodes(node_indices: np.ndarray | list[int]) -> np.ndarray:
    nodes = np.unique(np.asarray(node_indices, dtype=np.int64))
    return np.column_stack((3 * nodes, 3 * nodes + 1, 3 * nodes + 2)).reshape(-1)


def distribute_resultant_on_triangles(
    nodes_mm: np.ndarray,
    triangles: np.ndarray,
    resultant_n: np.ndarray | list[float] | tuple[float, float, float],
) -> np.ndarray:
    """Distribute a requested resultant as a uniform traction over TRI3 faces."""
    nodes = np.asarray(nodes_mm, dtype=float)
    tri = np.asarray(triangles, dtype=np.int64)
    resultant = np.asarray(resultant_n, dtype=float)
    if resultant.shape != (3,):
        raise ValueError("resultant_n must contain exactly 3 components")
    loads = np.zeros_like(nodes)
    areas = []
    for conn in tri:
        a, b, c = nodes[conn]
        area = 0.5 * np.linalg.norm(np.cross(b - a, c - a))
        if area <= 0:
            raise ValueError("degenerate surface triangle")
        areas.append(area)
    total_area = float(np.sum(areas))
    if total_area <= 0:
        raise ValueError("surface area must be positive")
    for conn, area in zip(tri, areas):
        triangle_force = resultant * (area / total_area)
        loads[conn] += triangle_force / 3.0
    return loads


def distribute_resultant_on_tri6(
    nodes_mm: np.ndarray,
    triangles6: np.ndarray,
    resultant_n: np.ndarray | list[float] | tuple[float, float, float],
) -> np.ndarray:
    """Apply uniform traction to straight-sided Gmsh TRI6 faces consistently.

    For a quadratic straight-sided triangle, the exact integrals of the corner
    shape functions are zero and the three midside shape functions are A/3.
    The resulting nodal load preserves both the requested resultant and its
    centroidal moment without silently reducing the surface to TRI3.
    """
    nodes = np.asarray(nodes_mm, dtype=float)
    tri = np.asarray(triangles6, dtype=np.int64)
    resultant = np.asarray(resultant_n, dtype=float)
    if tri.ndim != 2 or tri.shape[1] != 6:
        raise ValueError("triangles6 must have shape (n, 6)")
    if resultant.shape != (3,):
        raise ValueError("resultant_n must contain exactly 3 components")
    if tri.size and (np.any(tri < 0) or np.any(tri >= nodes.shape[0])):
        raise ValueError("triangles6 contains an out-of-range node index")

    loads = np.zeros_like(nodes)
    areas: list[float] = []
    for conn in tri:
        corners = nodes[conn[:3]]
        mids = nodes[conn[3:]]
        expected_mids = np.asarray(
            [
                0.5 * (corners[0] + corners[1]),
                0.5 * (corners[1] + corners[2]),
                0.5 * (corners[2] + corners[0]),
            ]
        )
        scale = max(float(np.linalg.norm(corners.max(axis=0) - corners.min(axis=0))), 1.0)
        if not np.allclose(mids, expected_mids, rtol=0.0, atol=scale * 1.0e-10):
            raise ValueError("curved TRI6 traction integration is outside the T10-B verification scope")
        area = 0.5 * np.linalg.norm(np.cross(corners[1] - corners[0], corners[2] - corners[0]))
        if area <= 0.0:
            raise ValueError("degenerate TRI6 surface triangle")
        areas.append(float(area))

    total_area = float(np.sum(areas))
    if total_area <= 0.0:
        raise ValueError("surface area must be positive")

    for conn, area in zip(tri, areas):
        triangle_force = resultant * (area / total_area)
        loads[conn[3]] += triangle_force / 3.0
        loads[conn[4]] += triangle_force / 3.0
        loads[conn[5]] += triangle_force / 3.0
    return loads


def force_and_moment(
    nodes_mm: np.ndarray,
    nodal_forces_n: np.ndarray,
    *,
    origin_mm: np.ndarray | list[float] | tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> tuple[np.ndarray, np.ndarray]:
    nodes = np.asarray(nodes_mm, dtype=float)
    forces = np.asarray(nodal_forces_n, dtype=float)
    origin = np.asarray(origin_mm, dtype=float)
    if nodes.shape != forces.shape or nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("nodes and nodal forces must both have shape (n, 3)")
    resultant = forces.sum(axis=0)
    moment = np.cross(nodes - origin, forces).sum(axis=0)
    return resultant, moment
