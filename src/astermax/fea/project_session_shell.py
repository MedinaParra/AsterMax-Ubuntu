from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from astermax.credibility import canonical_sha256
from .adaptive_hotspot_visualization import AdaptiveHotspotVisualizationV1
from .adaptive_stress_comparison import AdaptiveStressComparisonV1
from .portable_adaptive_results import (
    PortableAdaptiveResultsBindingReceiptV1,
    PortableAdaptiveResultsError,
    PortableAdaptiveResultsPackageV1,
    bind_portable_adaptive_results,
    open_portable_adaptive_results_package,
    verify_portable_adaptive_results_package,
)


class ProjectSessionShellError(ValueError):
    pass


@dataclass(frozen=True)
class RecentAnalysisEntryV1:
    schema: str
    package_path: str
    display_name: str
    package_file_sha256: str
    package_sha256: str
    source_step_sha256: str
    last_opened_utc: str
    entry_sha256: str


@dataclass(frozen=True)
class AnalysisInspectionV1:
    schema: str
    package_path: str
    display_name: str
    status: str
    detail: str
    package_file_sha256: str | None
    package_sha256: str | None
    source_step_sha256: str | None
    inspection_sha256: str


@dataclass(frozen=True)
class VerifiedProjectSessionV1:
    schema: str
    status: str
    package_path: str
    package_file_sha256: str
    package_sha256: str
    source_step_sha256: str
    baseline_mesh_sha256: str
    refined_mesh_sha256: str
    baseline_solve_evidence_sha256: str
    refined_solve_evidence_sha256: str
    qoi_status: str
    qoi_relative_change: float
    indicator_status: str
    indicator_relative_change: float
    bound_tabs: tuple[str, ...]
    binding_receipt_sha256: str
    claims: dict[str, bool]
    session_sha256: str


def default_recent_analyses_path() -> Path:
    return Path.home() / ".astermax" / "recent_analyses.json"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _entry_core(entry: RecentAnalysisEntryV1) -> dict[str, Any]:
    core = asdict(entry)
    core.pop("entry_sha256")
    return core


def _inspection(
    path: Path,
    *,
    status: str,
    detail: str,
    package_file_sha256: str | None = None,
    package_sha256: str | None = None,
    source_step_sha256: str | None = None,
) -> AnalysisInspectionV1:
    core = {
        "schema": "AsterMaxAnalysisInspectionV1",
        "package_path": str(path),
        "display_name": path.name,
        "status": status,
        "detail": detail,
        "package_file_sha256": package_file_sha256,
        "package_sha256": package_sha256,
        "source_step_sha256": source_step_sha256,
    }
    return AnalysisInspectionV1(**core, inspection_sha256=canonical_sha256(core))


def inspect_analysis_path(path: str | Path, *, expected_file_sha256: str | None = None) -> AnalysisInspectionV1:
    package_path = Path(path).expanduser().resolve()
    if not package_path.exists():
        return _inspection(package_path, status="MISSING", detail="Portable analysis file no longer exists at the recorded path.")
    if not package_path.is_file() or package_path.suffix.lower() != ".astermaxr":
        return _inspection(package_path, status="UNSUPPORTED", detail="AsterMax project shell accepts verified .astermaxr analysis packages only.")
    try:
        package = open_portable_adaptive_results_package(package_path)
        verify_portable_adaptive_results_package(package)
    except (PortableAdaptiveResultsError, OSError, ValueError) as exc:
        return _inspection(
            package_path,
            status="TAMPERED",
            detail=f"Package verification failed closed: {exc}",
            package_file_sha256=_sha256_file(package_path),
        )
    current_file_sha = package.package_file_sha256
    if expected_file_sha256 and current_file_sha != expected_file_sha256:
        return _inspection(
            package_path,
            status="STALE",
            detail="The path now contains a different but internally valid package than the recent-session identity.",
            package_file_sha256=current_file_sha,
            package_sha256=package.package_sha256,
            source_step_sha256=package.source_step_sha256,
        )
    return _inspection(
        package_path,
        status="VERIFIED",
        detail="Manifest, binary result payload, native views and provenance links verified. No solver/Gmsh execution required.",
        package_file_sha256=current_file_sha,
        package_sha256=package.package_sha256,
        source_step_sha256=package.source_step_sha256,
    )


def load_recent_analyses(store_path: str | Path | None = None) -> tuple[RecentAnalysisEntryV1, ...]:
    path = Path(store_path) if store_path is not None else default_recent_analyses_path()
    if not path.is_file():
        return ()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectSessionShellError("RECENT_ANALYSES_STORE_INVALID") from exc
    if raw.get("schema") != "AsterMaxRecentAnalysesStoreV1" or not isinstance(raw.get("entries"), list):
        raise ProjectSessionShellError("RECENT_ANALYSES_STORE_SCHEMA")
    entries: list[RecentAnalysisEntryV1] = []
    for row in raw["entries"]:
        entry = RecentAnalysisEntryV1(
            schema=str(row["schema"]), package_path=str(row["package_path"]), display_name=str(row["display_name"]),
            package_file_sha256=str(row["package_file_sha256"]), package_sha256=str(row["package_sha256"]),
            source_step_sha256=str(row["source_step_sha256"]), last_opened_utc=str(row["last_opened_utc"]),
            entry_sha256=str(row["entry_sha256"]),
        )
        if entry.schema != "AsterMaxRecentAnalysisEntryV1" or canonical_sha256(_entry_core(entry)) != entry.entry_sha256:
            raise ProjectSessionShellError("RECENT_ANALYSES_ENTRY_TAMPERED")
        entries.append(entry)
    return tuple(entries)


def _write_recent_analyses(entries: tuple[RecentAnalysisEntryV1, ...], store_path: str | Path | None = None) -> None:
    path = Path(store_path) if store_path is not None else default_recent_analyses_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": "AsterMaxRecentAnalysesStoreV1", "entries": [asdict(entry) for entry in entries]}
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def remember_verified_analysis(
    package: PortableAdaptiveResultsPackageV1,
    *,
    store_path: str | Path | None = None,
    opened_at_utc: str | None = None,
    maximum_entries: int = 12,
) -> RecentAnalysisEntryV1:
    verify_portable_adaptive_results_package(package)
    if maximum_entries < 1:
        raise ProjectSessionShellError("RECENT_ANALYSES_LIMIT")
    timestamp = opened_at_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    core = {
        "schema": "AsterMaxRecentAnalysisEntryV1",
        "package_path": str(Path(package.package_path).resolve()),
        "display_name": Path(package.package_path).name,
        "package_file_sha256": package.package_file_sha256,
        "package_sha256": package.package_sha256,
        "source_step_sha256": package.source_step_sha256,
        "last_opened_utc": timestamp,
    }
    entry = RecentAnalysisEntryV1(**core, entry_sha256=canonical_sha256(core))
    try:
        existing = load_recent_analyses(store_path)
    except ProjectSessionShellError:
        existing = ()
    kept = tuple(row for row in existing if Path(row.package_path) != Path(entry.package_path))
    _write_recent_analyses((entry,) + kept[: maximum_entries - 1], store_path)
    return entry


def open_verified_project_session(
    path: str | Path,
    *,
    hotspot_binder: Callable[[AdaptiveHotspotVisualizationV1], None],
    stress_binder: Callable[[AdaptiveStressComparisonV1], None],
    recent_store_path: str | Path | None = None,
    opened_at_utc: str | None = None,
) -> tuple[VerifiedProjectSessionV1, PortableAdaptiveResultsPackageV1, PortableAdaptiveResultsBindingReceiptV1]:
    package_path = Path(path).expanduser().resolve()
    inspection = inspect_analysis_path(package_path)
    if inspection.status != "VERIFIED":
        raise ProjectSessionShellError(f"PROJECT_SESSION_NOT_VERIFIED:{inspection.status}:{inspection.detail}")
    package = open_portable_adaptive_results_package(package_path)
    receipt = bind_portable_adaptive_results(package, hotspot_binder=hotspot_binder, stress_binder=stress_binder)
    remember_verified_analysis(package, store_path=recent_store_path, opened_at_utc=opened_at_utc)
    claims = {
        "package_verified_before_native_binding": True,
        "results_restored_without_solver": True,
        "results_restored_without_gmsh": True,
        "global_analysis_converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    core = {
        "schema": "AsterMaxVerifiedProjectSessionV1",
        "status": "VERIFIED",
        "package_path": str(package_path),
        "package_file_sha256": package.package_file_sha256,
        "package_sha256": package.package_sha256,
        "source_step_sha256": package.source_step_sha256,
        "baseline_mesh_sha256": package.baseline_mesh_sha256,
        "refined_mesh_sha256": package.refined_mesh_sha256,
        "baseline_solve_evidence_sha256": package.baseline_solve_evidence_sha256,
        "refined_solve_evidence_sha256": package.refined_solve_evidence_sha256,
        "qoi_status": package.stress_view.qoi_status,
        "qoi_relative_change": float(package.stress_view.qoi_relative_change),
        "indicator_status": package.stress_view.indicator_status,
        "indicator_relative_change": float(package.stress_view.indicator_relative_change),
        "bound_tabs": receipt.bound_tabs,
        "binding_receipt_sha256": receipt.receipt_sha256,
        "claims": claims,
    }
    return VerifiedProjectSessionV1(**core, session_sha256=canonical_sha256(core)), package, receipt


def inspect_recent_analyses(store_path: str | Path | None = None) -> tuple[AnalysisInspectionV1, ...]:
    entries = load_recent_analyses(store_path)
    return tuple(inspect_analysis_path(entry.package_path, expected_file_sha256=entry.package_file_sha256) for entry in entries)


def install_project_session_tab(
    notebook: Any,
    *,
    hotspot_binder: Callable[[AdaptiveHotspotVisualizationV1], None],
    stress_binder: Callable[[AdaptiveStressComparisonV1], None],
    recent_store_path: str | Path | None = None,
):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    panel = ttk.Frame(notebook, padding=14)
    notebook.add(panel, text="Projects")
    panel.columnconfigure(0, weight=1); panel.rowconfigure(3, weight=1)
    ttk.Label(panel, text="AsterMax Analysis Sessions", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(
        panel,
        text="Open verified .astermaxr results without re-running CAD import, Gmsh or the solver. Recent identities are checked before native Results binding.",
        wraplength=1000,
    ).grid(row=1, column=0, sticky="ew", pady=(2, 8))
    toolbar = ttk.Frame(panel); toolbar.grid(row=2, column=0, sticky="ew", pady=(0, 8))
    status_var = tk.StringVar(value="No portable analysis open.")
    tree = ttk.Treeview(panel, columns=("status", "path"), show="headings", height=12)
    tree.heading("status", text="Status"); tree.heading("path", text="Analysis package")
    tree.column("status", width=100, stretch=False); tree.column("path", width=780, stretch=True)
    tree.grid(row=3, column=0, sticky="nsew")
    ttk.Label(panel, textvariable=status_var, wraplength=1000).grid(row=4, column=0, sticky="ew", pady=(8, 0))
    current_paths: list[str] = []

    def refresh() -> None:
        for item in tree.get_children(): tree.delete(item)
        current_paths.clear()
        try:
            inspections = inspect_recent_analyses(recent_store_path)
        except ProjectSessionShellError as exc:
            status_var.set(f"Recent store invalid; verified packages can still be opened directly. {exc}")
            return
        for inspection in inspections:
            current_paths.append(inspection.package_path)
            tree.insert("", "end", values=(inspection.status, inspection.package_path))

    def open_path(path: str) -> None:
        try:
            session, _package, _receipt = open_verified_project_session(
                path, hotspot_binder=hotspot_binder, stress_binder=stress_binder, recent_store_path=recent_store_path,
            )
        except Exception as exc:
            inspection = inspect_analysis_path(path)
            status_var.set(f"{inspection.status}: {inspection.detail}")
            messagebox.showerror("AsterMax analysis verification", str(exc))
            refresh(); return
        status_var.set(
            f"VERIFIED · QoI {session.qoi_status} · Indicator {session.indicator_status} · Results restored without solver/Gmsh · {Path(session.package_path).name}"
        )
        refresh()

    def browse() -> None:
        path = filedialog.askopenfilename(filetypes=[("AsterMax Results", "*.astermaxr"), ("All files", "*.*")])
        if path: open_path(path)

    def open_selected() -> None:
        selected = tree.selection()
        if not selected: return
        values = tree.item(selected[0], "values")
        if len(values) >= 2: open_path(str(values[1]))

    ttk.Button(toolbar, text="Open Analysis…", command=browse).pack(side="left")
    ttk.Button(toolbar, text="Open Selected", command=open_selected).pack(side="left", padx=(8, 0))
    ttk.Button(toolbar, text="Refresh", command=refresh).pack(side="left", padx=(8, 0))
    tree.bind("<Double-1>", lambda _event: open_selected())
    refresh()

    # C5.5u packaged desktop cutover: install the unified project tree from the
    # same verified hotspot/stress binders already owned by the shipping shell.
    # The import stays local to avoid a module-import cycle because
    # unified_project_model itself reuses open_verified_project_session().
    from .unified_project_model import install_unified_project_tab

    install_unified_project_tab(
        notebook,
        hotspot_binder=hotspot_binder,
        stress_binder=stress_binder,
    )
    return open_path, refresh
