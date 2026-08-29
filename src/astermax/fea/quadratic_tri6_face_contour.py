from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np


_TET10_FACES: tuple[tuple[int, int, int, int, int, int], ...] = (
    (0, 1, 2, 4, 5, 6),
    (0, 1, 3, 4, 9, 7),
    (1, 2, 3, 5, 8, 9),
    (2, 0, 3, 6, 7, 8),
)


@dataclass(frozen=True)
class QuadraticTri6ContourSegmentV1:
    element_id: int
    face_id: int
    node_ids: tuple[int, int, int, int, int, int]
    reference_points: tuple[tuple[float, float], tuple[float, float]]
    points_mm: tuple[tuple[float, float, float], tuple[float, float, float]]
    max_plane_residual_mm: float


@dataclass(frozen=True)
class QuadraticTri6FaceContourV1:
    schema: str
    semantics: str
    length_unit: str
    workspace_sha256: str
    solve_evidence_sha256: str
    geometry_sha256: str
    plane_sha256: str
    contour_sha256: str
    plane_origin_mm: tuple[float, float, float]
    plane_normal_unit: tuple[float, float, float]
    tolerance_mm: float
    sampling_divisions: int
    segment_count: int
    ambiguous_cell_count: int
    max_plane_residual_mm: float
    segments: tuple[QuadraticTri6ContourSegmentV1, ...]


def _sha256_json(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _canonical_float(value: float) -> float:
    value = float(value)
    return 0.0 if value == 0.0 else value


def _tri6_point(face_nodes: np.ndarray, r: float, s: float) -> np.ndarray:
    l1 = 1.0 - float(r) - float(s)
    l2 = float(r)
    l3 = float(s)
    shape = np.asarray(
        (
            l1 * (2.0 * l1 - 1.0),
            l2 * (2.0 * l2 - 1.0),
            l3 * (2.0 * l3 - 1.0),
            4.0 * l1 * l2,
            4.0 * l2 * l3,
            4.0 * l3 * l1,
        ),
        dtype=float,
    )
    return shape @ face_nodes


def _reference_triangles(divisions: int) -> tuple[tuple[tuple[float, float], ...], ...]:
    n = int(divisions)
    triangles: list[tuple[tuple[float, float], ...]] = []
    for i in range(n):
        for j in range(n - i):
            p00 = (i / n, j / n)
            p10 = ((i + 1) / n, j / n)
            p01 = (i / n, (j + 1) / n)
            triangles.append((p00, p10, p01))
            if i + j < n - 1:
                p11 = ((i + 1) / n, (j + 1) / n)
                triangles.append((p10, p11, p01))
    return tuple(triangles)


def _dedupe_reference_points(
    points: list[tuple[float, float]], *, eps: float
) -> list[tuple[float, float]]:
    unique: list[tuple[float, float]] = []
    for point in points:
        if not any(abs(point[0] - other[0]) <= eps and abs(point[1] - other[1]) <= eps for other in unique):
            unique.append(point)
    unique.sort()
    return unique


def build_quadratic_tri6_face_contour(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    *,
    plane_origin_mm: tuple[float, float, float],
    plane_normal: tuple[float, float, float],
    workspace_sha256: str,
    solve_evidence_sha256: str,
    tolerance_mm: float = 1.0e-9,
    sampling_divisions: int = 24,
) -> QuadraticTri6FaceContourV1:
    """Approximate plane/TRI6 zero contours with a deterministic reference lattice.

    The physical face geometry and signed plane distance are evaluated with the
    quadratic TRI6 shape functions. Each small reference triangle is contoured by
    linear interpolation of its vertex signed distances, then every interpolated
    reference hit is mapped back through the exact quadratic TRI6 geometry. The
    returned plane residual therefore quantifies the geometric discretization error.

    This is a convergent visualization/reconstruction primitive, not an exact conic
    solver and not a cut-surface FEA field operator. It does not interpolate stress,
    smooth/extrapolate von Mises, integrate resultants, or claim ANSYS equivalence.
    """
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise ValueError("QUADRATIC_TRI6_CONTOUR_NODES")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("QUADRATIC_TRI6_CONTOUR_TET10")
    if elems.size and (int(np.min(elems)) < 0 or int(np.max(elems)) >= nodes.shape[0]):
        raise ValueError("QUADRATIC_TRI6_CONTOUR_CONNECTIVITY")

    origin = np.asarray(plane_origin_mm, dtype=float)
    normal = np.asarray(plane_normal, dtype=float)
    if origin.shape != (3,) or normal.shape != (3,) or not np.all(np.isfinite(origin)) or not np.all(np.isfinite(normal)):
        raise ValueError("QUADRATIC_TRI6_CONTOUR_PLANE")
    norm = float(np.linalg.norm(normal))
    if norm <= 0.0:
        raise ValueError("QUADRATIC_TRI6_CONTOUR_NORMAL")
    normal_unit = normal / norm

    tolerance = float(tolerance_mm)
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("QUADRATIC_TRI6_CONTOUR_TOLERANCE")
    divisions = int(sampling_divisions)
    if divisions < 2 or divisions > 256:
        raise ValueError("QUADRATIC_TRI6_CONTOUR_DIVISIONS")
    if not workspace_sha256 or not solve_evidence_sha256:
        raise ValueError("QUADRATIC_TRI6_CONTOUR_PROVENANCE")

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

    reference_triangles = _reference_triangles(divisions)
    uv_eps = 1.0e-12
    segments: list[QuadraticTri6ContourSegmentV1] = []
    ambiguous_cells = 0

    for element_id, tet in enumerate(elems):
        for face_id, local_face in enumerate(_TET10_FACES):
            node_ids = tuple(int(tet[index]) for index in local_face)
            face_nodes = nodes[list(node_ids)]
            for tri in reference_triangles:
                physical = [_tri6_point(face_nodes, *uv) for uv in tri]
                distances = [float(np.dot(point - origin, normal_unit)) for point in physical]
                crossings: list[tuple[float, float]] = []
                coincident_edge = False
                for a, b in ((0, 1), (1, 2), (2, 0)):
                    da = distances[a]
                    db = distances[b]
                    uva = tri[a]
                    uvb = tri[b]
                    a_zero = abs(da) <= tolerance
                    b_zero = abs(db) <= tolerance
                    if a_zero and b_zero:
                        coincident_edge = True
                        continue
                    if a_zero:
                        crossings.append(uva)
                        continue
                    if b_zero:
                        crossings.append(uvb)
                        continue
                    if da * db < 0.0:
                        alpha = da / (da - db)
                        crossings.append(
                            (
                                float(uva[0] + alpha * (uvb[0] - uva[0])),
                                float(uva[1] + alpha * (uvb[1] - uva[1])),
                            )
                        )

                unique = _dedupe_reference_points(crossings, eps=uv_eps)
                if coincident_edge or len(unique) not in (0, 2):
                    if coincident_edge or len(unique) > 2:
                        ambiguous_cells += 1
                    continue
                if not unique:
                    continue

                mapped = [_tri6_point(face_nodes, *uv) for uv in unique]
                residuals = [abs(float(np.dot(point - origin, normal_unit))) for point in mapped]
                segment = QuadraticTri6ContourSegmentV1(
                    element_id=int(element_id),
                    face_id=int(face_id),
                    node_ids=node_ids,
                    reference_points=tuple(
                        tuple(_canonical_float(v) for v in uv) for uv in unique
                    ),
                    points_mm=tuple(
                        tuple(_canonical_float(float(v)) for v in point) for point in mapped
                    ),
                    max_plane_residual_mm=max(residuals),
                )
                segments.append(segment)

    segments.sort(
        key=lambda item: (
            item.element_id,
            item.face_id,
            item.reference_points,
            item.points_mm,
        )
    )
    max_residual = max((segment.max_plane_residual_mm for segment in segments), default=0.0)
    contour_identity = {
        "schema": "AsterMaxQuadraticTri6FaceContourV1",
        "semantics": "quadratic_tri6_face_plane_contour_lattice_approximation_geometry_only",
        "workspace_sha256": str(workspace_sha256),
        "solve_evidence_sha256": str(solve_evidence_sha256),
        "geometry_sha256": geometry_sha,
        "plane_sha256": plane_sha,
        "sampling_divisions": divisions,
        "ambiguous_cell_count": ambiguous_cells,
        "segments": [
            {
                "element_id": segment.element_id,
                "face_id": segment.face_id,
                "node_ids": list(segment.node_ids),
                "reference_points": [list(uv) for uv in segment.reference_points],
                "points_mm": [list(point) for point in segment.points_mm],
                "max_plane_residual_mm": segment.max_plane_residual_mm,
            }
            for segment in segments
        ],
    }
    contour_sha = _sha256_json(contour_identity)
    return QuadraticTri6FaceContourV1(
        schema="AsterMaxQuadraticTri6FaceContourV1",
        semantics="quadratic_tri6_face_plane_contour_lattice_approximation_geometry_only",
        length_unit="mm",
        workspace_sha256=str(workspace_sha256),
        solve_evidence_sha256=str(solve_evidence_sha256),
        geometry_sha256=geometry_sha,
        plane_sha256=plane_sha,
        contour_sha256=contour_sha,
        plane_origin_mm=tuple(_canonical_float(float(v)) for v in origin),
        plane_normal_unit=tuple(_canonical_float(float(v)) for v in normal_unit),
        tolerance_mm=tolerance,
        sampling_divisions=divisions,
        segment_count=len(segments),
        ambiguous_cell_count=ambiguous_cells,
        max_plane_residual_mm=max_residual,
        segments=tuple(segments),
    )
