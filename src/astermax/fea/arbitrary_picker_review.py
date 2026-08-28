from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from astermax.credibility import canonical_sha256
from .face_ownership import Tet10FaceOwnershipInventory
from .native_cad_picker_ui import NativeCadPickerAssignment
from .production_picker_routing import ProductionPickerRoute, verify_picker_route
from .tet_quality import TetQualitySnapshot, require_quality_crosscheck


class ArbitraryPickerReviewError(ValueError):
    pass


@dataclass(frozen=True)
class ArbitraryPickerReviewSnapshot:
    schema: str
    source_step_sha256: str
    route_sha256: str
    ownership_sha256: str
    support_face_ids: tuple[str, ...]
    load_face_ids: tuple[str, ...]
    support_face_signature_sha256: tuple[str, ...]
    load_face_signature_sha256: tuple[str, ...]
    support_binding_sha256: str
    load_binding_sha256: str
    support_tri6_count: int
    load_tri6_count: int
    body_tri6_count: int
    node_count: int
    tet10_count: int
    mean_ratio_minimum: float
    mean_ratio_p10: float
    mean_ratio_median: float
    mean_ratio_crosscheck_verified: bool
    projected_faces: tuple[dict[str, Any], ...]
    converged: bool
    industrial_validation: bool
    ansys_equivalence: bool
    snapshot_sha256: str


def _projection(points_mm: np.ndarray) -> np.ndarray:
    p = np.asarray(points_mm, dtype=float)
    if p.ndim != 2 or p.shape[1] != 3 or not np.all(np.isfinite(p)):
        raise ArbitraryPickerReviewError("review points must have finite shape (n,3)")
    return np.column_stack((p[:, 0] + 0.35 * p[:, 1], p[:, 2] + 0.20 * p[:, 1]))


def build_arbitrary_picker_review_snapshot(prepared: dict, *, max_triangles_per_face: int = 120) -> ArbitraryPickerReviewSnapshot:
    route = verify_picker_route(prepared)
    assignment = prepared.get("picker_assignment")
    inventory = prepared.get("inventory")
    quality = prepared.get("quality")
    if not isinstance(route, ProductionPickerRoute):
        raise ArbitraryPickerReviewError("PICKER_REVIEW_ROUTE_MISSING")
    if not isinstance(assignment, NativeCadPickerAssignment):
        raise ArbitraryPickerReviewError("PICKER_REVIEW_ASSIGNMENT_MISSING")
    if not isinstance(inventory, Tet10FaceOwnershipInventory):
        raise ArbitraryPickerReviewError("PICKER_REVIEW_INVENTORY_MISSING")
    if not isinstance(quality, TetQualitySnapshot):
        raise ArbitraryPickerReviewError("PICKER_REVIEW_QUALITY_MISSING")
    require_quality_crosscheck(quality)
    if inventory.source_step_sha256 != route.source_step_sha256:
        raise ArbitraryPickerReviewError("PICKER_REVIEW_STEP_MISMATCH")
    if inventory.ownership_sha256 != prepared["evidence"].ownership_sha256:
        raise ArbitraryPickerReviewError("PICKER_REVIEW_OWNERSHIP_STALE")
    if max_triangles_per_face < 1:
        raise ArbitraryPickerReviewError("max_triangles_per_face must be positive")

    support_signatures = tuple(assignment.support_binding.face_signature_sha256)
    load_signatures = tuple(assignment.load_binding.face_signature_sha256)
    if set(support_signatures) & set(load_signatures):
        raise ArbitraryPickerReviewError("PICKER_REVIEW_SUPPORT_LOAD_OVERLAP")

    projected_nodes = _projection(inventory.nodes_mm)
    rows: list[dict[str, Any]] = []
    support_tri6 = 0
    load_tri6 = 0
    body_tri6 = 0
    for face in inventory.faces:
        if face.signature_sha256 in support_signatures:
            role = "SUPPORT"; support_tri6 += int(face.tri6_count)
        elif face.signature_sha256 in load_signatures:
            role = "LOAD"; load_tri6 += int(face.tri6_count)
        else:
            role = "BODY"; body_tri6 += int(face.tri6_count)
        tri = np.asarray(face.triangles, dtype=np.int64)
        stride = max(1, int(np.ceil(tri.shape[0] / max_triangles_per_face)))
        for conn in tri[::stride][:max_triangles_per_face]:
            pts = projected_nodes[conn[:3]]
            rows.append({
                "face_signature_sha256": face.signature_sha256,
                "role": role,
                "points": tuple((float(x), float(y)) for x, y in pts),
            })
    if support_tri6 != assignment.support_binding.tri6_count:
        raise ArbitraryPickerReviewError("PICKER_REVIEW_SUPPORT_TRI6_MISMATCH")
    if load_tri6 != assignment.load_binding.tri6_count:
        raise ArbitraryPickerReviewError("PICKER_REVIEW_LOAD_TRI6_MISMATCH")
    if not rows:
        raise ArbitraryPickerReviewError("PICKER_REVIEW_EMPTY")

    all_points = np.asarray([point for row in rows for point in row["points"]], dtype=float)
    lo = all_points.min(axis=0); hi = all_points.max(axis=0); span = hi - lo
    if np.any(span <= 0.0) or not np.all(np.isfinite(span)):
        raise ArbitraryPickerReviewError("PICKER_REVIEW_PROJECTION_DEGENERATE")
    normalized_rows = []
    for row in rows:
        pts = (np.asarray(row["points"], dtype=float) - lo) / span
        normalized_rows.append({
            "face_signature_sha256": row["face_signature_sha256"],
            "role": row["role"],
            "points": tuple((float(x), float(y)) for x, y in pts),
        })

    core = {
        "schema": "AsterMaxArbitraryPickerReviewV1",
        "source_step_sha256": route.source_step_sha256,
        "route_sha256": route.route_sha256,
        "ownership_sha256": inventory.ownership_sha256,
        "support_face_ids": list(route.support_face_ids),
        "load_face_ids": list(route.load_face_ids),
        "support_face_signature_sha256": list(support_signatures),
        "load_face_signature_sha256": list(load_signatures),
        "support_binding_sha256": route.support_binding_sha256,
        "load_binding_sha256": route.load_binding_sha256,
        "support_tri6_count": support_tri6,
        "load_tri6_count": load_tri6,
        "body_tri6_count": body_tri6,
        "node_count": int(inventory.nodes_mm.shape[0]),
        "tet10_count": int(inventory.elements.shape[0]),
        "mean_ratio_minimum": float(quality.minimum),
        "mean_ratio_p10": float(quality.percentile_10),
        "mean_ratio_median": float(quality.median),
        "mean_ratio_crosscheck_verified": bool(quality.crosscheck_verified),
        "projected_faces": tuple(normalized_rows),
        "converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    return ArbitraryPickerReviewSnapshot(**core, snapshot_sha256=canonical_sha256(core))


def install_arbitrary_picker_review_tab(notebook):
    import tkinter as tk
    from tkinter import ttk

    panel = ttk.Frame(notebook, padding=12)
    notebook.add(panel, text="Picker Review")
    panel.columnconfigure(0, weight=3); panel.columnconfigure(1, weight=2); panel.rowconfigure(1, weight=1)
    ttk.Label(panel, text="Arbitrary CAD Scope Review", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
    canvas = tk.Canvas(panel, background="#20252b", highlightthickness=1)
    canvas.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
    info = tk.Text(panel, width=42, height=28, wrap="word", state="disabled")
    info.grid(row=1, column=1, sticky="nsew")

    def bind(prepared: dict) -> ArbitraryPickerReviewSnapshot:
        snapshot = build_arbitrary_picker_review_snapshot(prepared)
        canvas.delete("all")
        width = max(int(canvas.winfo_width()), 560); height = max(int(canvas.winfo_height()), 420); margin = 22.0
        style = {"BODY": ("#7f8b96", 1), "SUPPORT": ("#45a3ff", 3), "LOAD": ("#ff8a45", 3)}
        for face in snapshot.projected_faces:
            pts = []
            for x, y in face["points"]:
                pts.extend((margin + x * (width - 2 * margin), height - margin - y * (height - 2 * margin)))
            color, line_width = style[face["role"]]
            canvas.create_polygon(*pts, fill="", outline=color, width=line_width)
        lines = [
            f"Support: {', '.join(snapshot.support_face_ids)}", f"TRI6: {snapshot.support_tri6_count}",
            f"Load: {', '.join(snapshot.load_face_ids)}", f"TRI6: {snapshot.load_tri6_count}", "",
            f"Nodes: {snapshot.node_count}", f"TET10: {snapshot.tet10_count}",
            f"Mean ratio min: {snapshot.mean_ratio_minimum:.3f}", f"p10: {snapshot.mean_ratio_p10:.3f}", f"median: {snapshot.mean_ratio_median:.3f}",
            f"Cross-check: {snapshot.mean_ratio_crosscheck_verified}", "",
            "Metric boundary: AsterMax tetra mean-ratio; not ANSYS Element Quality.",
            "No arbitrary-model convergence or ANSYS-equivalence claim.", "", f"Review SHA: {snapshot.snapshot_sha256}",
        ]
        info.configure(state="normal"); info.delete("1.0", "end"); info.insert("1.0", "\n".join(lines)); info.configure(state="disabled")
        return snapshot

    return bind
