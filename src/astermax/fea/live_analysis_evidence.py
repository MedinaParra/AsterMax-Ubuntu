from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
from typing import Any, Callable

from astermax.credibility import canonical_sha256


class LiveAnalysisEvidenceError(ValueError):
    pass


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class LiveAnalysisEvidenceSnapshot:
    schema: str
    result_class: str
    step_sha256: str
    mesh_family: str
    mesh_size_mm: float
    node_count: int
    element_count: int
    constraint_scope: str
    load_scope: str
    force_residual_n: float
    moment_residual_nmm: float
    vtu_sha256: str
    viewer_sha256: str
    converged: bool
    industrial_validation: bool
    ansys_equivalence: bool
    evidence_boundary: str
    snapshot_sha256: str


def build_live_analysis_evidence(summary: dict[str, Any], *, verify_files: bool = True) -> LiveAnalysisEvidenceSnapshot:
    if summary.get("schema") != "AsterMaxDesktopPMVResultV1":
        raise LiveAnalysisEvidenceError("unsupported desktop result schema")
    claims = summary.get("claims", {})
    if any(bool(claims.get(key, False)) for key in ("converged", "industrial_validation", "ansys_equivalence")):
        raise LiveAnalysisEvidenceError("C4.2 refuses upgraded user-model claims")
    source = Path(summary["source_step"])
    expected_step = str(summary.get("source_step_sha256", ""))
    if len(expected_step) != 64:
        raise LiveAnalysisEvidenceError("source STEP SHA-256 is missing")
    if verify_files and file_sha256(source) != expected_step:
        raise LiveAnalysisEvidenceError("source STEP hash mismatch")
    artifacts = summary["artifacts"]
    if verify_files:
        if file_sha256(artifacts["vtu"]) != artifacts["vtu_sha256"]:
            raise LiveAnalysisEvidenceError("VTU hash mismatch")
        if file_sha256(artifacts["viewer"]) != artifacts["viewer_sha256"]:
            raise LiveAnalysisEvidenceError("viewer hash mismatch")
    mesh = summary["mesh"]
    scopes = summary["scope_contract"]
    checks = summary["checks"]
    core = {
        "schema": "AsterMaxLiveAnalysisEvidenceV1",
        "result_class": summary["result_class"],
        "step_sha256": expected_step,
        "mesh_family": mesh["family"],
        "mesh_size_mm": float(mesh["target_size_mm"]),
        "node_count": int(mesh["nodes"]),
        "element_count": int(mesh["elements"]),
        "constraint_scope": scopes["constraint"],
        "load_scope": scopes["load"],
        "force_residual_n": float(checks["force_residual_n"]),
        "moment_residual_nmm": float(checks["moment_residual_nmm"]),
        "vtu_sha256": artifacts["vtu_sha256"],
        "viewer_sha256": artifacts["viewer_sha256"],
        "converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
        "evidence_boundary": "CURRENT_USER_MODEL_COMPUTED_NOT_CONVERGENCE_VERIFIED_NOT_INDUSTRIAL_VALIDATION_NOT_ANSYS_EQUIVALENCE",
    }
    if core["mesh_family"] != "TET10" or core["mesh_size_mm"] <= 0.0 or core["node_count"] <= 0 or core["element_count"] <= 0:
        raise LiveAnalysisEvidenceError("invalid mesh evidence")
    digest = canonical_sha256(core)
    return LiveAnalysisEvidenceSnapshot(**core, snapshot_sha256=digest)


def install_live_analysis_evidence_tab(notebook: Any) -> Callable[[dict[str, Any]], None]:
    """Install a native Current Model Evidence tab and return its strict binder."""
    import tkinter as tk
    from tkinter import ttk

    panel = ttk.Frame(notebook, padding=18)
    notebook.add(panel, text="Current Model Evidence")
    panel.columnconfigure(0, weight=1)
    ttk.Label(panel, text="Current Model Evidence", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(panel, text="Evidence from the just-completed user solve. This is intentionally separate from solver verification fixtures.", wraplength=780).grid(row=1, column=0, sticky="ew", pady=(2, 12))
    identity = tk.StringVar(value="No user analysis bound yet.")
    mesh = tk.StringVar(value="Mesh: —")
    scopes = tk.StringVar(value="BC / Load: —")
    equilibrium = tk.StringVar(value="Equilibrium: —")
    artifacts = tk.StringVar(value="Artifacts: —")
    claims = tk.StringVar(value="Claims: converged=false · industrial validation=false · ANSYS equivalence=false")
    for row, var in enumerate((identity, mesh, scopes, equilibrium, artifacts, claims), start=2):
        ttk.Label(panel, textvariable=var, wraplength=780).grid(row=row, column=0, sticky="w", pady=4)

    def bind(summary: dict[str, Any]) -> None:
        snapshot = build_live_analysis_evidence(summary, verify_files=True)
        identity.set(f"STEP SHA-256 {snapshot.step_sha256[:20]}… · evidence {snapshot.snapshot_sha256[:20]}…")
        mesh.set(f"Mesh: {snapshot.mesh_family} · {snapshot.mesh_size_mm:g} mm · {snapshot.node_count} nodes · {snapshot.element_count} elements")
        scopes.set(f"BC / Load: {snapshot.constraint_scope} · {snapshot.load_scope}")
        equilibrium.set(f"Equilibrium residuals: {snapshot.force_residual_n:.3e} N · {snapshot.moment_residual_nmm:.3e} N·mm")
        artifacts.set(f"VTU {snapshot.vtu_sha256[:16]}… · Viewer {snapshot.viewer_sha256[:16]}…")
        claims.set("Claims: converged=false · industrial validation=false · ANSYS equivalence=false")
    return bind
