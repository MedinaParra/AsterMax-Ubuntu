from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from astermax.credibility import canonical_sha256
from .portable_adaptive_results import open_portable_adaptive_results_package, verify_portable_adaptive_results_package
from .unified_project_model import (
    UnifiedProjectV1,
    append_project_revision,
    create_unified_project,
    open_unified_project,
    verify_unified_project,
)


class ProjectAuthoringError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectAuthoringReceiptV1:
    schema: str
    action: str
    project_path: str
    result_package_path: str
    source_step_sha256: str
    revision_count: int
    latest_revision_sha256: str
    project_sha256: str
    physics_changed: bool
    solver_executed: bool
    gmsh_executed: bool
    global_analysis_converged: bool
    industrial_validation: bool
    ansys_equivalence: bool
    receipt_sha256: str


def _receipt(action: str, project_path: Path, result_path: Path, project: UnifiedProjectV1) -> ProjectAuthoringReceiptV1:
    verify_unified_project(project, verify_revision_files=True)
    latest = project.revisions[-1]
    core = {
        "schema": "AsterMaxProjectAuthoringReceiptV1",
        "action": action,
        "project_path": str(project_path.resolve()),
        "result_package_path": str(result_path.resolve()),
        "source_step_sha256": project.source_step_sha256,
        "revision_count": len(project.revisions),
        "latest_revision_sha256": latest.revision_sha256,
        "project_sha256": project.project_sha256,
        "physics_changed": False,
        "solver_executed": False,
        "gmsh_executed": False,
        "global_analysis_converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    return ProjectAuthoringReceiptV1(**core, receipt_sha256=canonical_sha256(core))


def create_project_from_verified_results(
    project_path: str | Path,
    result_package_path: str | Path,
    *,
    project_name: str = "AsterMax Project",
) -> tuple[UnifiedProjectV1, ProjectAuthoringReceiptV1]:
    project_file = Path(project_path).expanduser().resolve()
    result_file = Path(result_package_path).expanduser().resolve()
    if project_file.suffix.lower() != ".astermax":
        raise ProjectAuthoringError("PROJECT_AUTHORING_EXTENSION")
    if project_file.exists():
        raise ProjectAuthoringError("PROJECT_AUTHORING_PROJECT_ALREADY_EXISTS")
    package = open_portable_adaptive_results_package(result_file)
    verify_portable_adaptive_results_package(package)
    project = create_unified_project(project_file, result_file, project_name=project_name)
    return project, _receipt("CREATE_PROJECT_FROM_VERIFIED_RESULTS", project_file, result_file, project)


def append_verified_results_revision(
    project_path: str | Path,
    result_package_path: str | Path,
    *,
    label: str | None = None,
    allow_duplicate_package: bool = False,
) -> tuple[UnifiedProjectV1, ProjectAuthoringReceiptV1]:
    project_file = Path(project_path).expanduser().resolve()
    result_file = Path(result_package_path).expanduser().resolve()
    current = open_unified_project(project_file)
    verify_unified_project(current, verify_revision_files=True)
    package = open_portable_adaptive_results_package(result_file)
    verify_portable_adaptive_results_package(package)
    if package.source_step_sha256 != current.source_step_sha256:
        raise ProjectAuthoringError("PROJECT_AUTHORING_STEP_IDENTITY_MISMATCH")
    duplicate = any(row.result_package_sha256 == package.package_sha256 for row in current.revisions)
    if duplicate and not allow_duplicate_package:
        raise ProjectAuthoringError("PROJECT_AUTHORING_DUPLICATE_RESULTS_REVISION")
    if duplicate and not (label and label.strip()):
        raise ProjectAuthoringError("PROJECT_AUTHORING_DUPLICATE_LABEL_REQUIRED")
    updated = append_project_revision(project_file, result_file, label=label)
    return updated, _receipt("APPEND_VERIFIED_RESULTS_REVISION", project_file, result_file, updated)


def verify_project_authoring_receipt(receipt: ProjectAuthoringReceiptV1) -> None:
    if receipt.schema != "AsterMaxProjectAuthoringReceiptV1":
        raise ProjectAuthoringError("PROJECT_AUTHORING_RECEIPT_SCHEMA")
    if receipt.physics_changed or receipt.solver_executed or receipt.gmsh_executed:
        raise ProjectAuthoringError("PROJECT_AUTHORING_EXECUTION_OVERCLAIM")
    if receipt.global_analysis_converged or receipt.industrial_validation or receipt.ansys_equivalence:
        raise ProjectAuthoringError("PROJECT_AUTHORING_VALIDATION_OVERCLAIM")
    core = receipt.__dict__.copy(); core.pop("receipt_sha256")
    if canonical_sha256(core) != receipt.receipt_sha256:
        raise ProjectAuthoringError("PROJECT_AUTHORING_RECEIPT_TAMPERED")


def install_project_authoring_controls(
    parent: Any,
    *,
    on_project_changed: Callable[[str], None],
):
    """Install New Project / Add Revision actions without solving or remeshing.

    Both actions accept only already-verified `.astermaxr` packages. The active
    project path is held by the UI and every mutation is followed by project
    verification before the Project Tree refresh callback is invoked.
    """
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk

    frame = ttk.LabelFrame(parent, text="Project Authoring", padding=8)
    frame.pack(fill="x")
    active_project = tk.StringVar(value="")
    status = tk.StringVar(value="No active .astermax project")

    def new_project() -> None:
        result_path = filedialog.askopenfilename(filetypes=[("AsterMax Results", "*.astermaxr")])
        if not result_path:
            return
        project_path = filedialog.asksaveasfilename(defaultextension=".astermax", filetypes=[("AsterMax Project", "*.astermax")])
        if not project_path:
            return
        name = simpledialog.askstring("AsterMax Project", "Project name:", initialvalue="AsterMax Project") or "AsterMax Project"
        try:
            project, receipt = create_project_from_verified_results(project_path, result_path, project_name=name)
            verify_project_authoring_receipt(receipt)
        except Exception as exc:
            messagebox.showerror("AsterMax project authoring", str(exc)); return
        active_project.set(str(Path(project_path).resolve()))
        status.set(f"ACTIVE · {project.project_name} · Revision {len(project.revisions):02d} · VERIFIED")
        on_project_changed(active_project.get())

    def open_project() -> None:
        path = filedialog.askopenfilename(filetypes=[("AsterMax Project", "*.astermax")])
        if not path:
            return
        try:
            project = open_unified_project(path); verify_unified_project(project, verify_revision_files=True)
        except Exception as exc:
            messagebox.showerror("AsterMax project authoring", str(exc)); return
        active_project.set(str(Path(path).resolve()))
        status.set(f"ACTIVE · {project.project_name} · {len(project.revisions)} revision(s) · VERIFIED")
        on_project_changed(active_project.get())

    def add_revision() -> None:
        if not active_project.get():
            messagebox.showwarning("AsterMax project authoring", "Open or create a project first."); return
        result_path = filedialog.askopenfilename(filetypes=[("AsterMax Results", "*.astermaxr")])
        if not result_path:
            return
        try:
            project, receipt = append_verified_results_revision(active_project.get(), result_path)
            verify_project_authoring_receipt(receipt)
        except Exception as exc:
            messagebox.showerror("AsterMax project authoring", str(exc)); return
        status.set(f"ACTIVE · {project.project_name} · Revision {len(project.revisions):02d} appended · VERIFIED")
        on_project_changed(active_project.get())

    buttons = ttk.Frame(frame); buttons.pack(fill="x")
    ttk.Button(buttons, text="New Project…", command=new_project).pack(side="left")
    ttk.Button(buttons, text="Open Project…", command=open_project).pack(side="left", padx=(6, 0))
    ttk.Button(buttons, text="Add Analysis Revision…", command=add_revision).pack(side="left", padx=(6, 0))
    ttk.Label(frame, textvariable=status).pack(anchor="w", pady=(6, 0))
    return active_project
