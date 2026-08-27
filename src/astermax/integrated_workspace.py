from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WorkspacePanel:
    key: str
    label: str
    state: str
    detail: str
    artifact: str | None = None


WORKSPACE_ORDER = (
    "overview",
    "geometry",
    "mesh",
    "boundary_conditions",
    "solution",
    "results",
    "evidence",
)


def _artifact(summary: dict[str, Any], key: str) -> str | None:
    value = summary.get("artifacts", {}).get(key)
    return str(Path(value)) if value else None


def build_integrated_workspace(summary: dict[str, Any] | None = None) -> tuple[WorkspacePanel, ...]:
    """Build the presentation state for the native engineering workspace.

    This layer is intentionally presentation-only. It consumes the same solver
    summary used by the project tree and must never upgrade numerical or
    validation claims.
    """
    if summary is None:
        return (
            WorkspacePanel("overview", "Overview", "READY", "Open a verified .astermax project to begin."),
            WorkspacePanel("geometry", "Geometry", "PENDING", "STEP provenance and TET10 geometry scope not evaluated."),
            WorkspacePanel("mesh", "Mesh", "PENDING", "Mesh not generated."),
            WorkspacePanel("boundary_conditions", "BC / Loads", "PENDING", "Persistent SUPPORT and LOAD scopes not resolved."),
            WorkspacePanel("solution", "Solution", "PENDING", "No FEA solution available."),
            WorkspacePanel("results", "Results", "PENDING", "No verified result artifact available."),
            WorkspacePanel("evidence", "Evidence", "PENDING", "No Analysis Passport available."),
        )

    mesh = summary.get("mesh", {})
    quality = summary.get("mesh_quality", {})
    geometry = summary.get("tet10_geometry_scope", {})
    checks = summary.get("checks", {})
    claims = summary.get("claims", {})
    passport = summary.get("analysis_passport", {})

    nodes = int(mesh.get("nodes", 0))
    elements = int(mesh.get("elements", 0))
    supports = int(mesh.get("support_tri6", 0))
    loads = int(mesh.get("load_tri6", 0))
    force_residual = float(checks.get("force_residual_n", float("nan")))
    moment_residual = float(checks.get("moment_residual_nmm", float("nan")))

    geometry_state = "VERIFIED" if geometry.get("status") == "PASS" else "FAILED"
    mesh_state = "VERIFIED" if quality.get("status") in {"PASS", "WARN"} and elements > 0 else "FAILED"
    bc_state = "VERIFIED" if supports > 0 and loads > 0 else "FAILED"
    solved = nodes > 0 and elements > 0
    equilibrium = solved and force_residual <= 1.0e-5 and moment_residual <= 1.0e-3
    solution_state = "EQUILIBRIUM_VERIFIED" if equilibrium else ("COMPUTED" if solved else "FAILED")
    highest = str(passport.get("highest_demonstrated_stage", "INCOMPLETE"))

    guarded_claims = (
        f"converged={bool(claims.get('converged', False))}; "
        f"industrial_validation={bool(claims.get('industrial_validation', False))}; "
        f"ansys_equivalence={bool(claims.get('ansys_equivalence', False))}; "
        f"curved_tet10={bool(claims.get('curved_tet10', False))}"
    )

    return (
        WorkspacePanel(
            "overview",
            "Overview",
            highest,
            f"{nodes} nodes / {elements} TET10 · SUPPORT {supports} TRI6 · LOAD {loads} TRI6 · {guarded_claims}",
        ),
        WorkspacePanel(
            "geometry",
            "Geometry",
            geometry_state,
            f"STEP provenance + TET10 geometry scope · status={geometry.get('status', 'UNKNOWN')}",
        ),
        WorkspacePanel(
            "mesh",
            "Mesh",
            mesh_state,
            f"quality={quality.get('status', 'UNKNOWN')} · {nodes} nodes / {elements} TET10",
            _artifact(summary, "mesh_inspector"),
        ),
        WorkspacePanel(
            "boundary_conditions",
            "BC / Loads",
            bc_state,
            f"SUPPORT {supports} TRI6 · LOAD {loads} TRI6 · persistent CAD selections",
        ),
        WorkspacePanel(
            "solution",
            "Solution",
            solution_state,
            f"|sum F|={force_residual:.3e} N · |sum M|={moment_residual:.3e} N*mm · {guarded_claims}",
        ),
        WorkspacePanel(
            "results",
            "Results",
            "AVAILABLE" if _artifact(summary, "viewer") else "MISSING",
            "Verified offline result viewer. Native 3D embedding is not claimed.",
            _artifact(summary, "viewer"),
        ),
        WorkspacePanel(
            "evidence",
            "Evidence",
            highest,
            "Analysis Passport and Results/Evidence workspace preserve the solver evidence boundary.",
            _artifact(summary, "results_evidence_workspace") or _artifact(summary, "analysis_passport"),
        ),
    )


def assert_workspace_does_not_upgrade_claims(summary: dict[str, Any], panels: tuple[WorkspacePanel, ...]) -> None:
    claims = summary.get("claims", {})
    combined = " ".join((p.state + " " + p.detail).lower() for p in panels)
    guarded = {
        "converged": bool(claims.get("converged", False)),
        "industrial_validation": bool(claims.get("industrial_validation", False)),
        "ansys_equivalence": bool(claims.get("ansys_equivalence", False)),
        "curved_tet10": bool(claims.get("curved_tet10", False)),
    }
    for token, allowed in guarded.items():
        if not allowed and f"{token}=true" in combined:
            raise ValueError(f"integrated workspace attempted to upgrade {token} claim")
