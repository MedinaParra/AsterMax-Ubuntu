from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .results_workspace import (
    AsterMaxProfessionalResultsWorkspaceV1,
    deformed_coordinates_mm,
    probe_result,
)
from .solver import Tet10LinearStaticResult


@dataclass(frozen=True)
class ResultsRenderTriangleV1:
    element_id: int
    node_ids: tuple[int, int, int]
    projected_xy: tuple[tuple[float, float], tuple[float, float], tuple[float, float]]
    value: float


@dataclass(frozen=True)
class ResultsRenderPayloadV1:
    schema: str
    field: str
    unit: str
    workspace_sha256: str
    solve_evidence_sha256: str
    deformation_scale: float
    value_min: float
    value_max: float
    triangles: tuple[ResultsRenderTriangleV1, ...]
    projected_nodes_xy: tuple[tuple[float, float], ...]
    undeformed_nodes_xy: tuple[tuple[float, float], ...]


def _boundary_corner_faces(elements: np.ndarray) -> tuple[tuple[int, tuple[int, int, int]], ...]:
    elems = np.asarray(elements, dtype=np.int64)
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("RESULTS_UI_TET10_SHAPE")
    local_faces = ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3))
    seen: dict[tuple[int, int, int], tuple[int, tuple[int, int, int]] | None] = {}
    for element_id, tet in enumerate(elems):
        for local in local_faces:
            oriented = tuple(int(tet[i]) for i in local)
            key = tuple(sorted(oriented))
            if key in seen:
                seen[key] = None
            else:
                seen[key] = (int(element_id), oriented)
    return tuple(value for key, value in sorted(seen.items()) if value is not None)


def _project_oblique(nodes_mm: np.ndarray) -> np.ndarray:
    nodes = np.asarray(nodes_mm, dtype=float)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise ValueError("RESULTS_UI_NODES_SHAPE")
    return np.column_stack((nodes[:, 0] + 0.36 * nodes[:, 2], -nodes[:, 1] + 0.22 * nodes[:, 2]))


def build_results_render_payload(
    workspace: AsterMaxProfessionalResultsWorkspaceV1,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    result: Tet10LinearStaticResult,
    *,
    field: str,
    deformation_scale: float | None = None,
) -> ResultsRenderPayloadV1:
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    if nodes.shape != np.asarray(result.displacement_mm).shape:
        raise ValueError("RESULTS_UI_DISPLACEMENT_SHAPE")
    if workspace.node_count != int(nodes.shape[0]) or workspace.tet10_count != int(elems.shape[0]):
        raise ValueError("RESULTS_UI_WORKSPACE_MESH_STALE")
    scale = workspace.deformation_scale if deformation_scale is None else float(deformation_scale)
    if not math.isfinite(scale) or scale < 0.0:
        raise ValueError("RESULTS_UI_DEFORMATION_SCALE")

    deformed = deformed_coordinates_mm(nodes, result, scale)
    projected = _project_oblique(deformed)
    undeformed = _project_oblique(nodes)
    boundary = _boundary_corner_faces(elems)

    if field == "U_MAG":
        values = np.linalg.norm(np.asarray(result.displacement_mm, dtype=float), axis=1)
        unit = "mm"
        triangle_values = [float(np.mean(values[list(face)])) for _eid, face in boundary]
        value_min = float(np.min(values)) if values.size else 0.0
        value_max = float(np.max(values)) if values.size else 0.0
    elif field == "VON_MISES_IP_MAX":
        ip_vm = np.asarray(result.integration_point_von_mises_mpa, dtype=float)
        if ip_vm.shape != (elems.shape[0], 4):
            raise ValueError("RESULTS_UI_VM_IP_SHAPE")
        values = np.max(ip_vm, axis=1)
        unit = "MPa"
        triangle_values = [float(values[eid]) for eid, _face in boundary]
        value_min = float(np.min(values)) if values.size else 0.0
        value_max = float(np.max(values)) if values.size else 0.0
    else:
        raise ValueError("RESULTS_UI_UNKNOWN_FIELD")

    triangles = tuple(
        ResultsRenderTriangleV1(
            element_id=eid,
            node_ids=face,
            projected_xy=tuple((float(projected[nid, 0]), float(projected[nid, 1])) for nid in face),
            value=value,
        )
        for (eid, face), value in zip(boundary, triangle_values, strict=True)
    )
    return ResultsRenderPayloadV1(
        schema="AsterMaxResultsRenderPayloadV1",
        field=field,
        unit=unit,
        workspace_sha256=workspace.workspace_sha256,
        solve_evidence_sha256=workspace.solve_evidence_sha256,
        deformation_scale=scale,
        value_min=value_min,
        value_max=value_max,
        triangles=triangles,
        projected_nodes_xy=tuple((float(x), float(y)) for x, y in projected),
        undeformed_nodes_xy=tuple((float(x), float(y)) for x, y in undeformed),
    )


def _canvas_transform(points: np.ndarray, width: float, height: float, margin: float = 38.0) -> np.ndarray:
    if points.size == 0:
        return points.copy()
    low = np.min(points, axis=0)
    high = np.max(points, axis=0)
    span = np.maximum(high - low, 1.0e-12)
    sx = max(width - 2.0 * margin, 1.0) / span[0]
    sy = max(height - 2.0 * margin, 1.0) / span[1]
    scale = min(sx, sy)
    out = (points - low) * scale
    out[:, 0] += margin + 0.5 * max(width - 2.0 * margin - span[0] * scale, 0.0)
    out[:, 1] += margin + 0.5 * max(height - 2.0 * margin - span[1] * scale, 0.0)
    return out


def _scalar_hex(value: float, low: float, high: float) -> str:
    if not math.isfinite(value):
        return "#808080"
    t = 0.5 if high <= low else min(max((value - low) / (high - low), 0.0), 1.0)
    stops = (
        (0.00, (31, 78, 121)),
        (0.25, (46, 134, 171)),
        (0.50, (171, 221, 164)),
        (0.75, (253, 174, 97)),
        (1.00, (215, 25, 28)),
    )
    for (ta, ca), (tb, cb) in zip(stops[:-1], stops[1:], strict=True):
        if t <= tb:
            q = (t - ta) / (tb - ta)
            rgb = tuple(round(a + q * (b - a)) for a, b in zip(ca, cb, strict=True))
            return "#%02x%02x%02x" % rgb
    return "#d7191c"


def install_professional_results_tab(notebook):
    """Install a Tk-native result viewer and return a binder for solved TET10 data.

    The rendered field is always derived from the provenance-bound workspace and
    raw solver fields. Von Mises remains the explicit per-element maximum of the
    four integration-point values; no nodal stress smoothing is performed.
    """
    import tkinter as tk
    from tkinter import ttk

    frame = ttk.Frame(notebook, padding=10)
    notebook.add(frame, text="Results")
    toolbar = ttk.Frame(frame)
    toolbar.pack(fill="x")
    field_var = tk.StringVar(value="U_MAG")
    scale_var = tk.StringVar(value="1.0")
    overlay_var = tk.BooleanVar(value=True)
    legend_var = tk.StringVar(value="No solved result bound")
    probe_var = tk.StringVar(value="Click the result to probe raw solver-derived values.")
    ttk.Label(toolbar, text="Field").pack(side="left")
    field_box = ttk.Combobox(toolbar, textvariable=field_var, values=("U_MAG", "VON_MISES_IP_MAX"), state="readonly", width=22)
    field_box.pack(side="left", padx=(6, 14))
    ttk.Label(toolbar, text="Deformation scale").pack(side="left")
    scale_entry = ttk.Entry(toolbar, textvariable=scale_var, width=10)
    scale_entry.pack(side="left", padx=(6, 14))
    ttk.Checkbutton(toolbar, text="Undeformed overlay", variable=overlay_var).pack(side="left")
    canvas = tk.Canvas(frame, background="#111820", highlightthickness=0)
    canvas.pack(fill="both", expand=True, pady=(10, 6))
    ttk.Label(frame, textvariable=legend_var).pack(fill="x")
    ttk.Label(frame, textvariable=probe_var).pack(fill="x", pady=(3, 0))

    bound: dict[str, object] = {}

    def redraw(*_args) -> None:
        if not bound:
            return
        try:
            scale = float(scale_var.get())
            payload = build_results_render_payload(
                bound["workspace"], bound["nodes"], bound["elements"], bound["result"],
                field=field_var.get(), deformation_scale=scale,
            )
        except Exception as exc:
            probe_var.set(str(exc))
            return
        bound["payload"] = payload
        canvas.delete("all")
        width = max(float(canvas.winfo_width()), 600.0)
        height = max(float(canvas.winfo_height()), 420.0)
        points = np.asarray(payload.projected_nodes_xy, dtype=float)
        mapped = _canvas_transform(points, width, height)
        undeformed = _canvas_transform(np.asarray(payload.undeformed_nodes_xy, dtype=float), width, height)
        for tri in sorted(payload.triangles, key=lambda item: item.element_id, reverse=True):
            xy = [coord for nid in tri.node_ids for coord in mapped[nid]]
            canvas.create_polygon(*xy, fill=_scalar_hex(tri.value, payload.value_min, payload.value_max), outline="#253443")
        if overlay_var.get():
            for tri in payload.triangles:
                xy = [coord for nid in tri.node_ids for coord in undeformed[nid]]
                canvas.create_polygon(*xy, fill="", outline="#d7dde3", dash=(3, 3))
        legend_var.set(
            f"{payload.field} [{payload.unit}]  min={payload.value_min:.6g}  max={payload.value_max:.6g}  "
            f"scale={payload.deformation_scale:g}  workspace={payload.workspace_sha256[:12]}  solve={payload.solve_evidence_sha256[:12]}"
        )
        bound["mapped"] = mapped

    def click_probe(event) -> None:
        payload = bound.get("payload")
        mapped = bound.get("mapped")
        result = bound.get("result")
        workspace = bound.get("workspace")
        if payload is None or mapped is None or result is None or workspace is None:
            return
        point = np.asarray((float(event.x), float(event.y)))
        if payload.field == "U_MAG":
            distances = np.linalg.norm(np.asarray(mapped) - point, axis=1)
            entity_id = int(np.argmin(distances))
        else:
            centroids = np.asarray([np.mean(np.asarray(mapped)[list(tri.node_ids)], axis=0) for tri in payload.triangles])
            tri_index = int(np.argmin(np.linalg.norm(centroids - point, axis=1)))
            entity_id = payload.triangles[tri_index].element_id
        probe = probe_result(workspace, result, kind=payload.field, entity_id=entity_id)
        probe_var.set(f"Probe {probe.kind} · entity {probe.entity_id} · {probe.value:.9g} {probe.unit} · raw solver-derived semantics")

    canvas.bind("<Button-1>", click_probe)
    canvas.bind("<Configure>", redraw)
    field_box.bind("<<ComboboxSelected>>", redraw)
    scale_entry.bind("<Return>", redraw)
    overlay_var.trace_add("write", redraw)

    def bind_results(workspace, nodes_mm, elements, result) -> ResultsRenderPayloadV1:
        bound.clear()
        bound.update(workspace=workspace, nodes=np.asarray(nodes_mm), elements=np.asarray(elements), result=result)
        scale_var.set(str(workspace.deformation_scale))
        redraw()
        return bound["payload"]

    return bind_results
