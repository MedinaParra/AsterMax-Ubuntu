from __future__ import annotations

from dataclasses import dataclass
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
    constraint_selection_sha256: str
    load_selection_sha256: str
    preparation_snapshot_sha256: str
    mesh_gate_sha256: str
    minimum_det_jacobian_mm3: float
    positive_jacobian_fraction: float
    maximum_relative_midside_deviation: float
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
        raise LiveAnalysisEvidenceError("live evidence refuses upgraded user-model claims")
    source = Path(summary["source_step"])
    expected_step = str(summary.get("source_step_sha256", ""))
    if len(expected_step) != 64:
        raise LiveAnalysisEvidenceError("source STEP SHA-256 is missing")
    if verify_files and file_sha256(source) != expected_step:
        raise LiveAnalysisEvidenceError("source STEP hash mismatch")

    preparation = summary.get("model_preparation", {})
    if preparation.get("schema") != "AsterMaxModelPreparationEvidenceV1":
        raise LiveAnalysisEvidenceError("C4.3 model preparation evidence is missing")
    if preparation.get("step_sha256") != expected_step:
        raise LiveAnalysisEvidenceError("model preparation STEP hash mismatch")
    mesh_gate = preparation.get("mesh_gate", {})
    if mesh_gate.get("schema") != "AsterMaxMeshPreparationGateV1":
        raise LiveAnalysisEvidenceError("mesh preparation gate is missing")
    if not bool(mesh_gate.get("positive_jacobian_verified")):
        raise LiveAnalysisEvidenceError("mesh preparation Jacobian gate is not verified")
    if not bool(mesh_gate.get("straight_sided_verified")):
        raise LiveAnalysisEvidenceError("mesh preparation straight-sided gate is not verified")
    if float(mesh_gate.get("positive_jacobian_fraction", 0.0)) != 1.0:
        raise LiveAnalysisEvidenceError("mesh preparation Jacobian fraction is not 1.0")
    if float(mesh_gate.get("minimum_det_jacobian_mm3", 0.0)) <= 0.0:
        raise LiveAnalysisEvidenceError("mesh preparation minimum Jacobian is nonpositive")
    if preparation.get("constraint_selection_sha256") == preparation.get("load_selection_sha256"):
        raise LiveAnalysisEvidenceError("constraint and load persistent selections must be distinct")

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
        "schema": "AsterMaxLiveAnalysisEvidenceV2",
        "result_class": summary["result_class"],
        "step_sha256": expected_step,
        "constraint_selection_sha256": preparation["constraint_selection_sha256"],
        "load_selection_sha256": preparation["load_selection_sha256"],
        "preparation_snapshot_sha256": preparation["snapshot_sha256"],
        "mesh_gate_sha256": mesh_gate["gate_sha256"],
        "minimum_det_jacobian_mm3": float(mesh_gate["minimum_det_jacobian_mm3"]),
        "positive_jacobian_fraction": float(mesh_gate["positive_jacobian_fraction"]),
        "maximum_relative_midside_deviation": float(mesh_gate["maximum_relative_midside_deviation"]),
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
        "evidence_boundary": "CURRENT_USER_MODEL_STEP_TO_PERSISTENT_SCOPES_TO_TET10_PREPARATION_TO_SOLVE_COMPUTED_NOT_ARBITRARY_CONVERGENCE_NOT_INDUSTRIAL_VALIDATION_NOT_ANSYS_EQUIVALENCE",
    }
    if core["mesh_family"] != "TET10" or core["mesh_size_mm"] <= 0.0 or core["node_count"] <= 0 or core["element_count"] <= 0:
        raise LiveAnalysisEvidenceError("invalid mesh evidence")
    digest = canonical_sha256(core)
    return LiveAnalysisEvidenceSnapshot(**core, snapshot_sha256=digest)


def install_live_analysis_evidence_tab(notebook: Any) -> Callable[[dict[str, Any]], None]:
    """Install Current Model Evidence and return its strict hash/provenance binder."""
    import tkinter as tk
    from tkinter import ttk

    panel = ttk.Frame(notebook, padding=18)
    notebook.add(panel, text="Current Model Evidence")
    panel.columnconfigure(0, weight=1)
    ttk.Label(panel, text="Current Model Evidence", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(panel, text="Live provenance from STEP through persistent scopes, mesh preparation, solve and artifacts. Verification fixtures remain separate.", wraplength=820).grid(row=1, column=0, sticky="ew", pady=(2, 12))
    identity = tk.StringVar(value="No user analysis bound yet.")
    preparation = tk.StringVar(value="Model preparation: —")
    mesh = tk.StringVar(value="Mesh: —")
    scopes = tk.StringVar(value="BC / Load: —")
    equilibrium = tk.StringVar(value="Equilibrium: —")
    artifacts = tk.StringVar(value="Artifacts: —")
    claims = tk.StringVar(value="Claims: converged=false · industrial validation=false · ANSYS equivalence=false")
    for row, var in enumerate((identity, preparation, mesh, scopes, equilibrium, artifacts, claims), start=2):
        ttk.Label(panel, textvariable=var, wraplength=820).grid(row=row, column=0, sticky="w", pady=4)

    def bind(summary: dict[str, Any]) -> None:
        snapshot = build_live_analysis_evidence(summary, verify_files=True)
        identity.set(f"STEP {snapshot.step_sha256[:16]}… · live evidence {snapshot.snapshot_sha256[:16]}…")
        preparation.set(
            f"Preparation: support {snapshot.constraint_selection_sha256[:12]}… · load {snapshot.load_selection_sha256[:12]}… · "
            f"min detJ {snapshot.minimum_det_jacobian_mm3:.3e} mm³ · positive IP Jacobians {snapshot.positive_jacobian_fraction:.0%} · "
            f"midside rel. deviation {snapshot.maximum_relative_midside_deviation:.3e}"
        )
        mesh.set(f"Mesh: {snapshot.mesh_family} · {snapshot.mesh_size_mm:g} mm · {snapshot.node_count} nodes · {snapshot.element_count} elements · gate {snapshot.mesh_gate_sha256[:12]}…")
        scopes.set(f"BC / Load: {snapshot.constraint_scope} · {snapshot.load_scope}")
        equilibrium.set(f"Equilibrium residuals: {snapshot.force_residual_n:.3e} N · {snapshot.moment_residual_nmm:.3e} N·mm")
        artifacts.set(f"VTU {snapshot.vtu_sha256[:16]}… · Viewer {snapshot.viewer_sha256[:16]}…")
        claims.set("Claims: converged=false · industrial validation=false · ANSYS equivalence=false")
    return bind
