from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .engineering_evidence_bus import EngineeringEvidenceBusV1


_STATES = (
    "IMPORTED",
    "GEOMETRY_VERIFIED",
    "PHYSICS_DEFINED",
    "MESHED",
    "MESH_VERIFIED",
    "BC_DEFINED",
    "PRE_SOLVE_VERIFIED",
    "SOLVED",
    "NUMERICALLY_VERIFIED",
    "PHYSICALLY_REVIEWED",
    "ENGINEERING_ACCEPTED",
)

_REQUIRED_EVIDENCE_KIND = {
    "IMPORTED": "CAD_IMPORT",
    "GEOMETRY_VERIFIED": "MODEL_PREPARATION",
    "PHYSICS_DEFINED": "MODEL_PREPARATION",
    "MESHED": "MESH_GENERATED",
    "MESH_VERIFIED": "MESH_VERIFICATION",
    "BC_DEFINED": "BC_LOAD_BINDING",
    "PRE_SOLVE_VERIFIED": "ENGINEERING_GATE",
    "SOLVED": "SOLVE_EXECUTION",
    "NUMERICALLY_VERIFIED": "SOLVE_VERIFICATION",
    "PHYSICALLY_REVIEWED": "ENGINEERING_GATE",
    "ENGINEERING_ACCEPTED": "ENGINEERING_GATE",
}


def _sha(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class EngineeringStateV1:
    schema: str
    state: str
    state_index: int
    evidence_bus_sha256: str
    evidence_head_sha256: str
    accepted_event_sha256: str
    claims: dict[str, bool]
    blockers: tuple[str, ...]
    state_sha256: str


def initial_engineering_state(bus: EngineeringEvidenceBusV1) -> EngineeringStateV1:
    if bus.schema != "AsterMaxEngineeringEvidenceBusV1":
        raise ValueError("ENGINEERING_STATE_EVIDENCE_SCHEMA")
    return _build("IMPORTED", bus, bus.events[0].event_sha256, ())


def _build(state: str, bus: EngineeringEvidenceBusV1, accepted_event_sha256: str, blockers: tuple[str, ...]) -> EngineeringStateV1:
    claims = {
        "converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
        "engineering_accepted": state == "ENGINEERING_ACCEPTED",
    }
    identity = {
        "schema": "AsterMaxEngineeringStateV1",
        "state": state,
        "state_index": _STATES.index(state),
        "evidence_bus_sha256": bus.bus_sha256,
        "evidence_head_sha256": bus.head_sha256,
        "accepted_event_sha256": accepted_event_sha256,
        "claims": claims,
        "blockers": blockers,
    }
    return EngineeringStateV1(
        schema="AsterMaxEngineeringStateV1",
        state=state,
        state_index=_STATES.index(state),
        evidence_bus_sha256=bus.bus_sha256,
        evidence_head_sha256=bus.head_sha256,
        accepted_event_sha256=accepted_event_sha256,
        claims=claims,
        blockers=blockers,
        state_sha256=_sha(identity),
    )


def advance_engineering_state(
    current: EngineeringStateV1,
    target_state: str,
    bus: EngineeringEvidenceBusV1,
    *,
    required_subject: str = "",
) -> EngineeringStateV1:
    if current.schema != "AsterMaxEngineeringStateV1":
        raise ValueError("ENGINEERING_STATE_SCHEMA")
    if target_state not in _STATES:
        raise ValueError("ENGINEERING_STATE_TARGET")
    if current.state not in _STATES:
        raise ValueError("ENGINEERING_STATE_CURRENT")
    target_index = _STATES.index(target_state)
    if target_index != current.state_index + 1:
        raise ValueError("ENGINEERING_STATE_ILLEGAL_TRANSITION")
    if bus.schema != "AsterMaxEngineeringEvidenceBusV1":
        raise ValueError("ENGINEERING_STATE_EVIDENCE_SCHEMA")
    if bus.bus_sha256 == current.evidence_bus_sha256:
        raise ValueError("ENGINEERING_STATE_NO_NEW_EVIDENCE")

    required_kind = _REQUIRED_EVIDENCE_KIND[target_state]
    candidates = [event for event in bus.events if event.kind == required_kind]
    if required_subject:
        candidates = [event for event in candidates if event.subject == required_subject]
    if not candidates:
        raise ValueError("ENGINEERING_STATE_REQUIRED_EVIDENCE_MISSING")
    event = candidates[-1]
    if event.status in {"BLOCKED", "FAIL"}:
        return _build(target_state, bus, event.event_sha256, (f"{required_kind}:{event.status}",))
    if event.status not in {"READY", "PASS", "OBSERVED"}:
        raise ValueError("ENGINEERING_STATE_EVIDENCE_STATUS")

    # Safety boundary: execution alone may never unlock verification/acceptance states.
    if target_state in {"MESH_VERIFIED", "PRE_SOLVE_VERIFIED", "NUMERICALLY_VERIFIED", "PHYSICALLY_REVIEWED", "ENGINEERING_ACCEPTED"}:
        if event.status not in {"READY", "PASS"}:
            raise ValueError("ENGINEERING_STATE_VERIFICATION_REQUIRED")

    return _build(target_state, bus, event.event_sha256, ())


def verify_claim_boundary(state: EngineeringStateV1) -> None:
    if state.claims.get("converged") is not False:
        raise ValueError("ENGINEERING_STATE_CONVERGENCE_OVERCLAIM")
    if state.claims.get("industrial_validation") is not False:
        raise ValueError("ENGINEERING_STATE_INDUSTRIAL_OVERCLAIM")
    if state.claims.get("ansys_equivalence") is not False:
        raise ValueError("ENGINEERING_STATE_ANSYS_OVERCLAIM")
    if state.claims.get("engineering_accepted") != (state.state == "ENGINEERING_ACCEPTED"):
        raise ValueError("ENGINEERING_STATE_ACCEPTANCE_STALE")
