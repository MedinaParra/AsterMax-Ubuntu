from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Iterable


_ALLOWED_KINDS = {
    "CAD_IMPORT",
    "MODEL_PREPARATION",
    "MESH_GENERATED",
    "MESH_VERIFICATION",
    "BC_LOAD_BINDING",
    "SOLVE_EXECUTION",
    "SOLVE_VERIFICATION",
    "POSTPROCESS",
    "SECTION_PROBE",
    "ARTIFACT_EXPORT",
    "ENGINEERING_GATE",
}


def _sha(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value)


@dataclass(frozen=True)
class EngineeringEvidenceEventV1:
    index: int
    kind: str
    source: str
    subject: str
    status: str
    parent_event_sha256: str
    artifact_sha256: str
    payload_sha256: str
    event_sha256: str


@dataclass(frozen=True)
class EngineeringEvidenceBusV1:
    schema: str
    semantics: str
    events: tuple[EngineeringEvidenceEventV1, ...]
    head_sha256: str
    bus_sha256: str


def make_evidence_event(
    *,
    index: int,
    kind: str,
    source: str,
    subject: str,
    status: str,
    parent_event_sha256: str,
    payload: dict[str, Any],
    artifact_sha256: str = "",
) -> EngineeringEvidenceEventV1:
    if index < 1:
        raise ValueError("EVIDENCE_EVENT_INDEX")
    if kind not in _ALLOWED_KINDS:
        raise ValueError("EVIDENCE_EVENT_KIND")
    if not source.strip() or not subject.strip():
        raise ValueError("EVIDENCE_EVENT_IDENTITY")
    if status not in {"OBSERVED", "READY", "BLOCKED", "PASS", "FAIL"}:
        raise ValueError("EVIDENCE_EVENT_STATUS")
    if index == 1:
        if parent_event_sha256:
            raise ValueError("EVIDENCE_EVENT_ROOT_PARENT")
    elif not _valid_sha(parent_event_sha256):
        raise ValueError("EVIDENCE_EVENT_PARENT_SHA")
    if artifact_sha256 and not _valid_sha(artifact_sha256):
        raise ValueError("EVIDENCE_EVENT_ARTIFACT_SHA")

    # Reject NaN/Inf because they destroy deterministic engineering evidence.
    def validate(value: Any) -> None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("EVIDENCE_EVENT_NONFINITE")
        if isinstance(value, dict):
            for child in value.values():
                validate(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                validate(child)

    validate(payload)
    payload_sha = _sha(payload)
    identity = {
        "index": index,
        "kind": kind,
        "source": source,
        "subject": subject,
        "status": status,
        "parent_event_sha256": parent_event_sha256,
        "artifact_sha256": artifact_sha256,
        "payload_sha256": payload_sha,
    }
    return EngineeringEvidenceEventV1(
        index=index,
        kind=kind,
        source=source,
        subject=subject,
        status=status,
        parent_event_sha256=parent_event_sha256,
        artifact_sha256=artifact_sha256,
        payload_sha256=payload_sha,
        event_sha256=_sha(identity),
    )


def build_evidence_bus(events: Iterable[EngineeringEvidenceEventV1]) -> EngineeringEvidenceBusV1:
    ordered = tuple(events)
    if not ordered:
        raise ValueError("EVIDENCE_BUS_EMPTY")
    previous = ""
    seen: set[str] = set()
    for expected_index, event in enumerate(ordered, start=1):
        if event.index != expected_index:
            raise ValueError("EVIDENCE_BUS_INDEX_GAP")
        if event.parent_event_sha256 != previous:
            raise ValueError("EVIDENCE_BUS_CHAIN_BROKEN")
        if not _valid_sha(event.event_sha256) or event.event_sha256 in seen:
            raise ValueError("EVIDENCE_BUS_EVENT_IDENTITY")
        seen.add(event.event_sha256)
        previous = event.event_sha256
    identity = {
        "schema": "AsterMaxEngineeringEvidenceBusV1",
        "event_sha256": [event.event_sha256 for event in ordered],
        "head_sha256": previous,
    }
    return EngineeringEvidenceBusV1(
        schema="AsterMaxEngineeringEvidenceBusV1",
        semantics="append_only_deterministic_engineering_evidence_chain_not_result_validation",
        events=ordered,
        head_sha256=previous,
        bus_sha256=_sha(identity),
    )
