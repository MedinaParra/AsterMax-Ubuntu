from __future__ import annotations

from dataclasses import asdict
import json
import threading
import webbrowser
from pathlib import Path

import numpy as np

from .fea.gmsh_bridge import distribute_resultant_on_tri6, fixed_dofs_for_nodes, force_and_moment, unique_surface_nodes
from .fea.live_analysis_evidence import install_live_analysis_evidence_tab
from .fea.native_credibility import install_native_credibility_tab
from .fea.postprocess_tet10 import write_tet10_linear_static_vtu
from .fea.pre_solve_review import accept_model_preparation, prepare_model_for_review, verify_acceptance, visual_preparation_payload
from .fea.solver import solve_linear_static_tet10
from .fea.tet4 import IsotropicMaterial
from .fea.viewer_tet10 import write_tet10_offline_viewer
from .fea.visual_model_preparation import install_visual_model_preparation_tab
from .fea.worst_element_inspector import install_worst_element_quality_tab

RESULT_CLASS = "PMV_UNCONVERGED_USER_MODEL_NOT_INDUSTRIAL_RESULT"


def prepare_step_analysis(
    step_path: str | Path,
    *,
    mesh_size_mm: float = 10.0,
    young_modulus_mpa: float = 200000.0,
    poisson_ratio: float = 0.30,
    resultant_n: tuple[float, float, float] = (0.0, -1000.0, 0.0),
    support_surface_keys: tuple[str, ...] = ("X_MIN",),
    load_surface_keys: tuple[str, ...] = ("X_MAX",),
) -> dict:
    """Prepare exact CAD, persistent named scopes and TET10 mesh without solving."""
    return prepare_model_for_review(
        step_path,
        mesh_size_mm=mesh_size_mm,
        young_modulus_mpa=young_modulus_mpa,
        poisson_ratio=poisson_ratio,
        resultant_n=resultant_n,
        support_surface_keys=support_surface_keys,
        load_surface_keys=load_surface_keys,
    )


def solve_prepared_analysis(prepared: dict, acceptance, output_dir: str | Path) -> dict:
    """Solve only an unchanged preparation with verified named-selection bindings."""
    verify_acceptance(prepared, acceptance)
    source = prepared["source"]
    mesh = prepared["mesh"]
    preparation = prepared["preparation"]
    review = prepared["review"]
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    material = IsotropicMaterial(review.material_young_modulus_mpa, review.material_poisson_ratio)
    load = np.asarray(review.resultant_n, dtype=float)
    support_triangles = np.asarray(prepared["support_triangles"], dtype=np.int64)
    load_triangles = np.asarray(prepared["load_triangles"], dtype=np.int64)
    fixed_nodes = unique_surface_nodes(support_triangles)
    fixed_dofs = fixed_dofs_for_nodes(fixed_nodes)
    loads = distribute_resultant_on_tri6(mesh.nodes_mm, load_triangles, load)
    applied_force, applied_moment = force_and_moment(mesh.nodes_mm, loads)
    result = solve_linear_static_tet10(mesh.nodes_mm, mesh.elements, material, loads, fixed_dofs)
    reaction_force, reaction_moment = force_and_moment(mesh.nodes_mm, result.reactions_n)
    force_residual_n = float(np.linalg.norm(reaction_force + applied_force))
    moment_residual_nmm = float(np.linalg.norm(reaction_moment + applied_moment))

    vtu_path = output / "astermax_result.vtu"
    viewer_path = output / "astermax_viewer.html"
    vtu_manifest = write_tet10_linear_static_vtu(vtu_path, mesh.nodes_mm, mesh.elements, result, result_class=RESULT_CLASS, converged_claim=False, industrial_validation_claim=False)
    viewer_manifest = write_tet10_offline_viewer(viewer_path, mesh.nodes_mm, mesh.elements, result, result_class=RESULT_CLASS, converged_claim=False, industrial_validation_claim=False)

    summary = {
        "schema": "AsterMaxDesktopPMVResultV1",
        "result_class": RESULT_CLASS,
        "source_step": str(source),
        "source_step_sha256": review.step_sha256,
        "units": {"length": "mm", "force": "N", "stress": "MPa"},
        "scope_contract": {
            "constraint": "PERSISTENT_NAMED_SELECTION_FIXED_ALL_TRANSLATIONS",
            "load": "PERSISTENT_NAMED_SELECTION_CONSISTENT_TRI6_RESULTANT",
            "support_name": prepared["support_selection"].name,
            "support_surface_keys": list(review.support_surface_keys),
            "support_named_selection_sha256": review.support_named_selection_sha256,
            "support_binding_sha256": review.support_binding_sha256,
            "load_name": prepared["load_named_selection"].name,
            "load_surface_keys": list(review.load_surface_keys),
            "load_named_selection_sha256": review.load_named_selection_sha256,
            "load_binding_sha256": review.load_binding_sha256,
        },
        "model_preparation": asdict(preparation),
        "pre_solve_review": {
            "schema": review.schema,
            "review_sha256": review.review_sha256,
            "acceptance_sha256": acceptance.acceptance_sha256,
            "state": acceptance.state,
        },
        "mesh": {"family": "TET10", "target_size_mm": review.mesh_target_size_mm, "nodes": int(mesh.nodes_mm.shape[0]), "elements": int(mesh.elements.shape[0]), "dimensions_mm": [float(v) for v in mesh.dimensions_mm]},
        "material": {"young_modulus_mpa": review.material_young_modulus_mpa, "poisson_ratio": review.material_poisson_ratio},
        "resultant_n": [float(v) for v in load],
        "checks": {"force_residual_n": force_residual_n, "moment_residual_nmm": moment_residual_nmm},
        "claims": {"converged": False, "industrial_validation": False, "ansys_equivalence": False},
        "artifacts": {"vtu": str(vtu_path), "viewer": str(viewer_path), "vtu_sha256": vtu_manifest.vtu_sha256, "viewer_sha256": viewer_manifest.html_sha256},
    }
    summary_path = output / "astermax_result_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary["artifacts"]["summary"] = str(summary_path)
    summary["_visual_preparation_payload"] = visual_preparation_payload(prepared)
    return summary


def run_step_analysis(
    step_path: str | Path,
    output_dir: str | Path,
    *,
    mesh_size_mm: float = 10.0,
    young_modulus_mpa: float = 200000.0,
    poisson_ratio: float = 0.30,
    resultant_n: tuple[float, float, float] = (0.0, -1000.0, 0.0),
    support_surface_keys: tuple[str, ...] = ("X_MIN",),
    load_surface_keys: tuple[str, ...] = ("X_MAX",),
) -> dict:
    prepared = prepare_step_analysis(
        step_path,
        mesh_size_mm=mesh_size_mm,
        young_modulus_mpa=young_modulus_mpa,
        poisson_ratio=poisson_ratio,
        resultant_n=resultant_n,
        support_surface_keys=support_surface_keys,
        load_surface_keys=load_surface_keys,
    )
    acceptance = accept_model_preparation(prepared["review"])
    return solve_prepared_analysis(prepared, acceptance, output_dir)


def _desktop_main() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("AsterMax PMV · Evidence-Gated TET10")
    root.geometry("1180x850")
    root.minsize(900, 720)

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=10, pady=10)
    frame = ttk.Frame(notebook, padding=18)
    notebook.add(frame, text="Analysis")
    bind_live_evidence = install_live_analysis_evidence_tab(notebook)
    bind_visual_preparation = install_visual_model_preparation_tab(notebook)
    bind_worst_quality = install_worst_element_quality_tab(notebook)
    install_native_credibility_tab(notebook)

    step_var = tk.StringVar()
    out_var = tk.StringVar(value=str((Path.home() / "AsterMaxResults").resolve()))
    mesh_var = tk.StringVar(value="10.0")
    e_var = tk.StringVar(value="200000.0")
    nu_var = tk.StringVar(value="0.30")
    fx_var = tk.StringVar(value="0.0")
    fy_var = tk.StringVar(value="-1000.0")
    fz_var = tk.StringVar(value="0.0")
    support_var = tk.StringVar(value="X_MIN")
    load_scope_var = tk.StringVar(value="X_MAX")
    status_var = tk.StringVar(value="Ready. Author Support/Load named scopes, then prepare the STEP model for review.")
    prepared_holder: dict[str, object] = {}

    frame.columnconfigure(1, weight=1)
    ttk.Label(frame, text="AsterMax PMV", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(frame, text="Named Selections → Prepare → Review → Accept & Solve · Linear static TET10 · N-mm-MPa").grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 16))

    def invalidate_review(*_args) -> None:
        prepared_holder.clear()
        solve_button.configure(state="disabled")

    def browse_step() -> None:
        path = filedialog.askopenfilename(filetypes=[("STEP geometry", "*.step *.stp"), ("All files", "*.*")])
        if path:
            step_var.set(path)
            invalidate_review()

    def browse_out() -> None:
        path = filedialog.askdirectory()
        if path:
            out_var.set(path)

    rows = [("STEP file", step_var, browse_step, "Browse"), ("Output folder", out_var, browse_out, "Browse"), ("Target mesh [mm]", mesh_var, None, None), ("Young's modulus [MPa]", e_var, None, None), ("Poisson ratio", nu_var, None, None), ("Resultant Fx [N]", fx_var, None, None), ("Resultant Fy [N]", fy_var, None, None), ("Resultant Fz [N]", fz_var, None, None)]
    for idx, (label, var, command, button_text) in enumerate(rows, start=2):
        ttk.Label(frame, text=label).grid(row=idx, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(frame, textvariable=var).grid(row=idx, column=1, sticky="ew", pady=4)
        if command:
            ttk.Button(frame, text=button_text, command=command).grid(row=idx, column=2, padx=(8, 0), pady=4)

    surface_values = ("X_MIN", "X_MAX", "Y_MIN", "Y_MAX", "Z_MIN", "Z_MAX")
    ttk.Label(frame, text="Support named face").grid(row=10, column=0, sticky="w", pady=4)
    support_combo = ttk.Combobox(frame, textvariable=support_var, values=surface_values, state="readonly")
    support_combo.grid(row=10, column=1, sticky="ew", pady=4)
    ttk.Label(frame, text="Load named face").grid(row=11, column=0, sticky="w", pady=4)
    load_combo = ttk.Combobox(frame, textvariable=load_scope_var, values=surface_values, state="readonly")
    load_combo.grid(row=11, column=1, sticky="ew", pady=4)
    support_combo.bind("<<ComboboxSelected>>", invalidate_review)
    load_combo.bind("<<ComboboxSelected>>", invalidate_review)

    warning = "C5.1: Support and Load are now persistent named selections bound to the exact STEP and reviewed TRI6 boundary groups before solve. The native authoring surface currently covers the six unique X/Y/Z MIN/MAX boundary faces; arbitrary sloped/internal face picking remains outside this increment. No industrial validation or ANSYS equivalence is claimed."
    ttk.Label(frame, text=warning, wraplength=980).grid(row=12, column=0, columnspan=3, sticky="ew", pady=(14, 8))
    progress = ttk.Progressbar(frame, mode="indeterminate")
    progress.grid(row=13, column=0, columnspan=3, sticky="ew", pady=(6, 8))
    ttk.Label(frame, textvariable=status_var, wraplength=980).grid(row=14, column=0, columnspan=3, sticky="w")
    prepare_button = ttk.Button(frame, text="1 · Prepare named scopes + model for review")
    prepare_button.grid(row=15, column=0, columnspan=3, sticky="ew", pady=(12, 4))
    solve_button = ttk.Button(frame, text="2 · Accept exact preparation & Solve", state="disabled")
    solve_button.grid(row=16, column=0, columnspan=3, sticky="ew", pady=(4, 6))

    def current_args() -> dict:
        support_key = support_var.get().strip().upper()
        load_key = load_scope_var.get().strip().upper()
        if support_key == load_key:
            raise ValueError("Support and Load named faces must be distinct")
        return {
            "step_path": step_var.get(),
            "mesh_size_mm": float(mesh_var.get()),
            "young_modulus_mpa": float(e_var.get()),
            "poisson_ratio": float(nu_var.get()),
            "resultant_n": (float(fx_var.get()), float(fy_var.get()), float(fz_var.get())),
            "support_surface_keys": (support_key,),
            "load_surface_keys": (load_key,),
        }

    def set_busy(busy: bool) -> None:
        prepare_button.configure(state="disabled" if busy else "normal")
        if busy:
            solve_button.configure(state="disabled")
            progress.start(10)
        else:
            progress.stop()

    def prepare_clicked() -> None:
        try:
            args = current_args()
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc)); return
        prepared_holder.clear(); set_busy(True)
        status_var.set("Capturing persistent named selections, meshing TET10 and cross-checking preparation evidence — no solve is running…")

        def worker() -> None:
            try:
                prepared = prepare_step_analysis(**args)
            except Exception as exc:
                root.after(0, lambda: (set_busy(False), status_var.set("Preparation failed; solve remains blocked."), messagebox.showerror("AsterMax preparation", str(exc))))
                return
            def finished() -> None:
                set_busy(False)
                try:
                    payload = visual_preparation_payload(prepared)
                    bind_visual_preparation(payload)
                    bind_worst_quality(payload)
                except Exception as exc:
                    status_var.set("Preparation completed but visual review binding failed; solve remains blocked.")
                    messagebox.showerror("AsterMax evidence", str(exc)); return
                prepared_holder["prepared"] = prepared
                prepared_holder["args"] = args
                solve_button.configure(state="normal")
                review = prepared["review"]
                status_var.set(f"REVIEW REQUIRED: Support={','.join(review.support_surface_keys)} · Load={','.join(review.load_surface_keys)} · {review.node_count} nodes / {review.tet10_count} TET10 · mean ratio min {review.tetra_mean_ratio_minimum:.3f}. Inspect evidence, then accept & solve.")
                notebook.select(3)
            root.after(0, finished)
        threading.Thread(target=worker, daemon=True).start()

    def solve_clicked() -> None:
        prepared = prepared_holder.get("prepared")
        original_args = prepared_holder.get("args")
        if prepared is None or original_args is None:
            messagebox.showerror("AsterMax", "Prepare the model first."); return
        try:
            now = current_args()
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc)); return
        if now != original_args:
            prepared_holder.clear(); solve_button.configure(state="disabled")
            status_var.set("Analysis inputs or named selections changed after review. Prepare the model again.")
            messagebox.showerror("Review invalidated", "STEP/material/mesh/load/named-selection inputs changed after preparation. Re-run Prepare before Solve."); return
        acceptance = accept_model_preparation(prepared["review"])
        set_busy(True); status_var.set("MODEL_PREPARATION_ACCEPTED · solving exact reviewed named-selection bindings…")

        def worker() -> None:
            try:
                summary = solve_prepared_analysis(prepared, acceptance, out_var.get())
            except Exception as exc:
                root.after(0, lambda: (set_busy(False), status_var.set("Solve blocked or failed."), messagebox.showerror("AsterMax", str(exc))))
                return
            def finished() -> None:
                set_busy(False); solve_button.configure(state="disabled"); prepared_holder.clear()
                try:
                    bind_live_evidence(summary)
                    payload = summary["_visual_preparation_payload"]
                    bind_visual_preparation(payload)
                    bind_worst_quality(payload)
                except Exception as exc:
                    status_var.set("Solve completed but evidence binding failed."); messagebox.showerror("AsterMax evidence", str(exc)); return
                checks = summary["checks"]
                status_var.set(f"Completed accepted named-scope model: {summary['mesh']['nodes']} nodes / {summary['mesh']['elements']} TET10 · force residual {checks['force_residual_n']:.3e} N · moment residual {checks['moment_residual_nmm']:.3e} N·mm")
                webbrowser.open(Path(summary["artifacts"]["viewer"]).as_uri())
                messagebox.showinfo("AsterMax", "Solve completed through persistent Support/Load named-selection bindings. Current-model evidence remains bounded; arbitrary-model convergence and ANSYS equivalence are unclaimed.")
            root.after(0, finished)
        threading.Thread(target=worker, daemon=True).start()

    prepare_button.configure(command=prepare_clicked)
    solve_button.configure(command=solve_clicked)
    root.mainloop()
    return 0


def main() -> int:
    return _desktop_main()


if __name__ == "__main__":
    raise SystemExit(main())
