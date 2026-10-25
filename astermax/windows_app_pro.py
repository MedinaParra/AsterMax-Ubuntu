"""Professional Windows shell for the AsterMax PMV.

This module is presentation-only: engineering validation, STEP unit gating,
model preparation approval and solving stay in the verified windows_app core.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import webbrowser

from .model_preparation import approve_static_preparation, preparation_summary
from .windows_app import (
    StepCaseConfig,
    WindowsAppError,
    _parse_force,
    build_windows_preparation,
    find_gmsh_for_windows,
    run_windows_step_case,
    validate_step_mm_file,
)


def launch_desktop() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    BG = "#101317"
    PANEL = "#171B21"
    PANEL_2 = "#1D232B"
    BORDER = "#2A313B"
    TEXT = "#F2F5F8"
    MUTED = "#98A4B3"
    ACCENT = "#36A3FF"
    SUCCESS = "#4ED69C"
    WARNING = "#FFB454"
    DANGER = "#FF6B6B"

    root = tk.Tk()
    root.title("AsterMax — Engineering Intelligence / Windows PMV")
    root.geometry("1440x900")
    root.minsize(1180, 760)
    root.configure(bg=BG)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("Panel2.TFrame", background=PANEL_2)
    style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
    style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED)
    style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED)
    style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI Semibold", 24))
    style.configure("Section.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI Semibold", 13))
    style.configure("Metric.TLabel", background=PANEL_2, foreground=TEXT, font=("Segoe UI Semibold", 15))
    style.configure("Accent.TButton", background=ACCENT, foreground="white", borderwidth=0, padding=(14, 10), font=("Segoe UI Semibold", 10))
    style.map("Accent.TButton", background=[("active", "#59B3FF"), ("disabled", "#30475A")])
    style.configure("Secondary.TButton", background=PANEL_2, foreground=TEXT, bordercolor=BORDER, padding=(12, 9))
    style.map("Secondary.TButton", background=[("active", "#26313D")])
    style.configure("Side.TButton", background=BG, foreground=MUTED, borderwidth=0, anchor="w", padding=(16, 12), font=("Segoe UI", 10))
    style.map("Side.TButton", background=[("active", PANEL_2)], foreground=[("active", TEXT)])
    style.configure("TEntry", fieldbackground="#0F1216", foreground=TEXT, insertcolor=TEXT, bordercolor=BORDER, padding=7)
    style.configure("TCombobox", fieldbackground="#0F1216", foreground=TEXT, bordercolor=BORDER, padding=6)
    style.map("TCombobox", fieldbackground=[("readonly", "#0F1216")], foreground=[("readonly", TEXT)])
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(18, 10), borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", PANEL_2)], foreground=[("selected", TEXT)])

    state = {"step": None, "preparation": None, "last_output": None, "last_result": None}
    status_var = tk.StringVar(value="Ready — import a STEP model in millimetres")
    step_var = tk.StringVar(value="No model loaded")
    unit_var = tk.StringVar(value="UNIT GATE · unresolved")
    gmsh_var = tk.StringVar(value="GMSH · checking")
    axis_var = tk.StringVar(value="x")
    fixed_side_var = tk.StringVar(value="min")
    load_side_var = tk.StringVar(value="max")
    fx_var, fy_var, fz_var = tk.StringVar(value="100"), tk.StringVar(value="0"), tk.StringVar(value="0")
    mesh_var = tk.StringVar(value="2.0")
    young_var = tk.StringVar(value="210000")
    poisson_var = tk.StringVar(value="0.30")
    quality_var = tk.StringVar(value="0.05")
    approver_var = tk.StringVar(value="")
    approval_var = tk.StringVar(value="NOT REVIEWED")
    node_metric = tk.StringVar(value="—")
    tet_metric = tk.StringVar(value="—")
    disp_metric = tk.StringVar(value="—")
    vm_metric = tk.StringVar(value="—")

    top = ttk.Frame(root, style="Panel.TFrame", padding=(20, 13))
    top.pack(fill="x")
    brand = ttk.Frame(top, style="Panel.TFrame")
    brand.pack(side="left")
    ttk.Label(brand, text="ASTERMAX", style="Panel.TLabel", font=("Segoe UI Black", 17)).pack(side="left")
    ttk.Label(brand, text="  ENGINEERING INTELLIGENCE", style="PanelMuted.TLabel", font=("Segoe UI", 9)).pack(side="left", padx=(4, 0))
    ttk.Label(top, textvariable=gmsh_var, style="PanelMuted.TLabel").pack(side="right")
    ttk.Label(top, text="PMV · WINDOWS · mm–N–MPa", style="PanelMuted.TLabel").pack(side="right", padx=24)

    body = ttk.Frame(root)
    body.pack(fill="both", expand=True)

    sidebar = ttk.Frame(body, style="Panel.TFrame", width=220, padding=(10, 18))
    sidebar.pack(side="left", fill="y")
    sidebar.pack_propagate(False)
    ttk.Label(sidebar, text="WORKFLOW", style="PanelMuted.TLabel", font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=12, pady=(0, 8))

    workspace = ttk.Frame(body, padding=(18, 16))
    workspace.pack(side="left", fill="both", expand=True)

    notebook = ttk.Notebook(workspace)
    notebook.pack(fill="both", expand=True)
    geometry = ttk.Frame(notebook, style="Panel.TFrame", padding=22)
    setup = ttk.Frame(notebook, style="Panel.TFrame", padding=22)
    solve_tab = ttk.Frame(notebook, style="Panel.TFrame", padding=22)
    results = ttk.Frame(notebook, style="Panel.TFrame", padding=22)
    notebook.add(geometry, text="Geometry")
    notebook.add(setup, text="Model Setup")
    notebook.add(solve_tab, text="Solve")
    notebook.add(results, text="Results")

    def nav(index: int) -> None:
        notebook.select(index)

    for label, index in (("01   Geometry", 0), ("02   Model Setup", 1), ("03   Mesh & Solve", 2), ("04   Results", 3)):
        ttk.Button(sidebar, text=label, style="Side.TButton", command=lambda i=index: nav(i)).pack(fill="x", pady=2)
    ttk.Separator(sidebar, orient="horizontal").pack(fill="x", padx=10, pady=18)
    ttk.Label(sidebar, text="TRUST PIPELINE", style="PanelMuted.TLabel", font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=12)
    ttk.Label(sidebar, text="STEP mm gate\nEngineering intent\nHuman approval\nMesh quality\nEquilibrium / residual\nSHA-256 evidence", style="PanelMuted.TLabel", justify="left").pack(anchor="w", padx=12, pady=10)

    def card(parent, title: str, value_var: tk.StringVar, subtitle: str):
        f = ttk.Frame(parent, style="Panel2.TFrame", padding=14)
        ttk.Label(f, text=title.upper(), style="PanelMuted.TLabel", background=PANEL_2, font=("Segoe UI Semibold", 8)).pack(anchor="w")
        ttk.Label(f, textvariable=value_var, style="Metric.TLabel").pack(anchor="w", pady=(4, 2))
        ttk.Label(f, text=subtitle, style="PanelMuted.TLabel", background=PANEL_2, font=("Segoe UI", 8)).pack(anchor="w")
        return f

    hero = ttk.Frame(geometry, style="Panel.TFrame")
    hero.pack(fill="x")
    ttk.Label(hero, text="Geometry workspace", style="Section.TLabel", font=("Segoe UI Semibold", 20)).pack(anchor="w")
    ttk.Label(hero, text="Import verified STEP geometry. AsterMax blocks unresolved or non-mm files before analysis.", style="PanelMuted.TLabel").pack(anchor="w", pady=(4, 16))

    drop = tk.Frame(geometry, bg="#11161C", highlightthickness=1, highlightbackground=BORDER, height=270)
    drop.pack(fill="x", pady=(0, 16))
    drop.pack_propagate(False)
    tk.Label(drop, text="◈", fg=ACCENT, bg="#11161C", font=("Segoe UI", 42)).pack(pady=(42, 6))
    tk.Label(drop, text="Import CAD / STEP", fg=TEXT, bg="#11161C", font=("Segoe UI Semibold", 17)).pack()
    tk.Label(drop, text="STEP / STP · analysis basis locked to millimetres", fg=MUTED, bg="#11161C", font=("Segoe UI", 10)).pack(pady=6)

    def log(text: str) -> None:
        console.configure(state="normal")
        console.insert("end", text.rstrip() + "\n")
        console.see("end")
        console.configure(state="disabled")

    def invalidate_approval(*_args) -> None:
        state["preparation"] = None
        approval_var.set("NOT REVIEWED")

    for variable in (axis_var, fixed_side_var, load_side_var, fx_var, fy_var, fz_var, mesh_var, young_var, poisson_var, quality_var):
        variable.trace_add("write", invalidate_approval)

    def choose_step() -> None:
        path = filedialog.askopenfilename(title="Import STEP geometry", filetypes=[("STEP files", "*.step *.stp"), ("All files", "*.*")])
        if not path:
            return
        source = Path(path)
        try:
            unit = validate_step_mm_file(source)
        except WindowsAppError as exc:
            state["step"] = None
            step_var.set(source.name)
            unit_var.set("UNIT GATE · BLOCKED")
            status_var.set("STEP rejected by unit trust gate")
            messagebox.showerror("AsterMax STEP gate", str(exc))
            return
        state["step"] = source
        state["preparation"] = None
        step_var.set(source.name)
        unit_var.set(f"UNIT GATE · {unit.upper()} · PASSED")
        status_var.set("Geometry verified — continue to model setup")
        log(f"STEP imported: {source}")
        log(f"Unit invariant passed: {unit} / mm-N-MPa")
        notebook.select(setup)

    ttk.Button(drop, text="IMPORT STEP / STP", style="Accent.TButton", command=choose_step).pack(pady=14)
    geometry_info = ttk.Frame(geometry, style="Panel.TFrame")
    geometry_info.pack(fill="x")
    ttk.Label(geometry_info, textvariable=step_var, style="Panel.TLabel", font=("Segoe UI Semibold", 11)).pack(side="left")
    ttk.Label(geometry_info, textvariable=unit_var, style="PanelMuted.TLabel").pack(side="right")

    ttk.Label(setup, text="Model setup", style="Section.TLabel", font=("Segoe UI Semibold", 20)).pack(anchor="w")
    ttk.Label(setup, text="Define semantic boundary intent, load, mesh and material. Any edit invalidates approval.", style="PanelMuted.TLabel").pack(anchor="w", pady=(4, 18))
    form = ttk.Frame(setup, style="Panel2.TFrame", padding=18)
    form.pack(fill="x")
    fields_left = ttk.Frame(form, style="Panel2.TFrame")
    fields_left.pack(side="left", fill="both", expand=True, padx=(0, 16))
    fields_right = ttk.Frame(form, style="Panel2.TFrame")
    fields_right.pack(side="left", fill="both", expand=True)

    def field(parent, label: str, variable, combo=None):
        row = ttk.Frame(parent, style="Panel2.TFrame")
        row.pack(fill="x", pady=6)
        ttk.Label(row, text=label, style="PanelMuted.TLabel", background=PANEL_2, width=24).pack(side="left")
        if combo:
            ttk.Combobox(row, textvariable=variable, values=combo, state="readonly", width=16).pack(side="left")
        else:
            ttk.Entry(row, textvariable=variable, width=18).pack(side="left")

    field(fields_left, "Semantic axis", axis_var, ("x", "y", "z"))
    field(fields_left, "FIXED side", fixed_side_var, ("min", "max"))
    field(fields_left, "LOAD side", load_side_var, ("min", "max"))
    field(fields_left, "Mesh size [mm]", mesh_var)
    field(fields_right, "Force Fx [N]", fx_var)
    field(fields_right, "Force Fy [N]", fy_var)
    field(fields_right, "Force Fz [N]", fz_var)
    field(fields_right, "Young E [MPa]", young_var)
    field(fields_right, "Poisson ν", poisson_var)
    field(fields_right, "Min TET4 quality", quality_var)

    approval = ttk.Frame(setup, style="Panel.TFrame")
    approval.pack(fill="x", pady=(18, 0))
    ttk.Label(approval, text="ENGINEER APPROVAL", style="PanelMuted.TLabel", font=("Segoe UI Semibold", 9)).pack(anchor="w")
    approve_line = ttk.Frame(approval, style="Panel.TFrame")
    approve_line.pack(fill="x", pady=8)
    ttk.Entry(approve_line, textvariable=approver_var, width=32).pack(side="left")
    approval_badge = tk.Label(approve_line, textvariable=approval_var, fg=WARNING, bg=PANEL, font=("Segoe UI Semibold", 9), padx=12)
    approval_badge.pack(side="left")

    def current_config() -> StepCaseConfig:
        source = state.get("step")
        if source is None:
            raise WindowsAppError("Import and validate a STEP file first")
        force = _parse_force((fx_var, fy_var, fz_var))
        output = source.parent / f"{source.stem}_AsterMax_Evidence"
        config = StepCaseConfig(source, output, axis_var.get(), fixed_side_var.get(), load_side_var.get(), force,
                                float(mesh_var.get()), float(young_var.get()), float(poisson_var.get()), float(quality_var.get()))
        config.validate()
        return config

    def review_and_approve() -> None:
        try:
            config = current_config()
            case = build_windows_preparation(config)
            if not approver_var.get().strip():
                raise WindowsAppError("Enter the engineer / approver identity")
            approve_static_preparation(case, approved_by=approver_var.get().strip())
            summary = preparation_summary(case)
        except (ValueError, WindowsAppError) as exc:
            messagebox.showerror("AsterMax approval gate", str(exc))
            return
        state["preparation"] = summary
        approval_var.set("PASSED · " + summary["engineering_intent_sha256"][:12])
        approval_badge.configure(fg=SUCCESS)
        status_var.set("Model preparation approved — solve enabled")
        log("ENGINEER APPROVAL PASSED")
        log(f"Engineering intent: {summary['engineering_intent_sha256']}")
        notebook.select(solve_tab)

    ttk.Button(approve_line, text="REVIEW + APPROVE", style="Accent.TButton", command=review_and_approve).pack(side="right")

    ttk.Label(solve_tab, text="Mesh & solve", style="Section.TLabel", font=("Segoe UI Semibold", 20)).pack(anchor="w")
    ttk.Label(solve_tab, text="Verified pipeline: STEP → semantic BC/load → Gmsh TET4 → quality gate → linear static FEA → residual → evidence.", style="PanelMuted.TLabel").pack(anchor="w", pady=(4, 14))
    console = tk.Text(solve_tab, height=22, state="disabled", bg="#0B0E12", fg="#C9D4E0", insertbackground=TEXT,
                      relief="flat", font=("Cascadia Mono", 9), padx=12, pady=10)
    console.pack(fill="both", expand=True)
    solve_bar = ttk.Frame(solve_tab, style="Panel.TFrame")
    solve_bar.pack(fill="x", pady=(12, 0))
    solve_button = ttk.Button(solve_bar, text="MESH + SOLVE + VERIFY", style="Accent.TButton")
    solve_button.pack(side="left")
    ttk.Label(solve_bar, text="No synthetic results. Solver evidence only.", style="PanelMuted.TLabel").pack(side="right")

    ttk.Label(results, text="Results & evidence", style="Section.TLabel", font=("Segoe UI Semibold", 20)).pack(anchor="w")
    metrics = ttk.Frame(results, style="Panel.TFrame")
    metrics.pack(fill="x", pady=(14, 14))
    for i, c in enumerate((("Nodes", node_metric, "mesh nodes"), ("TET4", tet_metric, "volume elements"),
                           ("Max displacement", disp_metric, "mm"), ("Max Von Mises", vm_metric, "MPa"))):
        widget = card(metrics, *c)
        widget.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0))
        metrics.columnconfigure(i, weight=1)
    summary_text = tk.Text(results, height=20, state="disabled", bg="#0B0E12", fg="#C9D4E0", relief="flat",
                           font=("Cascadia Mono", 9), padx=12, pady=10)
    summary_text.pack(fill="both", expand=True)
    result_buttons = ttk.Frame(results, style="Panel.TFrame")
    result_buttons.pack(fill="x", pady=(12, 0))

    def show_summary(result: dict, output: Path) -> None:
        s = result["summary"]
        node_metric.set(str(s.get("node_count", "—")))
        tet_metric.set(str(s.get("tet4_count", "—")))
        disp_metric.set(f"{s.get('max_displacement_mm', 0):.6g}")
        vm_metric.set(f"{s.get('max_element_von_mises_MPa', 0):.6g}")
        summary_text.configure(state="normal")
        summary_text.delete("1.0", "end")
        summary_text.insert("end", json.dumps(s, indent=2, sort_keys=True))
        summary_text.insert("end", "\n\nEvidence fingerprint:\n" + result["manifest"]["evidence_fingerprint_sha256"])
        summary_text.insert("end", "\n\nOutput:\n" + str(output.resolve()))
        summary_text.configure(state="disabled")

    def solve_worker(config: StepCaseConfig, approved_by: str) -> None:
        try:
            result = run_windows_step_case(config, approved_by=approved_by)
        except Exception as exc:
            root.after(0, lambda: solve_failed(exc))
            return
        root.after(0, lambda: solve_succeeded(config, result))

    def solve_failed(exc: Exception) -> None:
        solve_button.configure(state="normal")
        status_var.set("Solve blocked / failed")
        log(f"FAILED: {exc}")
        messagebox.showerror("AsterMax solve", str(exc))

    def solve_succeeded(config: StepCaseConfig, result: dict) -> None:
        solve_button.configure(state="normal")
        state["last_output"] = config.output_dir
        state["last_result"] = result
        status_var.set("VERIFIED · evidence bundle generated")
        s = result["summary"]
        log(f"SOLVED: nodes={s['node_count']} tet4={s['tet4_count']}")
        log(f"max displacement [mm]={s['max_displacement_mm']}")
        log(f"max element Von Mises [MPa]={s['max_element_von_mises_MPa']}")
        log(f"free residual max [N]={s['free_residual_max_N']}")
        show_summary(result, config.output_dir)
        notebook.select(results)

    def solve_case() -> None:
        try:
            config = current_config()
            approver = approver_var.get().strip()
            if not approver:
                raise WindowsAppError("solve blocked: engineer approval identity is required")
            live = build_windows_preparation(config)
            approve_static_preparation(live, approved_by=approver)
            live_summary = preparation_summary(live)
            approved = state.get("preparation")
            if not approved or approved.get("engineering_intent_sha256") != live_summary["engineering_intent_sha256"]:
                raise WindowsAppError("solve blocked: model settings changed after approval; review and approve again")
            gmsh = find_gmsh_for_windows()
        except (ValueError, WindowsAppError) as exc:
            messagebox.showerror("AsterMax model gate", str(exc))
            return
        solve_button.configure(state="disabled")
        status_var.set("Meshing and solving approved case…")
        log(f"Gmsh: {gmsh}")
        log(f"APPROVED: {config.step_path.name} | {config.axis} FIXED={config.fixed_side} LOAD={config.load_side}")
        threading.Thread(target=solve_worker, args=(config, approver), daemon=True).start()

    solve_button.configure(command=solve_case)

    def open_viewer() -> None:
        output = state.get("last_output")
        if not output:
            return
        viewer = Path(output) / "astermax_step_viewer.html"
        if viewer.is_file():
            webbrowser.open(viewer.resolve().as_uri(), new=1)

    def open_folder() -> None:
        output = state.get("last_output")
        if not output:
            return
        path = str(Path(output).resolve())
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            webbrowser.open(Path(path).as_uri())

    ttk.Button(result_buttons, text="OPEN RESULT VIEWER", style="Accent.TButton", command=open_viewer).pack(side="left")
    ttk.Button(result_buttons, text="OPEN EVIDENCE FOLDER", style="Secondary.TButton", command=open_folder).pack(side="left", padx=8)

    footer = ttk.Frame(root, style="Panel.TFrame", padding=(18, 8))
    footer.pack(fill="x")
    ttk.Label(footer, textvariable=status_var, style="Panel.TLabel").pack(side="left")
    ttk.Label(footer, text="FAIL-CLOSED · HUMAN-IN-THE-LOOP · SHA-256 TRACEABILITY", style="PanelMuted.TLabel").pack(side="right")

    try:
        gmsh_var.set("GMSH · READY · " + Path(find_gmsh_for_windows()).name)
    except WindowsAppError:
        gmsh_var.set("GMSH · NOT FOUND")

    root.mainloop()
    return 0


def main(argv=None) -> int:
    return launch_desktop()


if __name__ == "__main__":
    raise SystemExit(main())
