from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Any

from .integrated_workspace import (
    assert_workspace_does_not_upgrade_claims,
    build_integrated_workspace,
)
from .native_vtu_preview import (
    assert_native_preview_claim_boundary,
    load_native_vtu_preview,
    projected_preview_geometry,
)


def create_workspace_widget(parent, ttk):
    """Create native engineering tabs and return their update callback.

    Results contains a lightweight native projection of the actual hash-verified
    VTU. The full offline viewer remains available as a verified artifact; this
    widget does not claim a full interactive 3D CAE renderer.
    """
    import tkinter as tk

    notebook = ttk.Notebook(parent)
    frames: dict[str, Any] = {}
    state_vars: dict[str, Any] = {}
    detail_vars: dict[str, Any] = {}
    open_buttons: dict[str, Any] = {}
    artifacts: dict[str, str | None] = {}
    results_canvas = None
    results_caption = None
    results_preview = {"data": None, "scale": 0.0}

    def render_native_results() -> None:
        nonlocal results_canvas, results_caption
        if results_canvas is None or results_caption is None:
            return
        canvas = results_canvas
        canvas.delete("all")
        data = results_preview["data"]
        if data is None:
            canvas.create_text(310, 170, text="No verified VTU loaded", anchor="center")
            results_caption.set("Native preview unavailable until a hash-verified solve result exists.")
            return

        points2d, scalar = projected_preview_geometry(data, deformation_scale=float(results_preview["scale"]))
        if points2d.size == 0:
            results_caption.set("Verified VTU contains no points.")
            return
        xmin, ymin = points2d.min(axis=0)
        xmax, ymax = points2d.max(axis=0)
        span = max(float(xmax - xmin), float(ymax - ymin), 1.0e-12)
        margin = 28.0
        factor = min((620.0 - 2.0 * margin) / span, (340.0 - 2.0 * margin) / span)
        xy = (points2d - [xmin, ymin]) * factor + margin
        xy[:, 1] = 340.0 - xy[:, 1]

        edges = ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))
        for conn in data.tet10_connectivity:
            corners = conn[:4]
            for a, b in edges:
                pa = xy[int(corners[a])]
                pb = xy[int(corners[b])]
                canvas.create_line(float(pa[0]), float(pa[1]), float(pb[0]), float(pb[1]), width=1)

        mode = "DEFORMED 1x" if float(results_preview["scale"]) else "UNDEFORMED"
        vm_min = float(scalar.min()) if scalar.size else 0.0
        vm_max = float(scalar.max()) if scalar.size else 0.0
        results_caption.set(
            f"{mode} · hash-verified VTU · {data.points_mm.shape[0]} nodes / "
            f"{data.tet10_connectivity.shape[0]} TET10 · element IP-max von Mises range "
            f"{vm_min:.3g}–{vm_max:.3g} MPa · no nodal stress smoothing"
        )

    def set_result_scale(scale: float) -> None:
        results_preview["scale"] = float(scale)
        render_native_results()

    for panel in build_integrated_workspace():
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text=panel.label)
        frames[panel.key] = frame

        state_var = tk.StringVar(value=panel.state)
        detail_var = tk.StringVar(value=panel.detail)
        state_vars[panel.key] = state_var
        detail_vars[panel.key] = detail_var
        ttk.Label(frame, textvariable=state_var, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(frame, textvariable=detail_var, wraplength=720).pack(anchor="w", fill="x", pady=(4, 8))

        if panel.key == "results":
            toolbar = ttk.Frame(frame)
            toolbar.pack(anchor="w", fill="x", pady=(0, 6))
            ttk.Button(toolbar, text="Undeformed", command=lambda: set_result_scale(0.0)).pack(side="left")
            ttk.Button(toolbar, text="Deformed 1x", command=lambda: set_result_scale(1.0)).pack(side="left", padx=(6, 0))
            results_canvas = tk.Canvas(frame, width=620, height=340, highlightthickness=1)
            results_canvas.pack(anchor="w", fill="both", expand=True)
            results_caption = tk.StringVar(value="No verified VTU loaded.")
            ttk.Label(frame, textvariable=results_caption, wraplength=720).pack(anchor="w", fill="x", pady=(6, 8))

        def open_artifact(key=panel.key) -> None:
            artifact = artifacts.get(key)
            if artifact and Path(artifact).is_file():
                webbrowser.open(Path(artifact).resolve().as_uri())

        button = ttk.Button(frame, text="Open verified artifact", command=open_artifact, state="disabled")
        button.pack(anchor="w")
        open_buttons[panel.key] = button

    def update(summary: dict | None = None) -> None:
        panels = build_integrated_workspace(summary)
        if summary is not None:
            assert_workspace_does_not_upgrade_claims(summary, panels)
        for panel in panels:
            state_vars[panel.key].set(panel.state)
            detail_vars[panel.key].set(panel.detail)
            artifacts[panel.key] = panel.artifact
            enabled = bool(panel.artifact and Path(panel.artifact).is_file())
            open_buttons[panel.key].configure(state="normal" if enabled else "disabled")

        results_preview["data"] = None
        if summary is not None:
            artifact_map = summary.get("artifacts", {})
            vtu_path = artifact_map.get("vtu")
            vtu_sha = artifact_map.get("vtu_sha256")
            if vtu_path and vtu_sha:
                data = load_native_vtu_preview(vtu_path, expected_sha256=vtu_sha)
                assert_native_preview_claim_boundary(data)
                results_preview["data"] = data
        render_native_results()

    return notebook, update
