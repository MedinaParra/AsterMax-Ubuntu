from __future__ import annotations

from collections import deque
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvidenceNodeKind(StrEnum):
    REQUIREMENT = "REQUIREMENT"
    WORKPACKAGE = "WORKPACKAGE"
    AGENT_OUTPUT = "AGENT_OUTPUT"
    CHANGE = "CHANGE"
    TEST = "TEST"
    BENCHMARK = "BENCHMARK"
    ARTIFACT = "ARTIFACT"
    CLAIM = "CLAIM"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    RELEASE_DECISION = "RELEASE_DECISION"


MACHINE_EVIDENCE_KINDS = {
    EvidenceNodeKind.TEST,
    EvidenceNodeKind.BENCHMARK,
    EvidenceNodeKind.ARTIFACT,
}


class EvidenceNodeV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1)
    kind: EvidenceNodeKind
    label: str = Field(min_length=1)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceEdgeV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    relation: str = Field(min_length=1)


class EvidenceGraph:
    """Small deterministic evidence graph used by release gates.

    Edges point from a higher-level claim/decision toward the evidence that supports it.
    """

    def __init__(self) -> None:
        self.nodes: dict[str, EvidenceNodeV1] = {}
        self.edges: list[EvidenceEdgeV1] = []

    def add_node(self, node: EvidenceNodeV1) -> None:
        if node.node_id in self.nodes:
            raise ValueError(f"Duplicate evidence node: {node.node_id}")
        self.nodes[node.node_id] = node

    def add_edge(self, edge: EvidenceEdgeV1) -> None:
        if edge.source not in self.nodes or edge.target not in self.nodes:
            raise ValueError("Evidence edges must reference existing nodes")
        self.edges.append(edge)

    def _targets(self, source: str) -> list[str]:
        return [edge.target for edge in self.edges if edge.source == source]

    def has_machine_evidence_path(self, node_id: str) -> bool:
        if node_id not in self.nodes:
            raise KeyError(node_id)
        queue: deque[str] = deque([node_id])
        visited: set[str] = set()
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            node = self.nodes[current]
            if current != node_id and node.kind in MACHINE_EVIDENCE_KINDS:
                return True
            queue.extend(self._targets(current))
        return False

    def orphan_claims(self) -> list[str]:
        return sorted(
            node.node_id
            for node in self.nodes.values()
            if node.kind == EvidenceNodeKind.CLAIM
            and not self.has_machine_evidence_path(node.node_id)
        )

    def release_ready(self) -> bool:
        return not self.orphan_claims()
