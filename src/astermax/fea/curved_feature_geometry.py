from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .axisymmetric_shoulder import XAxisShoulderFeature
from .evidence import sha256_file
from .feature_adaptivity import _mesh_hash, shoulder_local_box
from .feature_geometry_error import (
    FeatureGeometryError,
    GeometryDeviationSummary,
    _closest_point_deviations,
    _unique_transition_surface,
    summarize_deviations,
)
from .gmsh_bridge import _gmsh
from .tri6_traction import tri6_shape_functions


@dataclass(frozen=True)
class CurvedShoulderGeometryEvidence:
    schema: str
    source_sha256: str
    feature_sha256: str
    mesh_sha256: str
    global_size_mm: float
    local_size_mm: float
    second_order_linear: bool
    transition_surface_tag_runtime_only: int
    tri6_count: int
    corner_nodes: GeometryDeviationSummary
    midside_nodes: GeometryDeviationSummary
    all_surface_nodes: GeometryDeviationSummary
    sampled_interpolated_surface: GeometryDeviationSummary
    max_midside_deviation_over_fillet_radius: float
    max_sampled_surface_deviation_over_fillet_radius: float
    method: str
    evidence_sha256: str


def tri6_verification_sample_points() -> np.ndarray:
    """Fixed non-nodal reference points used to audit quadratic surface geometry."""
    points = [
        (1.0 / 3.0, 1.0 / 3.0),
        (0.25, 0.0), (0.75, 0.0),
        (0.25, 0.75), (0.75, 0.25),
        (0.0, 0.25), (0.0, 0.75),
        (0.25, 0.25), (0.50, 0.25), (0.25, 0.50),
    ]
    return np.asarray(points, dtype=float)


def interpolated_tri6_points(nodes_mm: np.ndarray, tri6: np.ndarray) -> np.ndarray:
    nodes = np.asarray(nodes_mm, dtype=float)
    faces = np.asarray(tri6, dtype=np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise ValueError("nodes_mm must be finite with shape (n,3)")
    if faces.ndim != 2 or faces.shape[1] != 6 or faces.shape[0] == 0:
        raise ValueError("tri6 must have shape (m,6) with m>0")
    if np.any(faces < 0) or np.any(faces >= nodes.shape[0]):
        raise ValueError("tri6 contains out-of-range indices")
    sample_points = tri6_verification_sample_points()
    shapes = np.vstack([tri6_shape_functions(point) for point in sample_points])
    out = np.empty((faces.shape[0] * sample_points.shape[0], 3), dtype=float)
    cursor = 0
    for conn in faces:
        xyz = nodes[conn]
        block = shapes @ xyz
        out[cursor:cursor + block.shape[0]] = block
        cursor += block.shape[0]
    return out


def measure_curved_shoulder_geometry_error(
    step_path: str | Path,
    feature: XAxisShoulderFeature,
    *,
    global_size_mm: float,
    local_size_mm: float,
    padding_mm: float = 5.0,
) -> CurvedShoulderGeometryEvidence:
    """Regenerate CAD-projected TET10 and audit nodes plus interpolated TRI6 face points."""
    source = Path(step_path)
    if not source.is_file() or source.suffix.lower() not in {".step", ".stp"}:
        raise FeatureGeometryError("INPUT_MUST_BE_EXISTING_STEP")
    source_sha = sha256_file(source)
    if source_sha != feature.source_sha256 or int(source.stat().st_size) != feature.source_size_bytes:
        raise FeatureGeometryError("FEATURE_SOURCE_IDENTITY_MISMATCH")
    global_size = float(global_size_mm)
    local_size = float(local_size_mm)
    pad = float(padding_mm)
    if not all(math.isfinite(v) and v > 0.0 for v in (global_size, local_size, pad)):
        raise ValueError("mesh sizes and padding must be finite and positive")
    if local_size > global_size:
        raise ValueError("local_size_mm must be <= global_size_mm")
    box = shoulder_local_box(feature, padding_mm=pad)

    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_curved_feature_geometry_audit")
        gmsh.model.occ.importShapes(str(source))
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        if len(volumes) != 1:
            raise FeatureGeometryError(f"EXPECTED_ONE_SOLID:{len(volumes)}")
        transition_tag, _ = _unique_transition_surface(gmsh, feature)

        gmsh.option.setNumber("Mesh.MeshSizeMin", local_size)
        gmsh.option.setNumber("Mesh.MeshSizeMax", global_size)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.option.setNumber("Mesh.SecondOrderLinear", 0)
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
        raw_tets = []
        for etype, connectivity in zip(types3, blocks3):
            raw = np.asarray(connectivity, dtype=np.int64)
            if raw.size and int(etype) != 11:
                raise FeatureGeometryError(f"NON_TET10_VOLUME_TYPE:{int(etype)}")
            if raw.size:
                raw_tets.append(raw.reshape((-1, 10)))
        if not raw_tets:
            raise FeatureGeometryError("NO_TET10_VOLUME_ELEMENTS")
        elements = np.asarray(
            [[tag_to_index[int(tag)] for tag in row] for row in np.vstack(raw_tets)],
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
        mapped_tri6 = np.asarray(
            [[tag_to_index[int(tag)] for tag in row] for row in raw_tri6],
            dtype=np.int64,
        )
        corner_tags = np.unique(raw_tri6[:, :3].reshape(-1))
        midside_tags = np.unique(raw_tri6[:, 3:].reshape(-1))
        all_tags = np.unique(raw_tri6.reshape(-1))
        corner_coords = nodes[[tag_to_index[int(tag)] for tag in corner_tags]]
        midside_coords = nodes[[tag_to_index[int(tag)] for tag in midside_tags]]
        all_coords = nodes[[tag_to_index[int(tag)] for tag in all_tags]]
        sampled_coords = interpolated_tri6_points(nodes, mapped_tri6)
        corner_dev = summarize_deviations(_closest_point_deviations(gmsh, transition_tag, corner_coords))
        midside_dev = summarize_deviations(_closest_point_deviations(gmsh, transition_tag, midside_coords))
        all_dev = summarize_deviations(_closest_point_deviations(gmsh, transition_tag, all_coords))
        sampled_dev = summarize_deviations(_closest_point_deviations(gmsh, transition_tag, sampled_coords))
        midside_ratio = midside_dev.maximum_mm / float(feature.fillet_radius_mm)
        sampled_ratio = sampled_dev.maximum_mm / float(feature.fillet_radius_mm)

        payload = {
            "schema": "AsterMaxCurvedShoulderGeometryEvidenceV2",
            "source_sha256": source_sha,
            "feature_sha256": feature.feature_sha256,
            "mesh_sha256": mesh_sha,
            "global_size_mm": global_size,
            "local_size_mm": local_size,
            "second_order_linear": False,
            "transition_surface_tag_runtime_only": int(transition_tag),
            "tri6_count": int(raw_tri6.shape[0]),
            "corner_nodes": asdict(corner_dev),
            "midside_nodes": asdict(midside_dev),
            "all_surface_nodes": asdict(all_dev),
            "sampled_interpolated_surface": asdict(sampled_dev),
            "max_midside_deviation_over_fillet_radius": float(midside_ratio),
            "max_sampled_surface_deviation_over_fillet_radius": float(sampled_ratio),
            "method": "OCC_CLOSEST_POINT_DISTANCE_OF_CAD_PROJECTED_TRI6_NODES_AND_FIXED_NONNODAL_INTERPOLATED_FACE_POINTS",
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest()
        return CurvedShoulderGeometryEvidence(
            schema=payload["schema"],
            source_sha256=source_sha,
            feature_sha256=feature.feature_sha256,
            mesh_sha256=mesh_sha,
            global_size_mm=global_size,
            local_size_mm=local_size,
            second_order_linear=False,
            transition_surface_tag_runtime_only=int(transition_tag),
            tri6_count=int(raw_tri6.shape[0]),
            corner_nodes=corner_dev,
            midside_nodes=midside_dev,
            all_surface_nodes=all_dev,
            sampled_interpolated_surface=sampled_dev,
            max_midside_deviation_over_fillet_radius=float(midside_ratio),
            max_sampled_surface_deviation_over_fillet_radius=float(sampled_ratio),
            method=payload["method"],
            evidence_sha256=digest,
        )
    finally:
        gmsh.finalize()
