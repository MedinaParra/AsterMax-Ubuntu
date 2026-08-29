from __future__ import annotations

from dataclasses import replace

import pytest

from astermax.fea.demo_dashboard import build_demo_dashboard
from astermax.fea.demo_session import DemoStageV1, EndToEndDemoSessionV1


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64


def _session(*, blocked: bool = False) -> EndToEndDemoSessionV1:
    names = (
        "CAD_STEP_MM",
        "MODEL_PREPARATION",
        "BC_LOAD_BINDING",
        "MESH_TET10",
        "SPARSE_FEA_SOLVE",
        "PRODUCTION_RESULTS",
        "SECTION_CONTOUR_PROBE",
        "EVIDENCE_EXPORT",
    )
    stages = []
    for index, name in enumerate(names):
        is_blocked = blocked and index == 6
        stages.append(
            DemoStageV1(
                name=name,
                status="BLOCKED" if is_blocked else "READY",
                evidence_sha256=(hex(index + 1)[2:] * 64)[:64],
                blockers=("SECTION_UI_NOT_READY",) if is_blocked else (),
            )
        )
    ready = 7 if blocked else 8
    return EndToEndDemoSessionV1(
        schema="AsterMaxEndToEndDemoSessionV1",
        semantics="provenance_closed_windows_demo_session_readiness_not_physics_revalidation",
        status="BLOCKED" if blocked else "READY",
        blockers=("SECTION_CONTOUR_PROBE:SECTION_UI_NOT_READY",) if blocked else (),
        units={"length": "mm", "force": "N", "stress": "MPa"},
        stage_count=8,
        ready_stage_count=ready,
        stages=tuple(stages),
        source_step_sha256=SHA_A,
        solve_evidence_sha256=SHA_B,
        workspace_sha256=SHA_C,
        section_contour_sha256=SHA_D,
        session_sha256=SHA_E,
        claims={"converged": False, "industrial_validation": False, "ansys_equivalence": False},
    )


def test_ready_dashboard_is_deterministic_and_complete():
    session = _session()
    first = build_demo_dashboard(session)
    second = build_demo_dashboard(session)
    assert first == second
    assert first.status == "READY"
    assert first.progress_percent == 100
    assert first.ready_stage_count == first.stage_count == 8
    assert first.stages[0].label == "CAD / STEP [mm]"
    assert first.stages[-1].label == "Evidence export"
    assert len(first.dashboard_sha256) == 64


def test_blocked_dashboard_preserves_exact_stage_failure_without_hiding_it():
    dashboard = build_demo_dashboard(_session(blocked=True))
    assert dashboard.status == "BLOCKED"
    assert dashboard.progress_percent == 88
    blocked = [stage for stage in dashboard.stages if stage.status == "BLOCKED"]
    assert len(blocked) == 1
    assert blocked[0].name == "SECTION_CONTOUR_PROBE"
    assert blocked[0].blocker_count == 1


def test_fails_closed_on_stale_ready_count():
    session = replace(_session(), ready_stage_count=7)
    with pytest.raises(ValueError, match="READY_COUNT_STALE"):
        build_demo_dashboard(session)


def test_fails_closed_on_ready_stage_with_blocker():
    session = _session()
    stages = list(session.stages)
    stages[0] = replace(stages[0], blockers=("SHOULD_NOT_EXIST",))
    with pytest.raises(ValueError, match="READY_WITH_BLOCKERS"):
        build_demo_dashboard(replace(session, stages=tuple(stages)))


def test_fails_closed_on_provenance_or_claim_boundary_change():
    with pytest.raises(ValueError, match="PROVENANCE_SHA"):
        build_demo_dashboard(replace(_session(), workspace_sha256="short"))
    claims = {"converged": True, "industrial_validation": False, "ansys_equivalence": False}
    with pytest.raises(ValueError, match="CLAIM_BOUNDARY"):
        build_demo_dashboard(replace(_session(), claims=claims))
