from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Iterable

import numpy as np

from astermax.credibility import canonical_sha256
from .tet10 import tet10_B_matrix
from .tet4 import IsotropicMaterial, von_mises


class Tet10SurfaceStressError(ValueError):
    pass


# Local TET10 face node positions in Gmsh Tetrahedron10 ordering.
# Each tuple is (corner0, corner1, corner2, mid01, mid12, mid20).
_TET10_FACE_LOCAL = (
    (0, 1, 2, 4, 5, 6),
    (0, 1, 3, 4, 9, 7),
    (0, 2, 3, 6, 8, 7),
    (1, 2, 3, 5, 8, 9),
)


@dataclass(frozen=True)
class Tet10SurfaceParent:
    tri6_nodes: tuple[int, ...]
    element_index: int
    tet10_nodes: tuple[int, ...]
    face_local_nodes: tuple[int, ...]
    tri_corner_to_tet_vertex: tuple[int, int, int]
    opposite_tet_vertex: int
    mapping_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("mapping_sha256")
        return payload


@dataclass(frozen=True)
class Tet10SurfaceStressSample:
    element_index: int
    tri6_nodes: tuple[int, ...]
    tri6_natural_coordinates: tuple[float, float]
    tet10_natural_coordinates: tuple[float, float, float]
    physical_point_mm: tuple[float, float, float]
    det_jacobian: float
    strain: tuple[float, ...]
    stress_mpa: tuple[float, ...]
    axial_normal_stress_mpa: float
    von_mises_mpa: float
    parent_mapping_sha256: str
    sample_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("sample_sha256")
        return payload


def _validate_tri6(tri6_nodes: Iterable[int]) -> tuple[int, ...]:
    conn = tuple(int(v) for v in tri6_nodes)
    if len(conn) != 6 or len(set(conn)) != 6 or any(v < 0 for v in conn):
        raise Tet10SurfaceStressError("tri6_nodes must contain six unique non-negative node indices")
    return conn


def _validate_tets(elements: np.ndarray) -> np.ndarray:
    elems = np.asarray(elements, dtype=np.int64)
    if elems.ndim != 2 or elems.shape[1] != 10 or elems.shape[0] == 0:
        raise Tet10SurfaceStressError("elements must have shape (m,10) with m>0")
    if np.any(elems < 0):
        raise Tet10SurfaceStressError("elements contains negative node indices")
    return elems


def _face_for_element(conn: np.ndarray, tri_set: set[int]) -> tuple[int, tuple[int, ...]] | None:
    matches: list[tuple[int, tuple[int, ...]]] = []
    for face_index, local in enumerate(_TET10_FACE_LOCAL):
        nodes = tuple(int(conn[i]) for i in local)
        if set(nodes) == tri_set:
            matches.append((face_index, local))
    if len(matches) > 1:
        raise Tet10SurfaceStressError("TET10_FACE_MATCH_AMBIGUOUS_WITHIN_ELEMENT")
    return matches[0] if matches else None


def resolve_tri6_parent_tet10(elements: np.ndarray, tri6_nodes: Iterable[int]) -> Tet10SurfaceParent:
    """Resolve one TRI6 boundary face to exactly one parent TET10.

    Matching is by the complete six-node face set, not by coordinate proximity.
    The TRI6 corner/midside ordering is then checked against the Gmsh TET10
    face topology before any natural-coordinate mapping is permitted.
    """
    elems = _validate_tets(elements)
    tri = _validate_tri6(tri6_nodes)
    tri_set = set(tri)
    candidates: list[tuple[int, tuple[int, ...]]] = []
    for element_index, conn in enumerate(elems):
        match = _face_for_element(conn, tri_set)
        if match is not None:
            _, local = match
            candidates.append((int(element_index), tuple(int(v) for v in local)))
    if not candidates:
        raise Tet10SurfaceStressError("TRI6_PARENT_TET10_NOT_FOUND")
    if len(candidates) != 1:
        raise Tet10SurfaceStressError("TRI6_PARENT_TET10_AMBIGUOUS")

    element_index, face_local = candidates[0]
    tet = elems[element_index]
    tet_corner_global = tuple(int(v) for v in tet[:4])
    tri_corners = tri[:3]
    try:
        corner_map = tuple(tet_corner_global.index(int(v)) for v in tri_corners)
    except ValueError as exc:
        raise Tet10SurfaceStressError("TRI6_CORNER_NOT_TET10_VERTEX") from exc
    if len(set(corner_map)) != 3:
        raise Tet10SurfaceStressError("TRI6_CORNER_TO_TET10_VERTEX_NOT_UNIQUE")
    opposite = tuple(sorted(set(range(4)) - set(corner_map)))
    if len(opposite) != 1:
        raise Tet10SurfaceStressError("TRI6_OPPOSITE_TET10_VERTEX_NOT_UNIQUE")

    # Validate TRI6 midsides against the corresponding TET10 face edge nodes.
    local_face_nodes = tuple(int(tet[i]) for i in face_local)
    face_corner_globals = local_face_nodes[:3]
    face_mid_globals = local_face_nodes[3:]
    edge_to_mid = {
        frozenset((face_corner_globals[0], face_corner_globals[1])): face_mid_globals[0],
        frozenset((face_corner_globals[1], face_corner_globals[2])): face_mid_globals[1],
        frozenset((face_corner_globals[2], face_corner_globals[0])): face_mid_globals[2],
    }
    expected_tri_mid = (
        edge_to_mid[frozenset((tri[0], tri[1]))],
        edge_to_mid[frozenset((tri[1], tri[2]))],
        edge_to_mid[frozenset((tri[2], tri[0]))],
    )
    if tri[3:] != expected_tri_mid:
        raise Tet10SurfaceStressError("TRI6_MIDSIDE_ORDER_INCOMPATIBLE_WITH_TET10_FACE")

    payload = {
        "schema": "AsterMaxTet10SurfaceParentV1",
        "tri6_nodes": tri,
        "element_index": element_index,
        "tet10_nodes": tuple(int(v) for v in tet),
        "face_local_nodes": face_local,
        "tri_corner_to_tet_vertex": corner_map,
        "opposite_tet_vertex": int(opposite[0]),
    }
    return Tet10SurfaceParent(**payload, mapping_sha256=canonical_sha256(payload))


def tri6_point_to_tet10_natural(parent: Tet10SurfaceParent, rs: np.ndarray | tuple[float, float]) -> np.ndarray:
    point = np.asarray(rs, dtype=float).reshape(-1)
    if point.shape != (2,) or not np.all(np.isfinite(point)):
        raise Tet10SurfaceStressError("TRI6 natural point must be finite with shape (2,)")
    r, s = (float(point[0]), float(point[1]))
    ltri = np.asarray((1.0 - r - s, r, s), dtype=float)
    if np.min(ltri) < -1.0e-12 or np.max(ltri) > 1.0 + 1.0e-12:
        raise Tet10SurfaceStressError("TRI6_NATURAL_POINT_OUTSIDE_REFERENCE_FACE")
    bary = np.zeros(4, dtype=float)
    for tri_corner, tet_vertex in enumerate(parent.tri_corner_to_tet_vertex):
        bary[int(tet_vertex)] = ltri[tri_corner]
    if abs(float(bary[parent.opposite_tet_vertex])) > 1.0e-14:
        raise Tet10SurfaceStressError("TET10_FACE_BARYCENTRIC_MAPPING_FAILED")
    if not np.isclose(float(np.sum(bary)), 1.0, rtol=0.0, atol=1.0e-12):
        raise Tet10SurfaceStressError("TET10_FACE_BARYCENTRIC_PARTITION_FAILED")
    # TET10 natural coordinates are r=L2, s=L3, t=L4.
    return bary[1:].copy()


def evaluate_tet10_stress_at_natural_point(
    coords_mm: np.ndarray,
    displacement_mm: np.ndarray,
    material: IsotropicMaterial,
    natural_coordinates: np.ndarray | tuple[float, float, float],
) -> tuple[np.ndarray, np.ndarray, float]:
    coords = np.asarray(coords_mm, dtype=float)
    disp = np.asarray(displacement_mm, dtype=float)
    point = np.asarray(natural_coordinates, dtype=float).reshape(-1)
    if coords.shape != (10, 3) or disp.shape != (10, 3):
        raise Tet10SurfaceStressError("coords_mm and displacement_mm must both have shape (10,3)")
    if not np.all(np.isfinite(coords)) or not np.all(np.isfinite(disp)):
        raise Tet10SurfaceStressError("coords_mm and displacement_mm must be finite")
    if point.shape != (3,) or not np.all(np.isfinite(point)):
        raise Tet10SurfaceStressError("natural_coordinates must be finite with shape (3,)")
    bary = np.asarray((1.0 - point.sum(), point[0], point[1], point[2]), dtype=float)
    if np.min(bary) < -1.0e-12 or np.max(bary) > 1.0 + 1.0e-12:
        raise Tet10SurfaceStressError("TET10_NATURAL_POINT_OUTSIDE_REFERENCE_ELEMENT")
    b, det_j = tet10_B_matrix(coords, point)
    strain = b @ disp.reshape(30)
    stress = material.constitutive_matrix() @ strain
    if not np.all(np.isfinite(strain)) or not np.all(np.isfinite(stress)):
        raise Tet10SurfaceStressError("surface stress evaluation produced non-finite values")
    return np.asarray(strain, dtype=float), np.asarray(stress, dtype=float), float(det_j)


def evaluate_tri6_surface_stress_sample(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    displacement_mm: np.ndarray,
    material: IsotropicMaterial,
    tri6_nodes: Iterable[int],
    rs: np.ndarray | tuple[float, float],
) -> Tet10SurfaceStressSample:
    nodes = np.asarray(nodes_mm, dtype=float)
    disp = np.asarray(displacement_mm, dtype=float)
    elems = _validate_tets(elements)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise Tet10SurfaceStressError("nodes_mm must be finite with shape (n,3)")
    if disp.shape != nodes.shape or not np.all(np.isfinite(disp)):
        raise Tet10SurfaceStressError("displacement_mm must be finite with the same shape as nodes_mm")
    if np.any(elems >= nodes.shape[0]):
        raise Tet10SurfaceStressError("elements contains out-of-range node indices")

    parent = resolve_tri6_parent_tet10(elems, tri6_nodes)
    natural = tri6_point_to_tet10_natural(parent, rs)
    conn = elems[parent.element_index]
    strain, stress, det_j = evaluate_tet10_stress_at_natural_point(
        nodes[conn], disp[conn], material, natural
    )

    # Physical point is evaluated with the same quadratic TET10 interpolation
    # used by the solver geometry, not copied from a TRI6 stress field.
    from .tet10 import tet10_shape_functions
    x = tet10_shape_functions(natural) @ nodes[conn]
    payload = {
        "schema": "AsterMaxTet10SurfaceStressSampleV1",
        "element_index": parent.element_index,
        "tri6_nodes": parent.tri6_nodes,
        "tri6_natural_coordinates": tuple(float(v) for v in np.asarray(rs, dtype=float)),
        "tet10_natural_coordinates": tuple(float(v) for v in natural),
        "physical_point_mm": tuple(float(v) for v in x),
        "det_jacobian": det_j,
        "strain": tuple(float(v) for v in strain),
        "stress_mpa": tuple(float(v) for v in stress),
        "axial_normal_stress_mpa": float(stress[0]),
        "von_mises_mpa": float(von_mises(stress)),
        "parent_mapping_sha256": parent.mapping_sha256,
    }
    return Tet10SurfaceStressSample(**payload, sample_sha256=canonical_sha256(payload))
