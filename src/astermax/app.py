from __future__ import annotations

import json
import threading
import webbrowser
from pathlib import Path

import numpy as np

from .fea.gmsh_bridge import (
    distribute_resultant_on_tri6,
    fixed_dofs_for_nodes,
    force_and_moment,
    mesh_step_tet10,
    unique_surface_nodes,
)
from .fea.native_credibility import install_native_credibility_tab
from .fea.postprocess_tet10 import write_tet10_linear_static_vtu
from .fea.solver import solve_linear_static_tet10
from .fea.tet4 import IsotropicMaterial
from .fea.viewer_tet10 import write_tet10_offline_viewer

RESULT_CLASS = "PMV_UNCONVERGED_USER_MODEL_NOT_INDUSTRIAL_RESULT"


def run_step_analysis(step_path: str | Path, output_dir: str | Path, *, mesh_size_mm: float = 10.0, young_modulus_mpa: float = 200000.0, poisson_ratio: float = 0.30, resultant_n: tuple[float, float, float] = (0.0, -1000.0, 0.0)) -> dict:
    source = Path(step_path).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"STEP file not found: {source}")
    if source.suffix.lower() not in {".step", ".stp"}:
        raise ValueError("source geometry must be a .step or .stp file")
    if not np.isfinite(mesh_size_mm) or mesh_size_mm <= 0.0:
        raise ValueError("mesh_size_mm must be finite and positive")
    if not np.isfinite(young_modulus_mpa) or young_modulus_mpa <= 0.0:
        raise ValueError("young_modulus_mpa must be finite and positive")
    if not np.isfinite(poisson_ratio) or not (-1.0 < poisson_ratio < 0.5):
        raise ValueError("poisson_ratio must satisfy -1 < nu < 0.5")
    load = np.asarray(resultant_n, dtype=float)
    if load.shape != (3,) or not np.all(np.isfinite(load)):
        raise ValueError("resultant_n must contain three finite components")
    if float(np.linalg.norm(load)) == 0.0:
        raise ValueError("resultant_n must be non-zero")

    output.mkdir(parents=True, exist_ok=True)
    mesh = mesh_step_tet10(source, float(mesh_size_mm))
    material = IsotropicMaterial(float(young_modulus_mpa), float(poisson_ratio))
    fixed_nodes = unique_surface_nodes(mesh.surface_triangles["X_MIN"])
    fixed_dofs = fixed_dofs_for_nodes(fixed_nodes)
    loads = distribute_resultant_on_tri6(mesh.nodes_mm, mesh.surface_triangles["X_MAX"], load)
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
        "units": {"length": "mm", "force": "N", "stress": "MPa"},
        "scope_contract": {"constraint": "X_MIN_FIXED_ALL_TRANSLATIONS", "load": "X_MAX_CONSISTENT_TRI6_RESULTANT"},
        "mesh": {"family": "TET10", "target_size_mm": float(mesh_size_mm), "nodes": int(mesh.nodes_mm.shape[0]), "elements": int(mesh.elements.shape[0]), "dimensions_mm": [float(v) for v in mesh.dimensions_mm]},
        "material": {"young_modulus_mpa": float(young_modulus_mpa), "poisson_ratio": float(poisson_ratio)},
        "resultant_n": [float(v) for v in load],
        "checks": {"force_residual_n": force_residual_n, "moment_residual_nmm": moment_residual_nmm},
        "claims": {"converged": False, "industrial_validation": False, "ansys_equivalence": False},
        "artifacts": {"vtu": str(vtu_path), "viewer": str(viewer_path), "vtu_sha256": vtu_manifest.vtu_sha256, "viewer_sha256": viewer_manifest.html_sha256},
    }
    summary_path = output / "astermax_result_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary["artifacts"]["summary"] = str(summary_path)
    return summary


def _desktop_main() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("AsterMax PMV · TET10 Verification")
    root.geometry("900x700")
    root.minsize(780, 620)

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=10, pady=10)
    frame = ttk.Frame(notebook, padding=18)
    notebook.add(frame, text="Analysis")
    install_native_credibility_tab(notebook)

    step_var = tk.StringVar()
    out_var = tk.StringVar(value=str((Path.home() / "AsterMaxResults").resolve()))
    mesh_var = tk.StringVar(value="10.0")
    e_var = tk.StringVar(value="200000.0")
    nu_var = tk.StringVar(value="0.30")
    fx_var = tk.StringVar(value="0.0")
    fy_var = tk.StringVar(value="-1000.0")
    fz_var = tk.StringVar(value="0.0")
    status_var = tk.StringVar(value="Ready. Select one STEP solid in millimetres.")

    frame.columnconfigure(1, weight=1)
    ttk.Label(frame, text="AsterMax PMV", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(frame, text="Linear static TET10 · N-mm-MPa · verification build").grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 16))

    def browse_step() -> None:
        path = filedialog.askopenfilename(filetypes=[("STEP geometry", "*.step *.stp"), ("All files", "*.*")])
        if path:
            step_var.set(path)

    def browse_out() -> None:
        path = filedialog.askdirectory()
        if path:
            out_var.set(path)

    rows = [("STEP file", step_var, browse_step, "Browse"), ("Output folder", out_var, browse_out, "Browse"), ("Target mesh [mm]", mesh_var, None, None), ("Young's modulus [MPa]", e_var, None, None), ("Poisson ratio", nu_var, None, None), ("Resultant Fx [N]", fx_var, None, None), ("Resultant Fy [N]", fy_var, None, None), ("Resultant Fz [N]", fz_var, None, None)]
    for idx, (label, var, command, button_text) in enumerate(rows, start=2):
        ttk.Label(frame, text=label).grid(row=idx, column=0, sticky="w", padx=(0, 10), pady=5)
        ttk.Entry(frame, textvariable=var).grid(row=idx, column=1, sticky="ew", pady=5)
        if command:
            ttk.Button(frame, text=button_text, command=command).grid(row=idx, column=2, padx=(8, 0), pady=5)

    warning = "PMV scope: exactly one STEP solid; X_MIN is fixed and the requested resultant is applied on X_MAX. Arbitrary user models are exported with CONVERGED=false and INDUSTRIAL_VALIDATION=false. The Credibility tab accepts only validated fixture evidence and cannot upgrade these claims."
    ttk.Label(frame, text=warning, wraplength=760).grid(row=10, column=0, columnspan=3, sticky="ew", pady=(16, 10))
    progress = ttk.Progressbar(frame, mode="indeterminate")
    progress.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(6, 8))
    ttk.Label(frame, textvariable=status_var, wraplength=760).grid(row=12, column=0, columnspan=3, sticky="w")
    run_button = ttk.Button(frame, text="Run TET10 analysis")
    run_button.grid(row=13, column=0, columnspan=3, sticky="ew", pady=(16, 6))

    def set_busy(busy: bool) -> None:
        run_button.configure(state="disabled" if busy else "normal")
        if busy:
            progress.start(10)
        else:
            progress.stop()

    def run_clicked() -> None:
        try:
            args = {"step_path": step_var.get(), "output_dir": out_var.get(), "mesh_size_mm": float(mesh_var.get()), "young_modulus_mpa": float(e_var.get()), "poisson_ratio": float(nu_var.get()), "resultant_n": (float(fx_var.get()), float(fy_var.get()), float(fz_var.get()))}
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc))
            return
        set_busy(True)
        status_var.set("Meshing and solving…")

        def worker() -> None:
            try:
                summary = run_step_analysis(**args)
            except Exception as exc:
                root.after(0, lambda: (set_busy(False), status_var.set("Analysis failed."), messagebox.showerror("AsterMax", str(exc))))
                return

            def finished() -> None:
                set_busy(False)
                checks = summary["checks"]
                status_var.set(f"Completed: {summary['mesh']['nodes']} nodes / {summary['mesh']['elements']} TET10 · force residual {checks['force_residual_n']:.3e} N · moment residual {checks['moment_residual_nmm']:.3e} N·mm")
                webbrowser.open(Path(summary["artifacts"]["viewer"]).as_uri())
                messagebox.showinfo("AsterMax", "Analysis completed. Offline viewer opened. Results remain marked un-converged for arbitrary user geometry.")

            root.after(0, finished)

        threading.Thread(target=worker, daemon=True).start()

    run_button.configure(command=run_clicked)
    root.mainloop()
    return 0


def main() -> int:
    return _desktop_main()


if __name__ == "__main__":
    raise SystemExit(main())
