from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np


@dataclass(frozen=True)
class SectionPolygonV1:
    element_id: int
    points_mm: tuple[tuple[float, float, float], ...]


@dataclass(frozen=True)
class SectionIntersectionContractV1:
    schema: str
    origin_mm: tuple[float, float, float]
    normal_unit: tuple[float, float, float]
    tolerance_mm: float
    workspace_sha256: str
    solve_evidence_sha256: str
    geometry_sha256: str
    section_sha256: str
    polygons: tuple[SectionPolygonV1, ...]


def _sha256_json(payload) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _normalized_plane(origin_mm, normal, tolerance_mm: float):
    origin = np.asarray(origin_mm, dtype=float)
    vector = np.asarray(normal, dtype=float)
    if origin.shape != (3,) or not np.all(np.isfinite(origin)):
        raise ValueError("SECTION_ORIGIN")
    if vector.shape != (3,) or not np.all(np.isfinite(vector)):
        raise ValueError("SECTION_NORMAL")
    norm = float(np.linalg.norm(vector))
    if not math.isfinite(norm) or norm <= 1.0e-15:
        raise ValueError("SECTION_NORMAL_ZERO")
    tolerance = float(tolerance_mm)
    if not math.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError("SECTION_TOLERANCE")
    return origin, vector / norm, tolerance


def _geometry_sha(nodes_mm: np.ndarray, elements: np.ndarray) -> str:
    nodes = np.asarray(nodes_mm, dtype=np.float64)
    elems = np.asarray(elements, dtype=np.int64)
    payload = {
        "nodes_shape": list(nodes.shape),
        "elements_shape": list(elems.shape),
        "nodes_hex": nodes.tobytes(order="C").hex(),
        "elements_hex": elems.tobytes(order="C").hex(),
    }
    return _sha256_json(payload)


def _dedupe_points(points: list[np.ndarray], tolerance: float) -> list[np.ndarray]:
    unique: list[np.ndarray] = []
    merge_tol = max(tolerance, 1.0e-12)
    for point in points:
        if not any(float(np.linalg.norm(point - other)) <= merge_tol for other in unique):
            unique.append(point)
    return unique


def _ordered_polygon(points: list[np.ndarray], normal: np.ndarray) -> list[np.ndarray]:
    if len(points) < 3:
        return []
    center = np.mean(points, axis=0)
    seed = np.array((1.0, 0.0, 0.0), dtype=float)
    if abs(float(np.dot(seed, normal))) > 0.9:
        seed = np.array((0.0, 1.0, 0.0), dtype=float)
    u = seed - float(np.dot(seed, normal)) * normal
    u /= np.linalg.norm(u)
    v = np.cross(normal, u)
    decorated = []
    for point in points:
        delta = point - center
        angle = math.atan2(float(np.dot(delta, v)), float(np.dot(delta, u)))
        decorated.append((angle, tuple(float(x) for x in point), point))
    decorated.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in decorated]


def build_linearized_tet10_section_intersection(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    *,
    plane_origin_mm=(0.0, 0.0, 0.0),
    plane_normal=(1.0, 0.0, 0.0),
    tolerance_mm: float = 1.0e-9,
    workspace_sha256: str,
    solve_evidence_sha256: str,
) -> SectionIntersectionContractV1:
    """Intersect a plane with TET10 corner geometry deterministically.

    This is exact for the linear tetrahedron formed by each TET10 element's four
    corner nodes. Curved quadratic edges/faces defined by midside nodes are not
    reconstructed here. No solver field is interpolated, smoothed, extrapolated,
    integrated, or otherwise modified by this geometric instrument.
    """
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise ValueError("SECTION_NODES_SHAPE")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("SECTION_TET10_SHAPE")
    if elems.size and (int(np.min(elems)) < 0 or int(np.max(elems)) >= nodes.shape[0]):
        raise ValueError("SECTION_CONNECTIVITY")
    if not workspace_sha256 or not solve_evidence_sha256:
        raise ValueError("SECTION_PROVENANCE")

    origin, normal, tolerance = _normalized_plane(plane_origin_mm, plane_normal, tolerance_mm)
    edge_pairs = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
    polygons: list[SectionPolygonV1] = []

    for element_id, tet in enumerate(elems):
        corner_ids = tet[:4]
        corner_points = nodes[corner_ids]
        distances = np.dot(corner_points - origin, normal)
        candidates: list[np.ndarray] = []

        for local_id, distance in enumerate(distances):
            if abs(float(distance)) <= tolerance:
                candidates.append(corner_points[local_id].copy())

        for ia, ib in edge_pairs:
            da = float(distances[ia])
            db = float(distances[ib])
            if abs(da) <= tolerance and abs(db) <= tolerance:
                candidates.extend((corner_points[ia].copy(), corner_points[ib].copy()))
                continue
            if (da < -tolerance and db > tolerance) or (da > tolerance and db < -tolerance):
                t = da / (da - db)
                candidates.append(corner_points[ia] + t * (corner_points[ib] - corner_points[ia]))

        unique = _dedupe_points(candidates, tolerance)
        ordered = _ordered_polygon(unique, normal)
        if len(ordered) >= 3:
            polygons.append(
                SectionPolygonV1(
                    element_id=int(element_id),
                    points_mm=tuple(tuple(float(x) for x in point) for point in ordered),
                )
            )

    geometry_sha = _geometry_sha(nodes, elems)
    identity_payload = {
        "schema": "AsterMaxSectionIntersectionContractV1",
        "semantics": "linearized_tet10_corner_geometry_plane_intersection",
        "origin_mm": [float(x) for x in origin],
        "normal_unit": [float(x) for x in normal],
        "tolerance_mm": tolerance,
        "workspace_sha256": workspace_sha256,
        "solve_evidence_sha256": solve_evidence_sha256,
        "geometry_sha256": geometry_sha,
        "polygons": [
            {
                "element_id": polygon.element_id,
                "points_mm": [list(point) for point in polygon.points_mm],
            }
            for polygon in polygons
        ],
    }
    section_sha = _sha256_json(identity_payload)
    return SectionIntersectionContractV1(
        schema="AsterMaxSectionIntersectionContractV1",
        origin_mm=tuple(float(x) for x in origin),
        normal_unit=tuple(float(x) for x in normal),
        tolerance_mm=tolerance,
        workspace_sha256=workspace_sha256,
        solve_evidence_sha256=solve_evidence_sha256,
        geometry_sha256=geometry_sha,
        section_sha256=section_sha,
        polygons=tuple(polygons),
    )
