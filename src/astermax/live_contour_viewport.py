from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np

from .persistent_viewport import extract_tet10_surface, project_surface
from .results_scene import normalized_scalar
from .solver_results_bridge import build_results_scene_from_desktop_summary
from . import windows_shell as _shell


@dataclass(frozen=True)
class ContourFrame:
    xy: np.ndarray
    triangles: np.ndarray
    triangle_scalar: np.ndarray
    scalar_min: float
    scalar_max: float
    deformation_scale: float
    stress_representation: str
    workspace_sha256: str
    solve_evidence_sha256: str


def build_contour_frame(summary: dict, *, deformation_scale: float = 1.0, yaw_deg: float = 35.0, pitch_deg: float = 25.0) -> ContourFrame:
    """Build the exact display frame consumed by the Windows canvas.

    Geometry comes from the real TET10 runtime mesh, displacement from the live
    solver result, and scalar stress from the explicitly labelled conservative
    display projection created by solver_results_bridge. Missing/stale evidence
    fails closed before any contour can be exposed.
    """
    scene, evidence = build_results_scene_from_desktop_summary(summary, deformation_scale=deformation_scale)
    runtime = summary["_runtime_results"]
    nodes = np.asarray(runtime["nodes_mm"], dtype=float)
    elements = np.asarray(runtime["elements"], dtype=int)
    _, triangles = extract_tet10_surface(type("Inventory", (), {"nodes_mm": nodes, "elements": elements})())
    xy, ordered = project_surface(scene.deformed_nodes_mm, triangles, yaw_deg=yaw_deg, pitch_deg=pitch_deg)
    nodal_norm = normalized_scalar(scene.von_mises_mpa)
    tri_scalar = nodal_norm[ordered].mean(axis=1)
    if not np.isfinite(tri_scalar).all():
        raise ValueError("LIVE_CONTOUR_NONFINITE_TRIANGLE_SCALAR")
    return ContourFrame(
        xy=xy,
        triangles=ordered,
        triangle_scalar=tri_scalar,
        scalar_min=scene.scalar_min,
        scalar_max=scene.scalar_max,
        deformation_scale=scene.deformation_scale,
        stress_representation=evidence.stress_representation,
        workspace_sha256=evidence.workspace_sha256,
        solve_evidence_sha256=evidence.solve_evidence_sha256,
    )


def scalar_hex(value: float) -> str:
    """Deterministic blue→cyan→yellow→red engineering contour palette."""
    if not math.isfinite(value):
        raise ValueError("LIVE_CONTOUR_SCALAR_NONFINITE")
    t = min(max(float(value), 0.0), 1.0)
    if t < 1/3:
        u = t * 3.0
        rgb = (0, int(round(255*u)), 255)
    elif t < 2/3:
        u = (t-1/3)*3.0
        rgb = (int(round(255*u)), 255, int(round(255*(1-u))))
    else:
        u = (t-2/3)*3.0
        rgb = (255, int(round(255*(1-u))), 0)
    return "#%02x%02x%02x" % rgb


def fit_xy(xy: np.ndarray, width: float, height: float, *, margin: float = 42.0, zoom: float = 1.0, pan=(0.0, 0.0)) -> np.ndarray:
    pts = np.asarray(xy, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2 or len(pts) == 0 or not np.isfinite(pts).all():
        raise ValueError("LIVE_CONTOUR_XY_INVALID")
    if width <= 2*margin or height <= 2*margin or not math.isfinite(zoom) or zoom <= 0:
        raise ValueError("LIVE_CONTOUR_VIEW_INVALID")
    mn = pts.min(axis=0); mx = pts.max(axis=0); span = np.maximum(mx-mn, 1e-12)
    scale = min((width-2*margin)/span[0], (height-2*margin)/span[1]) * zoom
    center = (mn+mx)/2.0
    out = (pts-center)*scale
    out[:,0] += width/2 + float(pan[0]); out[:,1] = height/2 - out[:,1] + float(pan[1])
    return out


def install_live_contour_patch() -> None:
    """Patch the verified Windows shell without duplicating its analysis pipeline."""
    cls = _shell.AsterMaxWindowsRoot
    if getattr(cls, "_c69_live_contour_installed", False):
        return
    original_init = cls.__init__
    original_publish_results = cls.publish_results
    original_render = cls._render_viewport

    def __init__(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._live_contour_summary = None
        self._live_contour_mode = "von_mises"
        self._live_deformation_scale = 1.0
        self._live_yaw_deg = 35.0
        self._live_pitch_deg = 25.0
        self._live_zoom = 1.0
        self._live_pan = [0.0, 0.0]
        self._live_drag = None
        self.after(100, self._install_c69_bindings)

    def _install_c69_bindings(self):
        canvas = getattr(self, "_viewport_canvas", None)
        if canvas is None:
            self.after(100, self._install_c69_bindings); return
        canvas.bind("<ButtonPress-1>", lambda e: setattr(self, "_live_drag", (e.x, e.y)))
        canvas.bind("<B1-Motion>", self._c69_orbit)
        canvas.bind("<MouseWheel>", self._c69_wheel)
        canvas.bind("<ButtonPress-2>", lambda e: setattr(self, "_live_drag", (e.x, e.y)))
        canvas.bind("<B2-Motion>", self._c69_pan)
        canvas.bind("<Double-Button-1>", lambda _e: self._c69_fit())

    def _c69_orbit(self, event):
        if self._live_drag is None: return
        x0,y0=self._live_drag; self._live_drag=(event.x,event.y)
        self._live_yaw_deg += (event.x-x0)*0.5
        self._live_pitch_deg = max(-89.0, min(89.0, self._live_pitch_deg+(event.y-y0)*0.5))
        self._render_viewport()

    def _c69_pan(self, event):
        if self._live_drag is None: return
        x0,y0=self._live_drag; self._live_drag=(event.x,event.y)
        self._live_pan[0] += event.x-x0; self._live_pan[1] += event.y-y0
        self._render_viewport()

    def _c69_wheel(self, event):
        factor = 1.12 if event.delta > 0 else 1/1.12
        self._live_zoom = max(0.1, min(20.0, self._live_zoom*factor))
        self._render_viewport()

    def _c69_fit(self):
        self._live_zoom=1.0; self._live_pan=[0.0,0.0]; self._render_viewport()

    def publish_results(self, summary):
        # Validate and cache live scene before marking it available in the UI.
        build_contour_frame(summary, deformation_scale=self._live_deformation_scale)
        self._live_contour_summary = summary
        return original_publish_results(self, summary)

    def _render_viewport(self, event=None):
        summary = getattr(self, "_live_contour_summary", None)
        canvas = getattr(self, "_viewport_canvas", None)
        if summary is None or canvas is None:
            return original_render(self, event)
        frame = build_contour_frame(summary, deformation_scale=self._live_deformation_scale, yaw_deg=self._live_yaw_deg, pitch_deg=self._live_pitch_deg)
        canvas.delete("all"); w=max(canvas.winfo_width(),320); h=max(canvas.winfo_height(),180)
        pts=fit_xy(frame.xy,w,h,zoom=self._live_zoom,pan=self._live_pan)
        for tri, scalar in zip(frame.triangles, frame.triangle_scalar):
            coords=[]
            for node in tri: coords.extend((float(pts[node,0]),float(pts[node,1])))
            canvas.create_polygon(*coords, fill=scalar_hex(float(scalar)), outline="#303030", width=1)
        # Compact evidence-bound legend.
        x0=w-34; y0=48; y1=max(88,h-70); n=36
        for i in range(n):
            t=i/(n-1); ya=y1-(y1-y0)*i/n; yb=y1-(y1-y0)*(i+1)/n
            canvas.create_rectangle(x0,ya,x0+14,yb,fill=scalar_hex(t),outline=scalar_hex(t))
        canvas.create_text(x0-4,y0,anchor="e",text=f"{frame.scalar_max:.4g} MPa")
        canvas.create_text(x0-4,y1,anchor="e",text=f"{frame.scalar_min:.4g} MPa")
        canvas.create_text(12,10,anchor="nw",text="Von Mises · live solver contour",font=("Segoe UI",10,"bold"))
        canvas.create_text(12,29,anchor="nw",text=f"deformation scale ×{frame.deformation_scale:g} · mm / MPa")
        canvas.create_text(12,h-12,anchor="sw",text=frame.stress_representation,font=("Segoe UI",8))
        canvas.create_text(w-12,10,anchor="ne",text="Evidence: VERIFIED",font=("Segoe UI",9,"bold"))

    cls.__init__ = __init__
    cls._install_c69_bindings = _install_c69_bindings
    cls._c69_orbit = _c69_orbit
    cls._c69_pan = _c69_pan
    cls._c69_wheel = _c69_wheel
    cls._c69_fit = _c69_fit
    cls.publish_results = publish_results
    cls._render_viewport = _render_viewport
    cls._c69_live_contour_installed = True


def windows_desktop_main() -> int:
    install_live_contour_patch()
    return _shell.windows_desktop_main()
