from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any


@dataclass(frozen=True)
class DemoDashboardStageV1:
    index: int
    name: str
    label: str
    status: str
    evidence_sha256: str
    blocker_count: int


@dataclass(frozen=True)
class DemoDashboardV1:
    schema: str
    semantics: str
    status: str
    title: str
    subtitle: str
    progress_fraction: float
    progress_percent: int
    stage_count: int
    ready_stage_count: int
    stages: tuple[DemoDashboardStageV1, ...]
    provenance: dict[str, str]
    claims: dict[str, bool]
    dashboard_sha256: str


_LABELS = {
    "CAD_STEP_MM": "CAD / STEP [mm]",
    "MODEL_PREPARATION": "Model preparation",
    "BC_LOAD_BINDING": "Boundary conditions & loads",
    "MESH_TET10": "TET10 mesh",
    "SPARSE_FEA_SOLVE": "Sparse FEA solve",
    "PRODUCTION_RESULTS": "Professional Results",
    "SECTION_CONTOUR_PROBE": "Section contour & probe",
    "EVIDENCE_EXPORT": "Evidence export",
}


def _sha(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def build_demo_dashboard(session: Any) -> DemoDashboardV1:
    """Build a deterministic, presentation-only dashboard from a verified demo session.

    No physics is recomputed here. The dashboard is allowed to display only evidence that
    already exists in AsterMaxEndToEndDemoSessionV1 and fails closed on malformed/stale input.
    """
    if getattr(session, "schema", None) != "AsterMaxEndToEndDemoSessionV1":
        raise ValueError("DEMO_DASHBOARD_SESSION_SCHEMA")
    if getattr(session, "status", None) not in {"READY", "BLOCKED"}:
        raise ValueError("DEMO_DASHBOARD_SESSION_STATUS")

    stage_count = int(getattr(session, "stage_count", 0))
    ready_count = int(getattr(session, "ready_stage_count", -1))
    stages_raw = tuple(getattr(session, "stages", ()))
    if stage_count != len(stages_raw) or stage_count <= 0:
        raise ValueError("DEMO_DASHBOARD_STAGE_COUNT")
    if not 0 <= ready_count <= stage_count:
        raise ValueError("DEMO_DASHBOARD_READY_COUNT")

    stages: list[DemoDashboardStageV1] = []
    observed_ready = 0
    for index, stage in enumerate(stages_raw, start=1):
        name = str(getattr(stage, "name", ""))
        status = str(getattr(stage, "status", ""))
        evidence_sha = str(getattr(stage, "evidence_sha256", ""))
        blockers = tuple(getattr(stage, "blockers", ()))
        if name not in _LABELS:
            raise ValueError("DEMO_DASHBOARD_UNKNOWN_STAGE")
        if status not in {"READY", "BLOCKED"}:
            raise ValueError("DEMO_DASHBOARD_STAGE_STATUS")
        if len(evidence_sha) != 64:
            raise ValueError("DEMO_DASHBOARD_STAGE_EVIDENCE_SHA")
        if status == "READY" and blockers:
            raise ValueError("DEMO_DASHBOARD_READY_WITH_BLOCKERS")
        if status == "BLOCKED" and not blockers:
            raise ValueError("DEMO_DASHBOARD_BLOCKED_WITHOUT_BLOCKER")
        if status == "READY":
            observed_ready += 1
        stages.append(
            DemoDashboardStageV1(
                index=index,
                name=name,
                label=_LABELS[name],
                status=status,
                evidence_sha256=evidence_sha,
                blocker_count=len(blockers),
            )
        )
    if observed_ready != ready_count:
        raise ValueError("DEMO_DASHBOARD_READY_COUNT_STALE")

    session_status = str(session.status)
    if (session_status == "READY") != (ready_count == stage_count):
        raise ValueError("DEMO_DASHBOARD_SESSION_CLOSURE_STALE")

    provenance = {
        "session_sha256": str(getattr(session, "session_sha256", "")),
        "source_step_sha256": str(getattr(session, "source_step_sha256", "")),
        "solve_evidence_sha256": str(getattr(session, "solve_evidence_sha256", "")),
        "workspace_sha256": str(getattr(session, "workspace_sha256", "")),
        "section_contour_sha256": str(getattr(session, "section_contour_sha256", "")),
    }
    if any(len(value) != 64 for value in provenance.values()):
        raise ValueError("DEMO_DASHBOARD_PROVENANCE_SHA")

    claims = dict(getattr(session, "claims", {}))
    expected_claims = {"converged": False, "industrial_validation": False, "ansys_equivalence": False}
    if claims != expected_claims:
        raise ValueError("DEMO_DASHBOARD_CLAIM_BOUNDARY")

    progress_fraction = ready_count / stage_count
    identity = {
        "schema": "AsterMaxNativeDemoDashboardV1",
        "status": session_status,
        "progress_fraction": progress_fraction,
        "stages": [stage.__dict__ for stage in stages],
        "provenance": provenance,
        "claims": claims,
    }
    return DemoDashboardV1(
        schema="AsterMaxNativeDemoDashboardV1",
        semantics="presentation_only_provenance_closed_demo_dashboard_not_physics_revalidation",
        status=session_status,
        title="AsterMax PMV · Engineering Evidence Dashboard",
        subtitle="STEP [mm] → preparation → BC/load → TET10 → solve → Results → section/probe → evidence",
        progress_fraction=progress_fraction,
        progress_percent=round(progress_fraction * 100),
        stage_count=stage_count,
        ready_stage_count=ready_count,
        stages=tuple(stages),
        provenance=provenance,
        claims=claims,
        dashboard_sha256=_sha(identity),
    )
