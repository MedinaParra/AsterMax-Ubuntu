from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProjectTreeNode:
    key: str
    label: str
    state: str
    detail: str = ""
    artifact: str | None = None


TREE_ORDER = (
    "geometry",
    "mesh",
    "supports",
    "loads",
    "solution",
    "results",
    "evidence",
)


def _artifact(summary: dict[str, Any], key: str) -> str | None:
    raw = summary.get("artifacts", {}).get(key)
    if not raw:
        return None
    return str(Path(raw))


def build_project_tree(summary: dict[str, Any] | None = None) -> tuple[ProjectTreeNode, ...]:
    """Return a deterministic project-tree snapshot for the desktop shell.

    The tree is presentation-only. It derives state from solver evidence and never
    upgrades convergence, industrial-validation, ANSYS-equivalence or curved-TET10
    claims.
    """
    if summary is None:
        return (
            ProjectTreeNode("geometry", "Geometry", "READY", "Open STEP / .astermax"),
            ProjectTreeNode("mesh", "Mesh", "PENDING", "TET10 not generated"),
            ProjectTreeNode("supports", "Supports", "PENDING", "Persistent CAD scope"),
            ProjectTreeNode("loads", "Loads", "PENDING", "Persistent CAD scope"),
            ProjectTreeNode("solution", "Solution", "PENDING", "Not solved"),
            ProjectTreeNode("results", "Results", "PENDING", "No result artifact"),
            ProjectTreeNode("evidence", "Evidence", "PENDING", "No passport/workspace"),
        )

    mesh = summary.get("mesh", {})
    quality = summary.get("mesh_quality", {})
    geometry_scope = summary.get("tet10_geometry_scope", {})
    checks = summary.get("checks", {})
    claims = summary.get("claims", {})
    passport = summary.get("analysis_passport", {})

    geometry_ok = geometry_scope.get("status") == "PASS"
    mesh_ok = quality.get("status") in {"PASS", "WARN"} and int(mesh.get("elements", 0)) > 0
    support_ok = int(mesh.get("support_tri6", 0)) > 0
    load_ok = int(mesh.get("load_tri6", 0)) > 0
    force_ok = float(checks.get("force_residual_n", float("inf"))) <= 1.0e-5
    moment_ok = float(checks.get("moment_residual_nmm", float("inf"))) <= 1.0e-3
    solved = int(mesh.get("nodes", 0)) > 0 and int(mesh.get("elements", 0)) > 0

    claim_detail = (
        f"converged={bool(claims.get('converged', False))}; "
        f"industrial={bool(claims.get('industrial_validation', False))}; "
        f"ansys={bool(claims.get('ansys_equivalence', False))}"
    )

    return (
        ProjectTreeNode(
            "geometry",
            "Geometry",
            "VERIFIED" if geometry_ok else "FAILED",
            "STEP provenance + TET10 geometry scope",
        ),
        ProjectTreeNode(
            "mesh",
            "Mesh",
            "VERIFIED" if mesh_ok else "FAILED",
            f"{int(mesh.get('nodes', 0))} nodes / {int(mesh.get('elements', 0))} TET10 · quality={quality.get('status', 'UNKNOWN')}",
            _artifact(summary, "mesh_inspector"),
        ),
        ProjectTreeNode(
            "supports",
            "Supports",
            "VERIFIED" if support_ok else "FAILED",
            f"{int(mesh.get('support_tri6', 0))} TRI6 · persistent CAD selection",
        ),
        ProjectTreeNode(
            "loads",
            "Loads",
            "VERIFIED" if load_ok else "FAILED",
            f"{int(mesh.get('load_tri6', 0))} TRI6 · persistent CAD selection",
        ),
        ProjectTreeNode(
            "solution",
            "Solution",
            "EQUILIBRIUM_VERIFIED" if solved and force_ok and moment_ok else ("COMPUTED" if solved else "FAILED"),
            f"|ΣF|={float(checks.get('force_residual_n', float('nan'))):.3e} N · |ΣM|={float(checks.get('moment_residual_nmm', float('nan'))):.3e} N·mm · {claim_detail}",
        ),
        ProjectTreeNode(
            "results",
            "Results",
            "AVAILABLE" if _artifact(summary, "viewer") else "MISSING",
            "Offline result viewer",
            _artifact(summary, "viewer"),
        ),
        ProjectTreeNode(
            "evidence",
            "Evidence",
            str(passport.get("highest_demonstrated_stage", "INCOMPLETE")),
            "Analysis Passport + Results/Evidence Workspace",
            _artifact(summary, "results_evidence_workspace") or _artifact(summary, "analysis_passport"),
        ),
    )


def assert_tree_does_not_upgrade_claims(summary: dict[str, Any], nodes: tuple[ProjectTreeNode, ...]) -> None:
    """Fail closed if presentation text implies stronger claims than the summary."""
    claims = summary.get("claims", {})
    combined = " ".join((n.state + " " + n.detail).lower() for n in nodes)
    guarded = {
        "converged": bool(claims.get("converged", False)),
        "industrial": bool(claims.get("industrial_validation", False)),
        "ansys": bool(claims.get("ansys_equivalence", False)),
    }
    for token, allowed in guarded.items():
        if not allowed and f"{token}=true" in combined:
            raise ValueError(f"project tree attempted to upgrade {token} claim")
