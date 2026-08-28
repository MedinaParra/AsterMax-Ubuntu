from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from itertools import combinations
from pathlib import Path
from typing import Iterable

import numpy as np

from .axisymmetric_shoulder import XAxisShoulderFeature
from .evidence import sha256_file
from .gmsh_bridge import GmshBridgeError, _gmsh
from .persistent_geometry import (
    PersistentFaceSelection,
    PersistentGeometryError,
    resolve_face_selection_in_current_model,
)


class FeatureAdaptivityError(RuntimeError):
    pass


@dataclass(frozen=True)
class FeatureRefinedTet10Mesh:
    nodes_mm: np.ndarray
    elements: np.ndarray
    feature_sha256: str
    source_sha256: str
    global_size_mm: float
    local_size_mm: float
    local_box_mm: tuple[float, float, float, float, float, float]
    second_order_linear: bool
    gmsh_version: str
    local_element_count: int
    outside_element_count: int
    local_mean_max_corner_edge_mm: float
    outside_mean_max_corner_edge_mm: float | None
    mesh_sha256: str
    surface_tri6_by_selection: dict[str, np.ndarray] = field(default_factory=dict)
    surface_resolution_by_selection: dict[str, tuple[int, str, str]] = field(default_factory=dict)


def _step(path: str | Path) -> Path:
    p = Path(path)
    if p.suffix.lower() not in {".step", ".stp"} or not p.is_file():
        raise GmshBridgeError("feature adaptivity input must be an existing STEP/STP file")
    return p


def _mesh_hash(nodes: np.ndarray, elements: np.ndarray, feature_sha256: str, box: tuple[float, ...]) -> str:
    h = hashlib.sha256()
    h.update(b"AsterMaxFeatureRefinedTet10MeshV1\0")
    h.update(str(feature_sha256).encode("ascii"))
    h.update(np.asarray(box, dtype="<f8").tobytes(order="C"))
    h.update(np.asarray(nodes, dtype="<f8").tobytes(order="C"))
    h.update(np.asarray(elements, dtype="<i8").tobytes(order="C"))
    return h.hexdigest()


def shoulder_local_box(
    feature: XAxisShoulderFeature,
    *,
    padding_mm: float,
) -> tuple[float, float, float, float, float, float]:
    padding = float(padding_mm)
    if not np.isfinite(padding) or padding <= 0.0:
        raise ValueError("padding_mm must be finite and positive")
    b = feature.transition_bbox_mm
    return (
        float(b[0] - padding),
        float(b[1] - padding),
        float(b[2] - padding),
        float(b[3] + padding),
        float(b[4] + padding),
        float(b[5] + padding),
    )


def _element_max_corner_edges(nodes: np.ndarray, elements: np.ndarray) -> np.ndarray:
    corner_pairs = tuple(combinations(range(4), 2))
    values = np.empty(elements.shape[0], dtype=float)
    for i, conn in enumerate(elements):
        corners = nodes[conn[:4]]
        values[i] = max(float(np.linalg.norm(corners[a] - corners[b])) for a, b in corner_pairs)
    return values


def _inside_box(points: np.ndarray, box: tuple[float, ...]) -> np.ndarray:
    p = np.asarray(points, dtype=float)
    b = np.asarray(box, dtype=float)
    return np.all((p >= b[:3]) & (p <= b[3:]), axis=1)


def _selection_tri6(
    gmsh,
    *,
    selection: PersistentFaceSelection,
    tag_to_index: dict[int, int],
) -> tuple[np.ndarray, tuple[int, str, str]]:
    resolution = resolve_face_selection_in_current_model(gmsh, selection)
    types, _, blocks = gmsh.model.mesh.getElements(2, resolution.resolved_tag)
    tri6_blocks: list[np.ndarray] = []
    unsupported: list[int] = []
    for element_type, connectivity in zip(types, blocks):
        raw = np.asarray(connectivity, dtype=np.int64)
        if not raw.size:
            continue
        if int(element_type) == 9:
            tri6_blocks.append(raw.reshape((-1, 6)))
        else:
            unsupported.append(int(element_type))
    if unsupported:
        raise FeatureAdaptivityError(
            f"SELECTION_{selection.selection_id}_NON_TRI6_SURFACE_TYPES:" + ",".join(map(str, sorted(set(unsupported))))
        )
    if not tri6_blocks:
        raise FeatureAdaptivityError(f"SELECTION_{selection.selection_id}_HAS_NO_TRI6")
    raw_tri6 = np.vstack(tri6_blocks)
    try:
        mapped = np.asarray(
            [[tag_to_index[int(tag)] for tag in row] for row in raw_tri6],
            dtype=np.int64,
        )
    except KeyError as exc:
        raise FeatureAdaptivityError(f"SURFACE_NODE_TAG_NOT_IN_GLOBAL_NODE_MAP:{exc.args[0]}") from exc
    return mapped, (
        int(resolution.resolved_tag),
        str(resolution.signature_sha256),
        str(resolution.selection_sha256),
    )


def mesh_step_tet10_around_shoulder(
    step_path: str | Path,
    feature: XAxisShoulderFeature,
    *,
    global_size_mm: float,
    local_size_mm: float,
    padding_mm: float | None = None,
    face_selections: Iterable[PersistentFaceSelection] = (),
) -> FeatureRefinedTet10Mesh:
    """Generate a straight-sided TET10 mesh with a feature-bound local size box.

    Persistent face selections, when supplied, are resolved against the same
    imported OCC model used to generate the volume mesh. Their TRI6 connectivity
    is returned in global zero-based node indices so boundary conditions and
    consistent tractions cannot silently depend on a surface tag from another
    import session.
    """
    source = _step(step_path)
    global_size = float(global_size_mm)
    local_size = float(local_size_mm)
    selections = tuple(face_selections)
    if len({selection.selection_id for selection in selections}) != len(selections):
        raise ValueError("face selection IDs must be unique")
    if not np.isfinite(global_size) or global_size <= 0.0:
        raise ValueError("global_size_mm must be finite and positive")
    if not np.isfinite(local_size) or local_size <= 0.0 or local_size > global_size:
        raise ValueError("local_size_mm must be finite, positive and <= global_size_mm")
    source_sha = sha256_file(source)
    source_size = int(source.stat().st_size)
    if source_sha != feature.source_sha256 or source_size != feature.source_size_bytes:
        raise FeatureAdaptivityError("FEATURE_SOURCE_IDENTITY_MISMATCH")
    for selection in selections:
        if selection.source_sha256 != source_sha or selection.source_size_bytes != source_size:
            raise PersistentGeometryError(f"SOURCE_IDENTITY_MISMATCH:{selection.selection_id}")
    pad = float(padding_mm) if padding_mm is not None else max(feature.fillet_radius_mm, local_size)
    box = shoulder_local_box(feature, padding_mm=pad)

    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_feature_adaptivity")
        gmsh.model.occ.importShapes(str(source))
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        if len(volumes) != 1:
            raise FeatureAdaptivityError(f"EXPECTED_ONE_SOLID:{len(volumes)}")

        # Resolve geometry before meshing and again when extracting elements.
        for selection in selections:
            resolve_face_selection_in_current_model(gmsh, selection)

        gmsh.option.setNumber("Mesh.MeshSizeMin", local_size)
        gmsh.option.setNumber("Mesh.MeshSizeMax", global_size)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.option.setNumber("Mesh.SecondOrderLinear", 1)

        field_id = gmsh.model.mesh.field.add("Box")
        gmsh.model.mesh.field.setNumber(field_id, "VIn", local_size)
        gmsh.model.mesh.field.setNumber(field_id, "VOut", global_size)
        gmsh.model.mesh.field.setNumber(field_id, "XMin", box[0])
        gmsh.model.mesh.field.setNumber(field_id, "YMin", box[1])
        gmsh.model.mesh.field.setNumber(field_id, "ZMin", box[2])
        gmsh.model.mesh.field.setNumber(field_id, "XMax", box[3])
        gmsh.model.mesh.field.setNumber(field_id, "YMax", box[4])
        gmsh.model.mesh.field.setNumber(field_id, "ZMax", box[5])
        gmsh.model.mesh.field.setAsBackgroundMesh(field_id)
        gmsh.model.mesh.generate(3)

        node_tags, coords, _ = gmsh.model.mesh.getNodes()
        nodes = np.asarray(coords, dtype=float).reshape((-1, 3))
        if nodes.size == 0:
            raise FeatureAdaptivityError("GMSH_PRODUCED_NO_NODES")
        tag_to_index = {int(tag): index for index, tag in enumerate(node_tags)}

        types, _, blocks = gmsh.model.mesh.getElements(3)
        raw_tets = []
        unsupported = []
        for element_type, connectivity in zip(types, blocks):
            raw = np.asarray(connectivity, dtype=np.int64)
            if int(element_type) == 11:
                raw_tets.append(raw.reshape((-1, 10)))
            elif raw.size:
                unsupported.append(int(element_type))
        if unsupported:
            raise FeatureAdaptivityError("NON_TET10_VOLUME_TYPES:" + ",".join(map(str, sorted(set(unsupported)))))
        if not raw_tets:
            raise FeatureAdaptivityError("GMSH_PRODUCED_NO_TET10")
        raw = np.vstack(raw_tets)
        elements = np.asarray(
            [[tag_to_index[int(tag)] for tag in row] for row in raw],
            dtype=np.int64,
        )

        surface_tri6: dict[str, np.ndarray] = {}
        surface_resolution: dict[str, tuple[int, str, str]] = {}
        for selection in selections:
            tri6, resolution = _selection_tri6(gmsh, selection=selection, tag_to_index=tag_to_index)
            surface_tri6[selection.selection_id] = tri6
            surface_resolution[selection.selection_id] = resolution

        centroids = nodes[elements[:, :4]].mean(axis=1)
        inside = _inside_box(centroids, box)
        edge = _element_max_corner_edges(nodes, elements)
        local_count = int(np.count_nonzero(inside))
        outside_count = int(elements.shape[0] - local_count)
        if local_count == 0:
            raise FeatureAdaptivityError("LOCAL_REFINEMENT_BOX_CONTAINS_NO_ELEMENT_CENTROIDS")
        local_mean = float(np.mean(edge[inside]))
        outside_mean = float(np.mean(edge[~inside])) if outside_count else None
        if not np.isfinite(local_mean) or local_mean <= 0.0:
            raise FeatureAdaptivityError("INVALID_LOCAL_EDGE_METRIC")

        mesh_digest = _mesh_hash(nodes, elements, feature.feature_sha256, box)
        return FeatureRefinedTet10Mesh(
            nodes_mm=nodes,
            elements=np.asarray(elements, dtype=np.int64),
            feature_sha256=feature.feature_sha256,
            source_sha256=feature.source_sha256,
            global_size_mm=global_size,
            local_size_mm=local_size,
            local_box_mm=box,
            second_order_linear=True,
            gmsh_version=str(getattr(gmsh, "__version__", "unknown")),
            local_element_count=local_count,
            outside_element_count=outside_count,
            local_mean_max_corner_edge_mm=local_mean,
            outside_mean_max_corner_edge_mm=outside_mean,
            mesh_sha256=mesh_digest,
            surface_tri6_by_selection=surface_tri6,
            surface_resolution_by_selection=surface_resolution,
        )
    finally:
        gmsh.finalize()
