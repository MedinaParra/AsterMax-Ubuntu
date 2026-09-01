"""Persistent engineering intent for AsterMax cases.

This module is deliberately solver-agnostic. It records geometry units, assumptions,
assistant proposals and engineer approvals, then exposes a hard solve gate. The goal
is to keep the engineering case stable even if the UI evolves between releases.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any


class CaseValidationError(ValueError):
    """Raised when a case violates an AsterMax engineering invariant."""


SUPPORTED_PROPOSALS = {
    "fixed_support",
    "displacement",
    "force",
    "pressure",
    "traction",
    "gravity",
}


@dataclass(frozen=True)
class Proposal:
    id: str
    kind: str
    target: str
    definition: dict[str, Any]
    rationale: str
    source: str = "assistant"
    approved: bool = False


@dataclass
class EngineeringCase:
    case_id: str
    units: str = "mm-N-s"
    geometry: dict[str, Any] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    proposals: list[Proposal] = field(default_factory=list)
    decisions: list[dict[str, str]] = field(default_factory=list)

    def set_geometry(self, *, path: str, detected_unit: str, scale_to_mm: float = 1.0) -> None:
        """Register CAD geometry only after its unit basis is resolved to millimetres."""
        if detected_unit != "mm":
            raise CaseValidationError("STEP/CAD unit must be resolved to mm before analysis.")
        if abs(scale_to_mm - 1.0) > 1e-12:
            raise CaseValidationError("Geometry declared mm but non-unity scale requested.")
        self.geometry = {"path": path, "unit": "mm", "scale_to_mm": 1.0}

    def add_assumption(self, text: str) -> None:
        if not text.strip():
            raise CaseValidationError("Assumptions cannot be empty.")
        self.assumptions.append(text.strip())

    def propose(
        self,
        *,
        id: str,
        kind: str,
        target: str,
        definition: dict[str, Any],
        rationale: str,
    ) -> None:
        """Record an assistant suggestion without silently applying it to the model."""
        if kind not in SUPPORTED_PROPOSALS:
            raise CaseValidationError(f"Unsupported proposal kind: {kind}")
        if any(proposal.id == id for proposal in self.proposals):
            raise CaseValidationError(f"Duplicate proposal id: {id}")
        if not target.strip():
            raise CaseValidationError("A proposal requires an explicit geometric target.")
        if not rationale.strip():
            raise CaseValidationError("A proposal requires engineering rationale.")
        self.proposals.append(
            Proposal(
                id=id,
                kind=kind,
                target=target,
                definition=deepcopy(definition),
                rationale=rationale.strip(),
            )
        )

    def approve(self, proposal_id: str, *, approved_by: str) -> None:
        """Promote one proposed BC/load into the approved engineering intent."""
        if not approved_by.strip():
            raise CaseValidationError("Approval requires an identifiable approver.")
        proposal = next((item for item in self.proposals if item.id == proposal_id), None)
        if proposal is None:
            raise CaseValidationError(f"Unknown proposal: {proposal_id}")
        self.proposals = [
            Proposal(**{**asdict(item), "approved": True}) if item.id == proposal_id else item
            for item in self.proposals
        ]
        self.decisions.append(
            {"proposal_id": proposal_id, "action": "approved", "by": approved_by.strip()}
        )

    def solve_gate(self) -> dict[str, Any]:
        """Return whether a basic static solve is eligible to proceed.

        This is intentionally conservative: geometry, at least one approved kinematic
        constraint, and at least one approved load are mandatory. It is not a claim
        that the finite-element model is physically correct.
        """
        issues: list[str] = []
        if not self.geometry:
            issues.append("geometry_missing")
        approved = [proposal for proposal in self.proposals if proposal.approved]
        if not any(p.kind in {"fixed_support", "displacement"} for p in approved):
            issues.append("constraint_missing")
        if not any(p.kind in {"force", "pressure", "traction", "gravity"} for p in approved):
            issues.append("load_missing")
        return {"ready": not issues, "issues": issues}

    def canonical_json(self) -> str:
        """Stable serialization used by the session and certification layers."""
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    def fingerprint(self) -> str:
        """SHA-256 identity of the current engineering intent."""
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()
