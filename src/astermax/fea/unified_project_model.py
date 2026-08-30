from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from astermax.credibility import canonical_sha256
from .adaptive_hotspot_visualization import AdaptiveHotspotVisualizationV1
from .adaptive_stress_comparison import AdaptiveStressComparisonV1
from .portable_adaptive_results import open_portable_adaptive_results_package, verify_portable_adaptive_results_package
from .project_session_shell import open_verified_project_session


class UnifiedProjectError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectAnalysisRevisionV1:
    schema: str
    revision: int
    label: str
    result_package_path: str
    result_package_file_sha256: str
    result_package_sha256: str
    source_step_sha256: str
    baseline_mesh_sha256: str
    refined_mesh_sha256: str
    baseline_solve_evidence_sha256: str
    refined_solve_evidence_sha256: str
    qoi_status: str
    indicator_status: str
    revision_sha256: str


@dataclass(frozen=True)
class UnifiedProjectV1:
    schema: str
    project_name: str
    source_step_sha256: str
    units_length: str
    units_force: str
    units_stress: str
    revisions: tuple[ProjectAnalysisRevisionV1, ...]
    claims: dict[str, bool]
    project_sha256: str


@dataclass(frozen=True)
class ProjectRevisionInspectionV1:
    revision: int
    label: str
    status: str
    detail: str
    result_package_path: str
    inspection_sha256: str


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _revision_core(revision: ProjectAnalysisRevisionV1) -> dict[str, Any]:
    core = asdict(revision)
    core.pop("revision_sha256")
    return core


def _project_core(project: UnifiedProjectV1) -> dict[str, Any]:
    return {
        "schema": project.schema,
        "project_name": project.project_name,
        "source_step_sha256": project.source_step_sha256,
        "units_length": project.units_length,
        "units_force": project.units_force,
        "units_stress": project.units_stress,
        "revisions": [asdict(row) for row in project.revisions],
        "claims": project.claims,
    }


def _revision_from_package(path: Path, revision: int, label: str) -> ProjectAnalysisRevisionV1:
    package = open_portable_adaptive_results_package(path)
    verify_portable_adaptive_results_package(package)
    core = {
        "schema": "AsterMaxProjectAnalysisRevisionV1",
        "revision": int(revision),
        "label": str(label),
        "result_package_path": str(path.resolve()),
        "result_package_file_sha256": package.package_file_sha256,
        "result_package_sha256": package.package_sha256,
        "source_step_sha256": package.source_step_sha256,
        "baseline_mesh_sha256": package.baseline_mesh_sha256,
        "refined_mesh_sha256": package.refined_mesh_sha256,
        "baseline_solve_evidence_sha256": package.baseline_solve_evidence_sha256,
        "refined_solve_evidence_sha256": package.refined_solve_evidence_sha256,
        "qoi_status": package.stress_view.qoi_status,
        "indicator_status": package.stress_view.indicator_status,
    }
    return ProjectAnalysisRevisionV1(**core, revision_sha256=canonical_sha256(core))


def create_unified_project(project_path: str | Path, result_package_path: str | Path, *, project_name: str = "AsterMax Project") -> UnifiedProjectV1:
    result = Path(result_package_path).expanduser().resolve()
    revision = _revision_from_package(result, 1, "Revision 01 · Adaptive")
    claims = {"global_analysis_converged": False, "industrial_validation": False, "ansys_equivalence": False}
    draft = UnifiedProjectV1(
        schema="AsterMaxUnifiedProjectV1", project_name=project_name.strip() or "AsterMax Project",
        source_step_sha256=revision.source_step_sha256, units_length="mm", units_force="N", units_stress="MPa",
        revisions=(revision,), claims=claims, project_sha256="",
    )
    project = UnifiedProjectV1(**{**asdict(draft), "revisions": draft.revisions, "project_sha256": canonical_sha256(_project_core(draft))})
    write_unified_project(project, project_path)
    return project


def append_project_revision(project_path: str | Path, result_package_path: str | Path, *, label: str | None = None) -> UnifiedProjectV1:
    project = open_unified_project(project_path)
    number = len(project.revisions) + 1
    revision = _revision_from_package(Path(result_package_path).expanduser().resolve(), number, label or f"Revision {number:02d} · Adaptive")
    if revision.source_step_sha256 != project.source_step_sha256:
        raise UnifiedProjectError("PROJECT_REVISION_STEP_IDENTITY_MISMATCH")
    revisions = project.revisions + (revision,)
    draft = UnifiedProjectV1(
        schema=project.schema, project_name=project.project_name, source_step_sha256=project.source_step_sha256,
        units_length=project.units_length, units_force=project.units_force, units_stress=project.units_stress,
        revisions=revisions, claims=project.claims, project_sha256="",
    )
    updated = UnifiedProjectV1(**{**asdict(draft), "revisions": revisions, "project_sha256": canonical_sha256(_project_core(draft))})
    write_unified_project(updated, project_path)
    return updated


def write_unified_project(project: UnifiedProjectV1, path: str | Path) -> Path:
    verify_unified_project(project, verify_revision_files=False)
    output = Path(path).expanduser().resolve()
    if output.suffix.lower() != ".astermax":
        raise UnifiedProjectError("PROJECT_EXTENSION_REQUIRED")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {**_project_core(project), "project_sha256": project.project_sha256}
    temp = output.with_suffix(output.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(output)
    return output


def open_unified_project(path: str | Path) -> UnifiedProjectV1:
    source = Path(path).expanduser().resolve()
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UnifiedProjectError("PROJECT_FILE_INVALID") from exc
    revisions = tuple(ProjectAnalysisRevisionV1(**row) for row in raw.get("revisions", []))
    project = UnifiedProjectV1(
        schema=str(raw.get("schema", "")), project_name=str(raw.get("project_name", "")),
        source_step_sha256=str(raw.get("source_step_sha256", "")), units_length=str(raw.get("units_length", "")),
        units_force=str(raw.get("units_force", "")), units_stress=str(raw.get("units_stress", "")),
        revisions=revisions, claims=dict(raw.get("claims", {})), project_sha256=str(raw.get("project_sha256", "")),
    )
    verify_unified_project(project, verify_revision_files=False)
    return project


def verify_unified_project(project: UnifiedProjectV1, *, verify_revision_files: bool = True) -> None:
    if project.schema != "AsterMaxUnifiedProjectV1" or not project.revisions:
        raise UnifiedProjectError("PROJECT_SCHEMA_OR_REVISIONS")
    if (project.units_length, project.units_force, project.units_stress) != ("mm", "N", "MPa"):
        raise UnifiedProjectError("PROJECT_UNIT_SYSTEM")
    if project.claims.get("global_analysis_converged") or project.claims.get("industrial_validation") or project.claims.get("ansys_equivalence"):
        raise UnifiedProjectError("PROJECT_OVERCLAIM")
    for expected, revision in enumerate(project.revisions, start=1):
        if revision.schema != "AsterMaxProjectAnalysisRevisionV1" or revision.revision != expected:
            raise UnifiedProjectError("PROJECT_REVISION_SEQUENCE")
        if canonical_sha256(_revision_core(revision)) != revision.revision_sha256:
            raise UnifiedProjectError("PROJECT_REVISION_TAMPERED")
        if revision.source_step_sha256 != project.source_step_sha256:
            raise UnifiedProjectError("PROJECT_REVISION_STEP_IDENTITY_MISMATCH")
        if verify_revision_files:
            path = Path(revision.result_package_path)
            if not path.is_file():
                raise UnifiedProjectError("PROJECT_REVISION_MISSING")
            if _sha_file(path) != revision.result_package_file_sha256:
                raise UnifiedProjectError("PROJECT_REVISION_STALE_OR_TAMPERED")
            package = open_portable_adaptive_results_package(path)
            verify_portable_adaptive_results_package(package)
            if package.package_sha256 != revision.result_package_sha256:
                raise UnifiedProjectError("PROJECT_REVISION_PACKAGE_IDENTITY")
    if canonical_sha256(_project_core(project)) != project.project_sha256:
        raise UnifiedProjectError("PROJECT_TAMPERED")


def inspect_project_revisions(project: UnifiedProjectV1) -> tuple[ProjectRevisionInspectionV1, ...]:
    rows: list[ProjectRevisionInspectionV1] = []
    for revision in project.revisions:
        path = Path(revision.result_package_path)
        status, detail = "VERIFIED", "Revision package and provenance identity verified."
        try:
            if not path.is_file():
                raise UnifiedProjectError("MISSING")
            if _sha_file(path) != revision.result_package_file_sha256:
                raise UnifiedProjectError("STALE")
            package = open_portable_adaptive_results_package(path); verify_portable_adaptive_results_package(package)
            if package.package_sha256 != revision.result_package_sha256:
                raise UnifiedProjectError("STALE")
        except Exception as exc:
            code = str(exc)
            status = "MISSING" if "MISSING" in code else "STALE_OR_TAMPERED"
            detail = f"Revision rejected: {code}"
        core = {"revision": revision.revision, "label": revision.label, "status": status, "detail": detail, "result_package_path": str(path)}
        rows.append(ProjectRevisionInspectionV1(**core, inspection_sha256=canonical_sha256(core)))
    return tuple(rows)


def install_unified_project_tab(
    notebook: Any,
    *,
    hotspot_binder: Callable[[AdaptiveHotspotVisualizationV1], None],
    stress_binder: Callable[[AdaptiveStressComparisonV1], None],
):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    panel = ttk.Frame(notebook, padding=14); notebook.add(panel, text="Project Tree")
    panel.columnconfigure(0, weight=1); panel.rowconfigure(2, weight=1)
    ttk.Label(panel, text="AsterMax Unified Project", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, sticky="w")
    status = tk.StringVar(value="Open a .astermax project to inspect its analysis revision tree.")
    toolbar = ttk.Frame(panel); toolbar.grid(row=1, column=0, sticky="ew", pady=(8, 8))
    tree = ttk.Treeview(panel, columns=("status",), show="tree headings"); tree.heading("#0", text="Engineering object"); tree.heading("status", text="Status")
    tree.column("#0", width=720); tree.column("status", width=160, stretch=False); tree.grid(row=2, column=0, sticky="nsew")
    ttk.Label(panel, textvariable=status, wraplength=1000).grid(row=3, column=0, sticky="ew", pady=(8, 0))
    holder: dict[str, Any] = {}

    def populate(path: str) -> None:
        try:
            project = open_unified_project(path); inspections = inspect_project_revisions(project)
        except Exception as exc:
            messagebox.showerror("AsterMax project", str(exc)); return
        holder["project"] = project
        for item in tree.get_children(): tree.delete(item)
        geometry = tree.insert("", "end", text=f"Geometry · STEP SHA {project.source_step_sha256[:12]}…", values=("IDENTIFIED",), open=True)
        tree.insert(geometry, "end", text="Units · mm / N / MPa", values=("LOCKED",))
        analyses = tree.insert("", "end", text="Analyses", values=(f"{len(project.revisions)} revision(s)",), open=True)
        for revision, inspection in zip(project.revisions, inspections):
            item = tree.insert(analyses, "end", text=f"Revision {revision.revision:02d} · {revision.label}", values=(inspection.status,), tags=(str(revision.revision),))
            tree.insert(item, "end", text=f"Mesh · baseline {revision.baseline_mesh_sha256[:10]}… → refined {revision.refined_mesh_sha256[:10]}…", values=("EVIDENCE",))
            tree.insert(item, "end", text=f"Results · QoI {revision.qoi_status} · Indicator {revision.indicator_status}", values=("AVAILABLE",))
        tree.insert("", "end", text="Evidence · provenance / approvals / SHA chain", values=("FAIL-CLOSED",))
        status.set(f"VERIFIED PROJECT · {project.project_name} · {len(project.revisions)} revision(s)")

    def browse() -> None:
        path = filedialog.askopenfilename(filetypes=[("AsterMax Project", "*.astermax"), ("All files", "*.*")])
        if path: populate(path)

    def open_revision() -> None:
        selected = tree.selection()
        if not selected or "project" not in holder: return
        tags = tree.item(selected[0], "tags")
        if not tags: return
        number = int(tags[0]); project: UnifiedProjectV1 = holder["project"]; revision = project.revisions[number - 1]
        try:
            session, _package, _receipt = open_verified_project_session(revision.result_package_path, hotspot_binder=hotspot_binder, stress_binder=stress_binder)
        except Exception as exc:
            messagebox.showerror("AsterMax revision", str(exc)); return
        status.set(f"Revision {number:02d} restored · QoI {session.qoi_status} · Indicator {session.indicator_status} · VERIFIED")

    ttk.Button(toolbar, text="Open Project…", command=browse).pack(side="left")
    ttk.Button(toolbar, text="Open Selected Revision", command=open_revision).pack(side="left", padx=(8, 0))
    tree.bind("<Double-1>", lambda _event: open_revision())
    return populate
