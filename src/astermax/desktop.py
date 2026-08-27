from __future__ import annotations

import threading
import webbrowser
from pathlib import Path

from .face_picker import write_face_picker_html
from .project import read_project, resolve_project_geometry
from .project_runner import run_project
from .project_tree import assert_tree_does_not_upgrade_claims, build_project_tree


def main() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("AsterMax PMV · Evidence-first CAE Workspace")
    root.geometry("1040x640")
    root.minsize(900, 560)

    step_var = tk.StringVar()
    project_var = tk.StringVar()
    out_var = tk.StringVar(value=str((Path.home() / "AsterMaxResults").resolve()))
    status = tk.StringVar(value="1. Select a STEP solid in millimetres.")
    current_summary: dict | None = None
    tree_artifacts: dict[str, str] = {}

    outer = ttk.Frame(root, padding=14)
    outer.pack(fill="both", expand=True)
    ttk.Label(outer, text="AsterMax PMV", font=("Segoe UI", 21, "bold")).pack(anchor="w")
    ttk.Label(
        outer,
        text="Evidence-first CAE workspace · persistent CAD scopes · quadratic TET10 · N-mm-MPa",
        foreground="#5f6f88",
    ).pack(anchor="w", pady=(0, 12))

    panes = ttk.Panedwindow(outer, orient="horizontal")
    panes.pack(fill="both", expand=True)

    nav = ttk.Frame(panes, padding=(0, 0, 10, 0))
    work = ttk.Frame(panes, padding=(10, 0, 0, 0))
    panes.add(nav, weight=1)
    panes.add(work, weight=3)

    ttk.Label(nav, text="Project", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 6))
    tree = ttk.Treeview(nav, columns=("state",), show="tree headings", selectmode="browse", height=16)
    tree.heading("#0", text="CAE object")
    tree.heading("state", text="State")
    tree.column("#0", width=150, stretch=True)
    tree.column("state", width=130, stretch=False)
    tree.pack(fill="both", expand=True)
    detail_var = tk.StringVar(value="Select a project-tree item to inspect its evidence boundary.")
    ttk.Label(nav, textvariable=detail_var, wraplength=300, foreground="#5f6f88").pack(fill="x", pady=(8, 0))

    work.columnconfigure(1, weight=1)
    ttk.Label(work, text="Model preparation", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

    def refresh_tree(summary: dict | None = None) -> None:
        nonlocal current_summary
        current_summary = summary
        tree.delete(*tree.get_children())
        tree_artifacts.clear()
        nodes = build_project_tree(summary)
        if summary is not None:
            assert_tree_does_not_upgrade_claims(summary, nodes)
        for node in nodes:
            tree.insert("", "end", iid=node.key, text=node.label, values=(node.state,))
            if node.artifact:
                tree_artifacts[node.key] = node.artifact
        detail_var.set("Select Results, Mesh or Evidence and double-click to open the verified artifact.")

    def on_tree_select(_event=None) -> None:
        selected = tree.selection()
        if not selected:
            return
        key = selected[0]
        node = next((n for n in build_project_tree(current_summary) if n.key == key), None)
        if node is not None:
            detail_var.set(f"{node.label} · {node.state}\n{node.detail}")

    def on_tree_open(_event=None) -> None:
        selected = tree.selection()
        if not selected:
            return
        artifact = tree_artifacts.get(selected[0])
        if artifact and Path(artifact).is_file():
            webbrowser.open(Path(artifact).resolve().as_uri())

    tree.bind("<<TreeviewSelect>>", on_tree_select)
    tree.bind("<Double-1>", on_tree_open)
    refresh_tree()

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
            refresh_tree()
            tree.set("geometry", "state", "VERIFIED")
            detail_var.set("Geometry · VERIFIED\nSTEP provenance resolved from the .astermax project. Solve to populate mesh, results and evidence.")

    def browse_out() -> None:
        p = filedialog.askdirectory()
        if p:
            out_var.set(p)

    ttk.Label(work, text="STEP geometry").grid(row=1, column=0, sticky="w", pady=6)
    ttk.Entry(work, textvariable=step_var).grid(row=1, column=1, sticky="ew", pady=6)
    ttk.Button(work, text="Browse", command=browse_step).grid(row=1, column=2, padx=(8, 0))

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
        status.set(f"3D picker opened: {info['faces']} CAD faces. Export the .astermax project, then open it here.")

    ttk.Button(work, text="Prepare model · 3D CAD face picker", command=prepare).grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 14))

    ttk.Label(work, text="AsterMax project").grid(row=3, column=0, sticky="w", pady=6)
    ttk.Entry(work, textvariable=project_var).grid(row=3, column=1, sticky="ew", pady=6)
    ttk.Button(work, text="Open", command=browse_project).grid(row=3, column=2, padx=(8, 0))
    ttk.Label(work, text="Results folder").grid(row=4, column=0, sticky="w", pady=6)
    ttk.Entry(work, textvariable=out_var).grid(row=4, column=1, sticky="ew", pady=6)
    ttk.Button(work, text="Browse", command=browse_out).grid(row=4, column=2, padx=(8, 0))

    progress = ttk.Progressbar(work, mode="indeterminate")
    progress.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(18, 8))
    ttk.Label(work, textvariable=status, wraplength=650).grid(row=6, column=0, columnspan=3, sticky="w")
    solve = ttk.Button(work, text="Solve named-support TET10 project")
    solve.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(18, 8))

    ttk.Separator(work).grid(row=8, column=0, columnspan=3, sticky="ew", pady=12)
    ttk.Label(work, text="Evidence boundary", font=("Segoe UI", 11, "bold")).grid(row=9, column=0, columnspan=3, sticky="w")
    ttk.Label(
        work,
        text=(
            "The native tree is a navigation and evidence surface only. Arbitrary projects remain "
            "CONVERGED=false, INDUSTRIAL_VALIDATION=false, ANSYS_EQUIVALENCE=false and CURVED_TET10=false "
            "until separate verification/validation gates demonstrate those claims."
        ),
        wraplength=650,
        foreground="#7a5b32",
    ).grid(row=10, column=0, columnspan=3, sticky="w", pady=(5, 0))

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
        status.set("Resolving CAD selections, auditing TET10 geometry, meshing and solving…")

        def worker() -> None:
            try:
                result = run_project(project, Path(out_var.get()).expanduser())
                nodes = build_project_tree(result)
                assert_tree_does_not_upgrade_claims(result, nodes)
            except Exception as exc:
                root.after(0, lambda: (set_busy(False), status.set("Solve failed closed."), messagebox.showerror("AsterMax solve", str(exc))))
                return

            def done() -> None:
                set_busy(False)
                m, c = result["mesh"], result["checks"]
                refresh_tree(result)
                status.set(
                    f"Completed · {m['nodes']} nodes / {m['elements']} TET10 · SUPPORT {m['support_tri6']} TRI6 · "
                    f"LOAD {m['load_tri6']} TRI6 · |ΣF| {c['force_residual_n']:.3e} N · open Results/Evidence from the project tree"
                )
                evidence = result["artifacts"].get("results_evidence_workspace")
                if evidence and Path(evidence).is_file():
                    webbrowser.open(Path(evidence).resolve().as_uri())
            root.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    solve.configure(command=solve_clicked)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
