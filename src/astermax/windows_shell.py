from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from .desktop_picker_app import desktop_main

_ORIGINAL_TK = tk.Tk


class AsterMaxWindowsRoot(_ORIGINAL_TK):
    """Classic Windows application shell around the verified AsterMax desktop workspace."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.option_add("*Font", "Segoe UI 9")
        self._build_menubar()

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
