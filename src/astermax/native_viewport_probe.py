from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .native_viewport import NativeViewportSurface
from .native_vtu_preview import NativeVtuPreviewData


@dataclass(frozen=True)
class NativeViewportProbe:
    schema: str
    face_index: int
    owner_cell_index: int
    owner_von_mises_ip_max_mpa: float
    face_node_indices: tuple[int, int, int, int, int, int]
    maximum_face_displacement_mm: float
    maximum_face_displacement_node: int
    maximum_face_displacement_vector_mm: tuple[float, float, float]
    evidence_boundary: str


def probe_surface_face(
    data: NativeVtuPreviewData,
    surface: NativeViewportSurface,
    face_index: int,
) -> NativeViewportProbe:
    """Return exact, provenance-preserving data for one external TRI6 face.

    Von Mises is the owner element's integration-point maximum as stored in the
    verified VTU. Displacement is nodal and therefore may be probed directly.
    No nodal stress interpolation or smoothing is performed.
    """
    index = int(face_index)
    if index < 0 or index >= surface.tri6_connectivity.shape[0]:
        raise IndexError("face_index outside external TRI6 surface")

    face = np.asarray(surface.tri6_connectivity[index], dtype=np.int64)
    owner = int(surface.owner_cell_index[index])
    if owner < 0 or owner >= data.tet10_connectivity.shape[0]:
        raise ValueError("surface owner cell index is invalid")
    if not np.array_equal(
        np.sort(face[:3]),
        np.sort(np.intersect1d(face[:3], data.tet10_connectivity[owner], assume_unique=False)),
    ):
        raise ValueError("surface face provenance does not match owner TET10")

    displacement = np.asarray(data.displacement_mm[face], dtype=float)
    magnitudes = np.linalg.norm(displacement, axis=1)
    local_max = int(np.argmax(magnitudes))
    node = int(face[local_max])
    vector = displacement[local_max]
    vm = float(surface.owner_von_mises_ip_max_mpa[index])
    if not np.isfinite(vm) or not np.all(np.isfinite(vector)):
        raise ValueError("probe refuses non-finite result data")

    return NativeViewportProbe(
        schema="AsterMaxNativeViewportProbeV1",
        face_index=index,
        owner_cell_index=owner,
        owner_von_mises_ip_max_mpa=vm,
        face_node_indices=tuple(int(v) for v in face),
        maximum_face_displacement_mm=float(magnitudes[local_max]),
        maximum_face_displacement_node=node,
        maximum_face_displacement_vector_mm=tuple(float(v) for v in vector),
        evidence_boundary=(
            "VON_MISES_IS_OWNER_ELEMENT_IP_MAX_NOT_NODAL_STRESS;"
            "DISPLACEMENT_IS_EXACT_VTU_NODAL_DATA"
        ),
    )


def nearest_projected_face(
    xy_pixels: np.ndarray,
    surface: NativeViewportSurface,
    x_pixel: float,
    y_pixel: float,
    *,
    maximum_distance_pixels: float = 45.0,
) -> int | None:
    """Pick the nearest external face centroid in the current projected view.

    This is a deterministic lightweight picker, not ray/triangle occlusion picking.
    The explicit pixel tolerance prevents a click far from the model selecting a
    face silently.
    """
    points = np.asarray(xy_pixels, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or not np.all(np.isfinite(points)):
        raise ValueError("xy_pixels must be finite with shape (n, 2)")
    if not np.isfinite(x_pixel) or not np.isfinite(y_pixel):
        raise ValueError("pick coordinates must be finite")
    if not np.isfinite(maximum_distance_pixels) or maximum_distance_pixels <= 0.0:
        raise ValueError("maximum_distance_pixels must be finite and positive")
    if surface.tri6_connectivity.shape[0] == 0:
        return None

    corners = surface.tri6_connectivity[:, :3]
    centroids = points[corners].mean(axis=1)
    target = np.asarray([float(x_pixel), float(y_pixel)])
    distance = np.linalg.norm(centroids - target, axis=1)
    index = int(np.argmin(distance))
    return index if float(distance[index]) <= float(maximum_distance_pixels) else None
