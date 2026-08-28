from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
from pathlib import Path

import numpy as np

from .axisymmetric_shoulder import XAxisShoulderFeature
from .evidence import sha256_file
from .feature_adaptivity import _mesh_hash, shoulder_local_box
from .gmsh_bridge import _gmsh


class FeatureGeometryError(RuntimeError):
    pass


@dataclass(frozen=True)
class GeometryDeviationSummary:
    count: int
    maximum_mm: float
    mean_mm: float
    rms_mm: float


@dataclass(frozen=True)
class StraightSidedShoulderGeometryEvidence:
    schema: str
    source_sha256: str
    feature_sha256: str
    mesh_sha256: str
    global_size_mm: float
    local_size_mm: float
    transition_surface_tag_runtime_only: int
    transition_surface_bbox_match_error_mm: float
    tri6_count: int
    corner_nodes: GeometryDeviationSummary
    midside_nodes: GeometryDeviationSummary
    all_surface_nodes: GeometryDeviationSummary
    max_midside_deviation_over_fillet_radius: float
    method: str
    evidence_sha256: str

    def canonical_without_hash(self) -> dict:
        payload = asdict(self)
        payload.pop("evidence_sha256")
        return payload


def summarize_deviations(values_mm: np.ndarray) -> GeometryDeviationSummary:
    values = np.asarray(values_mm, dtype=float).reshape(-1)
    if values.size == 0 or not np.all(np.isfinite(values)) or np.any(values < 0.0):
        raise ValueError("deviation values must be a non-empty finite non-negative array")
    return GeometryDeviationSummary(
        count=int(values.size),
        maximum_mm=float(np.max(values)),
        mean_mm=float(np.mean(values)),
        rms_mm=float(np.sqrt(np.mean(values * values))),
    )


def _unique_transition_surface(gmsh, feature: XAxisShoulderFeature) -> tuple[int, float]:
    target = np.asarray(feature.transition_bbox_mm, dtype=float)
    ranked: list[tuple[float, int]] = []
    for _, tag in gmsh.model.getEntities(2):
        bbox = np.asarray(gmsh.model.getBoundingBox(2, int(tag)), dtype=float)
        ranked.append((float(np.max(np.abs(bbox - target))), int(tag)))
    if not ranked:
        raise FeatureGeometryError("NO_SURFACES_IN_IMPORTED_MODEL")
    ranked.sort()
    tolerance = max(1.0e-5, 1.0e-5 * max(feature.large_radius_mm, feature.fillet_radius_mm))
    eligible = [item for item in ranked if item[0] <= tolerance]
    if len(eligible) != 1:
        raise FeatureGeometryError(
            "TRANSITION_SURFACE_NOT_UNIQUE_BY_GEOMETRIC_BBOX:" +
            ",".join(f"tag={tag}:err={err:.9g}" for err, tag in ranked[:4])
        )
    return eligible[0][1], eligible[0][0]


def _closest_point_deviations(gmsh, surface_tag: int, coordinates: np.ndarray) -> np.ndarray:
    points = np.asarray(coordinates, dtype=float)
    deviations = np.empty(points.shape[0], dtype=float)
    for i, point in enumerate(points):
        closest, _ = gmsh.model.getClosestPoint(2, int(surface_tag), point.tolist())
        closest_arr = np.asarray(closest, dtype=float).reshape(-1)
        if closest_arr.size < 3 or not np.all(np.isfinite(closest_arr[:3])):
            raise FeatureGeometryError("INVALID_OCC_CLOSEST_POINT_RESULT")
        deviations[i] = float(np.linalg.norm(point - closest_arr[:3]))
    return deviations


def measure_straight_sided_shoulder_geometry_error(
    step_path: str | Path,
    feature: XAxisShoulderFeature,
    *,
    global_size_mm: float,
    local_size_mm: float,
    padding_mm: float = 5.0,
) -> StraightSidedShoulderGeometryEvidence:
    """Measure chordal geometry error against the exact imported OCC fillet.

    The audit independently regenerates the same deterministic straight-sided
    TET10 mesh settings and requires callers to compare its mesh SHA with the
    solved mesh. Runtime OCC tags are recorded for inspection only; the feature
    identity remains the source/geometry SHA.
    """
    source = Path(step_path)
    if not source.is_file() or source.suffix.lower() not in {".step", ".stp"}:
        raise FeatureGeometryError("INPUT_MUST_BE_EXISTING_STEP")
    source_sha = sha256_file(source)
    if source_sha != feature.source_sha256 or int(source.stat().st_size) != feature.source_size_bytes:
        raise FeatureGeometryError("FEATURE_SOURCE_IDENTITY_MISMATCH")
    global_size = float(global_size_mm)
    local_size = float(local_size_mm)
    if not all(math.isfinite(v) and v > 0.0 for v in (global_size, local_size, padding_mm)):
        raise ValueError("mesh sizes and padding must be finite and positive")
    if local_size > global_size:
        raise ValueError("local_size_mm must be <= global_size_mm")
    box = shoulder_local_box(feature, padding_mm=float(padding_mm))

    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_feature_geometry_error")
        gmsh.model.occ.importShapes(str(source))
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        if len(volumes) != 1:
            raise FeatureGeometryError(f"EXPECTED_ONE_SOLID:{len(volumes)}")
        transition_tag, bbox_error = _unique_transition_surface(gmsh, feature)

        gmsh.option.setNumber("Mesh.MeshSizeMin", local_size)
        gmsh.option.setNumber("Mesh.MeshSizeMax", global_size)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.option.setNumber("Mesh.SecondOrderLinear", 1)
        field_id = gmsh.model.mesh.field.add("Box")
        gmsh.model.mesh.field.setNumber(field_id, "VIn", local_size)
        gmsh.model.mesh.field.setNumber(field_id, "VOut", global_size)
        for name, value in zip(("XMin", "YMin", "ZMin", "XMax", "YMax", "ZMax"), box):
            gmsh.model.mesh.field.setNumber(field_id, name, value)
        gmsh.model.mesh.field.setAsBackgroundMesh(field_id)
        gmsh.model.mesh.generate(3)

        node_tags, coords, _ = gmsh.model.mesh.getNodes()
        nodes = np.asarray(coords, dtype=float).reshape((-1, 3))
        tag_to_index = {int(tag): index for index, tag in enumerate(node_tags)}

        types3, _, blocks3 = gmsh.model.mesh.getElements(3)
        tets = []
        for etype, connectivity in zip(types3, blocks3):
            raw = np.asarray(connectivity, dtype=np.int64)
            if raw.size and int(etype) != 11:
                raise FeatureGeometryError(f"NON_TET10_VOLUME_TYPE:{int(etype)}")
            if raw.size:
                tets.append(raw.reshape((-1, 10)))
        if not tets:
            raise FeatureGeometryError("NO_TET10_VOLUME_ELEMENTS")
        elements = np.asarray(
            [[tag_to_index[int(tag)] for tag in row] for row in np.vstack(tets)],
            dtype=np.int64,
        )
        mesh_sha = _mesh_hash(nodes, elements, feature.feature_sha256, box)

        types2, _, blocks2 = gmsh.model.mesh.getElements(2, int(transition_tag))
        tri6_blocks = []
        for etype, connectivity in zip(types2, blocks2):
            raw = np.asarray(connectivity, dtype=np.int64)
            if raw.size and int(etype) != 9:
                raise FeatureGeometryError(f"TRANSITION_NON_TRI6_SURFACE_TYPE:{int(etype)}")
            if raw.size:
                tri6_blocks.append(raw.reshape((-1, 6)))
        if not tri6_blocks:
            raise FeatureGeometryError("TRANSITION_SURFACE_HAS_NO_TRI6")
        raw_tri6 = np.vstack(tri6_blocks)
        corner_tags = np.unique(raw_tri6[:, :3].reshape(-1))
        midside_tags = np.unique(raw_tri6[:, 3:].reshape(-1))
        all_tags = np.unique(raw_tri6.reshape(-1))
        try:
            corner_coords = nodes[[tag_to_index[int(t)] for t in corner_tags]]
            midside_coords = nodes[[tag_to_index[int(t)] for t in midside_tags]]
            all_coords = nodes[[tag_to_index[int(t)] for t in all_tags]]
        except KeyError as exc:
            raise FeatureGeometryError(f"SURFACE_NODE_NOT_IN_GLOBAL_MAP:{exc.args[0]}") from exc

        corner_dev = summarize_deviations(_closest_point_deviations(gmsh, transition_tag, corner_coords))
        midside_dev = summarize_deviations(_closest_point_deviations(gmsh, transition_tag, midside_coords))
        all_dev = summarize_deviations(_closest_point_deviations(gmsh, transition_tag, all_coords))
        ratio = midside_dev.maximum_mm / float(feature.fillet_radius_mm)

        payload = {
            "schema": "AsterMaxStraightSidedShoulderGeometryEvidenceV1",
            "source_sha256": source_sha,
            "feature_sha256": feature.feature_sha256,
            "mesh_sha256": mesh_sha,
            "global_size_mm": global_size,
            "local_size_mm": local_size,
            "transition_surface_tag_runtime_only": int(transition_tag),
            "transition_surface_bbox_match_error_mm": float(bbox_error),
            "tri6_count": int(raw_tri6.shape[0]),
            "corner_nodes": asdict(corner_dev),
            "midside_nodes": asdict(midside_dev),
            "all_surface_nodes": asdict(all_dev),
            "max_midside_deviation_over_fillet_radius": float(ratio),
            "method": "OCC_CLOSEST_POINT_DISTANCE_OF_STRAIGHT_SIDED_TRI6_NODES_ON_IDENTIFIED_FILLET_SURFACE",
        }
        h = hashlib.sha256()
        import json
        h.update(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))
        return StraightSidedShoulderGeometryEvidence(
            schema=payload["schema"],
            source_sha256=source_sha,
            feature_sha256=feature.feature_sha256,
            mesh_sha256=mesh_sha,
            global_size_mm=global_size,
            local_size_mm=local_size,
            transition_surface_tag_runtime_only=int(transition_tag),
            transition_surface_bbox_match_error_mm=float(bbox_error),
            tri6_count=int(raw_tri6.shape[0]),
            corner_nodes=corner_dev,
            midside_nodes=midside_dev,
            all_surface_nodes=all_dev,
            max_midside_deviation_over_fillet_radius=float(ratio),
            method=payload["method"],
            evidence_sha256=h.hexdigest(),
        )
    finally:
        gmsh.finalize()
