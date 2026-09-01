"""AsterMax CAE workspace for Windows.

Professional shell goals:
- central, dominant 3D CAD workspace;
- ribbon-style commands across the top;
- operation/model tree on the left;
- always-visible engineering agent panel on the right;
- immediate STEP preview after the explicit millimetre trust gate.

The preview is deliberately independent from the analysis mesh and solver.  It is
a visualization tessellation only; verified FEA remains in windows_app.py.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import subprocess
import tempfile
import threading
from typing import Iterable

from .windows_app import WindowsAppError, find_gmsh_for_windows, validate_step_mm_file


@dataclass(frozen=True)
class PreviewMesh:
    nodes: tuple[tuple[float, float, float], ...]
    triangles: tuple[tuple[int, int, int], ...]


class PreviewError(RuntimeError):
    pass


def _parse_msh2_surface(text: str) -> PreviewMesh:
    """Parse nodes/TRI3 from a Gmsh v2 ASCII preview mesh.

    The function is intentionally tiny and independent from the solver mesh
    adapter because preview meshes may contain no tetrahedra or Physical Groups.
    """
    lines = [line.strip() for line in text.splitlines()]
    try:
        ni = lines.index("$Nodes")
        ne = lines.index("$EndNodes")
        ei = lines.index("$Elements")
        ee = lines.index("$EndElements")
    except ValueError as exc:
        raise PreviewError("preview mesh is not valid Gmsh v2 ASCII") from exc

    try:
        ncount = int(lines[ni + 1])
    except (IndexError, ValueError) as exc:
        raise PreviewError("invalid preview node count") from exc
    node_rows = lines[ni + 2:ne]
    if len(node_rows) != ncount:
        raise PreviewError("preview node count does not match file")
    id_to_xyz: dict[int, tuple[float, float, float]] = {}
    for row in node_rows:
        parts = row.split()
        if len(parts) != 4:
            raise PreviewError("invalid preview node row")
        try:
            nid = int(parts[0]); xyz = (float(parts[1]), float(parts[2]), float(parts[3]))
        except ValueError as exc:
            raise PreviewError("invalid numeric preview node data") from exc
        if not all(math.isfinite(v) for v in xyz):
            raise PreviewError("non-finite preview coordinate")
        id_to_xyz[nid] = xyz

    try:
        ecount = int(lines[ei + 1])
    except (IndexError, ValueError) as exc:
        raise PreviewError("invalid preview element count") from exc
    elem_rows = lines[ei + 2:ee]
    if len(elem_rows) != ecount:
        raise PreviewError("preview element count does not match file")

    tri_ids: list[tuple[int, int, int]] = []
    used: set[int] = set()
    for row in elem_rows:
        p = row.split()
        if len(p) < 4:
            continue
        try:
            etype = int(p[1]); ntags = int(p[2])
        except ValueError:
            continue
        if etype != 2:  # linear TRI3 only
            continue
        start = 3 + ntags
        if len(p) < start + 3:
            raise PreviewError("invalid TRI3 preview row")
        tri = tuple(int(v) for v in p[start:start + 3])
        if any(n not in id_to_xyz for n in tri):
            raise PreviewError("preview triangle references missing node")
        tri_ids.append(tri)  # type: ignore[arg-type]
        used.update(tri)
    if not tri_ids:
        raise PreviewError("STEP preview contains no TRI3 surface elements")

    ordered_ids = sorted(used)
    remap = {nid: i for i, nid in enumerate(ordered_ids)}
    nodes = tuple(id_to_xyz[nid] for nid in ordered_ids)
    triangles = tuple((remap[a], remap[b], remap[c]) for a, b, c in tri_ids)
    return PreviewMesh(nodes, triangles)


def build_step_preview(step_path: str | Path, *, gmsh_executable: str | None = None) -> PreviewMesh:
    """Create a surface-only visualization tessellation for a verified-mm STEP file."""
    source = Path(step_path)
    validate_step_mm_file(source)
    gmsh = find_gmsh_for_windows(gmsh_executable)
    with tempfile.TemporaryDirectory(prefix="astermax_preview_") as td:
        out = Path(td) / "preview.msh"
        completed = subprocess.run(
            [gmsh, str(source), "-2", "-format", "msh2", "-o", str(out), "-v", "1"],
            capture_output=True, text=True, check=False,
        )
        if completed.returncode != 0 or not out.is_file():
            detail = (completed.stderr or completed.stdout or "Gmsh preview failed").strip()
            raise PreviewError(detail[-1000:])
        return _parse_msh2_surface(out.read_text(encoding="utf-8", errors="strict"))


class TkSurfaceViewport:
    """Lightweight interactive TRI3 viewport using the Tk Canvas.

    This is a PMV CAD preview, not the long-term GPU renderer.  It keeps the
    executable dependency-light while proving the desired workspace UX.
    """
    def __init__(self, canvas, *, bg: str, edge: str, face: str, text: str):
        self.canvas = canvas
        self.bg, self.edge, self.face, self.text = bg, edge, face, text
        self.mesh: PreviewMesh | None = None
        self.yaw = -0.65
        self.pitch = 0.45
        self.zoom = 1.0
        self._last = None
        canvas.bind("<Configure>", lambda e: self.draw())
        canvas.bind("<ButtonPress-1>", self._press)
        canvas.bind("<B1-Motion>", self._drag)
        canvas.bind("<MouseWheel>", self._wheel)
        self.draw()

    def _press(self, event): self._last = (event.x, event.y)
    def _drag(self, event):
        if self._last is None: return
        dx, dy = event.x - self._last[0], event.y - self._last[1]
        self._last = (event.x, event.y)
        self.yaw += dx * 0.008; self.pitch += dy * 0.008
        self.draw()
    def _wheel(self, event):
        self.zoom *= 1.12 if event.delta > 0 else 1 / 1.12
        self.zoom = max(0.15, min(8.0, self.zoom)); self.draw()

    def set_mesh(self, mesh: PreviewMesh | None):
        self.mesh = mesh; self.zoom = 1.0; self.draw()

    def fit(self): self.zoom = 1.0; self.draw()

    def _rot(self, p):
        x, y, z = p
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        x1, z1 = cy*x + sy*z, -sy*x + cy*z
        y2, z2 = cp*y - sp*z1, sp*y + cp*z1
        return (x1, y2, z2)

    def draw(self):
        c = self.canvas; c.delete("all")
        w, h = max(c.winfo_width(), 2), max(c.winfo_height(), 2)
        if not self.mesh:
            c.create_text(w/2, h/2-15, text="3D WORKSPACE", fill=self.text, font=("Segoe UI Semibold", 20))
            c.create_text(w/2, h/2+18, text="Import a STEP model to begin", fill="#7F8B99", font=("Segoe UI", 10))
            return
        pts = self.mesh.nodes
        cx = sum(p[0] for p in pts)/len(pts); cy = sum(p[1] for p in pts)/len(pts); cz = sum(p[2] for p in pts)/len(pts)
        centered = [(p[0]-cx, p[1]-cy, p[2]-cz) for p in pts]
        rotated = [self._rot(p) for p in centered]
        span = max(max(abs(q[i]) for q in rotated) for i in range(3)) or 1.0
        scale = 0.42 * min(w, h) / span * self.zoom
        screen = [(w/2 + q[0]*scale, h/2 - q[1]*scale, q[2]) for q in rotated]
        tris = []
        for tri in self.mesh.triangles:
            a,b,d = (screen[i] for i in tri); depth=(a[2]+b[2]+d[2])/3
            tris.append((depth, tri))
        tris.sort(key=lambda item: item[0])
        # Cap display work for pathological CAD previews while keeping full mesh metadata.
        stride = max(1, len(tris)//18000)
        for _, tri in tris[::stride]:
            xy=[]
            for i in tri: xy.extend((screen[i][0], screen[i][1]))
            c.create_polygon(*xy, fill=self.face, outline=self.edge, width=1)
        c.create_text(14, 14, anchor="nw", text=f"CAD PREVIEW  •  {len(pts):,} nodes  •  {len(self.mesh.triangles):,} TRI3", fill="#9AA8B7", font=("Segoe UI", 9))
        c.create_text(14, h-14, anchor="sw", text="LMB drag: orbit   •   wheel: zoom   •   preview tessellation ≠ FEA mesh", fill="#708091", font=("Segoe UI", 9))


def launch_desktop() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    BG="#0C1015"; PANEL="#111820"; RIBBON="#151D26"; BORDER="#26313D"; TEXT="#EDF3F8"; MUTED="#8291A2"; ACCENT="#27A8FF"; FACE="#23384A"; EDGE="#3A607A"
    root=tk.Tk(); root.title("AsterMax — CAE Engineering Workspace"); root.geometry("1600x960"); root.minsize(1200,760); root.configure(bg=BG)
    style=ttk.Style(root)
    try: style.theme_use("clam")
    except tk.TclError: pass
    style.configure("TFrame",background=BG); style.configure("Ribbon.TFrame",background=RIBBON); style.configure("Panel.TFrame",background=PANEL)
    style.configure("TLabel",background=BG,foreground=TEXT,font=("Segoe UI",10)); style.configure("Panel.TLabel",background=PANEL,foreground=TEXT)
    style.configure("Muted.TLabel",background=BG,foreground=MUTED); style.configure("Ribbon.TLabel",background=RIBBON,foreground=TEXT)
    style.configure("Ribbon.TButton",background=RIBBON,foreground=TEXT,padding=(14,8),borderwidth=0); style.map("Ribbon.TButton",background=[("active","#22303D")])
    style.configure("Accent.TButton",background=ACCENT,foreground="white",padding=(15,9),borderwidth=0,font=("Segoe UI Semibold",10))
    style.configure("Treeview",background=PANEL,fieldbackground=PANEL,foreground=TEXT,borderwidth=0,rowheight=27); style.map("Treeview",background=[("selected","#1C5C85")])
    style.configure("Treeview.Heading",background=RIBBON,foreground=TEXT)

    state={"step":None,"preview":None,"analysis":False}
    status=tk.StringVar(value="Ready")

    # Ribbon tabs + command band
    title=tk.Frame(root,bg="#090D11",height=34); title.pack(fill="x"); title.pack_propagate(False)
    tk.Label(title,text="ASTERMAX",fg="white",bg="#090D11",font=("Segoe UI Black",13)).pack(side="left",padx=(14,8))
    tk.Label(title,text="CAE ENGINEERING WORKSPACE",fg=MUTED,bg="#090D11",font=("Segoe UI",9)).pack(side="left")
    tk.Label(title,text="mm · N · MPa",fg=MUTED,bg="#090D11",font=("Segoe UI",9)).pack(side="right",padx=14)
    tabbar=tk.Frame(root,bg=RIBBON,height=30); tabbar.pack(fill="x"); tabbar.pack_propagate(False)
    for name in ("File","Geometry","Model","Connections","Mesh","Analysis","Results","Automation"):
        tk.Label(tabbar,text=name,fg=TEXT,bg=RIBBON,font=("Segoe UI",9),padx=13,pady=6).pack(side="left")
    commands=ttk.Frame(root,style="Ribbon.TFrame",padding=(8,7)); commands.pack(fill="x")

    body=tk.PanedWindow(root,orient="horizontal",sashwidth=5,bg=BORDER,bd=0); body.pack(fill="both",expand=True)
    left=tk.Frame(body,bg=PANEL,width=255); center=tk.Frame(body,bg=BG); right=tk.Frame(body,bg=PANEL,width=320)
    body.add(left,minsize=205); body.add(center,minsize=600); body.add(right,minsize=250)

    tk.Label(left,text="MODEL",fg=MUTED,bg=PANEL,font=("Segoe UI Semibold",9),anchor="w").pack(fill="x",padx=12,pady=(12,5))
    tree=ttk.Treeview(left,show="tree",selectmode="browse"); tree.pack(fill="both",expand=True,padx=4,pady=(0,6))
    model=tree.insert("","end",text="▾ Model",open=True); geom=tree.insert(model,"end",text="  Geometry  [empty]"); mats=tree.insert(model,"end",text="  Materials")
    meshnode=tree.insert(model,"end",text="  Mesh"); tree.insert(model,"end",text="  Named Selections")

    viewport_canvas=tk.Canvas(center,bg=BG,highlightthickness=0); viewport_canvas.pack(fill="both",expand=True)
    viewport=TkSurfaceViewport(viewport_canvas,bg=BG,edge=EDGE,face=FACE,text=TEXT)
    statusbar=tk.Frame(center,bg="#0A0E12",height=28); statusbar.pack(fill="x"); statusbar.pack_propagate(False)
    tk.Label(statusbar,textvariable=status,fg=MUTED,bg="#0A0E12",font=("Segoe UI",9)).pack(side="left",padx=10)
    tk.Label(statusbar,text="CAD preview • analysis evidence remains solver-controlled",fg=MUTED,bg="#0A0E12",font=("Segoe UI",9)).pack(side="right",padx=10)

    tk.Label(right,text="ASTERMAX AI",fg=TEXT,bg=PANEL,font=("Segoe UI Semibold",11),anchor="w").pack(fill="x",padx=12,pady=(12,2))
    tk.Label(right,text="Engineering copilot / case context",fg=MUTED,bg=PANEL,font=("Segoe UI",9),anchor="w").pack(fill="x",padx=12,pady=(0,8))
    chat=tk.Text(right,bg="#0D1319",fg=TEXT,insertbackground=TEXT,relief="flat",wrap="word",font=("Segoe UI",9),state="disabled")
    chat.pack(fill="both",expand=True,padx=10,pady=(0,8))
    prompt=tk.Text(right,height=4,bg="#0A0F14",fg=TEXT,insertbackground=TEXT,relief="flat",wrap="word",font=("Segoe UI",9)); prompt.pack(fill="x",padx=10)
    sendrow=tk.Frame(right,bg=PANEL); sendrow.pack(fill="x",padx=10,pady=8)
    ai_state=tk.Label(sendrow,text="AGENT SHELL · LOCAL",fg=MUTED,bg=PANEL,font=("Segoe UI",8)); ai_state.pack(side="left")

    def chat_line(who,text):
        chat.configure(state="normal"); chat.insert("end",f"{who}\n{text}\n\n"); chat.see("end"); chat.configure(state="disabled")
    chat_line("AsterMax AI","Import a STEP model. I will keep geometry, model intent and analysis operations visible here. External LLM connectivity is not enabled in this PMV build; deterministic engineering commands are available.")

    def ensure_static_analysis():
        if state["analysis"]: return
        analysis=tree.insert(model,"end",text="▾ Static Structural",open=True)
        tree.insert(analysis,"end",text="  Analysis Settings")
        tree.insert(analysis,"end",text="  Fixed Support  [proposed]")
        tree.insert(analysis,"end",text="  Force  [proposed]")
        sol=tree.insert(analysis,"end",text="▾ Solution",open=True)
        tree.insert(sol,"end",text="  Total Deformation")
        tree.insert(sol,"end",text="  Equivalent Stress")
        state["analysis"]=True; status.set("Static Structural analysis created — proposals require engineering approval")
        chat_line("AsterMax AI","Created a Static Structural analysis tree. Boundary conditions and loads are proposals only until engineer approval.")

    def submit_ai():
        text=prompt.get("1.0","end").strip()
        if not text: return
        prompt.delete("1.0","end"); chat_line("You",text)
        low=text.lower()
        if "estatic" in low or "static" in low or "análisis" in low or "analisis" in low:
            ensure_static_analysis()
        elif "step" in low or "geometr" in low:
            chat_line("AsterMax AI", "Geometry is " + (f"loaded: {Path(state['step']).name}" if state['step'] else "not loaded. Use Import STEP in the ribbon."))
        elif "malla" in low or "mesh" in low:
            chat_line("AsterMax AI","The visible CAD tessellation is only a preview. The FEA mesh is generated separately after model preparation and approval.")
        else:
            chat_line("AsterMax AI","Command recorded in case context. The external conversational model is not connected in this PMV; no engineering decision has been fabricated.")

    ttk.Button(sendrow,text="SEND",style="Accent.TButton",command=submit_ai).pack(side="right")

    def preview_done(source, mesh):
        state["preview"]=mesh; viewport.set_mesh(mesh); tree.item(geom,text=f"  Geometry  [{source.name}]")
        status.set(f"STEP preview ready — {len(mesh.nodes):,} nodes / {len(mesh.triangles):,} surface TRI3")
        chat_line("AsterMax AI",f"STEP loaded and mm gate passed: {source.name}. CAD preview is ready. You can now create a Static Structural analysis.")

    def preview_failed(exc):
        status.set("STEP unit gate passed, but CAD preview failed")
        chat_line("AsterMax AI",f"Preview failed: {exc}")
        messagebox.showerror("AsterMax 3D preview",str(exc))

    def choose_step():
        path=filedialog.askopenfilename(title="Import STEP",filetypes=[("STEP","*.step *.stp"),("All files","*.*")])
        if not path: return
        source=Path(path)
        try: validate_step_mm_file(source)
        except WindowsAppError as exc:
            messagebox.showerror("AsterMax STEP gate",str(exc)); status.set("STEP blocked by mm trust gate"); return
        state["step"]=source; tree.item(geom,text=f"  Geometry  [{source.name}] — loading preview")
        status.set("STEP mm gate passed — generating immediate CAD preview…")
        def worker():
            try: mesh=build_step_preview(source)
            except Exception as exc: root.after(0,lambda e=exc:preview_failed(e)); return
            root.after(0,lambda:preview_done(source,mesh))
        threading.Thread(target=worker,daemon=True).start()

    ttk.Button(commands,text="IMPORT STEP",style="Accent.TButton",command=choose_step).pack(side="left",padx=(0,6))
    ttk.Button(commands,text="NEW STATIC",style="Ribbon.TButton",command=ensure_static_analysis).pack(side="left")
    ttk.Button(commands,text="FIT",style="Ribbon.TButton",command=viewport.fit).pack(side="left")
    ttk.Button(commands,text="MESH",style="Ribbon.TButton",command=lambda:chat_line("AsterMax AI","FEA mesh command will use the verified preparation/approval pipeline; the preview mesh is not reused as analysis evidence.")).pack(side="left")
    ttk.Button(commands,text="SOLVE",style="Ribbon.TButton",command=lambda:chat_line("AsterMax AI","Solve remains gated until the Static Structural model has approved BC/load intent. Open the validated model-preparation workflow to execute FEA.")).pack(side="left")
    ttk.Separator(commands,orient="vertical").pack(side="left",fill="y",padx=8)
    ttk.Label(commands,text="VIEW",style="Ribbon.TLabel",font=("Segoe UI Semibold",8)).pack(side="left",padx=(0,6))
    for label in ("ISO","FRONT","TOP"):
        ttk.Button(commands,text=label,style="Ribbon.TButton",command=viewport.fit).pack(side="left")

    root.mainloop(); return 0


def main(argv=None) -> int:
    return launch_desktop()


if __name__ == "__main__":
    raise SystemExit(main())
