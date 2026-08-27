from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Iterable


_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ConsequenceLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EvidenceStatus(str, Enum):
    VERIFIED = "VERIFIED"
    ASSUMED = "ASSUMED"
    UNKNOWN = "UNKNOWN"
    CONTRADICTED = "CONTRADICTED"
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"
    NOT_ASSESSED = "NOT_ASSESSED"


class EvidenceSource(str, Enum):
    DETERMINISTIC_CHECK = "DETERMINISTIC_CHECK"
    HUMAN_CONFIRMED = "HUMAN_CONFIRMED"
    DOCUMENT = "DOCUMENT"
    MEASUREMENT = "MEASUREMENT"
    ANALYTICAL_WITNESS = "ANALYTICAL_WITNESS"
    CROSS_CODE = "CROSS_CODE"
    AI_PROPOSAL = "AI_PROPOSAL"


class ClaimState(str, Enum):
    PERMITTED = "PERMITTED"
    BLOCKED = "BLOCKED"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_id(name: str, value: str) -> str:
    clean = str(value).strip()
    if not _ID_RE.fullmatch(clean):
        raise ValueError(f"{name} must be a non-empty stable identifier")
    return clean


def _require_text(name: str, value: str) -> str:
    clean = str(value).strip()
    if not clean:
        raise ValueError(f"{name} must be non-empty")
    return clean


def _text_tuple(name: str, values: Iterable[str], *, allow_empty: bool = False) -> tuple[str, ...]:
    result = tuple(_require_text(name, value) for value in values)
    if not result and not allow_empty:
        raise ValueError(f"{name} must contain at least one item")
    if len(set(result)) != len(result):
        raise ValueError(f"{name} must not contain duplicates")
    return result


def _json_snapshot(value: Any) -> Any:
    """Validate and deep-copy JSON evidence so caller-owned objects cannot mutate it."""
    return json.loads(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    )


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True)
class ContextOfUse:
    context_id: str
    engineering_question: str
    intended_decision: str
    quantities_of_interest: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    consequence_level: ConsequenceLevel
    assumptions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "context_id", _require_id("context_id", self.context_id))
        object.__setattr__(
            self,
            "engineering_question",
            _require_text("engineering_question", self.engineering_question),
        )
        object.__setattr__(
            self,
            "intended_decision",
            _require_text("intended_decision", self.intended_decision),
        )
        object.__setattr__(
            self,
            "quantities_of_interest",
            _text_tuple("quantities_of_interest", self.quantities_of_interest),
        )
        object.__setattr__(
            self,
            "acceptance_criteria",
            _text_tuple("acceptance_criteria", self.acceptance_criteria),
        )
        object.__setattr__(
            self,
            "assumptions",
            _text_tuple("assumptions", self.assumptions, allow_empty=True),
        )
        if not isinstance(self.consequence_level, ConsequenceLevel):
            object.__setattr__(self, "consequence_level", ConsequenceLevel(self.consequence_level))

    def canonical(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "engineering_question": self.engineering_question,
            "intended_decision": self.intended_decision,
            "quantities_of_interest": list(self.quantities_of_interest),
            "acceptance_criteria": list(self.acceptance_criteria),
            "consequence_level": self.consequence_level.value,
            "assumptions": list(self.assumptions),
        }


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    kind: str
    status: EvidenceStatus
    source: EvidenceSource
    description: str
    payload_sha256: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _require_id("evidence_id", self.evidence_id))
        object.__setattr__(self, "kind", _require_id("kind", self.kind))
        object.__setattr__(self, "description", _require_text("description", self.description))
        if not isinstance(self.status, EvidenceStatus):
            object.__setattr__(self, "status", EvidenceStatus(self.status))
        if not isinstance(self.source, EvidenceSource):
            object.__setattr__(self, "source", EvidenceSource(self.source))
        if self.source is EvidenceSource.AI_PROPOSAL and self.status is EvidenceStatus.VERIFIED:
            raise ValueError("AI_PROPOSAL cannot create VERIFIED evidence")
        if self.payload_sha256 is not None:
            digest = str(self.payload_sha256).lower().strip()
            if not _SHA256_RE.fullmatch(digest):
                raise ValueError("payload_sha256 must be a lowercase SHA-256 hex digest")
            object.__setattr__(self, "payload_sha256", digest)

        snapshot = _json_snapshot(dict(self.metadata))
        object.__setattr__(self, "metadata", _freeze_json(snapshot))

    @property
    def claim_grade(self) -> bool:
        return self.status is EvidenceStatus.VERIFIED and self.source is not EvidenceSource.AI_PROPOSAL

    def canonical(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "kind": self.kind,
            "status": self.status.value,
            "source": self.source.value,
            "description": self.description,
            "payload_sha256": self.payload_sha256,
            "metadata": _thaw_json(self.metadata),
        }


@dataclass(frozen=True)
class EvidenceEdge:
    child_id: str
    parent_id: str
    relation: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "child_id", _require_id("child_id", self.child_id))
        object.__setattr__(self, "parent_id", _require_id("parent_id", self.parent_id))
        object.__setattr__(self, "relation", _require_id("relation", self.relation))
        if self.child_id == self.parent_id:
            raise ValueError("evidence edge cannot point to itself")


class EvidenceGraph:
    """Deterministic acyclic evidence graph scoped to one ContextOfUse.

    The graph records provenance and dependency. It intentionally does not assign
    a scalar trust score. Evidence status is categorical and claims are evaluated
    separately by ClaimEngine.
    """

    def __init__(self, context: ContextOfUse):
        self.context = context
        self._records: dict[str, EvidenceRecord] = {}
        self._edges: set[EvidenceEdge] = set()

    def add(self, record: EvidenceRecord) -> None:
        if record.evidence_id in self._records:
            raise ValueError(f"duplicate evidence_id: {record.evidence_id}")
        self._records[record.evidence_id] = record

    def _has_path(self, start_id: str, target_id: str) -> bool:
        parents: dict[str, set[str]] = {}
        for edge in self._edges:
            parents.setdefault(edge.child_id, set()).add(edge.parent_id)
        pending = [start_id]
        visited: set[str] = set()
        while pending:
            current = pending.pop()
            if current == target_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            pending.extend(parents.get(current, ()))
        return False

    def link(self, child_id: str, parent_id: str, relation: str = "DERIVED_FROM") -> None:
        edge = EvidenceEdge(child_id, parent_id, relation)
        if edge.child_id not in self._records or edge.parent_id not in self._records:
            raise ValueError("both evidence edge endpoints must already exist")
        if self._has_path(edge.parent_id, edge.child_id):
            raise ValueError("evidence provenance must be acyclic")
        self._edges.add(edge)

    def get(self, evidence_id: str) -> EvidenceRecord:
        try:
            return self._records[evidence_id]
        except KeyError as exc:
            raise KeyError(f"unknown evidence_id: {evidence_id}") from exc

    def by_kind(self, kind: str) -> tuple[EvidenceRecord, ...]:
        key = _require_id("kind", kind)
        return tuple(sorted((r for r in self._records.values() if r.kind == key), key=lambda r: r.evidence_id))

    @property
    def records(self) -> tuple[EvidenceRecord, ...]:
        return tuple(sorted(self._records.values(), key=lambda record: record.evidence_id))

    @property
    def edges(self) -> tuple[EvidenceEdge, ...]:
        return tuple(sorted(self._edges, key=lambda edge: (edge.child_id, edge.parent_id, edge.relation)))

    def canonical(self) -> dict[str, Any]:
        return {
            "schema": "AsterMaxEvidenceGraphV1",
            "context": self.context.canonical(),
            "records": [record.canonical() for record in self.records],
            "edges": [asdict(edge) for edge in self.edges],
        }

    @property
    def fingerprint_sha256(self) -> str:
        return canonical_sha256(self.canonical())


@dataclass(frozen=True)
class ClaimRequirement:
    evidence_kind: str
    min_count: int = 1
    allowed_sources: tuple[EvidenceSource, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_kind", _require_id("evidence_kind", self.evidence_kind))
        if int(self.min_count) < 1:
            raise ValueError("min_count must be at least 1")
        object.__setattr__(self, "min_count", int(self.min_count))
        sources = tuple(
            source if isinstance(source, EvidenceSource) else EvidenceSource(source)
            for source in self.allowed_sources
        )
        if len(set(sources)) != len(sources):
            raise ValueError("allowed_sources must not contain duplicates")
        if EvidenceSource.AI_PROPOSAL in sources:
            raise ValueError("AI_PROPOSAL cannot be an allowed claim-grade source")
        object.__setattr__(self, "allowed_sources", sources)


@dataclass(frozen=True)
class ClaimDefinition:
    claim_id: str
    context_id: str
    statement: str
    requirements: tuple[ClaimRequirement, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim_id", _require_id("claim_id", self.claim_id))
        object.__setattr__(self, "context_id", _require_id("context_id", self.context_id))
        object.__setattr__(self, "statement", _require_text("statement", self.statement))
        requirements = tuple(self.requirements)
        if not requirements:
            raise ValueError("a claim must declare at least one evidence requirement")
        if len({requirement.evidence_kind for requirement in requirements}) != len(requirements):
            raise ValueError("a claim cannot repeat the same evidence requirement")
        object.__setattr__(self, "requirements", requirements)


@dataclass(frozen=True)
class ClaimDecision:
    claim_id: str
    state: ClaimState
    evidence_ids: tuple[str, ...]
    blockers: tuple[str, ...]
    graph_sha256: str
    decision_sha256: str


class ClaimEngine:
    """Fail-closed deterministic claim evaluator."""

    _hard_blocking_statuses = {EvidenceStatus.CONTRADICTED, EvidenceStatus.OUT_OF_DOMAIN}

    @classmethod
    def evaluate(cls, claim: ClaimDefinition, graph: EvidenceGraph) -> ClaimDecision:
        blockers: list[str] = []
        accepted: list[str] = []

        if claim.context_id != graph.context.context_id:
            blockers.append("CONTEXT_MISMATCH")

        for requirement in claim.requirements:
            records = graph.by_kind(requirement.evidence_kind)
            hard_blockers = [record for record in records if record.status in cls._hard_blocking_statuses]
            if hard_blockers:
                statuses = ",".join(
                    f"{record.evidence_id}:{record.status.value}" for record in hard_blockers
                )
                blockers.append(f"{requirement.evidence_kind}:BLOCKING_EVIDENCE:{statuses}")
                continue

            candidates = [record for record in records if record.claim_grade]
            if requirement.allowed_sources:
                candidates = [record for record in candidates if record.source in requirement.allowed_sources]
            if len(candidates) < requirement.min_count:
                observed = ",".join(
                    f"{record.evidence_id}:{record.status.value}/{record.source.value}" for record in records
                ) or "NONE"
                blockers.append(
                    f"{requirement.evidence_kind}:INSUFFICIENT_VERIFIED_EVIDENCE:"
                    f"required={requirement.min_count}:observed={observed}"
                )
                continue
            accepted.extend(record.evidence_id for record in candidates[: requirement.min_count])

        state = ClaimState.PERMITTED if not blockers else ClaimState.BLOCKED
        graph_hash = graph.fingerprint_sha256
        payload = {
            "schema": "AsterMaxClaimDecisionV1",
            "claim_id": claim.claim_id,
            "context_id": claim.context_id,
            "state": state.value,
            "evidence_ids": sorted(set(accepted)),
            "blockers": blockers,
            "graph_sha256": graph_hash,
        }
        decision_hash = canonical_sha256(payload)
        return ClaimDecision(
            claim_id=claim.claim_id,
            state=state,
            evidence_ids=tuple(payload["evidence_ids"]),
            blockers=tuple(blockers),
            graph_sha256=graph_hash,
            decision_sha256=decision_hash,
        )


def build_analysis_passport(
    graph: EvidenceGraph,
    decisions: Iterable[ClaimDecision],
) -> dict[str, Any]:
    """Build a transparent credibility vector; deliberately no aggregate score."""
    vector: dict[str, list[dict[str, str]]] = {}
    for record in graph.records:
        vector.setdefault(record.kind, []).append(
            {
                "evidence_id": record.evidence_id,
                "status": record.status.value,
                "source": record.source.value,
            }
        )
    ordered_decisions = sorted(decisions, key=lambda decision: decision.claim_id)
    payload = {
        "schema": "AsterMaxAnalysisPassportV1",
        "context": graph.context.canonical(),
        "evidence_graph_sha256": graph.fingerprint_sha256,
        "credibility_vector": {key: vector[key] for key in sorted(vector)},
        "claims": [
            {
                "claim_id": decision.claim_id,
                "state": decision.state.value,
                "evidence_ids": list(decision.evidence_ids),
                "blockers": list(decision.blockers),
                "decision_sha256": decision.decision_sha256,
            }
            for decision in ordered_decisions
        ],
    }
    payload["passport_sha256"] = canonical_sha256(payload)
    return payload
