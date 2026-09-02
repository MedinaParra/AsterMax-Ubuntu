from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .cae_scene_contract import CaeSceneContract, build_cae_scene_contract
from .persistent_viewport import project_surface
from .live_contour_viewport import fit_xy, install_live_contour_patch, scalar_hex
from . import windows_shell as _shell


@dataclass(frozen=True)
class CachedContourData:
    scene: CaeSceneContract
    triangle_scalar_by_key: dict[tuple[int, int, int], float]


def build_cached_contour_data(summary: dict, *, deformation_scale: float = 1.0) -> CachedContourData:
    """Perform solver/evidence/surface work once per published solve, not per mouse event."""
    scene = build_cae_scene_contract(summary, deformation_scale=deformation_scale)
    scalar_map = {
        tuple(int(v) for v in tri): float(s)
        for tri, s in zip(scene.surface_triangles, scene.triangle_scalar_normalized)
    }
    return CachedContourData(scene=scene, triangle_scalar_by_key=scalar_map)


def project_cached_contour(data: CachedContourData, *, yaw_deg: float, pitch_deg: float):
    """Interaction hot path: only rotate/project verified deformed coordinates."""
    xy, ordered = project_surface(
        data.scene.deformed_nodes_mm,
        data.scene.surface_triangles,
        yaw_deg=yaw_deg,
        pitch_deg=pitch_deg,
    )
    scalars = np.asarray([
        data.triangle_scalar_by_key[tuple(int(v) for v in tri)]
        for tri in ordered
    ], dtype=float)
    return xy, ordered, scalars


def install_fast_contour_patch() -> None:
    """Coalesce mouse events and cache CAE result preparation for the Tk fallback renderer."""
    install_live_contour_patch()
    cls = _shell.AsterMaxWindowsRoot
    if getattr(cls, "_c71_fast_contour_installed", False):
        return

    original_init = cls.__init__
    original_publish_results = cls.publish_results
    original_render = cls._render_viewport

    def __init__(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._c71_cached_contour = None
        self._c71_projected = None
        self._c71_orientation = None
        self._c71_render_pending = False

    def _c71_schedule_render(self):
        if self._c71_render_pending:
            return
        self._c71_render_pending = True
        self.after(16, self._c71_flush_render)

    def _c71_flush_render(self):
        self._c71_render_pending = False
        self._render_viewport()

    def _c69_orbit(self, event):
        if self._live_drag is None:
            return
        x0, y0 = self._live_drag
        self._live_drag = (event.x, event.y)
        self._live_yaw_deg += (event.x - x0) * 0.5
        self._live_pitch_deg = max(-89.0, min(89.0, self._live_pitch_deg + (event.y - y0) * 0.5))
        self._c71_schedule_render()

    def _c69_pan(self, event):
        if self._live_drag is None:
            return
        x0, y0 = self._live_drag
        self._live_drag = (event.x, event.y)
        self._live_pan[0] += event.x - x0
        self._live_pan[1] += event.y - y0
        self._c71_schedule_render()

    def _c69_wheel(self, event):
        factor = 1.12 if event.delta > 0 else 1 / 1.12
        self._live_zoom = max(0.1, min(20.0, self._live_zoom * factor))
        self._c71_schedule_render()

    def publish_results(self, summary):
        # Build/validate once. Missing or stale provenance still fails closed here.
        cached = build_cached_contour_data(summary, deformation_scale=self._live_deformation_scale)
        self._c71_cached_contour = cached
        self._c71_projected = None
        self._c71_orientation = None
        return original_publish_results(self, summary)

    def _render_viewport(self, event=None):
        data = getattr(self, "_c71_cached_contour", None)
        canvas = getattr(self, "_viewport_canvas", None)
        if data is None or canvas is None:
            return original_render(self, event)

        orientation = (float(self._live_yaw_deg), float(self._live_pitch_deg))
        if self._c71_projected is None or self._c71_orientation != orientation:
            self._c71_projected = project_cached_contour(
                data, yaw_deg=orientation[0], pitch_deg=orientation[1]
            )
            self._c71_orientation = orientation
        xy, triangles, tri_scalar = self._c71_projected

        canvas.delete("all")
        w = max(canvas.winfo_width(), 320)
        h = max(canvas.winfo_height(), 180)
        pts = fit_xy(xy, w, h, zoom=self._live_zoom, pan=self._live_pan)
        for tri, scalar in zip(triangles, tri_scalar):
            coords = []
            for node in tri:
                coords.extend((float(pts[node, 0]), float(pts[node, 1])))
            canvas.create_polygon(*coords, fill=scalar_hex(float(scalar)), outline="#303030", width=1)

        scene = data.scene
        x0 = w - 34
        y0 = 48
        y1 = max(88, h - 70)
        n = 36
        for i in range(n):
            t = i / (n - 1)
            ya = y1 - (y1 - y0) * i / n
            yb = y1 - (y1 - y0) * (i + 1) / n
            c = scalar_hex(t)
            canvas.create_rectangle(x0, ya, x0 + 14, yb, fill=c, outline=c)
        canvas.create_text(x0 - 4, y0, anchor="e", text=f"{scene.scalar_max_mpa:.4g} MPa")
        canvas.create_text(x0 - 4, y1, anchor="e", text=f"{scene.scalar_min_mpa:.4g} MPa")
        canvas.create_text(12, 10, anchor="nw", text="Von Mises · cached live solver contour", font=("Segoe UI", 10, "bold"))
        canvas.create_text(12, 29, anchor="nw", text=f"deformation scale ×{scene.deformation_scale:g} · mm / MPa")
        canvas.create_text(12, h - 12, anchor="sw", text=scene.stress_representation, font=("Segoe UI", 8))
        canvas.create_text(w - 12, 10, anchor="ne", text="Evidence: VERIFIED · interaction cache", font=("Segoe UI", 9, "bold"))

    cls.__init__ = __init__
    cls._c71_schedule_render = _c71_schedule_render
    cls._c71_flush_render = _c71_flush_render
    cls._c69_orbit = _c69_orbit
    cls._c69_pan = _c69_pan
    cls._c69_wheel = _c69_wheel
    cls.publish_results = publish_results
    cls._render_viewport = _render_viewport
    cls._c71_fast_contour_installed = True


def windows_desktop_main() -> int:
    install_fast_contour_patch()
    return _shell.windows_desktop_main()
