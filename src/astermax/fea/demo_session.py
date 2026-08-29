from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any


@dataclass(frozen=True)
class DemoStageV1:
    name: str
    status: str
    evidence_sha256: str
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class EndToEndDemoSessionV1:
    schema: str
    semantics: str
    status: str
    blockers: tuple[str, ...]
    units: dict[str, str]
    stage_count: int
    ready_stage_count: int
    stages: tuple[DemoStageV1, ...]
    source_step_sha256: str
    solve_evidence_sha256: str
    workspace_sha256: str
    section_contour_sha256: str
    session_sha256: str
    claims: dict[str, bool]


def _sha(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _mapping(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def build_end_to_end_demo_session(summary: dict, section_ui: Any) -> EndToEndDemoSessionV1:
    """Audit one Windows demo session from CAD provenance through native section Results.

    This contract does not recompute physics. It verifies that evidence already produced by
    the CAD/mesh/BC/solve/Results/section chain is internally closed and publishes one
    deterministic READY/BLOCKED manifest for a professional demo session.
    """
    if not isinstance(summary, dict):
        raise ValueError("DEMO_SESSION_SUMMARY")
    units = summary.get("units")
    expected_units = {"length": "mm", "force": "N", "stress": "MPa"}
    if units != expected_units:
        raise ValueError("DEMO_SESSION_UNIT_CONTRACT")

    claims = summary.get("claims")
    if claims != {"converged": False, "industrial_validation": False, "ansys_equivalence": False}:
        raise ValueError("DEMO_SESSION_CLAIM_BOUNDARY")

    stage_specs: list[tuple[str, dict, list[str]]] = []

    source_sha = str(summary.get("source_step_sha256") or "")
    cad_blockers = [] if len(source_sha) == 64 else ["CAD_SOURCE_SHA_REQUIRED"]
    stage_specs.append(("CAD_STEP_MM", {"source_step_sha256": source_sha, "units": units}, cad_blockers))

    prep = _mapping(summary.get("preparation"))
    prep_blockers = [] if prep else ["MODEL_PREPARATION_EVIDENCE_REQUIRED"]
    stage_specs.append(("MODEL_PREPARATION", prep, prep_blockers))

    scope = _mapping(summary.get("scope_contract"))
    bc_required = ("support_binding_sha256", "load_binding_sha256", "route_sha256")
    bc_blockers = [f"BC_LOAD_{key.upper()}_REQUIRED" for key in bc_required if not scope.get(key)]
    stage_specs.append(("BC_LOAD_BINDING", scope, bc_blockers))

    mesh = _mapping(summary.get("mesh"))
    mesh_blockers: list[str] = []
    if mesh.get("family") != "TET10": mesh_blockers.append("MESH_TET10_REQUIRED")
    if int(mesh.get("nodes", 0)) <= 0 or int(mesh.get("elements", 0)) <= 0: mesh_blockers.append("MESH_NONEMPTY_REQUIRED")
    if not math.isfinite(float(mesh.get("target_size_mm", 0.0))) or float(mesh.get("target_size_mm", 0.0)) <= 0.0: mesh_blockers.append("MESH_SIZE_MM_REQUIRED")
    stage_specs.append(("MESH_TET10", mesh, mesh_blockers))

    solve = _mapping(summary.get("solve_evidence"))
    solve_sha = str(solve.get("solve_evidence_sha256") or "")
    solve_blockers: list[str] = []
    if len(solve_sha) != 64: solve_blockers.append("SOLVE_EVIDENCE_SHA_REQUIRED")
    checks = _mapping(summary.get("checks"))
    for key in ("force_residual_n", "moment_residual_nmm"):
        try: value = float(checks[key])
        except Exception: solve_blockers.append(f"{key.upper()}_REQUIRED"); continue
        if not math.isfinite(value): solve_blockers.append(f"{key.upper()}_FINITE_REQUIRED")
    stage_specs.append(("SPARSE_FEA_SOLVE", {"solve": solve, "checks": checks}, solve_blockers))

    results = _mapping(summary.get("production_results"))
    workspace_sha = str(results.get("workspace_sha256") or "")
    results_blockers: list[str] = []
    if len(workspace_sha) != 64: results_blockers.append("RESULTS_WORKSPACE_SHA_REQUIRED")
    if str(results.get("solve_evidence_sha256") or "") != solve_sha: results_blockers.append("RESULTS_SOLVE_PROVENANCE_STALE")
    stage_specs.append(("PRODUCTION_RESULTS", results, results_blockers))

    ui = _mapping(section_ui)
    contour_sha = str(ui.get("contour_sha256") or "")
    section_blockers: list[str] = []
    if ui.get("status") != "READY": section_blockers.append("SECTION_UI_NOT_READY")
    if str(ui.get("workspace_sha256") or "") != workspace_sha: section_blockers.append("SECTION_WORKSPACE_STALE")
    if str(ui.get("solve_evidence_sha256") or "") != solve_sha: section_blockers.append("SECTION_SOLVE_STALE")
    if len(contour_sha) != 64: section_blockers.append("SECTION_CONTOUR_SHA_REQUIRED")
    stage_specs.append(("SECTION_CONTOUR_PROBE", ui, section_blockers))

    artifacts = _mapping(summary.get("artifacts"))
    artifact_blockers = [f"ARTIFACT_{key.upper()}_SHA_REQUIRED" for key in ("vtu_sha256", "viewer_sha256") if not artifacts.get(key)]
    stage_specs.append(("EVIDENCE_EXPORT", artifacts, artifact_blockers))

    stages: list[DemoStageV1] = []
    all_blockers: list[str] = []
    for name, payload, blockers in stage_specs:
        status = "READY" if not blockers else "BLOCKED"
        stages.append(DemoStageV1(name=name, status=status, evidence_sha256=_sha(payload), blockers=tuple(blockers)))
        all_blockers.extend(f"{name}:{item}" for item in blockers)

    identity = {
        "schema": "AsterMaxEndToEndDemoSessionV1",
        "units": units,
        "source_step_sha256": source_sha,
        "solve_evidence_sha256": solve_sha,
        "workspace_sha256": workspace_sha,
        "section_contour_sha256": contour_sha,
        "stages": [stage.__dict__ for stage in stages],
        "claims": claims,
    }
    return EndToEndDemoSessionV1(
        schema="AsterMaxEndToEndDemoSessionV1",
        semantics="provenance_closed_windows_demo_session_readiness_not_physics_revalidation",
        status="READY" if not all_blockers else "BLOCKED",
        blockers=tuple(all_blockers),
        units=dict(units),
        stage_count=len(stages),
        ready_stage_count=sum(stage.status == "READY" for stage in stages),
        stages=tuple(stages),
        source_step_sha256=source_sha,
        solve_evidence_sha256=solve_sha,
        workspace_sha256=workspace_sha,
        section_contour_sha256=contour_sha,
        session_sha256=_sha(identity),
        claims=dict(claims),
    )
