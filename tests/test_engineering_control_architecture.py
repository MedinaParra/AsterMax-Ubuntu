from __future__ import annotations

from dataclasses import replace

import pytest

from astermax.fea.engineering_evidence_bus import build_evidence_bus, make_evidence_event
from astermax.fea.engineering_state_machine import (
    advance_engineering_state,
    initial_engineering_state,
    verify_claim_boundary,
)


def append_event(events, *, kind, subject, status="PASS", payload=None):
    parent = events[-1].event_sha256 if events else ""
    event = make_evidence_event(
        index=len(events) + 1,
        kind=kind,
        source="c5.4x-harness",
        subject=subject,
        status=status,
        parent_event_sha256=parent,
        payload=payload or {"verified": status in {"PASS", "READY"}},
    )
    return [*events, event]


def test_evidence_bus_is_deterministic_and_chain_closed():
    events = append_event([], kind="CAD_IMPORT", subject="model.step", status="OBSERVED", payload={"units": "mm"})
    events = append_event(events, kind="MODEL_PREPARATION", subject="geometry", status="PASS")
    first = build_evidence_bus(events)
    second = build_evidence_bus(events)
    assert first.bus_sha256 == second.bus_sha256
    assert first.head_sha256 == events[-1].event_sha256
    assert first.schema == "AsterMaxEngineeringEvidenceBusV1"


def test_evidence_bus_rejects_broken_parent_chain():
    events = append_event([], kind="CAD_IMPORT", subject="model.step", status="OBSERVED")
    second = make_evidence_event(
        index=2,
        kind="MODEL_PREPARATION",
        source="harness",
        subject="geometry",
        status="PASS",
        parent_event_sha256="0" * 64,
        payload={"ok": True},
    )
    with pytest.raises(ValueError, match="EVIDENCE_BUS_CHAIN_BROKEN"):
        build_evidence_bus([events[0], second])


def test_state_machine_forbids_skipping_engineering_gates():
    events = append_event([], kind="CAD_IMPORT", subject="model.step", status="OBSERVED")
    bus = build_evidence_bus(events)
    state = initial_engineering_state(bus)
    events = append_event(events, kind="MESH_GENERATED", subject="mesh", status="OBSERVED")
    with pytest.raises(ValueError, match="ENGINEERING_STATE_ILLEGAL_TRANSITION"):
        advance_engineering_state(state, "MESHED", build_evidence_bus(events))


def test_verification_state_requires_pass_or_ready_not_execution_only():
    events = append_event([], kind="CAD_IMPORT", subject="model.step", status="OBSERVED")
    state = initial_engineering_state(build_evidence_bus(events))

    events = append_event(events, kind="MODEL_PREPARATION", subject="geometry", status="PASS")
    state = advance_engineering_state(state, "GEOMETRY_VERIFIED", build_evidence_bus(events))
    events = append_event(events, kind="MODEL_PREPARATION", subject="physics", status="READY")
    state = advance_engineering_state(state, "PHYSICS_DEFINED", build_evidence_bus(events))
    events = append_event(events, kind="MESH_GENERATED", subject="mesh", status="OBSERVED")
    state = advance_engineering_state(state, "MESHED", build_evidence_bus(events))
    events = append_event(events, kind="MESH_VERIFICATION", subject="mesh", status="OBSERVED")
    with pytest.raises(ValueError, match="ENGINEERING_STATE_VERIFICATION_REQUIRED"):
        advance_engineering_state(state, "MESH_VERIFIED", build_evidence_bus(events))


def test_failed_verification_is_visible_blocker_not_fake_success():
    events = append_event([], kind="CAD_IMPORT", subject="model.step", status="OBSERVED")
    state = initial_engineering_state(build_evidence_bus(events))
    events = append_event(events, kind="MODEL_PREPARATION", subject="geometry", status="PASS")
    state = advance_engineering_state(state, "GEOMETRY_VERIFIED", build_evidence_bus(events))
    events = append_event(events, kind="MODEL_PREPARATION", subject="physics", status="READY")
    state = advance_engineering_state(state, "PHYSICS_DEFINED", build_evidence_bus(events))
    events = append_event(events, kind="MESH_GENERATED", subject="mesh", status="OBSERVED")
    state = advance_engineering_state(state, "MESHED", build_evidence_bus(events))
    events = append_event(events, kind="MESH_VERIFICATION", subject="mesh", status="FAIL", payload={"quality_gate": "FAIL"})
    state = advance_engineering_state(state, "MESH_VERIFIED", build_evidence_bus(events))
    assert state.blockers == ("MESH_VERIFICATION:FAIL",)
    assert state.claims["engineering_accepted"] is False
    verify_claim_boundary(state)


def test_claim_boundary_rejects_ansys_equivalence_overclaim():
    events = append_event([], kind="CAD_IMPORT", subject="model.step", status="OBSERVED")
    state = initial_engineering_state(build_evidence_bus(events))
    invalid = replace(state, claims={**state.claims, "ansys_equivalence": True})
    with pytest.raises(ValueError, match="ENGINEERING_STATE_ANSYS_OVERCLAIM"):
        verify_claim_boundary(invalid)


def test_nonfinite_evidence_is_rejected():
    with pytest.raises(ValueError, match="EVIDENCE_EVENT_NONFINITE"):
        make_evidence_event(
            index=1,
            kind="SOLVE_VERIFICATION",
            source="harness",
            subject="equilibrium",
            status="PASS",
            parent_event_sha256="",
            payload={"force_residual_n": float("nan")},
        )
