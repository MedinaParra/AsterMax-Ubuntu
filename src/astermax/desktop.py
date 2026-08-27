from __future__ import annotations

import threading
import webbrowser
from pathlib import Path

from .face_picker import write_face_picker_html
from .project import read_project, resolve_project_geometry
from .project_runner import run_project


def main() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("AsterMax PMV · CAD → TET10 → Results")
    root.geometry("760x520")
    root.minsize(700, 480)

    step_var = tk.StringVar()
    project_var = tk.StringVar()
    out_var = tk.StringVar(value=str((Path.home() / "AsterMaxResults").resolve()))
    status = tk.StringVar(value="1. Select a STEP solid in millimetres.")

    frame = ttk.Frame(root, padding=20)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(1, weight=1)
    ttk.Label(frame, text="AsterMax PMV", font=("Segoe UI", 21, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(frame, text="Persistent CAD selections · quadratic TET10 · N-mm-MPa", foreground="#5f6f88").grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 20))

    def browse_step() -> None:
        p = filedialog.askopenfilename(filetypes=[("STEP geometry", "*.step *.stp")])
        if p:
            step_var.set(p)
            status.set("2. Prepare the model and assign SUPPORT / LOAD by clicking CAD faces.")

    def browse_project() -> None:
        p = filedialog.askopenfilename(filetypes=[("AsterMax project", "*.astermax")])
        if p:
            try:
                project = read_project(p)
                geometry = resolve_project_geometry(p, project)
            except Exception as exc:
                messagebox.showerror("AsterMax project", str(exc))
                return
            project_var.set(p)
            step_var.set(str(geometry))
            status.set("Project provenance verified. Ready to solve.")

    def browse_out() -> None:
        p = filedialog.askdirectory()
        if p:
            out_var.set(p)

    ttk.Label(frame, text="STEP geometry").grid(row=2, column=0, sticky="w", pady=6)
    ttk.Entry(frame, textvariable=step_var).grid(row=2, column=1, sticky="ew", pady=6)
    ttk.Button(frame, text="Browse", command=browse_step).grid(row=2, column=2, padx=(8, 0))

    def prepare() -> None:
        source = Path(step_var.get()).expanduser()
        if not source.is_file():
            messagebox.showerror("AsterMax", "Select an existing STEP/STP file first.")
            return
        target = Path(out_var.get()).expanduser().resolve() / "astermax_model_prep.html"
        try:
            info = write_face_picker_html(source, target)
        except Exception as exc:
            messagebox.showerror("Model preparation", str(exc))
            return
        webbrowser.open(target.as_uri())
        status.set(f"3D picker opened: {info['faces']} CAD faces. Download the .astermax file beside the STEP, then open it here.")

    ttk.Button(frame, text="Prepare model · 3D CAD face picker", command=prepare).grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 14))

    ttk.Label(frame, text="AsterMax project").grid(row=4, column=0, sticky="w", pady=6)
    ttk.Entry(frame, textvariable=project_var).grid(row=4, column=1, sticky="ew", pady=6)
    ttk.Button(frame, text="Open", command=browse_project).grid(row=4, column=2, padx=(8, 0))
    ttk.Label(frame, text="Results folder").grid(row=5, column=0, sticky="w", pady=6)
    ttk.Entry(frame, textvariable=out_var).grid(row=5, column=1, sticky="ew", pady=6)
    ttk.Button(frame, text="Browse", command=browse_out).grid(row=5, column=2, padx=(8, 0))

    progress = ttk.Progressbar(frame, mode="indeterminate")
    progress.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(18, 8))
    ttk.Label(frame, textvariable=status, wraplength=700).grid(row=7, column=0, columnspan=3, sticky="w")
    solve = ttk.Button(frame, text="Solve named-support TET10 project")
    solve.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(18, 8))

    ttk.Label(
        frame,
        text="Verification boundary: arbitrary projects remain CONVERGED=false, INDUSTRIAL_VALIDATION=false and ANSYS_EQUIVALENCE=false until separate physical validation gates exist.",
        wraplength=700,
        foreground="#7a5b32",
    ).grid(row=9, column=0, columnspan=3, sticky="w", pady=(8, 0))

    def set_busy(value: bool) -> None:
        solve.configure(state="disabled" if value else "normal")
        if value:
            progress.start(10)
        else:
            progress.stop()

    def solve_clicked() -> None:
        project = Path(project_var.get()).expanduser()
        if not project.is_file():
            messagebox.showerror("AsterMax", "Open a valid .astermax project first.")
            return
        set_busy(True)
        status.set("Resolving CAD selections, meshing TET10 and solving…")

        def worker() -> None:
            try:
                result = run_project(project, Path(out_var.get()).expanduser())
            except Exception as exc:
                root.after(0, lambda: (set_busy(False), status.set("Solve failed closed."), messagebox.showerror("AsterMax solve", str(exc))))
                return

            def done() -> None:
                set_busy(False)
                m, c = result["mesh"], result["checks"]
                status.set(f"Completed · {m['nodes']} nodes / {m['elements']} TET10 · SUPPORT {m['support_tri6']} TRI6 · LOAD {m['load_tri6']} TRI6 · |ΣF| {c['force_residual_n']:.3e} N")
                webbrowser.open(Path(result["artifacts"]["viewer"]).as_uri())
            root.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    solve.configure(command=solve_clicked)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
