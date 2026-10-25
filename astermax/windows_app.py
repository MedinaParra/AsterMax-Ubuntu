"""AsterMax Windows desktop shell for a real STEP -> FEA workflow.

The GUI orchestrates verified engineering kernels and now enforces an explicit
human approval gate before any imported STEP case is solved.  Agent/model
preparation proposals are evidence, not engineering decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import sys
import threading
import webbrowser

from .model_preparation import (
    StaticPreparationSpec,
    approve_static_preparation,
    build_static_preparation_case,
    preparation_summary,
    write_preparation_evidence,
)
from .semantic_surface import SemanticSurfaceIntent
from .step_static_demo import StepStaticDemoError, run_step_static_demo
from .step_units import require_step_mm


class WindowsAppError(RuntimeError):
    """Raised when a Windows desktop case cannot pass a trust gate."""


@dataclass(frozen=True)
class StepCaseConfig:
    step_path: Path
    output_dir: Path
    axis: str = "x"
    fixed_side: str = "min"
    load_side: str = "max"
    force_n: tuple[float, float, float] = (100.0, 0.0, 0.0)
    mesh_size_mm: float = 2.0
    young_mpa: float = 210000.0
    poisson: float = 0.30
    minimum_tet_quality: float = 0.05

    def validate(self) -> None:
        if not self.step_path.is_file():
            raise WindowsAppError(f"STEP file does not exist: {self.step_path}")
        if self.axis not in ("x", "y", "z"):
            raise WindowsAppError("semantic axis must be x, y, or z")
        if self.fixed_side not in ("min", "max") or self.load_side not in ("min", "max"):
            raise WindowsAppError("surface sides must be min or max")
        if self.fixed_side == self.load_side:
            raise WindowsAppError("FIXED and LOAD cannot use the same semantic side")
        if len(self.force_n) != 3 or not all(math.isfinite(float(v)) for v in self.force_n):
            raise WindowsAppError("force must contain three finite components")
        if not math.isfinite(self.mesh_size_mm) or self.mesh_size_mm <= 0.0:
            raise WindowsAppError("mesh size must be finite and positive")
        if not math.isfinite(self.young_mpa) or self.young_mpa <= 0.0:
            raise WindowsAppError("Young's modulus must be finite and positive")
        if not math.isfinite(self.poisson) or not (-1.0 < self.poisson < 0.5):
            raise WindowsAppError("Poisson ratio must satisfy -1 < nu < 0.5")
        if not math.isfinite(self.minimum_tet_quality) or not (0.0 < self.minimum_tet_quality <= 1.0):
            raise WindowsAppError("minimum TET4 quality must be in (0,1]")


def validate_step_mm_file(path: str | Path) -> str:
    source = Path(path)
    if not source.is_file():
        raise WindowsAppError(f"STEP file does not exist: {source}")
    try:
        unit = require_step_mm(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise WindowsAppError(f"STEP mm gate failed: {exc}") from exc
    return unit.name


def find_gmsh_for_windows(explicit: str | None = None) -> str:
    """Locate bundled portable Gmsh first, then an installed PATH copy."""
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
    else:
        exe_dir = Path(__file__).resolve().parents[1]
    candidates.extend((exe_dir / "tools" / "gmsh" / "gmsh.exe", exe_dir / "gmsh" / "gmsh.exe"))
    path_hit = shutil.which("gmsh") or shutil.which("gmsh.exe")
    if path_hit:
        candidates.append(Path(path_hit))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    raise WindowsAppError(
        "Gmsh was not found. Use the portable AsterMax package with tools/gmsh, "
        "or install Gmsh 4.12+ and place gmsh.exe on PATH."
    )


def build_windows_preparation(config: StepCaseConfig):
    """Convert desktop inputs into an auditable, initially unapproved engineering case."""
    config.validate()
    detected_unit = validate_step_mm_file(config.step_path)
    spec = StaticPreparationSpec(
        step_path=config.step_path,
        axis=config.axis,
        fixed_side=config.fixed_side,
        load_side=config.load_side,
        force_n=config.force_n,
        mesh_size_mm=config.mesh_size_mm,
        young_mpa=config.young_mpa,
        poisson=config.poisson,
        minimum_tet_quality=config.minimum_tet_quality,
        detected_unit=detected_unit,
    )
    return build_static_preparation_case(spec)


def run_windows_step_case(
    config: StepCaseConfig,
    *,
    approved_by: str,
    gmsh_executable: str | None = None,
) -> dict:
    """Execute STEP FEA only after explicit engineer approval of preparation intent."""
    if not approved_by.strip():
        raise WindowsAppError("solve blocked: engineer approval is required")
    case = build_windows_preparation(config)
    try:
        approve_static_preparation(case, approved_by=approved_by.strip())
    except ValueError as exc:
        raise WindowsAppError(f"solve blocked by model-preparation gate: {exc}") from exc
    prep = preparation_summary(case)
    if not prep["solve_gate"]["ready"]:
        raise WindowsAppError(f"solve blocked by preparation gate: {prep['solve_gate']['issues']}")
    preparation_evidence = write_preparation_evidence(case, config.output_dir)

    gmsh = find_gmsh_for_windows(gmsh_executable)
    fixed = SemanticSurfaceIntent("FIXED", config.axis, config.fixed_side)
    load = SemanticSurfaceIntent("LOAD", config.axis, config.load_side)
    try:
        result = run_step_static_demo(
            config.step_path,
            config.output_dir,
            fixed_intent=fixed,
            load_intent=load,
            total_force_n=config.force_n,
            mesh_size_mm=config.mesh_size_mm,
            young_mpa=config.young_mpa,
            poisson=config.poisson,
            gmsh_executable=gmsh,
            minimum_tet_quality=config.minimum_tet_quality,
        )
    except StepStaticDemoError as exc:
        raise WindowsAppError(str(exc)) from exc
    result["model_preparation"] = preparation_evidence["summary"]
    return result


def _parse_force(texts) -> tuple[float, float, float]:
    try:
        values = tuple(float(v.get().strip()) for v in texts)
    except ValueError as exc:
        raise WindowsAppError("Fx, Fy and Fz must be numeric") from exc
    if len(values) != 3 or not all(math.isfinite(v) for v in values):
        raise WindowsAppError("force must contain three finite values")
    return values


def launch_desktop() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("AsterMax PMV — Engineering FEA for Windows")
    root.geometry("1180x790")
    root.minsize(1000, 680)

    state = {"step": None, "last_output": None, "last_result": None, "preparation": None}
    status_var = tk.StringVar(value="Ready — import a STEP file in mm")
    step_var = tk.StringVar(value="No STEP loaded")
    unit_var = tk.StringVar(value="Units: unresolved")
    gmsh_var = tk.StringVar(value="Gmsh: checking…")
    axis_var = tk.StringVar(value="x")
    fixed_side_var = tk.StringVar(value="min")
    load_side_var = tk.StringVar(value="max")
    fx_var, fy_var, fz_var = tk.StringVar(value="100"), tk.StringVar(value="0"), tk.StringVar(value="0")
    mesh_var = tk.StringVar(value="2.0")
    young_var = tk.StringVar(value="210000")
    poisson_var = tk.StringVar(value="0.30")
    quality_var = tk.StringVar(value="0.05")
    approver_var = tk.StringVar(value="")
    approval_var = tk.StringVar(value="Approval gate: NOT REVIEWED")

    header = ttk.Frame(root, padding=12)
    header.pack(fill="x")
    ttk.Label(header, text="AsterMax", font=("Segoe UI", 22, "bold")).pack(side="left")
    ttk.Label(header, text="PMV / Windows · STEP → Prepare → Approve → Mesh → FEA → Evidence", font=("Segoe UI", 11)).pack(side="left", padx=14)
    ttk.Label(header, textvariable=gmsh_var).pack(side="right")

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=12, pady=(0, 8))
    geometry = ttk.Frame(notebook, padding=18)
    setup = ttk.Frame(notebook, padding=18)
    solve_tab = ttk.Frame(notebook, padding=18)
    results = ttk.Frame(notebook, padding=18)
    notebook.add(geometry, text="1  Geometry")
    notebook.add(setup, text="2  Model Setup & Approval")
    notebook.add(solve_tab, text="3  Mesh & Solve")
    notebook.add(results, text="4  Results & Evidence")

    def log(text: str) -> None:
        console.configure(state="normal")
        console.insert("end", text.rstrip() + "\n")
        console.see("end")
        console.configure(state="disabled")

    def invalidate_approval(*_args) -> None:
        state["preparation"] = None
        approval_var.set("Approval gate: NOT REVIEWED")

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
            unit_var.set("Units: BLOCKED")
            status_var.set("STEP rejected by unit trust gate")
            log(f"BLOCKED: {exc}")
            messagebox.showerror("AsterMax STEP gate", str(exc))
            return
        state["step"] = source
        state["preparation"] = None
        step_var.set(str(source))
        unit_var.set(f"Units: {unit} · mm gate PASSED")
        approval_var.set("Approval gate: NOT REVIEWED")
        status_var.set("STEP loaded and unit-verified")
        log(f"STEP imported: {source}")
        log(f"Unit invariant passed: {unit} / analysis basis mm-N-MPa")
        notebook.select(setup)

    ttk.Label(geometry, text="Geometry import", font=("Segoe UI", 15, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(geometry, text="AsterMax fails closed unless the STEP Part 21 file explicitly resolves to millimetres.", wraplength=820).grid(row=1, column=0, sticky="w", pady=(4,16))
    ttk.Button(geometry, text="Import STEP / STP…", command=choose_step).grid(row=2, column=0, sticky="w")
    ttk.Label(geometry, textvariable=step_var, wraplength=900).grid(row=3, column=0, sticky="w", pady=(18,4))
    ttk.Label(geometry, textvariable=unit_var, font=("Segoe UI", 10, "bold")).grid(row=4, column=0, sticky="w")
    ttk.Label(geometry, text="Semantic boundary intent is persistent across remeshing; the next CAD-workspace increment will replace axis/end selection with direct 3D face selection.", wraplength=900).grid(row=5, column=0, sticky="w", pady=(24,0))

    ttk.Label(setup, text="Engineering model setup", font=("Segoe UI", 15, "bold")).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0,14))
    ttk.Label(setup, text="Semantic axis").grid(row=1,column=0,sticky="w")
    ttk.Combobox(setup,textvariable=axis_var,values=("x","y","z"),state="readonly",width=8).grid(row=1,column=1,sticky="w",padx=8)
    ttk.Label(setup, text="FIXED side").grid(row=2,column=0,sticky="w",pady=6)
    ttk.Combobox(setup,textvariable=fixed_side_var,values=("min","max"),state="readonly",width=8).grid(row=2,column=1,sticky="w",padx=8)
    ttk.Label(setup, text="LOAD side").grid(row=3,column=0,sticky="w",pady=6)
    ttk.Combobox(setup,textvariable=load_side_var,values=("min","max"),state="readonly",width=8).grid(row=3,column=1,sticky="w",padx=8)

    ttk.Label(setup, text="Total force [N]").grid(row=4,column=0,sticky="w",pady=(18,6))
    for col,(label,var) in enumerate((("Fx",fx_var),("Fy",fy_var),("Fz",fz_var)), start=1):
        box=ttk.Frame(setup); box.grid(row=4,column=col,sticky="w",padx=6,pady=(18,6))
        ttk.Label(box,text=label).pack(side="left"); ttk.Entry(box,textvariable=var,width=10).pack(side="left",padx=4)

    fields=(("Global mesh size [mm]",mesh_var),("Young's modulus [MPa]",young_var),("Poisson ratio",poisson_var),("Minimum TET4 quality",quality_var))
    for row,(label,var) in enumerate(fields,start=5):
        ttk.Label(setup,text=label).grid(row=row,column=0,sticky="w",pady=6)
        ttk.Entry(setup,textvariable=var,width=16).grid(row=row,column=1,sticky="w",padx=8)

    ttk.Separator(setup, orient="horizontal").grid(row=9,column=0,columnspan=4,sticky="ew",pady=(18,14))
    ttk.Label(setup, text="Engineer approval", font=("Segoe UI", 11, "bold")).grid(row=10,column=0,sticky="w")
    ttk.Label(setup, text="Approver / engineer").grid(row=11,column=0,sticky="w",pady=6)
    ttk.Entry(setup,textvariable=approver_var,width=28).grid(row=11,column=1,sticky="w",padx=8)
    ttk.Label(setup,textvariable=approval_var,font=("Segoe UI",10,"bold")).grid(row=12,column=0,columnspan=3,sticky="w",pady=(6,0))

    def current_config() -> StepCaseConfig:
        source=state.get("step")
        if source is None:
            raise WindowsAppError("Import and validate a STEP file first")
        force=_parse_force((fx_var,fy_var,fz_var))
        output=source.parent / f"{source.stem}_AsterMax_Evidence"
        config=StepCaseConfig(
            step_path=source, output_dir=output, axis=axis_var.get(), fixed_side=fixed_side_var.get(),
            load_side=load_side_var.get(), force_n=force, mesh_size_mm=float(mesh_var.get()),
            young_mpa=float(young_var.get()), poisson=float(poisson_var.get()),
            minimum_tet_quality=float(quality_var.get()),
        )
        config.validate()
        return config

    def review_and_approve() -> None:
        try:
            config=current_config()
            case=build_windows_preparation(config)
            summary=preparation_summary(case)
            if not approver_var.get().strip():
                raise WindowsAppError("Enter the engineer/approver identity before approval")
            approve_static_preparation(case, approved_by=approver_var.get().strip())
            summary=preparation_summary(case)
        except (ValueError, WindowsAppError) as exc:
            messagebox.showerror("AsterMax approval gate", str(exc)); return
        state["preparation"] = summary
        approval_var.set("Approval gate: PASSED · intent " + summary["engineering_intent_sha256"][:12])
        status_var.set("Model preparation approved — solve enabled")
        log("ENGINEER APPROVAL PASSED")
        log(f"Approver: {approver_var.get().strip()}")
        log(f"Approved proposals: {summary['approved_proposal_ids']}")
        log(f"Engineering intent SHA-256: {summary['engineering_intent_sha256']}")
        notebook.select(solve_tab)

    ttk.Button(setup,text="Review + Approve Model Preparation",command=review_and_approve).grid(row=13,column=0,columnspan=2,sticky="w",pady=(12,0))
    ttk.Label(setup,text="Changing geometry, BC, load, material or mesh settings invalidates approval. Contact, GAP, friction and pretension are not silently enabled for imported assemblies.",wraplength=900).grid(row=14,column=0,columnspan=4,sticky="w",pady=(18,0))

    ttk.Label(solve_tab, text="Verified solve pipeline", font=("Segoe UI", 15, "bold")).pack(anchor="w")
    ttk.Label(solve_tab, text="STEP mm gate → agent proposal → engineer approval → OpenCASCADE/Gmsh → TET4 quality gate → BC/load → static solve → equilibrium/residual → Von Mises → VTK/HTML → SHA-256 evidence", wraplength=940).pack(anchor="w", pady=(6,14))
    console = tk.Text(solve_tab, height=22, state="disabled", font=("Consolas", 9))
    console.pack(fill="both", expand=True, pady=(8,10))
    solve_button = ttk.Button(solve_tab, text="Mesh + Solve + Verify")
    solve_button.pack(anchor="w")

    summary_text = tk.Text(results, height=26, state="disabled", font=("Consolas", 9))
    summary_text.pack(fill="both", expand=True)
    buttons = ttk.Frame(results); buttons.pack(fill="x", pady=10)

    def show_summary(result: dict, output: Path) -> None:
        summary_text.configure(state="normal")
        summary_text.delete("1.0","end")
        summary_text.insert("end", json.dumps(result["summary"], indent=2, sort_keys=True))
        prep=result.get("model_preparation", {})
        if prep:
            summary_text.insert("end", "\n\nModel preparation / approval:\n" + json.dumps(prep, indent=2, sort_keys=True))
        summary_text.insert("end", "\n\nEvidence fingerprint:\n" + result["manifest"]["evidence_fingerprint_sha256"] + "\n")
        summary_text.insert("end", "\nOutput:\n" + str(output.resolve()) + "\n")
        summary_text.configure(state="disabled")

    def solve_worker(config: StepCaseConfig, approved_by: str) -> None:
        try:
            result = run_windows_step_case(config, approved_by=approved_by)
        except Exception as exc:
            root.after(0, lambda: solve_failed(exc)); return
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
        status_var.set("Solve verified — evidence bundle generated")
        s=result["summary"]
        log(f"SOLVED: nodes={s['node_count']} tet4={s['tet4_count']}")
        log(f"max displacement [mm]={s['max_displacement_mm']}")
        log(f"max element Von Mises [MPa]={s['max_element_von_mises_MPa']}")
        log(f"free residual max [N]={s['free_residual_max_N']}")
        log(f"evidence fingerprint={result['manifest']['evidence_fingerprint_sha256']}")
        show_summary(result, config.output_dir)
        notebook.select(results)

    def solve_case() -> None:
        try:
            config=current_config()
            approver=approver_var.get().strip()
            if not approver:
                raise WindowsAppError("solve blocked: engineer approval identity is required")
            live=build_windows_preparation(config)
            approve_static_preparation(live, approved_by=approver)
            live_summary=preparation_summary(live)
            approved=state.get("preparation")
            if not approved or approved.get("engineering_intent_sha256") != live_summary["engineering_intent_sha256"]:
                raise WindowsAppError("solve blocked: model settings changed after approval; review and approve again")
            gmsh=find_gmsh_for_windows()
        except (ValueError, WindowsAppError) as exc:
            messagebox.showerror("AsterMax model gate", str(exc)); return
        solve_button.configure(state="disabled")
        status_var.set("Meshing and solving approved case…")
        log(f"Gmsh: {gmsh}")
        log(f"APPROVED CASE: {config.step_path.name} | axis={config.axis} FIXED={config.fixed_side} LOAD={config.load_side}")
        log(f"Force [N]={config.force_n} mesh [mm]={config.mesh_size_mm} E [MPa]={config.young_mpa} nu={config.poisson}")
        threading.Thread(target=solve_worker,args=(config,approver),daemon=True).start()

    solve_button.configure(command=solve_case)

    def open_viewer() -> None:
        output=state.get("last_output")
        if not output: return
        viewer=Path(output)/"astermax_step_viewer.html"
        if viewer.is_file(): webbrowser.open(viewer.resolve().as_uri(),new=1)

    def open_folder() -> None:
        output=state.get("last_output")
        if not output: return
        path=str(Path(output).resolve())
        if os.name=="nt": os.startfile(path)  # type: ignore[attr-defined]
        else: webbrowser.open(Path(path).as_uri())

    ttk.Button(buttons,text="Open AsterMax Result Viewer",command=open_viewer).pack(side="left")
    ttk.Button(buttons,text="Open Evidence Folder",command=open_folder).pack(side="left",padx=8)

    footer = ttk.Frame(root, padding=(12,6,12,10)); footer.pack(fill="x")
    ttk.Label(footer,textvariable=status_var).pack(side="left")
    ttk.Label(footer,text="mm · N · MPa | explicit human approval | fail-closed gates",font=("Segoe UI",9)).pack(side="right")

    try:
        gmsh_var.set("Gmsh: ready · " + Path(find_gmsh_for_windows()).name)
    except WindowsAppError:
        gmsh_var.set("Gmsh: not found")

    root.mainloop()
    return 0


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description="AsterMax Windows desktop PMV")
    parser.add_argument("--desktop", action="store_true", help="launch the Windows STEP desktop UI")
    parser.add_argument("--check-gmsh", action="store_true", help="print resolved Gmsh path and exit")
    args=parser.parse_args(argv)
    if args.check_gmsh:
        print(find_gmsh_for_windows()); return 0
    return launch_desktop()


if __name__ == "__main__":
    raise SystemExit(main())
