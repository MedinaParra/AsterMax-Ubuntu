from __future__ import annotations

from pathlib import Path

import numpy as np

from .gmsh_bridge import GmshBridgeError, GmshTet10Mesh
from .selections import SurfaceSelectionError, SurfaceSignature, resolve_surface_signature_in_model


def _gmsh():
    try:
        import gmsh  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise GmshBridgeError("gmsh is required for selected STEP meshing") from exc
    return gmsh


def _node_table(gmsh):
    node_tags, coords, _ = gmsh.model.mesh.getNodes()
    nodes = np.asarray(coords, dtype=float).reshape((-1, 3))
    if nodes.size == 0:
        raise GmshBridgeError("Gmsh produced no nodes")
    return nodes, {int(tag): index for index, tag in enumerate(node_tags)}


def _remap(raw_tags: np.ndarray, tag_to_index: dict[int, int]) -> np.ndarray:
    try:
        return np.vectorize(lambda tag: tag_to_index[int(tag)], otypes=[np.int64])(raw_tags)
    except KeyError as exc:
        raise GmshBridgeError("mesh connectivity references an unknown node tag") from exc


def mesh_step_tet10_with_selections(
    step_path: str | Path,
    mesh_size_mm: float,
    selections: dict[str, SurfaceSignature],
    *,
    relative_tolerance: float = 1.0e-8,
) -> GmshTet10Mesh:
    """Mesh one STEP solid and recover persisted CAD selections as TRI6 groups.

    Selection names are user/project identities.  Gmsh entity tags and mesh
    node IDs are intentionally not persisted.  Every signature is resolved
    against OCC geometry before meshing and failure/ambiguity aborts the run.
    """
    path = Path(step_path)
    if path.suffix.lower() not in {".step", ".stp"} or not path.is_file():
        raise GmshBridgeError("selected meshing requires an existing STEP/STP file")
    if not np.isfinite(mesh_size_mm) or mesh_size_mm <= 0.0:
        raise GmshBridgeError("mesh_size_mm must be finite and positive")
    if not selections:
        raise GmshBridgeError("at least one persistent surface selection is required")
    bad_names = [name for name in selections if not name or name.strip() != name]
    if bad_names:
        raise GmshBridgeError("selection names must be non-empty and trimmed")

    gmsh = _gmsh()
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_persistent_selected_mesh")
        imported = gmsh.model.occ.importShapes(str(path))
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        if len(volumes) != 1 or not any(dim == 3 for dim, _ in imported):
            raise GmshBridgeError(f"PMV requires exactly one imported 3-D solid; found {len(volumes)}")
        bbox = tuple(float(v) for v in gmsh.model.getBoundingBox(3, volumes[0][1]))
        dimensions = tuple(float(hi - lo) for lo, hi in zip(bbox[:3], bbox[3:]))
        if not all(value > 0.0 for value in dimensions):
            raise GmshBridgeError(f"invalid STEP dimensions: {dimensions}")

        resolved_tags: dict[str, int] = {}
        try:
            for name, signature in selections.items():
                resolved_tags[name] = resolve_surface_signature_in_model(
                    gmsh,
                    signature,
                    bbox,
                    relative_tolerance=relative_tolerance,
                ).entity_tag
        except SurfaceSelectionError as exc:
            raise GmshBridgeError(str(exc)) from exc
        if len(set(resolved_tags.values())) != len(resolved_tags):
            raise GmshBridgeError("two persistent selection names resolved to the same CAD face")

        gmsh.option.setNumber("Mesh.MeshSizeMin", float(mesh_size_mm))
        gmsh.option.setNumber("Mesh.MeshSizeMax", float(mesh_size_mm))
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.model.mesh.generate(3)
        nodes, tag_to_index = _node_table(gmsh)

        volume_types, _, volume_nodes = gmsh.model.mesh.getElements(3)
        tetra_blocks: list[np.ndarray] = []
        unsupported: list[int] = []
        for element_type, connectivity in zip(volume_types, volume_nodes):
            raw = np.asarray(connectivity, dtype=np.int64)
            if int(element_type) == 11:
                tetra_blocks.append(raw.reshape((-1, 10)))
            elif raw.size:
                unsupported.append(int(element_type))
        if unsupported:
            raise GmshBridgeError(f"non-TET10 volume element types: {sorted(set(unsupported))}")
        if not tetra_blocks:
            raise GmshBridgeError("Gmsh produced no TET10 elements")
        elements = _remap(np.vstack(tetra_blocks), tag_to_index)

        triangle_groups: dict[str, np.ndarray] = {}
        for name, entity_tag in resolved_tags.items():
            blocks: list[np.ndarray] = []
            surface_types, _, surface_nodes = gmsh.model.mesh.getElements(2, entity_tag)
            for element_type, connectivity in zip(surface_types, surface_nodes):
                raw = np.asarray(connectivity, dtype=np.int64)
                if int(element_type) == 9:
                    blocks.append(raw.reshape((-1, 6)))
                elif raw.size:
                    raise GmshBridgeError(
                        f"selected surface {name} contains unsupported element type {int(element_type)}"
                    )
            if not blocks:
                raise GmshBridgeError(f"selected surface {name} contains no TRI6 elements")
            triangle_groups[name] = _remap(np.vstack(blocks), tag_to_index)

        return GmshTet10Mesh(
            nodes_mm=nodes,
            elements=np.asarray(elements, dtype=np.int64),
            surface_triangles=triangle_groups,
            bbox_mm=bbox,
            dimensions_mm=dimensions,
            gmsh_version=str(getattr(gmsh, "__version__", "unknown")),
        )
    finally:
        gmsh.finalize()
