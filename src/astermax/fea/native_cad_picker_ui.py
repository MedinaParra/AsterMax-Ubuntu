from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .cad_face_picker import (
    CadFacePickerCatalog,
    CadFacePickerError,
    PickerNamedSelectionEvidence,
    capture_picker_named_selection,
    pick_cad_face,
)
from .face_ownership import ArbitraryNamedSelectionBinding, Tet10FaceOwnershipInventory
from .named_selections import PersistentNamedSelection


class NativeCadPickerUiError(ValueError):
    pass


@dataclass(frozen=True)
class NativeCadPickerAssignment:
    schema: str
    support_face_ids: tuple[str, ...]
    load_face_ids: tuple[str, ...]
    support_selection: PersistentNamedSelection
    load_selection: PersistentNamedSelection
    support_binding: ArbitraryNamedSelectionBinding
    load_binding: ArbitraryNamedSelectionBinding
    support_evidence: PickerNamedSelectionEvidence
    load_evidence: PickerNamedSelectionEvidence


def update_selected_face_ids(
    catalog: CadFacePickerCatalog,
    selected_face_ids: tuple[str, ...],
    x_px: float,
    y_px: float,
    *,
    additive: bool,
) -> tuple[str, ...]:
    """Apply one native-canvas click to deterministic picker state.

    Ctrl-click semantics are represented by additive=True. Clicking an already
    selected face in additive mode removes it, matching common CAE selection UX.
    """
    pick = pick_cad_face(catalog, x_px, y_px)
    current = list(selected_face_ids)
    if additive:
        if pick.face_id in current:
            current.remove(pick.face_id)
        else:
            current.append(pick.face_id)
    else:
        current = [pick.face_id]
    order = {face.face_id: index for index, face in enumerate(catalog.faces)}
    return tuple(sorted(current, key=lambda face_id: order[face_id]))


def build_native_picker_assignment(
    step_path: str | Path,
    inventory: Tet10FaceOwnershipInventory,
    catalog: CadFacePickerCatalog,
    *,
    support_face_ids: tuple[str, ...],
    load_face_ids: tuple[str, ...],
) -> NativeCadPickerAssignment:
    if not support_face_ids or not load_face_ids:
        raise NativeCadPickerUiError("Support and Load must each contain at least one picked CAD face")
    if set(support_face_ids) & set(load_face_ids):
        raise NativeCadPickerUiError("NATIVE_PICKER_SUPPORT_LOAD_OVERLAP")
    support, support_binding, _support_tri, support_evidence = capture_picker_named_selection(
        step_path,
        inventory,
        catalog,
        support_face_ids,
        name="Support",
        role="SUPPORT",
    )
    load, load_binding, _load_tri, load_evidence = capture_picker_named_selection(
        step_path,
        inventory,
        catalog,
        load_face_ids,
        name="Load",
        role="LOAD",
    )
    return NativeCadPickerAssignment(
        schema="AsterMaxNativeCadPickerAssignmentV1",
        support_face_ids=tuple(support_face_ids),
        load_face_ids=tuple(load_face_ids),
        support_selection=support,
        load_selection=load,
        support_binding=support_binding,
        load_binding=load_binding,
        support_evidence=support_evidence,
        load_evidence=load_evidence,
    )


def install_native_cad_face_picker_tab(notebook, on_assignment: Callable[[NativeCadPickerAssignment], None] | None = None):
    """Install a native Tk canvas picker tab and return a binder for CAD catalogs.

    The binder signature is ``bind(step_path, inventory, catalog)``. Face drawing
    uses the exact projected owned-TRI6 corners from C5.3; hit testing delegates
    to the same deterministic picker contract. No alternate visual-only geometry
    identity is introduced.
    """
    import tkinter as tk
    from tkinter import messagebox, ttk

    frame = ttk.Frame(notebook, padding=12)
    notebook.add(frame, text="CAD Face Picker")
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(1, weight=1)

    header = ttk.Frame(frame)
    header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    status_var = tk.StringVar(value="Prepare a CAD ownership catalog to enable picking.")
    ttk.Label(header, textvariable=status_var).pack(side="left", fill="x", expand=True)

    canvas = tk.Canvas(frame, width=760, height=560, background="#f4f6f8", highlightthickness=1)
    canvas.grid(row=1, column=0, sticky="nsew")

    controls = ttk.Frame(frame)
    controls.grid(row=2, column=0, sticky="ew", pady=(8, 0))
    ttk.Label(controls, text="Click = single select · Ctrl+click = add/remove").pack(side="left")
    support_button = ttk.Button(controls, text="Assign Support", state="disabled")
    support_button.pack(side="right", padx=(6, 0))
    load_button = ttk.Button(controls, text="Assign Load", state="disabled")
    load_button.pack(side="right", padx=(6, 0))
    clear_button = ttk.Button(controls, text="Clear", state="disabled")
    clear_button.pack(side="right")

    state: dict[str, object] = {
        "step_path": None,
        "inventory": None,
        "catalog": None,
        "selected": tuple(),
        "support": tuple(),
        "load": tuple(),
    }

    def redraw() -> None:
        canvas.delete("all")
        catalog = state.get("catalog")
        if not isinstance(catalog, CadFacePickerCatalog):
            return
        selected = set(state["selected"])
        support = set(state["support"])
        load = set(state["load"])
        for face in sorted(catalog.faces, key=lambda item: item.projected_depth):
            if face.face_id in support:
                fill, outline, width = "#b7e4c7", "#2d6a4f", 2
            elif face.face_id in load:
                fill, outline, width = "#ffd6a5", "#b45309", 2
            elif face.face_id in selected:
                fill, outline, width = "#bee3f8", "#1d4ed8", 3
            else:
                fill, outline, width = "#e5e7eb", "#6b7280", 1
            for triangle in face.projected_triangles_px:
                coords = [coord for point in triangle for coord in point]
                canvas.create_polygon(*coords, fill=fill, outline=outline, width=width)
            x, y = face.projected_center_px
            canvas.create_text(x, y, text=face.face_id, fill="#111827", font=("Segoe UI", 8, "bold"))

    def click(event, additive: bool) -> None:
        catalog = state.get("catalog")
        if not isinstance(catalog, CadFacePickerCatalog):
            return
        try:
            state["selected"] = update_selected_face_ids(
                catalog,
                tuple(state["selected"]),
                float(event.x),
                float(event.y),
                additive=additive,
            )
        except CadFacePickerError as exc:
            if str(exc) != "CAD_FACE_PICK_MISS":
                messagebox.showerror("AsterMax CAD picker", str(exc))
            return
        status_var.set("Selected: " + ", ".join(state["selected"]))
        redraw()

    canvas.bind("<Button-1>", lambda event: click(event, False))
    canvas.bind("<Control-Button-1>", lambda event: click(event, True))

    def clear() -> None:
        state["selected"] = tuple()
        status_var.set("Selection cleared.")
        redraw()

    def assign(role: str) -> None:
        selected = tuple(state["selected"])
        if not selected:
            messagebox.showerror("AsterMax CAD picker", "Pick at least one CAD face first.")
            return
        if role == "SUPPORT":
            if set(selected) & set(state["load"]):
                messagebox.showerror("AsterMax CAD picker", "Support cannot overlap the current Load faces.")
                return
            state["support"] = selected
        else:
            if set(selected) & set(state["support"]):
                messagebox.showerror("AsterMax CAD picker", "Load cannot overlap the current Support faces.")
                return
            state["load"] = selected
        state["selected"] = tuple()
        redraw()
        if state["support"] and state["load"]:
            try:
                assignment = build_native_picker_assignment(
                    state["step_path"],
                    state["inventory"],
                    state["catalog"],
                    support_face_ids=tuple(state["support"]),
                    load_face_ids=tuple(state["load"]),
                )
            except Exception as exc:
                messagebox.showerror("AsterMax CAD picker", str(exc))
                return
            status_var.set(
                f"Bound Support={','.join(assignment.support_face_ids)} · Load={','.join(assignment.load_face_ids)} · exact persistent CAD provenance verified."
            )
            if on_assignment is not None:
                on_assignment(assignment)

    clear_button.configure(command=clear)
    support_button.configure(command=lambda: assign("SUPPORT"))
    load_button.configure(command=lambda: assign("LOAD"))

    def bind(step_path: str | Path, inventory: Tet10FaceOwnershipInventory, catalog: CadFacePickerCatalog) -> None:
        if catalog.source_step_sha256 != inventory.source_step_sha256 or catalog.ownership_sha256 != inventory.ownership_sha256:
            raise NativeCadPickerUiError("NATIVE_PICKER_CATALOG_OWNERSHIP_MISMATCH")
        state.update(
            step_path=Path(step_path),
            inventory=inventory,
            catalog=catalog,
            selected=tuple(),
            support=tuple(),
            load=tuple(),
        )
        canvas.configure(width=catalog.viewport_width_px, height=catalog.viewport_height_px)
        support_button.configure(state="normal")
        load_button.configure(state="normal")
        clear_button.configure(state="normal")
        status_var.set(f"{len(catalog.faces)} persistent CAD faces ready. Pick Support and Load scopes.")
        redraw()

    return bind
