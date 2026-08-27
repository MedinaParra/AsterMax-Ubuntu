from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Any

from .integrated_workspace import (
    assert_workspace_does_not_upgrade_claims,
    build_integrated_workspace,
)
from .native_viewport import (
    assert_native_viewport_claim_boundary,
    viewport_geometry,
)
from .native_vtu_preview import (
    assert_native_preview_claim_boundary,
    load_native_vtu_preview,
)


def create_workspace_widget(parent, ttk):
    """Create native engineering tabs and return their update callback.

    Results V2 renders only the external TET10 skin from the actual hash-verified
    VTU, supports deterministic orbit controls and deformation scale, and uses
    flat owner-element IP-max von Mises color without inventing nodal smoothing.
    The full offline viewer remains available as a verified artifact.
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
    results_preview = {"data": None, "scale": 0.0, "azimuth": 35.0, "elevation": 25.0}

    def scalar_color(value: float, minimum: float, maximum: float) -> str:
        """Small deterministic blue-to-red flat-face palette for element data."""
        if maximum <= minimum:
            t = 0.5
        else:
            t = max(0.0, min(1.0, (float(value) - minimum) / (maximum - minimum)))
        r = int(45 + 200 * t)
        g = int(95 + 70 * (1.0 - abs(2.0 * t - 1.0)))
        b = int(220 - 185 * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    def render_native_results() -> None:
        nonlocal results_canvas, results_caption
        if results_canvas is None or results_caption is None:
            return
        canvas = results_canvas
        canvas.delete("all")
        data = results_preview["data"]
        if data is None:
            canvas.create_text(360, 190, text="No verified VTU loaded", anchor="center")
            results_caption.set("Native viewport unavailable until a hash-verified solve result exists.")
            return

        points2d, depth, surface = viewport_geometry(
            data,
            deformation_scale=float(results_preview["scale"]),
            azimuth_deg=float(results_preview["azimuth"]),
            elevation_deg=float(results_preview["elevation"]),
        )
        if points2d.size == 0:
            results_caption.set("Verified VTU contains no points.")
            return
        xmin, ymin = points2d.min(axis=0)
        xmax, ymax = points2d.max(axis=0)
        span_x = max(float(xmax - xmin), 1.0e-12)
        span_y = max(float(ymax - ymin), 1.0e-12)
        margin = 30.0
        factor = min((720.0 - 2.0 * margin) / span_x, (380.0 - 2.0 * margin) / span_y)
        xy = (points2d - [xmin, ymin]) * factor + margin
        xy[:, 1] = 380.0 - xy[:, 1]

        scalar = surface.owner_von_mises_ip_max_mpa
        vm_min = float(scalar.min()) if scalar.size else 0.0
        vm_max = float(scalar.max()) if scalar.size else 0.0
        order = sorted(
            range(surface.tri6_connectivity.shape[0]),
            key=lambda i: float(depth[surface.tri6_connectivity[i, :3]].mean()),
        )
        for face_index in order:
            face = surface.tri6_connectivity[face_index]
            corners = face[:3]
            polygon = []
            for node in corners:
                polygon.extend((float(xy[int(node), 0]), float(xy[int(node), 1])))
            fill = scalar_color(float(scalar[face_index]), vm_min, vm_max)
            canvas.create_polygon(*polygon, fill=fill, outline="")
            # Preserve TRI6 curvature topology in the wire overlay by traversing
            # each corner-edge through its midside node.
            for a, mid, b in ((0, 3, 1), (1, 4, 2), (2, 5, 0)):
                pa = xy[int(face[a])]
                pm = xy[int(face[mid])]
                pb = xy[int(face[b])]
                canvas.create_line(float(pa[0]), float(pa[1]), float(pm[0]), float(pm[1]), width=1)
                canvas.create_line(float(pm[0]), float(pm[1]), float(pb[0]), float(pb[1]), width=1)

        scale = float(results_preview["scale"])
        mode = "UNDEFORMED" if scale == 0.0 else f"DEFORMED {scale:g}x"
        results_caption.set(
            f"{mode} · external TRI6 skin {surface.tri6_connectivity.shape[0]} faces · "
            f"orbit az={results_preview['azimuth']:.0f}° el={results_preview['elevation']:.0f}° · "
            f"hash-verified VTU · {data.points_mm.shape[0]} nodes / "
            f"{data.tet10_connectivity.shape[0]} TET10 · flat owner-element IP-max von Mises "
            f"{vm_min:.3g}–{vm_max:.3g} MPa · no nodal stress smoothing"
        )

    def set_result_scale(scale: float) -> None:
        results_preview["scale"] = float(scale)
        render_native_results()

    def orbit(delta_azimuth: float = 0.0, delta_elevation: float = 0.0) -> None:
        results_preview["azimuth"] = (float(results_preview["azimuth"]) + float(delta_azimuth)) % 360.0
        results_preview["elevation"] = max(
            -85.0, min(85.0, float(results_preview["elevation"]) + float(delta_elevation))
        )
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
        ttk.Label(frame, textvariable=detail_var, wraplength=820).pack(anchor="w", fill="x", pady=(4, 8))

        if panel.key == "results":
            toolbar = ttk.Frame(frame)
            toolbar.pack(anchor="w", fill="x", pady=(0, 6))
            ttk.Button(toolbar, text="Undeformed", command=lambda: set_result_scale(0.0)).pack(side="left")
            ttk.Button(toolbar, text="Deformed 1x", command=lambda: set_result_scale(1.0)).pack(side="left", padx=(6, 0))
            ttk.Button(toolbar, text="Deformed 10x", command=lambda: set_result_scale(10.0)).pack(side="left", padx=(6, 12))
            ttk.Button(toolbar, text="◀ Orbit", command=lambda: orbit(delta_azimuth=-15.0)).pack(side="left")
            ttk.Button(toolbar, text="Orbit ▶", command=lambda: orbit(delta_azimuth=15.0)).pack(side="left", padx=(4, 0))
            ttk.Button(toolbar, text="Elev +", command=lambda: orbit(delta_elevation=10.0)).pack(side="left", padx=(12, 0))
            ttk.Button(toolbar, text="Elev -", command=lambda: orbit(delta_elevation=-10.0)).pack(side="left", padx=(4, 0))
            results_canvas = tk.Canvas(frame, width=720, height=380, highlightthickness=1)
            results_canvas.pack(anchor="w", fill="both", expand=True)
            results_caption = tk.StringVar(value="No verified VTU loaded.")
            ttk.Label(frame, textvariable=results_caption, wraplength=820).pack(anchor="w", fill="x", pady=(6, 8))

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
                assert_native_viewport_claim_boundary(data)
                results_preview["data"] = data
        render_native_results()

    return notebook, update
