from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np


_TET10_EDGES: tuple[tuple[int, int, int], ...] = (
    (0, 1, 4),
    (1, 2, 5),
    (2, 0, 6),
    (0, 3, 7),
    (2, 3, 8),
    (1, 3, 9),
)


@dataclass(frozen=True)
class QuadraticTet10EdgeHitV1:
    element_id: int
    edge_id: int
    node_ids: tuple[int, int, int]
    parameter_t: float
    point_mm: tuple[float, float, float]


@dataclass(frozen=True)
class QuadraticTet10CoincidentEdgeV1:
    element_id: int
    edge_id: int
    node_ids: tuple[int, int, int]


@dataclass(frozen=True)
class QuadraticTet10PlaneEdgeIntersectionV1:
    schema: str
    semantics: str
    length_unit: str
    workspace_sha256: str
    solve_evidence_sha256: str
    geometry_sha256: str
    plane_sha256: str
    intersection_sha256: str
    plane_origin_mm: tuple[float, float, float]
    plane_normal_unit: tuple[float, float, float]
    tolerance_mm: float
    hit_count: int
    coincident_edge_count: int
    hits: tuple[QuadraticTet10EdgeHitV1, ...]
    coincident_edges: tuple[QuadraticTet10CoincidentEdgeV1, ...]


def _sha256_json(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _canonical_float(value: float) -> float:
    value = float(value)
    return 0.0 if value == 0.0 else value


def _lagrange_edge_point(p0: np.ndarray, pm: np.ndarray, p1: np.ndarray, t: float) -> np.ndarray:
    """Quadratic 3-node edge interpolation with the midside node at t=0.5."""
    q = float(t)
    n0 = 2.0 * q * q - 3.0 * q + 1.0
    nm = 4.0 * q - 4.0 * q * q
    n1 = 2.0 * q * q - q
    return n0 * p0 + nm * pm + n1 * p1


def _quadratic_roots_in_unit_interval(
    d0: float,
    dm: float,
    d1: float,
    *,
    tolerance_mm: float,
) -> tuple[tuple[float, ...], bool]:
    """Solve signed plane distance along one quadratic TET10 edge.

    Returns roots in [0, 1] and a flag indicating that the full quadratic edge is
    coincident with the plane. The signed distances are in mm because the plane
    normal is unit length.
    """
    a = 2.0 * d0 - 4.0 * dm + 2.0 * d1
    b = -3.0 * d0 + 4.0 * dm - d1
    c = d0
    eps = max(float(tolerance_mm), 1.0e-14)

    if abs(a) <= eps:
        if abs(b) <= eps:
            if abs(c) <= eps:
                return (), True
            return (), False
        root = -c / b
        if -eps <= root <= 1.0 + eps:
            return (_canonical_float(min(max(root, 0.0), 1.0)),), False
        return (), False

    disc = b * b - 4.0 * a * c
    disc_eps = eps * max(1.0, abs(b * b), abs(4.0 * a * c))
    if disc < -disc_eps:
        return (), False
    if abs(disc) <= disc_eps:
        candidates = (-b / (2.0 * a),)
    else:
        root_disc = math.sqrt(max(disc, 0.0))
        candidates = ((-b - root_disc) / (2.0 * a), (-b + root_disc) / (2.0 * a))

    roots: list[float] = []
    for root in sorted(candidates):
        if -eps <= root <= 1.0 + eps:
            clamped = _canonical_float(min(max(float(root), 0.0), 1.0))
            if not roots or abs(clamped - roots[-1]) > eps:
                roots.append(clamped)
    return tuple(roots), False


def build_quadratic_tet10_plane_edge_intersection(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    *,
    plane_origin_mm: tuple[float, float, float],
    plane_normal: tuple[float, float, float],
    workspace_sha256: str,
    solve_evidence_sha256: str,
    tolerance_mm: float = 1.0e-9,
) -> QuadraticTet10PlaneEdgeIntersectionV1:
    """Intersect a plane with the six *quadratic edges* of each TET10 element.

    This is a geometric foundation for a future curved section reconstruction.
    It deliberately does not claim to reconstruct the complete plane/curved-face
    intersection, interpolate FEA fields on the cut, smooth stress, recover section
    resultants, or establish ANSYS equivalence.
    """
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise ValueError("QUADRATIC_SECTION_NODES")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("QUADRATIC_SECTION_TET10")
    if elems.size and (int(np.min(elems)) < 0 or int(np.max(elems)) >= nodes.shape[0]):
        raise ValueError("QUADRATIC_SECTION_CONNECTIVITY")

    origin = np.asarray(plane_origin_mm, dtype=float)
    normal = np.asarray(plane_normal, dtype=float)
    if origin.shape != (3,) or normal.shape != (3,) or not np.all(np.isfinite(origin)) or not np.all(np.isfinite(normal)):
        raise ValueError("QUADRATIC_SECTION_PLANE")
    norm = float(np.linalg.norm(normal))
    if norm <= 0.0:
        raise ValueError("QUADRATIC_SECTION_NORMAL")
    normal_unit = normal / norm
    tolerance = float(tolerance_mm)
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("QUADRATIC_SECTION_TOLERANCE")
    if not workspace_sha256 or not solve_evidence_sha256:
        raise ValueError("QUADRATIC_SECTION_PROVENANCE")

    geometry_identity = {
        "nodes_mm": [[float(v) for v in row] for row in nodes],
        "elements": [[int(v) for v in row] for row in elems],
    }
    geometry_sha = _sha256_json(geometry_identity)
    plane_identity = {
        "origin_mm": [float(v) for v in origin],
        "normal_unit": [float(v) for v in normal_unit],
        "tolerance_mm": tolerance,
    }
    plane_sha = _sha256_json(plane_identity)

    hits: list[QuadraticTet10EdgeHitV1] = []
    coincident: list[QuadraticTet10CoincidentEdgeV1] = []
    for element_id, tet in enumerate(elems):
        for edge_id, local in enumerate(_TET10_EDGES):
            n0, n1, nm = (int(tet[i]) for i in local)
            p0, p1, pm = nodes[n0], nodes[n1], nodes[nm]
            d0 = float(np.dot(p0 - origin, normal_unit))
            d1 = float(np.dot(p1 - origin, normal_unit))
            dm = float(np.dot(pm - origin, normal_unit))
            roots, is_coincident = _quadratic_roots_in_unit_interval(
                d0, dm, d1, tolerance_mm=tolerance
            )
            if is_coincident:
                coincident.append(
                    QuadraticTet10CoincidentEdgeV1(
                        element_id=int(element_id), edge_id=int(edge_id), node_ids=(n0, n1, nm)
                    )
                )
                continue
            for root in roots:
                point = _lagrange_edge_point(p0, pm, p1, root)
                residual = abs(float(np.dot(point - origin, normal_unit)))
                if residual > max(tolerance * 10.0, 1.0e-12):
                    raise ValueError("QUADRATIC_SECTION_ROOT_RESIDUAL")
                hits.append(
                    QuadraticTet10EdgeHitV1(
                        element_id=int(element_id),
                        edge_id=int(edge_id),
                        node_ids=(n0, n1, nm),
                        parameter_t=float(root),
                        point_mm=tuple(_canonical_float(float(v)) for v in point),
                    )
                )

    hits.sort(key=lambda item: (item.element_id, item.edge_id, item.parameter_t, item.point_mm))
    coincident.sort(key=lambda item: (item.element_id, item.edge_id, item.node_ids))
    intersection_identity = {
        "schema": "AsterMaxQuadraticTet10PlaneEdgeIntersectionV1",
        "semantics": "quadratic_tet10_edge_plane_roots_geometry_only",
        "workspace_sha256": workspace_sha256,
        "solve_evidence_sha256": solve_evidence_sha256,
        "geometry_sha256": geometry_sha,
        "plane_sha256": plane_sha,
        "hits": [
            {
                "element_id": hit.element_id,
                "edge_id": hit.edge_id,
                "node_ids": list(hit.node_ids),
                "parameter_t": hit.parameter_t,
                "point_mm": list(hit.point_mm),
            }
            for hit in hits
        ],
        "coincident_edges": [
            {"element_id": edge.element_id, "edge_id": edge.edge_id, "node_ids": list(edge.node_ids)}
            for edge in coincident
        ],
    }
    intersection_sha = _sha256_json(intersection_identity)
    return QuadraticTet10PlaneEdgeIntersectionV1(
        schema="AsterMaxQuadraticTet10PlaneEdgeIntersectionV1",
        semantics="quadratic_tet10_edge_plane_roots_geometry_only",
        length_unit="mm",
        workspace_sha256=str(workspace_sha256),
        solve_evidence_sha256=str(solve_evidence_sha256),
        geometry_sha256=geometry_sha,
        plane_sha256=plane_sha,
        intersection_sha256=intersection_sha,
        plane_origin_mm=tuple(_canonical_float(float(v)) for v in origin),
        plane_normal_unit=tuple(_canonical_float(float(v)) for v in normal_unit),
        tolerance_mm=tolerance,
        hit_count=len(hits),
        coincident_edge_count=len(coincident),
        hits=tuple(hits),
        coincident_edges=tuple(coincident),
    )
