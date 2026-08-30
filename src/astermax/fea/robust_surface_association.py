from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np

from astermax.credibility import canonical_sha256


class SurfaceAssociationError(ValueError):
    pass


@dataclass(frozen=True)
class SurfaceDescriptorV1:
    bbox_mm: tuple[float, float, float, float, float, float]
    centroid_mm: tuple[float, float, float]
    area_mm2: float
    normal_abs: tuple[float, float, float]
    descriptor_sha256: str


def build_mesh_surface_descriptor(nodes_mm: np.ndarray, tri6: np.ndarray) -> SurfaceDescriptorV1:
    """Reconstruct mesh-surface invariants from actual TRI6 boundary ownership.

    V1 deliberately uses the three corner nodes of each TRI6 for a linearized
    geometric witness. The surface centroid is area-weighted, not the arithmetic
    mean of boundary nodes, so local mesh-density changes do not shift identity.
    """
    nodes = np.asarray(nodes_mm, dtype=float)
    tris = np.asarray(tri6, dtype=np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise SurfaceAssociationError("SURFACE_ASSOC_NODES")
    if tris.ndim != 2 or tris.shape[1] != 6 or tris.shape[0] == 0:
        raise SurfaceAssociationError("SURFACE_ASSOC_TRI6")
    if np.any(tris < 0) or np.any(tris >= nodes.shape[0]):
        raise SurfaceAssociationError("SURFACE_ASSOC_CONNECTIVITY")

    used = np.unique(tris.reshape(-1))
    xyz = nodes[used]
    lo, hi = xyz.min(axis=0), xyz.max(axis=0)
    area = 0.0
    centroid_numerator = np.zeros(3)
    normal = np.zeros(3)
    for row in tris:
        p0, p1, p2 = nodes[row[0]], nodes[row[1]], nodes[row[2]]
        cross = np.cross(p1 - p0, p2 - p0)
        triangle_area = 0.5 * float(np.linalg.norm(cross))
        area += triangle_area
        centroid_numerator += triangle_area * ((p0 + p1 + p2) / 3.0)
        normal += cross
    mag = float(np.linalg.norm(normal))
    if area <= 0.0 or mag <= 0.0 or not math.isfinite(area + mag):
        raise SurfaceAssociationError("SURFACE_ASSOC_DEGENERATE")
    centroid = centroid_numerator / area
    if not np.all(np.isfinite(centroid)):
        raise SurfaceAssociationError("SURFACE_ASSOC_CENTROID")

    core = {
        "bbox_mm": tuple(float(v) for v in (*lo, *hi)),
        "centroid_mm": tuple(float(v) for v in centroid),
        "area_mm2": float(area),
        "normal_abs": tuple(float(v) for v in np.abs(normal / mag)),
    }
    return SurfaceDescriptorV1(**core, descriptor_sha256=canonical_sha256(core))


def _axis_aligned_plane_normal_from_bbox(cad_bbox: np.ndarray, model_diagonal_mm: float) -> np.ndarray | None:
    """Return an axis normal only when the CAD bbox proves the plane is axis-aligned.

    A sloped planar face can have non-zero spans in X, Y and Z, so inferring its
    normal from the smallest span is invalid. In that case the V1 association must
    rely on the other independent invariants until an OCC-derived CAD normal is
    added to the persistent FaceSignature contract.
    """
    spans = np.asarray(cad_bbox[3:] - cad_bbox[:3], dtype=float)
    tol = max(float(model_diagonal_mm) * 1.0e-9, 1.0e-9)
    collapsed = np.flatnonzero(np.abs(spans) <= tol)
    if collapsed.size != 1:
        return None
    expected = np.zeros(3)
    expected[int(collapsed[0])] = 1.0
    return expected


def score_planar_cad_match(descriptor: SurfaceDescriptorV1, signature, model_diagonal_mm: float) -> tuple[float, dict]:
    diagonal = float(model_diagonal_mm)
    if not math.isfinite(diagonal) or diagonal <= 0.0:
        raise SurfaceAssociationError("SURFACE_ASSOC_DIAGONAL")
    bbox = np.asarray(descriptor.bbox_mm, dtype=float)
    cad_bbox = np.asarray(signature.bbox_mm, dtype=float)
    centroid = np.asarray(descriptor.centroid_mm, dtype=float)
    cad_centroid = np.asarray(signature.center_mm, dtype=float)
    if not np.all(np.isfinite(cad_bbox)) or not np.all(np.isfinite(cad_centroid)):
        raise SurfaceAssociationError("SURFACE_ASSOC_CAD_NONFINITE")
    bbox_error = float(np.linalg.norm(bbox - cad_bbox) / diagonal)
    centroid_error = float(np.linalg.norm(centroid - cad_centroid) / diagonal)
    cad_area = float(signature.area_mm2)
    if not math.isfinite(cad_area) or cad_area <= 0.0:
        raise SurfaceAssociationError("SURFACE_ASSOC_CAD_AREA")
    area_error = abs(descriptor.area_mm2 - cad_area) / cad_area

    normal_error = 0.0
    normal_checked = False
    if str(signature.surface_type).upper().startswith("PLANE"):
        expected = _axis_aligned_plane_normal_from_bbox(cad_bbox, diagonal)
        if expected is not None:
            normal_checked = True
            normal_error = float(np.linalg.norm(np.asarray(descriptor.normal_abs) - expected))

    metrics = {
        "bbox_error_rel": bbox_error,
        "centroid_error_rel": centroid_error,
        "area_error_rel": area_error,
        "normal_error": normal_error,
        "normal_checked": normal_checked,
    }
    score = bbox_error / 1e-6 + centroid_error / 1e-6 + area_error / 5e-3
    if normal_checked:
        score += normal_error / 2e-3
    return float(score), metrics


def choose_unique_cad_face(
    descriptor: SurfaceDescriptorV1,
    cad_faces,
    model_diagonal_mm: float,
    uniqueness_margin_min: float = 0.15,
):
    if not math.isfinite(float(uniqueness_margin_min)) or not 0.0 < float(uniqueness_margin_min) < 1.0:
        raise SurfaceAssociationError("SURFACE_ASSOC_UNIQUENESS_MARGIN")
    ranked = []
    for _, signature in cad_faces:
        score, metrics = score_planar_cad_match(descriptor, signature, model_diagonal_mm)
        ranked.append((score, signature, metrics))
    if not ranked:
        raise SurfaceAssociationError("SURFACE_ASSOC_CAD_FACES")
    ranked.sort(key=lambda item: item[0])
    best = ranked[0]
    if (
        best[2]["bbox_error_rel"] > 1e-6
        or best[2]["centroid_error_rel"] > 1e-6
        or best[2]["area_error_rel"] > 5e-3
        or (best[2]["normal_checked"] and best[2]["normal_error"] > 2e-3)
    ):
        raise SurfaceAssociationError("SURFACE_ASSOC_NO_MATCH")
    if len(ranked) > 1:
        margin = (ranked[1][0] - best[0]) / max(abs(ranked[1][0]), 1e-12)
        if margin < uniqueness_margin_min:
            raise SurfaceAssociationError("SURFACE_ASSOC_AMBIGUOUS")
    return best[1], best[2]
