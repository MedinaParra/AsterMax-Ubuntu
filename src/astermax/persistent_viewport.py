from __future__ import annotations

from dataclasses import dataclass, replace
from collections import Counter
import numpy as np


@dataclass(frozen=True)
class ViewportSnapshot:
    stage: str
    units: tuple[str, str, str]
    bbox_min_mm: tuple[float, float, float] | None = None
    bbox_max_mm: tuple[float, float, float] | None = None
    node_count: int | None = None
    element_count: int | None = None
    support_face_ids: tuple[str, ...] = ()
    load_face_ids: tuple[str, ...] = ()
    workspace_sha256: str | None = None
    solve_evidence_sha256: str | None = None
    scene_node_count: int | None = None
    scene_triangle_count: int | None = None


# TET10 local nodes: 0..3 corners; midsides 4:(0,1), 5:(1,2), 6:(0,2),
# 7:(0,3), 8:(1,3), 9:(2,3). Each quadratic face is rendered as 4 triangles.
_TET10_FACES = (
    (0, 1, 2, 4, 5, 6),
    (0, 1, 3, 4, 8, 7),
    (0, 2, 3, 6, 9, 7),
    (1, 2, 3, 5, 9, 8),
)
_FACE_TRIANGLES = ((0, 3, 5), (3, 1, 4), (5, 4, 2), (3, 4, 5))


def extract_tet10_surface(inventory) -> tuple[np.ndarray, np.ndarray]:
    """Extract the actual external quadratic TET10 surface as linear display triangles.

    Boundary ownership is determined only from the four corner node IDs, while the
    six-node quadratic face is retained for rendering. This is visualization
    geometry derived from the solver mesh, not a reconstructed/fake CAD surface.
    """
    nodes = np.asarray(inventory.nodes_mm, dtype=float)
    elements = np.asarray(inventory.elements, dtype=int)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or len(nodes) == 0:
        raise ValueError("VIEWPORT_EMPTY_INVENTORY")
    if elements.ndim != 2 or elements.shape[1] != 10 or len(elements) == 0:
        raise ValueError("VIEWPORT_TET10_REQUIRED")
    if elements.min() < 0 or elements.max() >= len(nodes):
        raise ValueError("VIEWPORT_CONNECTIVITY_OUT_OF_RANGE")

    counts: Counter[tuple[int, int, int]] = Counter()
    faces: list[tuple[tuple[int, int, int], tuple[int, ...]]] = []
    for element in elements:
        for local in _TET10_FACES:
            face = tuple(int(element[i]) for i in local)
            key = tuple(sorted(face[:3]))
            counts[key] += 1
            faces.append((key, face))

    triangles: list[tuple[int, int, int]] = []
    for key, face in faces:
        if counts[key] != 1:
            continue
        for a, b, c in _FACE_TRIANGLES:
            triangles.append((face[a], face[b], face[c]))
    if not triangles:
        raise ValueError("VIEWPORT_SURFACE_EMPTY")
    return nodes.copy(), np.asarray(triangles, dtype=int)


def snapshot_from_inventory(inventory) -> ViewportSnapshot:
    nodes, triangles = extract_tet10_surface(inventory)
    mins = tuple(float(v) for v in nodes.min(axis=0))
    maxs = tuple(float(v) for v in nodes.max(axis=0))
    return ViewportSnapshot(
        stage="MESH_READY", units=("mm", "N", "MPa"),
        bbox_min_mm=mins, bbox_max_mm=maxs,
        node_count=int(nodes.shape[0]), element_count=int(np.asarray(inventory.elements).shape[0]),
        scene_node_count=int(nodes.shape[0]), scene_triangle_count=int(triangles.shape[0]),
    )


def snapshot_with_assignment(base: ViewportSnapshot, assignment) -> ViewportSnapshot:
    return replace(base, stage="BOUNDARY_CONDITIONS_READY",
                   support_face_ids=tuple(assignment.support_selection.face_ids),
                   load_face_ids=tuple(assignment.load_selection.face_ids))


def snapshot_with_results(base: ViewportSnapshot, summary: dict) -> ViewportSnapshot:
    metadata = summary.get("production_results") or {}
    solve = summary.get("solve_evidence") or {}
    return replace(base, stage="RESULTS_READY",
                   workspace_sha256=metadata.get("workspace_sha256"),
                   solve_evidence_sha256=solve.get("solve_evidence_sha256"))


def validate_snapshot(snapshot: ViewportSnapshot) -> None:
    if snapshot.units != ("mm", "N", "MPa"):
        raise ValueError("VIEWPORT_UNIT_CONTRACT_CHANGED")
    if snapshot.stage not in {"EMPTY", "MESH_READY", "BOUNDARY_CONDITIONS_READY", "RESULTS_READY"}:
        raise ValueError("VIEWPORT_STAGE_INVALID")
    if snapshot.stage != "EMPTY":
        if snapshot.bbox_min_mm is None or snapshot.bbox_max_mm is None:
            raise ValueError("VIEWPORT_GEOMETRY_EVIDENCE_REQUIRED")
        if not snapshot.node_count or not snapshot.element_count:
            raise ValueError("VIEWPORT_MESH_EVIDENCE_REQUIRED")
        if not snapshot.scene_triangle_count:
            raise ValueError("VIEWPORT_SURFACE_EVIDENCE_REQUIRED")
    if snapshot.stage == "BOUNDARY_CONDITIONS_READY" and (not snapshot.support_face_ids or not snapshot.load_face_ids):
        raise ValueError("VIEWPORT_BC_EVIDENCE_REQUIRED")
    if snapshot.stage == "RESULTS_READY" and (not snapshot.workspace_sha256 or not snapshot.solve_evidence_sha256):
        raise ValueError("VIEWPORT_RESULTS_PROVENANCE_REQUIRED")


def project_surface(nodes_mm: np.ndarray, triangles: np.ndarray, *, yaw_deg: float = 35.0, pitch_deg: float = 25.0):
    """Deterministic orthographic projection with depth ordering for the desktop canvas."""
    p = np.asarray(nodes_mm, dtype=float)
    yaw, pitch = np.deg2rad([yaw_deg, pitch_deg])
    rz = np.array([[np.cos(yaw), -np.sin(yaw), 0.0], [np.sin(yaw), np.cos(yaw), 0.0], [0.0, 0.0, 1.0]])
    rx = np.array([[1.0, 0.0, 0.0], [0.0, np.cos(pitch), -np.sin(pitch)], [0.0, np.sin(pitch), np.cos(pitch)]])
    q = (p - p.mean(axis=0)) @ (rx @ rz).T
    order = np.argsort(q[np.asarray(triangles, dtype=int), 2].mean(axis=1))
    return q[:, :2], np.asarray(triangles, dtype=int)[order]


def projected_box_segments(snapshot: ViewportSnapshot):
    """Legacy evidence-envelope projection retained for compatibility and fallback."""
    validate_snapshot(snapshot)
    mn, mx = snapshot.bbox_min_mm, snapshot.bbox_max_mm
    corners = [(x, y, z) for x in (mn[0], mx[0]) for y in (mn[1], mx[1]) for z in (mn[2], mx[2])]
    center = np.mean(np.asarray(corners), axis=0); scale = max(np.ptp(np.asarray(corners), axis=0).max(), 1e-12)
    def project(p):
        x, y, z = (np.asarray(p) - center) / scale
        return 0.866025403784*x - 0.866025403784*y, 0.5*x + 0.5*y - z
    pts = [project(p) for p in corners]; edges=[]
    for i in range(8):
        for bit in (1,2,4):
            j=i^bit
            if i<j: edges.append((*pts[i],*pts[j]))
    return tuple(edges)


def stage_caption(snapshot: ViewportSnapshot) -> str:
    validate_snapshot(snapshot)
    if snapshot.stage == "EMPTY":
        return "Open a STEP/STP model to begin. Units locked to mm / N / MPa."
    dims = tuple(snapshot.bbox_max_mm[i]-snapshot.bbox_min_mm[i] for i in range(3))
    base = f"{snapshot.stage} · {snapshot.node_count} nodes · {snapshot.element_count} TET10 · {snapshot.scene_triangle_count} surface triangles · envelope {dims[0]:.3f} × {dims[1]:.3f} × {dims[2]:.3f} mm"
    if snapshot.stage == "BOUNDARY_CONDITIONS_READY": return base + f" · Support {','.join(snapshot.support_face_ids)} · Load {','.join(snapshot.load_face_ids)}"
    if snapshot.stage == "RESULTS_READY": return base + " · results provenance verified"
    return base
