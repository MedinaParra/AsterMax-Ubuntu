from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .native_vtu_preview import NativeVtuPreviewData


# Gmsh/VTK quadratic tetra local face ordering. Corner identity is used only to
# detect shared/internal faces; the full TRI6 connectivity is retained for
# provenance and future curved rendering.
_TET10_FACES = (
    (0, 1, 2, 4, 5, 6),
    (0, 1, 3, 4, 9, 7),
    (1, 2, 3, 5, 8, 9),
    (0, 2, 3, 6, 8, 7),
)


@dataclass(frozen=True)
class NativeViewportSurface:
    schema: str
    tri6_connectivity: np.ndarray
    owner_cell_index: np.ndarray
    owner_von_mises_ip_max_mpa: np.ndarray


def extract_tet10_boundary(data: NativeVtuPreviewData) -> NativeViewportSurface:
    """Extract the external TRI6 skin without inventing nodal stress.

    A face is external iff its three corner node ids occur exactly once. Repeated
    faces are internal and removed. More than two owners is rejected as
    non-manifold connectivity rather than rendered ambiguously.
    """
    owners: dict[tuple[int, int, int], list[tuple[int, np.ndarray]]] = {}
    for cell_index, conn in enumerate(np.asarray(data.tet10_connectivity, dtype=np.int64)):
        for local_face in _TET10_FACES:
            face = np.asarray([conn[i] for i in local_face], dtype=np.int64)
            key = tuple(sorted(int(v) for v in face[:3]))
            owners.setdefault(key, []).append((int(cell_index), face))

    boundary_faces: list[np.ndarray] = []
    boundary_owners: list[int] = []
    for key in sorted(owners):
        hits = owners[key]
        if len(hits) > 2:
            raise ValueError(f"non-manifold TET10 face {key} has {len(hits)} owners")
        if len(hits) == 1:
            owner, face = hits[0]
            boundary_faces.append(face)
            boundary_owners.append(owner)

    tri6 = (
        np.vstack(boundary_faces).astype(np.int64, copy=False)
        if boundary_faces
        else np.empty((0, 6), dtype=np.int64)
    )
    owner_idx = np.asarray(boundary_owners, dtype=np.int64)
    owner_vm = data.von_mises_ip_max_mpa[owner_idx].copy() if owner_idx.size else np.empty((0,), dtype=float)
    return NativeViewportSurface(
        schema="AsterMaxNativeViewportSurfaceV1",
        tri6_connectivity=tri6,
        owner_cell_index=owner_idx,
        owner_von_mises_ip_max_mpa=owner_vm,
    )


def orthographic_camera_projection(
    points_mm: np.ndarray,
    *,
    azimuth_deg: float = 35.0,
    elevation_deg: float = 25.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Project 3D points with a deterministic engineering orbit camera.

    Returns projected XY and camera-space depth. No perspective or hidden-surface
    claim is made; depth is provided so callers can painter-sort boundary faces.
    """
    points = np.asarray(points_mm, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not np.all(np.isfinite(points)):
        raise ValueError("points_mm must be finite with shape (n, 3)")
    if not np.isfinite(azimuth_deg) or not np.isfinite(elevation_deg):
        raise ValueError("camera angles must be finite")

    az = math.radians(float(azimuth_deg))
    el = math.radians(float(elevation_deg))
    cz, sz = math.cos(az), math.sin(az)
    cx, sx = math.cos(el), math.sin(el)
    rz = np.asarray(((cz, -sz, 0.0), (sz, cz, 0.0), (0.0, 0.0, 1.0)))
    rx = np.asarray(((1.0, 0.0, 0.0), (0.0, cx, -sx), (0.0, sx, cx)))

    centered = points - np.mean(points, axis=0, keepdims=True) if points.shape[0] else points.copy()
    camera = centered @ (rz @ rx).T
    return camera[:, :2].copy(), camera[:, 2].copy()


def viewport_geometry(
    data: NativeVtuPreviewData,
    *,
    deformation_scale: float = 0.0,
    azimuth_deg: float = 35.0,
    elevation_deg: float = 25.0,
) -> tuple[np.ndarray, np.ndarray, NativeViewportSurface]:
    if not np.isfinite(deformation_scale):
        raise ValueError("deformation_scale must be finite")
    xyz = data.points_mm + float(deformation_scale) * data.displacement_mm
    xy, depth = orthographic_camera_projection(
        xyz, azimuth_deg=azimuth_deg, elevation_deg=elevation_deg
    )
    surface = extract_tet10_boundary(data)
    return xy, depth, surface


def assert_native_viewport_claim_boundary(data: NativeVtuPreviewData) -> None:
    if data.converged_claim:
        raise ValueError("native viewport refuses unearned convergence claim")
    if data.industrial_validation_claim:
        raise ValueError("native viewport refuses unearned industrial-validation claim")
    if data.stress_is_nodal:
        raise ValueError("native viewport refuses nodal stress representation")
