from __future__ import annotations

from dataclasses import dataclass
import hashlib
from itertools import combinations
from pathlib import Path

import numpy as np

from .axisymmetric_shoulder import XAxisShoulderFeature
from .evidence import sha256_file
from .gmsh_bridge import GmshBridgeError, _gmsh


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


def mesh_step_tet10_around_shoulder(
    step_path: str | Path,
    feature: XAxisShoulderFeature,
    *,
    global_size_mm: float,
    local_size_mm: float,
    padding_mm: float | None = None,
) -> FeatureRefinedTet10Mesh:
    """Generate a straight-sided TET10 mesh with a feature-bound local size box.

    This is a deterministic meshing increment, not an adaptive-solve loop.
    `Mesh.SecondOrderLinear=1` is mandatory because the current TET10 solver
    verification boundary rejects curved quadratic geometry.
    """
    source = _step(step_path)
    global_size = float(global_size_mm)
    local_size = float(local_size_mm)
    if not np.isfinite(global_size) or global_size <= 0.0:
        raise ValueError("global_size_mm must be finite and positive")
    if not np.isfinite(local_size) or local_size <= 0.0 or local_size > global_size:
        raise ValueError("local_size_mm must be finite, positive and <= global_size_mm")
    if sha256_file(source) != feature.source_sha256 or int(source.stat().st_size) != feature.source_size_bytes:
        raise FeatureAdaptivityError("FEATURE_SOURCE_IDENTITY_MISMATCH")
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

        gmsh.option.setNumber("Mesh.MeshSizeMin", local_size)
        gmsh.option.setNumber("Mesh.MeshSizeMax", global_size)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.option.setNumber("Mesh.SecondOrderLinear", 1)

        field = gmsh.model.mesh.field.add("Box")
        gmsh.model.mesh.field.setNumber(field, "VIn", local_size)
        gmsh.model.mesh.field.setNumber(field, "VOut", global_size)
        gmsh.model.mesh.field.setNumber(field, "XMin", box[0])
        gmsh.model.mesh.field.setNumber(field, "YMin", box[1])
        gmsh.model.mesh.field.setNumber(field, "ZMin", box[2])
        gmsh.model.mesh.field.setNumber(field, "XMax", box[3])
        gmsh.model.mesh.field.setNumber(field, "YMax", box[4])
        gmsh.model.mesh.field.setNumber(field, "ZMax", box[5])
        gmsh.model.mesh.field.setAsBackgroundMesh(field)
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
        elements = np.vectorize(lambda tag: tag_to_index[int(tag)], otypes=[np.int64])(raw)

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
        )
    finally:
        gmsh.finalize()
