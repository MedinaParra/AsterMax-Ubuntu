from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from . import desktop_picker_app as desktop_app
from .persistent_viewport import (
    ViewportSnapshot,
    projected_box_segments,
    snapshot_from_inventory,
    snapshot_with_assignment,
    snapshot_with_results,
    stage_caption,
    validate_snapshot,
)

_ORIGINAL_TK = tk.Tk
_ACTIVE_ROOT: "AsterMaxWindowsRoot | None" = None


def build_project_tree_spec() -> tuple[tuple[str, str, str | None], ...]:
    return (
        ("model", "Model", None),
        ("geometry", "Geometry · STEP [mm]", "Analysis"),
        ("materials", "Materials", "Analysis"),
        ("connections", "Connections · not enabled", None),
        ("mesh", "Mesh · TET10", "Review"),
        ("static", "Static Structural", None),
        ("supports", "Supports · CAD faces", "Picker"),
        ("loads", "Loads · CAD faces", "Picker"),
        ("solution", "Solution", None),
        ("review", "Model Review", "Review"),
        ("results", "Results", "Results"),
        ("provenance", "Evidence / Provenance", "Results"),
    )


class AsterMaxWindowsRoot(_ORIGINAL_TK):
    """Windows CAE shell with an evidence-bound persistent engineering viewport."""

    def __init__(self, *args, **kwargs):
        global _ACTIVE_ROOT
        super().__init__(*args, **kwargs)
        _ACTIVE_ROOT = self
        self.option_add("*Font", "Segoe UI 9")
        self._tree: ttk.Treeview | None = None
        self._workspace_host: ttk.Panedwindow | None = None
        self._viewport_canvas: tk.Canvas | None = None
        self._viewport_caption = tk.StringVar(value="Open a STEP/STP model to begin. Units locked to mm / N / MPa.")
        self._viewport_snapshot = ViewportSnapshot(stage="EMPTY", units=("mm", "N", "MPa"))
        self._build_menubar()
        self.after_idle(self._install_mechanical_workspace)

    def _find_notebook(self):
        stack = list(self.winfo_children())
        while stack:
            widget = stack.pop(0)
            if isinstance(widget, ttk.Notebook):
                return widget
            stack.extend(widget.winfo_children())
        return None

    def publish_viewport_snapshot(self, snapshot: ViewportSnapshot) -> None:
        validate_snapshot(snapshot)
        self._viewport_snapshot = snapshot
        self._viewport_caption.set(stage_caption(snapshot))
        self._render_viewport()

    def publish_inventory(self, inventory) -> None:
        snapshot = snapshot_from_inventory(inventory)
        self.after(0, lambda: self.publish_viewport_snapshot(snapshot))

    def publish_assignment(self, assignment) -> None:
        base = self._viewport_snapshot
        snapshot = snapshot_with_assignment(base, assignment)
        self.after(0, lambda: self.publish_viewport_snapshot(snapshot))

    def publish_results(self, summary: dict) -> None:
        base = self._viewport_snapshot
        snapshot = snapshot_with_results(base, summary)
        self.after(0, lambda: self.publish_viewport_snapshot(snapshot))

    def _render_viewport(self, _event=None) -> None:
        canvas = self._viewport_canvas
        if canvas is None:
            return
        canvas.delete("all")
        w = max(canvas.winfo_width(), 320)
        h = max(canvas.winfo_height(), 180)
        snapshot = self._viewport_snapshot
        if snapshot.stage == "EMPTY":
            canvas.create_text(w / 2, h / 2, text="Persistent Engineering Viewport\nSTEP [mm] → TET10 → BC → Results", justify="center", font=("Segoe UI", 13, "bold"))
            return
        segments = projected_box_segments(snapshot)
        if not segments:
            return
        xs = [v for seg in segments for v in (seg[0], seg[2])]
        ys = [v for seg in segments for v in (seg[1], seg[3])]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        spanx = max(xmax - xmin, 1e-12)
        spany = max(ymax - ymin, 1e-12)
        margin = 35.0
        scale = min((w - 2 * margin) / spanx, (h - 2 * margin) / spany)

        def px(x: float) -> float:
            return margin + (x - xmin) * scale

        def py(y: float) -> float:
            return h - margin - (y - ymin) * scale

        for x1, y1, x2, y2 in segments:
            canvas.create_line(px(x1), py(y1), px(x2), py(y2), width=2)
        canvas.create_text(12, 10, anchor="nw", text=snapshot.stage, font=("Segoe UI", 10, "bold"))
        canvas.create_text(12, 29, anchor="nw", text=f"{snapshot.node_count} nodes · {snapshot.element_count} TET10 · mm / N / MPa")
        if snapshot.support_face_ids:
            canvas.create_text(12, h - 32, anchor="sw", text="Support: " + ", ".join(snapshot.support_face_ids))
        if snapshot.load_face_ids:
            canvas.create_text(w - 12, h - 32, anchor="se", text="Load: " + ", ".join(snapshot.load_face_ids))
        if snapshot.stage == "RESULTS_READY":
            canvas.create_text(w - 12, 10, anchor="ne", text="Results provenance: VERIFIED", font=("Segoe UI", 9, "bold"))

    def _select_tab_contains(self, text: str) -> None:
        notebook = self._find_notebook()
        if notebook is None:
            return
        needle = text.lower()
        for tab_id in notebook.tabs():
            if needle in notebook.tab(tab_id, "text").lower():
                notebook.select(tab_id)
                return

    def _tree_target(self, node_id: str) -> str | None:
        for candidate, _label, target in build_project_tree_spec():
            if candidate == node_id:
                return target
        return None

    def _tree_open(self, _event=None) -> None:
        if self._tree is None:
            return
        selected = self._tree.selection()
        if not selected:
            return
        target = self._tree_target(selected[0])
        if target:
            self._select_tab_contains(target)

    def _install_mechanical_workspace(self) -> None:
        if self._workspace_host is not None:
            return
        notebook = self._find_notebook()
        if notebook is None:
            self.after(50, self._install_mechanical_workspace)
            return
        notebook.pack_forget()
        host = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        host.pack(fill="both", expand=True, padx=8, pady=8)

        navigator = ttk.Frame(host, padding=(6, 8))
        navigator.columnconfigure(0, weight=1)
        navigator.rowconfigure(1, weight=1)
        ttk.Label(navigator, text="Outline", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 6))
        tree = ttk.Treeview(navigator, show="tree", selectmode="browse", height=24)
        tree.grid(row=1, column=0, sticky="nsew")
        tree.bind("<<TreeviewSelect>>", self._tree_open)
        self._tree = tree
        parents = {"geometry": "model", "materials": "model", "connections": "model", "mesh": "model", "supports": "static", "loads": "static", "review": "solution", "results": "solution", "provenance": "solution"}
        for node_id, label, _target in build_project_tree_spec():
            tree.insert(parents.get(node_id, ""), "end", iid=node_id, text=label, open=True)

        details = ttk.Frame(navigator, padding=(0, 8, 0, 0))
        details.grid(row=2, column=0, sticky="ew")
        ttk.Separator(details).pack(fill="x", pady=(0, 8))
        ttk.Label(details, text="Verified workflow", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        ttk.Label(details, text="STEP [mm] → persistent CAD faces → TET10 → review → sparse solve → evidence-bound results", wraplength=245, justify="left").pack(anchor="w", pady=(3, 0))
        ttk.Label(details, text="Viewport envelope comes from actual TET10 nodes; it is not a synthetic CAD surface renderer.", wraplength=245, justify="left").pack(anchor="w", pady=(5, 0))

        workspace = ttk.Frame(host)
        workspace.columnconfigure(0, weight=1)
        workspace.rowconfigure(1, weight=1)
        header = ttk.Frame(workspace, padding=(10, 5))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="AsterMax Mechanical Workspace", font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Label(header, text="   Length: mm   Force: N   Stress: MPa").pack(side="left")

        vertical = ttk.Panedwindow(workspace, orient=tk.VERTICAL)
        vertical.grid(row=1, column=0, sticky="nsew")
        viewport_frame = ttk.Frame(vertical, padding=4)
        viewport_frame.columnconfigure(0, weight=1)
        viewport_frame.rowconfigure(0, weight=1)
        canvas = tk.Canvas(viewport_frame, highlightthickness=1)
        canvas.grid(row=0, column=0, sticky="nsew")
        canvas.bind("<Configure>", self._render_viewport)
        self._viewport_canvas = canvas
        ttk.Label(viewport_frame, textvariable=self._viewport_caption, anchor="w").grid(row=1, column=0, sticky="ew", pady=(4, 0))
        notebook_frame = ttk.Frame(vertical)
        notebook_frame.columnconfigure(0, weight=1)
        notebook_frame.rowconfigure(0, weight=1)
        notebook.grid(in_=notebook_frame, row=0, column=0, sticky="nsew")
        vertical.add(viewport_frame, weight=2)
        vertical.add(notebook_frame, weight=3)

        host.add(navigator, weight=0)
        host.add(workspace, weight=1)
        self._workspace_host = host
        self.after_idle(self._render_viewport)
        try:
            host.sashpos(0, 285)
        except tk.TclError:
            pass

    def _not_ready(self, feature: str) -> None:
        messagebox.showinfo("AsterMax", f"{feature} is not enabled in the verified PMV yet. The command remains visible so capability is added behind harness gates rather than implied early.", parent=self)

    def _build_menubar(self) -> None:
        bar = tk.Menu(self)
        file_menu = tk.Menu(bar, tearoff=False)
        file_menu.add_command(label="Nuevo análisis", command=lambda: self._select_tab_contains("Analysis"), accelerator="Ctrl+N")
        file_menu.add_command(label="Abrir STEP/STP…", command=lambda: self._select_tab_contains("Analysis"), accelerator="Ctrl+O")
        file_menu.add_separator(); file_menu.add_command(label="Resultados", command=lambda: self._select_tab_contains("Results")); file_menu.add_separator()
        file_menu.add_command(label="Salir", command=self.destroy, accelerator="Alt+F4"); bar.add_cascade(label="Archivo", menu=file_menu)
        edit_menu = tk.Menu(bar, tearoff=False); edit_menu.add_command(label="Deshacer", command=lambda: self.event_generate("<<Undo>>"), accelerator="Ctrl+Z"); edit_menu.add_command(label="Rehacer", command=lambda: self.event_generate("<<Redo>>"), accelerator="Ctrl+Y"); edit_menu.add_separator(); edit_menu.add_command(label="Preferencias…", command=lambda: self._not_ready("Preferencias")); bar.add_cascade(label="Editar", menu=edit_menu)
        view_menu = tk.Menu(bar, tearoff=False); view_menu.add_command(label="Análisis", command=lambda: self._select_tab_contains("Analysis")); view_menu.add_command(label="Selector CAD", command=lambda: self._select_tab_contains("Picker")); view_menu.add_command(label="Revisión", command=lambda: self._select_tab_contains("Review")); view_menu.add_command(label="Resultados", command=lambda: self._select_tab_contains("Results")); bar.add_cascade(label="Ver", menu=view_menu)
        model_menu = tk.Menu(bar, tearoff=False); model_menu.add_command(label="Geometría STEP", command=lambda: self._select_tab_contains("Analysis")); model_menu.add_command(label="Material", command=lambda: self._select_tab_contains("Analysis")); model_menu.add_command(label="Soportes y cargas", command=lambda: self._select_tab_contains("Picker")); model_menu.add_command(label="Contactos…", command=lambda: self._not_ready("Contactos")); bar.add_cascade(label="Modelo", menu=model_menu)
        mesh_menu = tk.Menu(bar, tearoff=False); mesh_menu.add_command(label="Configuración de malla", command=lambda: self._select_tab_contains("Analysis")); mesh_menu.add_command(label="Calidad de malla", command=lambda: self._select_tab_contains("Review")); bar.add_cascade(label="Malla", menu=mesh_menu)
        solution_menu = tk.Menu(bar, tearoff=False); solution_menu.add_command(label="Revisar modelo", command=lambda: self._select_tab_contains("Review"), accelerator="F5"); solution_menu.add_command(label="Resolver", command=lambda: self._select_tab_contains("Analysis"), accelerator="F6"); bar.add_cascade(label="Solución", menu=solution_menu)
        results_menu = tk.Menu(bar, tearoff=False); results_menu.add_command(label="Resultados", command=lambda: self._select_tab_contains("Results"), accelerator="F7"); results_menu.add_command(label="Evidencia / proveniencia", command=lambda: self._select_tab_contains("Results")); bar.add_cascade(label="Resultados", menu=results_menu)
        help_menu = tk.Menu(bar, tearoff=False); help_menu.add_command(label="Documentación", command=lambda: webbrowser.open("https://github.com/MedinaParra/AsterMax-Ubuntu")); help_menu.add_command(label="Comprobar instalación", command=lambda: messagebox.showinfo("AsterMax", "El runtime cargó correctamente. El instalador y packaged self-test verifican dependencias y ruta numérica.", parent=self)); help_menu.add_separator(); help_menu.add_command(label="Acerca de AsterMax", command=lambda: messagebox.showinfo("AsterMax", "AsterMax Mechanical · Windows PMV\nEvidence-native finite-element engineering workspace", parent=self)); bar.add_cascade(label="Ayuda", menu=help_menu)
        self.config(menu=bar)
        self.bind_all("<Control-n>", lambda _e: self._select_tab_contains("Analysis")); self.bind_all("<Control-o>", lambda _e: self._select_tab_contains("Analysis")); self.bind_all("<F5>", lambda _e: self._select_tab_contains("Review")); self.bind_all("<F6>", lambda _e: self._select_tab_contains("Analysis")); self.bind_all("<F7>", lambda _e: self._select_tab_contains("Results"))


def _install_viewport_bridges():
    original_mesh = desktop_app.mesh_step_tet10_with_face_ownership
    original_picker_installer = desktop_app.install_native_cad_face_picker_tab
    original_solve = desktop_app.solve_desktop_picker_model

    def mesh_bridge(*args, **kwargs):
        inventory = original_mesh(*args, **kwargs)
        if _ACTIVE_ROOT is not None:
            _ACTIVE_ROOT.publish_inventory(inventory)
        return inventory

    def picker_installer_bridge(notebook, *, on_assignment):
        def bridged_assignment(assignment):
            if _ACTIVE_ROOT is not None:
                _ACTIVE_ROOT.publish_assignment(assignment)
            on_assignment(assignment)
        return original_picker_installer(notebook, on_assignment=bridged_assignment)

    def solve_bridge(*args, **kwargs):
        summary = original_solve(*args, **kwargs)
        if _ACTIVE_ROOT is not None:
            _ACTIVE_ROOT.publish_results(summary)
        return summary

    desktop_app.mesh_step_tet10_with_face_ownership = mesh_bridge
    desktop_app.install_native_cad_face_picker_tab = picker_installer_bridge
    desktop_app.solve_desktop_picker_model = solve_bridge
    return original_mesh, original_picker_installer, original_solve


def windows_desktop_main() -> int:
    global _ACTIVE_ROOT
    tk.Tk = AsterMaxWindowsRoot
    originals = _install_viewport_bridges()
    try:
        return desktop_app.desktop_main()
    finally:
        desktop_app.mesh_step_tet10_with_face_ownership, desktop_app.install_native_cad_face_picker_tab, desktop_app.solve_desktop_picker_model = originals
        tk.Tk = _ORIGINAL_TK
        _ACTIVE_ROOT = None
