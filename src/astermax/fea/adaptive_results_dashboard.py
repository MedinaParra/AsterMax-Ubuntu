from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Any

from astermax.credibility import canonical_sha256
from .adaptive_demo_session import (
    AdaptiveDemoSessionV1,
    AdaptiveDemoStageV1,
    AdaptiveDemoSessionError,
    verify_adaptive_demo_session,
)


class AdaptiveResultsDashboardError(ValueError):
    pass


@dataclass(frozen=True)
class AdaptiveMetricComparisonV1:
    name: str
    unit: str
    baseline_value: float
    refined_value: float
    absolute_change: float
    relative_change: float | None


@dataclass(frozen=True)
class AdaptiveResultsDashboardV1:
    schema: str
    semantics: str
    status: str
    title: str
    session_sha256: str
    source_step_sha256: str
    route_sha256: str
    qoi_status: str
    qoi_criterion_maximum_relative_change: float
    metrics: tuple[AdaptiveMetricComparisonV1, ...]
    stages: tuple[AdaptiveDemoStageV1, ...]
    claims: dict[str, bool]
    evidence_boundary: str
    dashboard_sha256: str


def _comparison(name: str, unit: str, baseline: float, refined: float, relative: float | None = None) -> AdaptiveMetricComparisonV1:
    a = float(baseline); b = float(refined)
    if not math.isfinite(a) or not math.isfinite(b):
        raise AdaptiveResultsDashboardError("ADAPTIVE_RESULTS_NONFINITE")
    delta = b - a
    if relative is None:
        scale = max(abs(a), abs(b))
        rel = None if scale == 0.0 else abs(delta) / scale
    else:
        rel = float(relative)
        if not math.isfinite(rel) or rel < 0.0:
            raise AdaptiveResultsDashboardError("ADAPTIVE_RESULTS_RELATIVE_CHANGE")
    return AdaptiveMetricComparisonV1(name, unit, a, b, delta, rel)


def build_adaptive_results_dashboard(session: AdaptiveDemoSessionV1) -> AdaptiveResultsDashboardV1:
    try:
        verify_adaptive_demo_session(session)
    except AdaptiveDemoSessionError as exc:
        raise AdaptiveResultsDashboardError(f"ADAPTIVE_RESULTS_SESSION:{exc}") from exc

    metrics = (
        _comparison(session.qoi_name, session.qoi_unit, session.baseline_qoi_value, session.remesh_qoi_value, session.qoi_relative_change),
        _comparison("Force equilibrium residual", "N", session.baseline_force_residual_n, session.remesh_force_residual_n),
        _comparison("Moment equilibrium residual", "N·mm", session.baseline_moment_residual_nmm, session.remesh_moment_residual_nmm),
    )
    claims = dict(session.claims)
    if claims.get("global_analysis_converged") or claims.get("industrial_validation") or claims.get("ansys_equivalence"):
        raise AdaptiveResultsDashboardError("ADAPTIVE_RESULTS_OVERCLAIM")

    core = {
        "schema": "AsterMaxNativeAdaptiveResultsDashboardV1",
        "status": "READY",
        "session_sha256": session.session_sha256,
        "source_step_sha256": session.source_step_sha256,
        "route_sha256": session.route_sha256,
        "qoi_status": session.qoi_status,
        "qoi_criterion_maximum_relative_change": session.qoi_criterion_maximum_relative_change,
        "metrics": [asdict(item) for item in metrics],
        "stages": [asdict(item) for item in session.stages],
        "claims": claims,
    }
    return AdaptiveResultsDashboardV1(
        schema=core["schema"],
        semantics="native_presentation_projection_of_verified_adaptive_session_no_physics_recomputation",
        status="READY",
        title="Adaptive Results · Baseline vs Refined",
        session_sha256=session.session_sha256,
        source_step_sha256=session.source_step_sha256,
        route_sha256=session.route_sha256,
        qoi_status=session.qoi_status,
        qoi_criterion_maximum_relative_change=float(session.qoi_criterion_maximum_relative_change),
        metrics=metrics,
        stages=session.stages,
        claims=claims,
        evidence_boundary="QOI_DISCRETIZATION_ONLY_NOT_GLOBAL_CONVERGENCE_NOT_INDUSTRIAL_VALIDATION_NOT_ANSYS_EQUIVALENCE",
        dashboard_sha256=canonical_sha256(core),
    )


def save_adaptive_demo_session_json(session: AdaptiveDemoSessionV1, path: str | Path) -> Path:
    verify_adaptive_demo_session(session)
    target = Path(path)
    payload = asdict(session)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def load_adaptive_demo_session_json(path: str | Path) -> AdaptiveDemoSessionV1:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        payload["stages"] = tuple(AdaptiveDemoStageV1(**item) for item in payload["stages"])
        session = AdaptiveDemoSessionV1(**payload)
        verify_adaptive_demo_session(session)
        return session
    except Exception as exc:
        raise AdaptiveResultsDashboardError(f"ADAPTIVE_RESULTS_JSON:{exc}") from exc


def install_adaptive_results_dashboard_tab(notebook: Any) -> Any:
    """Install a native Tk/ttk adaptive Results tab backed only by verified session JSON."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    panel = ttk.Frame(notebook, padding=18)
    notebook.add(panel, text="Adaptive Results")
    panel.columnconfigure(0, weight=1)
    ttk.Label(panel, text="Adaptive FEA · Baseline vs Refined", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(panel, text="Presentation-only view of a provenance-matched two-solve session. No physics is recomputed in this tab.", wraplength=900).grid(row=1, column=0, sticky="ew", pady=(2, 10))

    identity = tk.StringVar(value="No verified adaptive session loaded.")
    qoi = tk.StringVar(value="QoI comparison: —")
    boundary = tk.StringVar(value="Global convergence: false · Industrial validation: false · ANSYS equivalence: false")
    ttk.Label(panel, textvariable=identity, wraplength=900).grid(row=2, column=0, sticky="w", pady=3)
    ttk.Label(panel, textvariable=qoi, font=("Segoe UI", 11, "bold"), wraplength=900).grid(row=3, column=0, sticky="w", pady=3)

    metrics = ttk.Treeview(panel, columns=("metric", "baseline", "refined", "delta"), show="headings", height=4)
    for key, label, width in (("metric", "Metric", 260), ("baseline", "Baseline", 170), ("refined", "Refined", 170), ("delta", "Δ", 170)):
        metrics.heading(key, text=label); metrics.column(key, width=width, anchor="center")
    metrics.grid(row=4, column=0, sticky="ew", pady=(10, 8))

    stages = ttk.Treeview(panel, columns=("index", "stage", "status", "evidence"), show="headings", height=9)
    for key, label, width in (("index", "#", 50), ("stage", "Evidence stage", 360), ("status", "Status", 90), ("evidence", "Evidence SHA", 260)):
        stages.heading(key, text=label); stages.column(key, width=width, anchor="center")
    stages.grid(row=5, column=0, sticky="ew", pady=(4, 8))
    ttk.Label(panel, textvariable=boundary, wraplength=900).grid(row=6, column=0, sticky="ew", pady=3)

    def bind_dashboard(dashboard: AdaptiveResultsDashboardV1) -> None:
        identity.set(f"STEP {dashboard.source_step_sha256[:16]}… · Route {dashboard.route_sha256[:16]}… · Session {dashboard.session_sha256[:16]}…")
        first = dashboard.metrics[0]
        qoi.set(f"{first.name}: {first.baseline_value:.6g} → {first.refined_value:.6g} {first.unit} · relative change {100*(first.relative_change or 0.0):.4g}% · criterion ≤ {100*dashboard.qoi_criterion_maximum_relative_change:.4g}% · {dashboard.qoi_status}")
        for item in metrics.get_children(): metrics.delete(item)
        for row in dashboard.metrics:
            metrics.insert("", "end", values=(f"{row.name} [{row.unit}]", f"{row.baseline_value:.6g}", f"{row.refined_value:.6g}", f"{row.absolute_change:+.6g}"))
        for item in stages.get_children(): stages.delete(item)
        for stage in dashboard.stages:
            stages.insert("", "end", values=(stage.index, stage.label, stage.status, stage.evidence_sha256[:20] + "…"))
        boundary.set("Evidence boundary: QoI discretization only · global convergence = false · industrial validation = false · ANSYS equivalence = false")

    def load_session() -> None:
        path = filedialog.askopenfilename(filetypes=[("AsterMax adaptive session", "*.json"), ("All files", "*.*")])
        if not path: return
        try:
            bind_dashboard(build_adaptive_results_dashboard(load_adaptive_demo_session_json(path)))
        except Exception as exc:
            messagebox.showerror("AsterMax Adaptive Results", str(exc))

    ttk.Button(panel, text="Load verified adaptive session", command=load_session).grid(row=7, column=0, sticky="ew", pady=(12, 0))
    return bind_dashboard
