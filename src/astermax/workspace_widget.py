from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Any

from .integrated_workspace import (
    assert_workspace_does_not_upgrade_claims,
    build_integrated_workspace,
)


def create_workspace_widget(parent, ttk):
    """Create a native tabbed evidence host and return its update callback.

    The tabs display solver-derived engineering state inside the desktop shell.
    HTML artifacts remain externally rendered; this function does not claim a
    native 3D renderer.
    """
    notebook = ttk.Notebook(parent)
    frames: dict[str, Any] = {}
    state_vars: dict[str, Any] = {}
    detail_vars: dict[str, Any] = {}
    open_buttons: dict[str, Any] = {}
    artifacts: dict[str, str | None] = {}

    for panel in build_integrated_workspace():
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text=panel.label)
        frames[panel.key] = frame
        import tkinter as tk

        state_var = tk.StringVar(value=panel.state)
        detail_var = tk.StringVar(value=panel.detail)
        state_vars[panel.key] = state_var
        detail_vars[panel.key] = detail_var
        ttk.Label(frame, textvariable=state_var, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(frame, textvariable=detail_var, wraplength=620).pack(anchor="w", fill="x", pady=(4, 8))

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

    return notebook, update
