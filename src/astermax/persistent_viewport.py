from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import math


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


def snapshot_from_inventory(inventory) -> ViewportSnapshot:
    nodes = inventory.nodes_mm
    if len(nodes) == 0:
        raise ValueError("VIEWPORT_EMPTY_INVENTORY")
    mins = tuple(float(v) for v in nodes.min(axis=0))
    maxs = tuple(float(v) for v in nodes.max(axis=0))
    return ViewportSnapshot(
        stage="MESH_READY",
        units=("mm", "N", "MPa"),
        bbox_min_mm=mins,
        bbox_max_mm=maxs,
        node_count=int(nodes.shape[0]),
        element_count=int(inventory.elements.shape[0]),
    )


def snapshot_with_assignment(base: ViewportSnapshot, assignment) -> ViewportSnapshot:
    return ViewportSnapshot(
        stage="BOUNDARY_CONDITIONS_READY",
        units=base.units,
        bbox_min_mm=base.bbox_min_mm,
        bbox_max_mm=base.bbox_max_mm,
        node_count=base.node_count,
        element_count=base.element_count,
        support_face_ids=tuple(assignment.support_selection.face_ids),
        load_face_ids=tuple(assignment.load_selection.face_ids),
    )


def snapshot_with_results(base: ViewportSnapshot, summary: dict) -> ViewportSnapshot:
    metadata = summary.get("production_results") or {}
    solve = summary.get("solve_evidence") or {}
    return ViewportSnapshot(
        stage="RESULTS_READY",
        units=base.units,
        bbox_min_mm=base.bbox_min_mm,
        bbox_max_mm=base.bbox_max_mm,
        node_count=base.node_count,
        element_count=base.element_count,
        support_face_ids=base.support_face_ids,
        load_face_ids=base.load_face_ids,
        workspace_sha256=metadata.get("workspace_sha256"),
        solve_evidence_sha256=solve.get("solve_evidence_sha256"),
    )


def validate_snapshot(snapshot: ViewportSnapshot) -> None:
    if snapshot.units != ("mm", "N", "MPa"):
        raise ValueError("VIEWPORT_UNIT_CONTRACT_CHANGED")
    if snapshot.stage not in {"EMPTY", "MESH_READY", "BOUNDARY_CONDITIONS_READY", "RESULTS_READY"}:
        raise ValueError("VIEWPORT_STAGE_INVALID")
    if snapshot.stage != "EMPTY":
        if snapshot.bbox_min_mm is None or snapshot.bbox_max_mm is None:
            raise ValueError("VIEWPORT_GEOMETRY_EVIDENCE_REQUIRED")
        if snapshot.node_count is None or snapshot.node_count <= 0:
            raise ValueError("VIEWPORT_NODE_EVIDENCE_REQUIRED")
        if snapshot.element_count is None or snapshot.element_count <= 0:
            raise ValueError("VIEWPORT_ELEMENT_EVIDENCE_REQUIRED")
    if snapshot.stage == "BOUNDARY_CONDITIONS_READY":
        if not snapshot.support_face_ids or not snapshot.load_face_ids:
            raise ValueError("VIEWPORT_BC_EVIDENCE_REQUIRED")
    if snapshot.stage == "RESULTS_READY":
        if not snapshot.workspace_sha256 or not snapshot.solve_evidence_sha256:
            raise ValueError("VIEWPORT_RESULTS_PROVENANCE_REQUIRED")


def projected_box_segments(snapshot: ViewportSnapshot) -> tuple[tuple[float, float, float, float], ...]:
    """Return normalized 2D line segments for a truthful bounding-box projection.

    This is deliberately not a fake surface renderer. Until a native GPU scene is
    validated, the persistent viewport shows a deterministic engineering envelope
    derived from the actual TET10 node coordinates.
    """
    validate_snapshot(snapshot)
    if snapshot.bbox_min_mm is None or snapshot.bbox_max_mm is None:
        return ()
    mn, mx = snapshot.bbox_min_mm, snapshot.bbox_max_mm
    corners = []
    for x in (mn[0], mx[0]):
        for y in (mn[1], mx[1]):
            for z in (mn[2], mx[2]):
                corners.append((x, y, z))
    cx = (mn[0] + mx[0]) / 2.0
    cy = (mn[1] + mx[1]) / 2.0
    cz = (mn[2] + mx[2]) / 2.0
    sx = max(mx[0] - mn[0], 1e-12)
    sy = max(mx[1] - mn[1], 1e-12)
    sz = max(mx[2] - mn[2], 1e-12)
    scale = max(sx, sy, sz)

    def project(p):
        x = (p[0] - cx) / scale
        y = (p[1] - cy) / scale
        z = (p[2] - cz) / scale
        # fixed isometric projection; deterministic and independent of display DPI
        u = 0.866025403784 * x - 0.866025403784 * y
        v = 0.5 * x + 0.5 * y - z
        return u, v

    pts = [project(p) for p in corners]
    # corner index bits map x,y,z; connect corners differing by one bit
    edges = []
    for i in range(8):
        for bit in (1, 2, 4):
            j = i ^ bit
            if i < j:
                edges.append((*pts[i], *pts[j]))
    return tuple(edges)


def stage_caption(snapshot: ViewportSnapshot) -> str:
    validate_snapshot(snapshot)
    if snapshot.stage == "EMPTY":
        return "Open a STEP/STP model to begin. Units locked to mm / N / MPa."
    dims = tuple(snapshot.bbox_max_mm[i] - snapshot.bbox_min_mm[i] for i in range(3))
    base = f"{snapshot.stage} · {snapshot.node_count} nodes · {snapshot.element_count} TET10 · envelope {dims[0]:.3f} × {dims[1]:.3f} × {dims[2]:.3f} mm"
    if snapshot.stage == "BOUNDARY_CONDITIONS_READY":
        return base + f" · Support {','.join(snapshot.support_face_ids)} · Load {','.join(snapshot.load_face_ids)}"
    if snapshot.stage == "RESULTS_READY":
        return base + " · results provenance verified"
    return base
