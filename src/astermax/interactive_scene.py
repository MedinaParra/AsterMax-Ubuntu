from __future__ import annotations

from dataclasses import dataclass, replace
import math
import numpy as np


@dataclass(frozen=True)
class CameraState:
    yaw_deg: float = 35.0
    pitch_deg: float = 25.0
    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0


def validate_camera(camera: CameraState) -> None:
    if not all(math.isfinite(v) for v in (camera.yaw_deg, camera.pitch_deg, camera.zoom, camera.pan_x, camera.pan_y)):
        raise ValueError("SCENE_CAMERA_NONFINITE")
    if camera.zoom <= 0.0:
        raise ValueError("SCENE_ZOOM_INVALID")
    if not -89.0 <= camera.pitch_deg <= 89.0:
        raise ValueError("SCENE_PITCH_OUT_OF_RANGE")


def orbit(camera: CameraState, delta_yaw_deg: float, delta_pitch_deg: float) -> CameraState:
    validate_camera(camera)
    pitch = min(89.0, max(-89.0, camera.pitch_deg + float(delta_pitch_deg)))
    yaw = (camera.yaw_deg + float(delta_yaw_deg)) % 360.0
    updated = replace(camera, yaw_deg=yaw, pitch_deg=pitch)
    validate_camera(updated)
    return updated


def zoom_by(camera: CameraState, factor: float) -> CameraState:
    validate_camera(camera)
    if not math.isfinite(factor) or factor <= 0.0:
        raise ValueError("SCENE_ZOOM_FACTOR_INVALID")
    updated = replace(camera, zoom=min(100.0, max(0.01, camera.zoom * factor)))
    validate_camera(updated)
    return updated


def pan_by(camera: CameraState, dx: float, dy: float) -> CameraState:
    validate_camera(camera)
    if not math.isfinite(dx) or not math.isfinite(dy):
        raise ValueError("SCENE_PAN_NONFINITE")
    return replace(camera, pan_x=camera.pan_x + float(dx), pan_y=camera.pan_y + float(dy))


def fit_camera() -> CameraState:
    return CameraState()


def triangle_wire_edges(triangles: np.ndarray) -> np.ndarray:
    tri = np.asarray(triangles, dtype=int)
    if tri.ndim != 2 or tri.shape[1] != 3:
        raise ValueError("SCENE_TRIANGLES_REQUIRED")
    edges = set()
    for a, b, c in tri:
        for u, v in ((a, b), (b, c), (c, a)):
            edges.add(tuple(sorted((int(u), int(v)))))
    return np.asarray(sorted(edges), dtype=int)


def project_scene(nodes_mm: np.ndarray, triangles: np.ndarray, camera: CameraState) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Project a real mesh surface with deterministic orbit/pan/zoom and depth order.

    Returns (xy, depth_sorted_triangles, unique_wire_edges). Coordinates are still
    model-relative display coordinates; pixel scaling belongs to the GUI adapter.
    """
    validate_camera(camera)
    nodes = np.asarray(nodes_mm, dtype=float)
    tri = np.asarray(triangles, dtype=int)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or len(nodes) == 0:
        raise ValueError("SCENE_NODES_REQUIRED")
    if tri.ndim != 2 or tri.shape[1] != 3 or len(tri) == 0:
        raise ValueError("SCENE_TRIANGLES_REQUIRED")
    if tri.min() < 0 or tri.max() >= len(nodes):
        raise ValueError("SCENE_CONNECTIVITY_OUT_OF_RANGE")

    yaw = math.radians(camera.yaw_deg)
    pitch = math.radians(camera.pitch_deg)
    rz = np.array([[math.cos(yaw), -math.sin(yaw), 0.0],
                   [math.sin(yaw),  math.cos(yaw), 0.0],
                   [0.0, 0.0, 1.0]])
    rx = np.array([[1.0, 0.0, 0.0],
                   [0.0, math.cos(pitch), -math.sin(pitch)],
                   [0.0, math.sin(pitch),  math.cos(pitch)]])
    centered = nodes - nodes.mean(axis=0)
    q = centered @ (rx @ rz).T
    xy = q[:, :2] * camera.zoom
    xy[:, 0] += camera.pan_x
    xy[:, 1] += camera.pan_y
    depth = q[tri, 2].mean(axis=1)
    ordered = tri[np.argsort(depth)]
    return xy, ordered, triangle_wire_edges(tri)


def scene_modes() -> tuple[str, ...]:
    # Results contours are intentionally not advertised until result-field binding
    # is added behind its own evidence gate.
    return ("surface", "wireframe", "surface+edges")
