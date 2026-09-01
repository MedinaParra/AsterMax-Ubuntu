from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from .desktop_picker_app import desktop_main

_ORIGINAL_TK = tk.Tk


def build_project_tree_spec() -> tuple[tuple[str, str, str | None], ...]:
    """Stable Mechanical-like information architecture for the Windows PMV.

    Each tuple is (node_id, visible_label, target_notebook_tab_substring).
    Nodes with a None target are structural only and must not imply capability.
    """
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
    """Classic Windows application shell around the verified AsterMax desktop workspace."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.option_add("*Font", "Segoe UI 9")
        self._tree: ttk.Treeview | None = None
        self._workspace_host: ttk.Panedwindow | None = None
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
        """Re-parent the existing verified notebook into a Windows CAE-style split workspace."""
        if self._workspace_host is not None:
            return
        notebook = self._find_notebook()
        if notebook is None:
            self.after(50, self._install_mechanical_workspace)
            return

        # desktop_main packs the notebook directly in the root. Preserve the exact
        # verified tabs and callbacks; only alter presentation/navigation.
        notebook.pack_forget()
        host = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        host.pack(fill="both", expand=True, padx=8, pady=(8, 8))

        navigator = ttk.Frame(host, padding=(6, 8))
        navigator.columnconfigure(0, weight=1)
        navigator.rowconfigure(1, weight=1)
        ttk.Label(navigator, text="Outline", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 6))
        tree = ttk.Treeview(navigator, show="tree", selectmode="browse", height=24)
        tree.grid(row=1, column=0, sticky="nsew")
        tree.bind("<<TreeviewSelect>>", self._tree_open)
        self._tree = tree

        parents = {
            "geometry": "model",
            "materials": "model",
            "connections": "model",
            "mesh": "model",
            "supports": "static",
            "loads": "static",
            "review": "solution",
            "results": "solution",
            "provenance": "solution",
        }
        for node_id, label, _target in build_project_tree_spec():
            parent = parents.get(node_id, "")
            tree.insert(parent, "end", iid=node_id, text=label, open=True)

        details = ttk.Frame(navigator, padding=(0, 8, 0, 0))
        details.grid(row=2, column=0, sticky="ew")
        ttk.Separator(details, orient=tk.HORIZONTAL).pack(fill="x", pady=(0, 8))
        ttk.Label(details, text="Verified workflow", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        ttk.Label(
            details,
            text="STEP [mm] → persistent CAD faces → TET10 → review → sparse solve → evidence-bound results",
            wraplength=245,
            justify="left",
        ).pack(anchor="w", pady=(3, 0))
        ttk.Label(
            details,
            text="No arbitrary-model convergence, industrial-validation or ANSYS-equivalence claim.",
            wraplength=245,
            justify="left",
        ).pack(anchor="w", pady=(5, 0))

        workspace = ttk.Frame(host)
        workspace.columnconfigure(0, weight=1)
        workspace.rowconfigure(1, weight=1)
        header = ttk.Frame(workspace, padding=(10, 5))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="AsterMax Mechanical Workspace", font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Label(header, text="   Length: mm   Force: N   Stress: MPa").pack(side="left")
        notebook.grid(in_=workspace, row=1, column=0, sticky="nsew", padx=2, pady=(0, 2))

        host.add(navigator, weight=0)
        host.add(workspace, weight=1)
        self._workspace_host = host
        try:
            host.sashpos(0, 285)
        except tk.TclError:
            pass

    def _not_ready(self, feature: str) -> None:
        messagebox.showinfo(
            "AsterMax",
            f"{feature} is not enabled in the verified PMV yet. The command remains visible so the desktop information architecture stays stable while capability is added behind harness gates.",
            parent=self,
        )

    def _build_menubar(self) -> None:
        bar = tk.Menu(self)
        file_menu = tk.Menu(bar, tearoff=False)
        file_menu.add_command(label="Nuevo análisis", command=lambda: self._select_tab_contains("Analysis"), accelerator="Ctrl+N")
        file_menu.add_command(label="Abrir STEP/STP…", command=lambda: self._select_tab_contains("Analysis"), accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Resultados", command=lambda: self._select_tab_contains("Results"))
        file_menu.add_separator()
        file_menu.add_command(label="Salir", command=self.destroy, accelerator="Alt+F4")
        bar.add_cascade(label="Archivo", menu=file_menu)

        edit_menu = tk.Menu(bar, tearoff=False)
        edit_menu.add_command(label="Deshacer", command=lambda: self.event_generate("<<Undo>>"), accelerator="Ctrl+Z")
        edit_menu.add_command(label="Rehacer", command=lambda: self.event_generate("<<Redo>>"), accelerator="Ctrl+Y")
        edit_menu.add_separator()
        edit_menu.add_command(label="Preferencias…", command=lambda: self._not_ready("Preferencias"))
        bar.add_cascade(label="Editar", menu=edit_menu)

        view_menu = tk.Menu(bar, tearoff=False)
        view_menu.add_command(label="Análisis", command=lambda: self._select_tab_contains("Analysis"))
        view_menu.add_command(label="Selector CAD", command=lambda: self._select_tab_contains("Picker"))
        view_menu.add_command(label="Revisión", command=lambda: self._select_tab_contains("Review"))
        view_menu.add_command(label="Resultados", command=lambda: self._select_tab_contains("Results"))
        bar.add_cascade(label="Ver", menu=view_menu)

        model_menu = tk.Menu(bar, tearoff=False)
        model_menu.add_command(label="Geometría STEP", command=lambda: self._select_tab_contains("Analysis"))
        model_menu.add_command(label="Material", command=lambda: self._select_tab_contains("Analysis"))
        model_menu.add_command(label="Soportes y cargas", command=lambda: self._select_tab_contains("Picker"))
        model_menu.add_command(label="Contactos…", command=lambda: self._not_ready("Contactos"))
        bar.add_cascade(label="Modelo", menu=model_menu)

        mesh_menu = tk.Menu(bar, tearoff=False)
        mesh_menu.add_command(label="Configuración de malla", command=lambda: self._select_tab_contains("Analysis"))
        mesh_menu.add_command(label="Calidad de malla", command=lambda: self._select_tab_contains("Review"))
        bar.add_cascade(label="Malla", menu=mesh_menu)

        solution_menu = tk.Menu(bar, tearoff=False)
        solution_menu.add_command(label="Revisar modelo", command=lambda: self._select_tab_contains("Review"), accelerator="F5")
        solution_menu.add_command(label="Resolver", command=lambda: self._select_tab_contains("Analysis"), accelerator="F6")
        bar.add_cascade(label="Solución", menu=solution_menu)

        results_menu = tk.Menu(bar, tearoff=False)
        results_menu.add_command(label="Resultados", command=lambda: self._select_tab_contains("Results"), accelerator="F7")
        results_menu.add_command(label="Evidencia / proveniencia", command=lambda: self._select_tab_contains("Results"))
        bar.add_cascade(label="Resultados", menu=results_menu)

        help_menu = tk.Menu(bar, tearoff=False)
        help_menu.add_command(label="Documentación", command=lambda: webbrowser.open("https://github.com/MedinaParra/AsterMax-Ubuntu"))
        help_menu.add_command(label="Comprobar instalación", command=lambda: messagebox.showinfo("AsterMax", "El runtime de la aplicación cargó correctamente. El instalador y el packaged self-test verifican las dependencias y la ruta numérica.", parent=self))
        help_menu.add_separator()
        help_menu.add_command(label="Acerca de AsterMax", command=lambda: messagebox.showinfo("AsterMax", "AsterMax Mechanical · Windows PMV\nEvidence-native finite-element engineering workspace", parent=self))
        bar.add_cascade(label="Ayuda", menu=help_menu)

        self.config(menu=bar)
        self.bind_all("<Control-n>", lambda _e: self._select_tab_contains("Analysis"))
        self.bind_all("<Control-o>", lambda _e: self._select_tab_contains("Analysis"))
        self.bind_all("<F5>", lambda _e: self._select_tab_contains("Review"))
        self.bind_all("<F6>", lambda _e: self._select_tab_contains("Analysis"))
        self.bind_all("<F7>", lambda _e: self._select_tab_contains("Results"))


def windows_desktop_main() -> int:
    tk.Tk = AsterMaxWindowsRoot
    try:
        return desktop_main()
    finally:
        tk.Tk = _ORIGINAL_TK
