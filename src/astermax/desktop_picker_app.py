from __future__ import annotations

from dataclasses import asdict
import json
import threading
import webbrowser
from pathlib import Path

from .fea.arbitrary_picker_review import build_arbitrary_picker_review_snapshot, install_arbitrary_picker_review_tab
from .fea.cad_face_picker import build_cad_face_picker_catalog
from .fea.evidence import sha256_file
from .fea.face_ownership import mesh_step_tet10_with_face_ownership
from .fea.native_cad_picker_ui import NativeCadPickerAssignment, install_native_cad_face_picker_tab
from .fea.postprocess_tet10 import write_tet10_linear_static_vtu
from .fea.production_picker_routing import prepare_picker_routed_model, solve_picker_routed_model, verify_picker_route
from .fea.viewer_tet10 import write_tet10_offline_viewer

RESULT_CLASS = "PMV_UNCONVERGED_USER_MODEL_NOT_INDUSTRIAL_RESULT"


def desktop_input_contract(
    step_path: str | Path,
    *,
    mesh_size_mm: float,
    young_modulus_mpa: float,
    poisson_ratio: float,
    resultant_n: tuple[float, float, float],
) -> dict:
    step = Path(step_path).expanduser().resolve()
    if not step.is_file() or step.suffix.lower() not in {".step", ".stp"}:
        raise ValueError("Select an existing STEP/STP file")
    mesh = float(mesh_size_mm)
    young = float(young_modulus_mpa)
    poisson = float(poisson_ratio)
    resultant = tuple(float(v) for v in resultant_n)
    if mesh <= 0.0:
        raise ValueError("Target mesh must be positive")
    if young <= 0.0:
        raise ValueError("Young's modulus must be positive")
    if not (-1.0 < poisson < 0.5):
        raise ValueError("Poisson ratio must be between -1 and 0.5")
    if len(resultant) != 3 or sum(v * v for v in resultant) <= 0.0:
        raise ValueError("Resultant load must be non-zero")
    return {
        "step_path": str(step),
        "step_sha256": sha256_file(step),
        "mesh_size_mm": mesh,
        "young_modulus_mpa": young,
        "poisson_ratio": poisson,
        "resultant_n": resultant,
    }


def prepare_desktop_picker_model(contract: dict, assignment: NativeCadPickerAssignment) -> dict:
    if contract["step_sha256"] != assignment.support_selection.source_sha256:
        raise ValueError("DESKTOP_PICKER_SUPPORT_STEP_STALE")
    if contract["step_sha256"] != assignment.load_selection.source_sha256:
        raise ValueError("DESKTOP_PICKER_LOAD_STEP_STALE")
    prepared = prepare_picker_routed_model(
        contract["step_path"], assignment, mesh_size_mm=contract["mesh_size_mm"]
    )
    review = build_arbitrary_picker_review_snapshot(prepared)
    prepared["desktop_input_contract"] = dict(contract)
    prepared["desktop_picker_review"] = review
    return prepared


def verify_desktop_picker_model(prepared: dict, contract: dict) -> None:
    original = prepared.get("desktop_input_contract")
    if original != contract:
        raise ValueError("DESKTOP_PICKER_INPUTS_CHANGED_AFTER_REVIEW")
    route = verify_picker_route(prepared)
    review = prepared.get("desktop_picker_review")
    if review is None or review.route_sha256 != route.route_sha256:
        raise ValueError("DESKTOP_PICKER_REVIEW_ROUTE_STALE")
    if review.support_binding_sha256 != route.support_binding_sha256:
        raise ValueError("DESKTOP_PICKER_REVIEW_SUPPORT_STALE")
    if review.load_binding_sha256 != route.load_binding_sha256:
        raise ValueError("DESKTOP_PICKER_REVIEW_LOAD_STALE")


def solve_desktop_picker_model(prepared: dict, contract: dict, output_dir: str | Path) -> dict:
    verify_desktop_picker_model(prepared, contract)
    solved = solve_picker_routed_model(
        prepared,
        young_modulus_mpa=contract["young_modulus_mpa"],
        poisson_ratio=contract["poisson_ratio"],
        resultant_n=contract["resultant_n"],
    )
    inventory = prepared["inventory"]
    result = solved["result"]
    route = prepared["production_picker_route"]
    review = prepared["desktop_picker_review"]
    evidence = prepared["evidence"]
    solve_evidence = solved["solve_evidence"]

    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    vtu_path = output / "astermax_result.vtu"
    viewer_path = output / "astermax_viewer.html"
    vtu_manifest = write_tet10_linear_static_vtu(
        vtu_path,
        inventory.nodes_mm,
        inventory.elements,
        result,
        result_class=RESULT_CLASS,
        converged_claim=False,
        industrial_validation_claim=False,
    )
    viewer_manifest = write_tet10_offline_viewer(
        viewer_path,
        inventory.nodes_mm,
        inventory.elements,
        result,
        result_class=RESULT_CLASS,
        converged_claim=False,
        industrial_validation_claim=False,
    )
    summary = {
        "schema": "AsterMaxDesktopPickerResultV1",
        "result_class": RESULT_CLASS,
        "source_step": contract["step_path"],
        "source_step_sha256": contract["step_sha256"],
        "units": {"length": "mm", "force": "N", "stress": "MPa"},
        "scope_contract": {
            "authoring": "NATIVE_CAD_FACE_PICKER_PERSISTENT_SIGNATURE",
            "constraint": "PERSISTENT_NAMED_SELECTION_FIXED_ALL_TRANSLATIONS",
            "load": "PERSISTENT_NAMED_SELECTION_CONSISTENT_TRI6_RESULTANT",
            "support_face_ids": list(route.support_face_ids),
            "load_face_ids": list(route.load_face_ids),
            "support_binding_sha256": route.support_binding_sha256,
            "load_binding_sha256": route.load_binding_sha256,
            "route_sha256": route.route_sha256,
        },
        "preparation": asdict(evidence),
        "review": asdict(review),
        "solve_evidence": asdict(solve_evidence),
        "mesh": {
            "family": "TET10",
            "target_size_mm": contract["mesh_size_mm"],
            "nodes": int(inventory.nodes_mm.shape[0]),
            "elements": int(inventory.elements.shape[0]),
            "dimensions_mm": [float(v) for v in inventory.dimensions_mm],
        },
        "material": {
            "young_modulus_mpa": contract["young_modulus_mpa"],
            "poisson_ratio": contract["poisson_ratio"],
        },
        "resultant_n": [float(v) for v in contract["resultant_n"]],
        "checks": {
            "force_residual_n": solve_evidence.force_residual_n,
            "moment_residual_nmm": solve_evidence.moment_residual_nmm,
        },
        "claims": {"converged": False, "industrial_validation": False, "ansys_equivalence": False},
        "artifacts": {
            "vtu": str(vtu_path),
            "viewer": str(viewer_path),
            "vtu_sha256": vtu_manifest.vtu_sha256,
            "viewer_sha256": viewer_manifest.html_sha256,
        },
    }
    summary_path = output / "astermax_result_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary["artifacts"]["summary"] = str(summary_path)
    return summary


def desktop_main() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("AsterMax PMV · Native CAD Picker · Evidence-Gated TET10")
    root.geometry("1240x880")
    root.minsize(980, 740)

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=10, pady=10)
    analysis = ttk.Frame(notebook, padding=18)
    notebook.add(analysis, text="Analysis")

    state: dict[str, object] = {"assignment": None, "prepared": None, "contract": None}
    status_var = tk.StringVar(value="1) Select STEP and build CAD picker. 2) Pick Support/Load. 3) Prepare review. 4) Solve.")
    step_var = tk.StringVar()
    out_var = tk.StringVar(value=str((Path.home() / "AsterMaxResults").resolve()))
    mesh_var = tk.StringVar(value="10.0")
    e_var = tk.StringVar(value="200000.0")
    nu_var = tk.StringVar(value="0.30")
    fx_var = tk.StringVar(value="0.0")
    fy_var = tk.StringVar(value="-1000.0")
    fz_var = tk.StringVar(value="0.0")

    def invalidate(*_args) -> None:
        state["assignment"] = None
        state["prepared"] = None
        state["contract"] = None
        review_button.configure(state="disabled")
        solve_button.configure(state="disabled")

    def contract() -> dict:
        return desktop_input_contract(
            step_var.get(),
            mesh_size_mm=float(mesh_var.get()),
            young_modulus_mpa=float(e_var.get()),
            poisson_ratio=float(nu_var.get()),
            resultant_n=(float(fx_var.get()), float(fy_var.get()), float(fz_var.get())),
        )

    def on_assignment(assignment: NativeCadPickerAssignment) -> None:
        state["assignment"] = assignment
        state["prepared"] = None
        state["contract"] = None
        review_button.configure(state="normal")
        solve_button.configure(state="disabled")
        status_var.set(
            f"Picker bound: Support={','.join(assignment.support_face_ids)} · Load={','.join(assignment.load_face_ids)}. Prepare review to rebuild and verify exact TRI6 bindings."
        )

    bind_picker = install_native_cad_face_picker_tab(notebook, on_assignment=on_assignment)
    bind_review = install_arbitrary_picker_review_tab(notebook)

    analysis.columnconfigure(1, weight=1)
    ttk.Label(analysis, text="AsterMax PMV", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(
        analysis,
        text="STEP [mm] → CAD Face Picker → Persistent Support/Load → Review → Sparse TET10 Solve",
    ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 16))

    def browse_step() -> None:
        path = filedialog.askopenfilename(filetypes=[("STEP geometry", "*.step *.stp"), ("All files", "*.*")])
        if path:
            step_var.set(path)
            invalidate()

    def browse_out() -> None:
        path = filedialog.askdirectory()
        if path:
            out_var.set(path)

    rows = [
        ("STEP file", step_var, browse_step),
        ("Output folder", out_var, browse_out),
        ("Target mesh [mm]", mesh_var, None),
        ("Young's modulus [MPa]", e_var, None),
        ("Poisson ratio", nu_var, None),
        ("Resultant Fx [N]", fx_var, None),
        ("Resultant Fy [N]", fy_var, None),
        ("Resultant Fz [N]", fz_var, None),
    ]
    for idx, (label, var, command) in enumerate(rows, start=2):
        ttk.Label(analysis, text=label).grid(row=idx, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(analysis, textvariable=var).grid(row=idx, column=1, sticky="ew", pady=4)
        if command:
            ttk.Button(analysis, text="Browse", command=command).grid(row=idx, column=2, padx=(8, 0), pady=4)

    for var in (step_var, mesh_var, e_var, nu_var, fx_var, fy_var, fz_var):
        var.trace_add("write", invalidate)

    warning = (
        "Production desktop authoring uses persistent arbitrary CAD-face picks; X/Y/Z MIN/MAX comboboxes are no longer in the main workflow. "
        "AsterMax tetra mean-ratio is not ANSYS Element Quality. Arbitrary-model convergence, industrial validation and ANSYS equivalence are not claimed."
    )
    ttk.Label(analysis, text=warning, wraplength=1040).grid(row=10, column=0, columnspan=3, sticky="ew", pady=(14, 8))
    progress = ttk.Progressbar(analysis, mode="indeterminate")
    progress.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(6, 8))
    ttk.Label(analysis, textvariable=status_var, wraplength=1040).grid(row=12, column=0, columnspan=3, sticky="w")
    picker_button = ttk.Button(analysis, text="1 · Build TET10 CAD ownership + open native face picker")
    picker_button.grid(row=13, column=0, columnspan=3, sticky="ew", pady=(12, 4))
    review_button = ttk.Button(analysis, text="2 · Prepare exact picker route + review", state="disabled")
    review_button.grid(row=14, column=0, columnspan=3, sticky="ew", pady=4)
    solve_button = ttk.Button(analysis, text="3 · Solve exact reviewed picker route", state="disabled")
    solve_button.grid(row=15, column=0, columnspan=3, sticky="ew", pady=(4, 6))

    def set_busy(busy: bool) -> None:
        picker_button.configure(state="disabled" if busy else "normal")
        if busy:
            review_button.configure(state="disabled")
            solve_button.configure(state="disabled")
            progress.start(10)
        else:
            progress.stop()

    def build_picker_clicked() -> None:
        try:
            current = contract()
        except Exception as exc:
            messagebox.showerror("Invalid input", str(exc)); return
        invalidate(); set_busy(True)
        status_var.set("Meshing STEP in mm and capturing persistent CAD-face → TRI6 ownership…")

        def worker() -> None:
            try:
                inventory = mesh_step_tet10_with_face_ownership(current["step_path"], current["mesh_size_mm"])
                catalog = build_cad_face_picker_catalog(inventory)
            except Exception as exc:
                root.after(0, lambda: (set_busy(False), messagebox.showerror("AsterMax picker", str(exc))))
                return
            def finished() -> None:
                set_busy(False)
                bind_picker(current["step_path"], inventory, catalog)
                status_var.set(f"{len(catalog.faces)} persistent CAD faces ready. Pick Support and Load in CAD Face Picker.")
                notebook.select(1)
            root.after(0, finished)
        threading.Thread(target=worker, daemon=True).start()

    def prepare_review_clicked() -> None:
        assignment = state.get("assignment")
        if not isinstance(assignment, NativeCadPickerAssignment):
            messagebox.showerror("AsterMax", "Assign Support and Load in CAD Face Picker first."); return
        try:
            current = contract()
        except Exception as exc:
            messagebox.showerror("Invalid input", str(exc)); return
        set_busy(True)
        status_var.set("Rebuilding picker bindings through production preparation and cross-checking TET10 quality…")

        def worker() -> None:
            try:
                prepared = prepare_desktop_picker_model(current, assignment)
            except Exception as exc:
                root.after(0, lambda: (set_busy(False), messagebox.showerror("AsterMax review", str(exc))))
                return
            def finished() -> None:
                set_busy(False)
                snapshot = bind_review(prepared)
                state["prepared"] = prepared
                state["contract"] = current
                review_button.configure(state="normal")
                solve_button.configure(state="normal")
                status_var.set(
                    f"REVIEW REQUIRED · Support={','.join(snapshot.support_face_ids)} · Load={','.join(snapshot.load_face_ids)} · {snapshot.node_count} nodes / {snapshot.tet10_count} TET10 · mean ratio min {snapshot.mean_ratio_minimum:.3f}."
                )
                notebook.select(2)
            root.after(0, finished)
        threading.Thread(target=worker, daemon=True).start()

    def solve_clicked() -> None:
        prepared = state.get("prepared")
        reviewed_contract = state.get("contract")
        if not isinstance(prepared, dict) or not isinstance(reviewed_contract, dict):
            messagebox.showerror("AsterMax", "Prepare and review the picker-routed model first."); return
        try:
            current = contract()
            verify_desktop_picker_model(prepared, current)
        except Exception as exc:
            state["prepared"] = None; state["contract"] = None; solve_button.configure(state="disabled")
            messagebox.showerror("Review invalidated", str(exc)); return
        set_busy(True)
        status_var.set("Solving exact reviewed FaceSignature/TRI6 bindings through sparse TET10 path…")

        def worker() -> None:
            try:
                summary = solve_desktop_picker_model(prepared, current, out_var.get())
            except Exception as exc:
                root.after(0, lambda: (set_busy(False), messagebox.showerror("AsterMax solve", str(exc))))
                return
            def finished() -> None:
                set_busy(False); state["prepared"] = None; state["contract"] = None; solve_button.configure(state="disabled")
                checks = summary["checks"]
                status_var.set(
                    f"Completed picker-routed model: {summary['mesh']['nodes']} nodes / {summary['mesh']['elements']} TET10 · force residual {checks['force_residual_n']:.3e} N · moment residual {checks['moment_residual_nmm']:.3e} N·mm"
                )
                webbrowser.open(Path(summary["artifacts"]["viewer"]).as_uri())
                messagebox.showinfo(
                    "AsterMax",
                    "Solve completed from native CAD face picks through persistent FaceSignature/TRI6 bindings. No arbitrary-model convergence or ANSYS-equivalence claim is made.",
                )
            root.after(0, finished)
        threading.Thread(target=worker, daemon=True).start()

    picker_button.configure(command=build_picker_clicked)
    review_button.configure(command=prepare_review_clicked)
    solve_button.configure(command=solve_clicked)
    root.mainloop()
    return 0
