from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any, Callable

import numpy as np

from astermax.credibility import canonical_sha256
from .tet10 import TET10_GAUSS_POINTS, tet10_B_matrix


class VisualModelPreparationError(ValueError):
    pass


@dataclass(frozen=True)
class VisualModelPreparationSnapshot:
    schema: str
    step_sha256: str
    preparation_snapshot_sha256: str
    constraint_selection_sha256: str
    load_selection_sha256: str
    support_surface_keys: tuple[str, ...]
    load_surface_keys: tuple[str, ...]
    support_tri6_count: int
    load_tri6_count: int
    body_tri6_count: int
    rendered_face_count: int
    projection: str
    projected_faces: tuple[dict[str, Any], ...]
    jacobian_ip_count: int
    minimum_det_jacobian_mm3: float
    median_det_jacobian_mm3: float
    maximum_det_jacobian_mm3: float
    edge_ratio_minimum: float
    edge_ratio_p10: float
    edge_ratio_median: float
    edge_ratio_histogram_edges: tuple[float, ...]
    edge_ratio_histogram_counts: tuple[int, ...]
    quality_metric_boundary: str
    converged: bool
    industrial_validation: bool
    ansys_equivalence: bool
    snapshot_sha256: str


def _finite_nodes_elements(nodes_mm: np.ndarray, elements: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise VisualModelPreparationError("nodes_mm must have finite shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 10 or elems.shape[0] == 0:
        raise VisualModelPreparationError("elements must contain at least one TET10")
    if np.any(elems < 0) or np.any(elems >= nodes.shape[0]):
        raise VisualModelPreparationError("elements contains an out-of-range node index")
    return nodes, elems


def tet10_edge_ratio_proxy(nodes_mm: np.ndarray, elements: np.ndarray) -> np.ndarray:
    nodes, elems = _finite_nodes_elements(nodes_mm, elements)
    pairs = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
    out = np.empty(elems.shape[0], dtype=float)
    for i, conn in enumerate(elems):
        corners = nodes[conn[:4]]
        lengths = np.asarray([np.linalg.norm(corners[a] - corners[b]) for a, b in pairs], dtype=float)
        if not np.all(np.isfinite(lengths)) or float(np.min(lengths)) <= 0.0:
            raise VisualModelPreparationError("degenerate corner edge in TET10")
        out[i] = float(np.min(lengths) / np.max(lengths))
    if np.any(out <= 0.0) or np.any(out > 1.0 + 1.0e-12):
        raise VisualModelPreparationError("edge-ratio proxy outside (0,1]")
    return out


def tet10_jacobian_distribution(nodes_mm: np.ndarray, elements: np.ndarray) -> np.ndarray:
    nodes, elems = _finite_nodes_elements(nodes_mm, elements)
    values: list[float] = []
    for conn in elems:
        coords = nodes[conn]
        for point in TET10_GAUSS_POINTS:
            _, det_j = tet10_B_matrix(coords, point)
            values.append(float(det_j))
    result = np.asarray(values, dtype=float)
    if result.size != elems.shape[0] * 4 or not np.all(np.isfinite(result)):
        raise VisualModelPreparationError("invalid TET10 Jacobian distribution")
    if np.any(result <= 0.0):
        raise VisualModelPreparationError("visual inspector refuses nonpositive TET10 Jacobian")
    return result


def _oblique_projection(points_mm: np.ndarray) -> np.ndarray:
    p = np.asarray(points_mm, dtype=float)
    u = p[:, 0] + 0.35 * p[:, 1]
    v = p[:, 2] + 0.20 * p[:, 1]
    return np.column_stack((u, v))


def _sample_tri6(triangles: np.ndarray, max_faces: int) -> np.ndarray:
    tri = np.asarray(triangles, dtype=np.int64)
    if tri.ndim != 2 or tri.shape[1] != 6:
        raise VisualModelPreparationError("surface TRI6 arrays must have shape (n, 6)")
    if max_faces < 1:
        raise VisualModelPreparationError("max_faces_per_group must be positive")
    if tri.shape[0] <= max_faces:
        return tri
    stride = int(ceil(tri.shape[0] / max_faces))
    return tri[::stride][:max_faces]


def _scope_contract(
    preparation: dict[str, Any],
    named_selections: dict[str, Any] | None,
) -> tuple[tuple[str, ...], tuple[str, ...], str, str]:
    if named_selections is None:
        return (
            ("X_MIN",),
            ("X_MAX",),
            str(preparation["constraint_selection_sha256"]),
            str(preparation["load_selection_sha256"]),
        )
    support = named_selections.get("support", {})
    load = named_selections.get("load", {})
    support_keys = tuple(str(v) for v in support.get("surface_keys", ()))
    load_keys = tuple(str(v) for v in load.get("surface_keys", ()))
    if not support_keys or not load_keys:
        raise VisualModelPreparationError("named Support/Load surface keys are required")
    if set(support_keys) & set(load_keys):
        raise VisualModelPreparationError("named Support/Load visual scopes overlap")
    support_sha = str(support.get("named_selection_sha256", ""))
    load_sha = str(load.get("named_selection_sha256", ""))
    if len(support_sha) != 64 or len(load_sha) != 64 or support_sha == load_sha:
        raise VisualModelPreparationError("named Support/Load visual provenance is invalid")
    return support_keys, load_keys, support_sha, load_sha


def build_visual_model_preparation_snapshot(
    *,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    surface_triangles: dict[str, np.ndarray],
    preparation: dict[str, Any],
    named_selections: dict[str, Any] | None = None,
    max_faces_per_group: int = 160,
) -> VisualModelPreparationSnapshot:
    nodes, elems = _finite_nodes_elements(nodes_mm, elements)
    if preparation.get("schema") != "AsterMaxModelPreparationEvidenceV1":
        raise VisualModelPreparationError("C4.3 model preparation evidence is required")
    mesh_gate = preparation.get("mesh_gate", {})
    if mesh_gate.get("schema") != "AsterMaxMeshPreparationGateV1":
        raise VisualModelPreparationError("C4.3 mesh preparation gate is required")
    if not bool(mesh_gate.get("positive_jacobian_verified")) or not bool(mesh_gate.get("straight_sided_verified")):
        raise VisualModelPreparationError("visual inspector requires verified C4.3 preparation gates")
    required = ("X_MIN", "X_MAX", "Y_MIN", "Y_MAX", "Z_MIN", "Z_MAX")
    if any(name not in surface_triangles for name in required):
        raise VisualModelPreparationError("all six PMV axis surface groups are required")

    support_keys, load_keys, support_sha, load_sha = _scope_contract(preparation, named_selections)
    if any(key not in required for key in support_keys + load_keys):
        raise VisualModelPreparationError("visual named selection references unsupported mesh boundary")

    det = tet10_jacobian_distribution(nodes, elems)
    edge = tet10_edge_ratio_proxy(nodes, elems)
    gate_min = float(mesh_gate["minimum_det_jacobian_mm3"])
    if not np.isclose(float(np.min(det)), gate_min, rtol=1.0e-10, atol=max(abs(gate_min), 1.0) * 1.0e-12):
        raise VisualModelPreparationError("Jacobian distribution does not match C4.3 gate")

    role_map = {name: "BODY" for name in required}
    for key in support_keys:
        role_map[key] = "SUPPORT"
    for key in load_keys:
        role_map[key] = "LOAD"

    face_rows: list[dict[str, Any]] = []
    for group in required:
        tri_all = np.asarray(surface_triangles[group], dtype=np.int64)
        if tri_all.ndim != 2 or tri_all.shape[1] != 6 or tri_all.shape[0] == 0:
            raise VisualModelPreparationError(f"surface {group} must contain TRI6 faces")
        if np.any(tri_all < 0) or np.any(tri_all >= nodes.shape[0]):
            raise VisualModelPreparationError(f"surface {group} contains invalid node indices")
        for conn in _sample_tri6(tri_all, max_faces_per_group):
            projected = _oblique_projection(nodes[conn[:3]])
            face_rows.append({"group": group, "role": role_map[group], "points": [[float(x), float(y)] for x, y in projected]})

    all_points = np.asarray([point for face in face_rows for point in face["points"]], dtype=float)
    low = all_points.min(axis=0)
    high = all_points.max(axis=0)
    span = high - low
    if np.any(span <= 0.0):
        raise VisualModelPreparationError("projection has zero visual span")
    for face in face_rows:
        pts = np.asarray(face["points"], dtype=float)
        normalized = (pts - low) / span
        face["points"] = [[float(x), float(y)] for x, y in normalized]

    hist_edges = np.linspace(0.0, 1.0, 6)
    hist_counts, _ = np.histogram(edge, bins=hist_edges)
    support_count = int(sum(np.asarray(surface_triangles[name]).shape[0] for name in support_keys))
    load_count = int(sum(np.asarray(surface_triangles[name]).shape[0] for name in load_keys))
    body_count = int(sum(np.asarray(surface_triangles[name]).shape[0] for name in required if role_map[name] == "BODY"))
    core = {
        "schema": "AsterMaxVisualModelPreparationV2" if named_selections is not None else "AsterMaxVisualModelPreparationV1",
        "step_sha256": str(preparation["step_sha256"]),
        "preparation_snapshot_sha256": str(preparation["snapshot_sha256"]),
        "constraint_selection_sha256": support_sha,
        "load_selection_sha256": load_sha,
        "support_surface_keys": support_keys,
        "load_surface_keys": load_keys,
        "support_tri6_count": support_count,
        "load_tri6_count": load_count,
        "body_tri6_count": body_count,
        "rendered_face_count": len(face_rows),
        "projection": "DETERMINISTIC_OBLIQUE_X_PLUS_0.35Y__Z_PLUS_0.20Y_NORMALIZED_FOR_DISPLAY",
        "projected_faces": tuple(face_rows),
        "jacobian_ip_count": int(det.size),
        "minimum_det_jacobian_mm3": float(np.min(det)),
        "median_det_jacobian_mm3": float(np.median(det)),
        "maximum_det_jacobian_mm3": float(np.max(det)),
        "edge_ratio_minimum": float(np.min(edge)),
        "edge_ratio_p10": float(np.percentile(edge, 10.0)),
        "edge_ratio_median": float(np.median(edge)),
        "edge_ratio_histogram_edges": tuple(float(v) for v in hist_edges),
        "edge_ratio_histogram_counts": tuple(int(v) for v in hist_counts),
        "quality_metric_boundary": "EDGE_RATIO_IS_SIMPLE_MIN_CORNER_EDGE_OVER_MAX_CORNER_EDGE_PROXY_NOT_ANSYS_ELEMENT_QUALITY_NOT_SCALED_JACOBIAN",
        "converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    return VisualModelPreparationSnapshot(**core, snapshot_sha256=canonical_sha256(core))


def install_visual_model_preparation_tab(notebook: Any) -> Callable[[dict[str, Any]], None]:
    import tkinter as tk
    from tkinter import ttk

    panel = ttk.Frame(notebook, padding=12)
    notebook.add(panel, text="Model Prep Inspector")
    panel.columnconfigure(0, weight=3)
    panel.columnconfigure(1, weight=2)
    panel.rowconfigure(2, weight=1)

    ttk.Label(panel, text="Visual Model Preparation Inspector", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
    ttk.Label(panel, text="Native diagnostic view of the exact reviewed named Support/Load TRI6 scopes plus mesh evidence. Edge ratio is a geometric proxy only, not ANSYS Element Quality.", wraplength=860).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 8))

    canvas = tk.Canvas(panel, background="#20252b", highlightthickness=1)
    canvas.grid(row=2, column=0, sticky="nsew", padx=(0, 10))
    info = tk.Text(panel, width=42, height=28, wrap="word", state="disabled")
    info.grid(row=2, column=1, sticky="nsew")

    def bind(payload: dict[str, Any]) -> None:
        snapshot = build_visual_model_preparation_snapshot(
            nodes_mm=np.asarray(payload["nodes_mm"], dtype=float),
            elements=np.asarray(payload["elements"], dtype=np.int64),
            surface_triangles={key: np.asarray(value, dtype=np.int64) for key, value in payload["surface_triangles"].items()},
            preparation=payload["preparation"],
            named_selections=payload.get("named_selections"),
        )
        canvas.delete("all")
        width = max(int(canvas.winfo_width()), 560)
        height = max(int(canvas.winfo_height()), 420)
        margin = 22.0
        role_style = {"BODY": ("#7f8b96", 1), "SUPPORT": ("#45a3ff", 3), "LOAD": ("#ff8a45", 3)}
        for face in snapshot.projected_faces:
            pts = []
            for x, y in face["points"]:
                pts.extend((margin + x * (width - 2 * margin), height - margin - y * (height - 2 * margin)))
            color, line_width = role_style[face["role"]]
            canvas.create_polygon(*pts, fill="", outline=color, width=line_width)
        support_label = ", ".join(snapshot.support_surface_keys)
        load_label = ", ".join(snapshot.load_surface_keys)
        canvas.create_text(12, 12, anchor="nw", fill="#45a3ff", text=f"SUPPORT · {support_label}")
        canvas.create_text(12, 30, anchor="nw", fill="#ff8a45", text=f"LOAD · {load_label}")
        canvas.create_text(12, 48, anchor="nw", fill="#c5ccd3", text="BODY · remaining axis surfaces")

        counts = snapshot.edge_ratio_histogram_counts
        edges = snapshot.edge_ratio_histogram_edges
        lines = [
            f"STEP\n{snapshot.step_sha256[:24]}…", "",
            f"Support · {support_label}\n{snapshot.constraint_selection_sha256[:24]}…",
            f"TRI6 faces: {snapshot.support_tri6_count}", "",
            f"Load · {load_label}\n{snapshot.load_selection_sha256[:24]}…",
            f"TRI6 faces: {snapshot.load_tri6_count}", "",
            "TET10 Jacobian distribution",
            f"IP samples: {snapshot.jacobian_ip_count}",
            f"min: {snapshot.minimum_det_jacobian_mm3:.3e} mm³",
            f"median: {snapshot.median_det_jacobian_mm3:.3e} mm³",
            f"max: {snapshot.maximum_det_jacobian_mm3:.3e} mm³", "",
            "Edge-ratio proxy (min edge / max edge)",
            f"min: {snapshot.edge_ratio_minimum:.3f}",
            f"p10: {snapshot.edge_ratio_p10:.3f}",
            f"median: {snapshot.edge_ratio_median:.3f}",
        ]
        for i, count in enumerate(counts):
            lines.append(f"[{edges[i]:.1f}, {edges[i+1]:.1f}]: {count}")
        lines.extend(["", "Boundary", "Not ANSYS Element Quality. Not scaled Jacobian. No arbitrary-model convergence claim.", f"Inspector SHA\n{snapshot.snapshot_sha256}"])
        info.configure(state="normal")
        info.delete("1.0", "end")
        info.insert("1.0", "\n".join(lines))
        info.configure(state="disabled")

    return bind
