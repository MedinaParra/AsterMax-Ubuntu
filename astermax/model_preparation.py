"""Auditable model-preparation layer for the AsterMax Windows PMV.

The solver must never infer that an assistant proposal is an engineer decision.
This module converts a STEP static case definition into persistent engineering
intent, keeps FIXED/LOAD proposals unapproved by default, and exposes an explicit
human approval gate before a professional demo solve is considered eligible.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any

from .case_context import CaseValidationError, EngineeringCase


class ModelPreparationError(ValueError):
    """Raised when a model-preparation request violates a trust invariant."""


@dataclass(frozen=True)
class StaticPreparationSpec:
    step_path: Path
    axis: str
    fixed_side: str
    load_side: str
    force_n: tuple[float, float, float]
    mesh_size_mm: float
    young_mpa: float
    poisson: float
    minimum_tet_quality: float
    detected_unit: str = "mm"

    def validate(self) -> None:
        if not self.step_path.is_file():
            raise ModelPreparationError(f"STEP file does not exist: {self.step_path}")
        if self.detected_unit != "mm":
            raise ModelPreparationError("model preparation requires STEP resolved to mm")
        if self.axis not in {"x", "y", "z"}:
            raise ModelPreparationError("axis must be x, y, or z")
        if self.fixed_side not in {"min", "max"} or self.load_side not in {"min", "max"}:
            raise ModelPreparationError("semantic sides must be min or max")
        if self.fixed_side == self.load_side:
            raise ModelPreparationError("FIXED and LOAD semantic sides must be distinct")
        if len(self.force_n) != 3 or not all(math.isfinite(float(v)) for v in self.force_n):
            raise ModelPreparationError("force vector must contain three finite components")
        if not math.isfinite(self.mesh_size_mm) or self.mesh_size_mm <= 0.0:
            raise ModelPreparationError("mesh size must be finite and positive")
        if not math.isfinite(self.young_mpa) or self.young_mpa <= 0.0:
            raise ModelPreparationError("Young's modulus must be finite and positive")
        if not math.isfinite(self.poisson) or not (-1.0 < self.poisson < 0.5):
            raise ModelPreparationError("Poisson ratio must satisfy -1 < nu < 0.5")
        if not math.isfinite(self.minimum_tet_quality) or not (0.0 < self.minimum_tet_quality <= 1.0):
            raise ModelPreparationError("minimum TET4 quality must be in (0,1]")


def build_static_preparation_case(spec: StaticPreparationSpec, *, case_id: str | None = None) -> EngineeringCase:
    """Create an unapproved, solver-agnostic engineering case from desktop inputs."""
    spec.validate()
    case = EngineeringCase(case_id=case_id or spec.step_path.stem)
    try:
        case.set_geometry(path=str(spec.step_path.resolve()), detected_unit=spec.detected_unit)
        case.add_assumption("Linear-elastic small-displacement static analysis.")
        case.add_assumption("Length-force-stress basis is mm-N-MPa.")
        case.add_assumption(
            f"Global TET4 target size {spec.mesh_size_mm:g} mm; minimum quality {spec.minimum_tet_quality:g}."
        )
        case.add_assumption(f"Material model: E={spec.young_mpa:g} MPa, nu={spec.poisson:g}.")
        case.propose(
            id="fixed-support-1",
            kind="fixed_support",
            target=f"semantic:{spec.axis}:{spec.fixed_side}",
            definition={"components": ["x", "y", "z"]},
            rationale="Stabilize the linear-static model on the engineer-selected semantic end surface.",
        )
        case.propose(
            id="resultant-force-1",
            kind="force",
            target=f"semantic:{spec.axis}:{spec.load_side}",
            definition={"force_N": [float(v) for v in spec.force_n]},
            rationale="Apply the engineer-entered total resultant on the selected semantic load surface.",
        )
    except CaseValidationError as exc:
        raise ModelPreparationError(str(exc)) from exc
    return case


def approve_static_preparation(case: EngineeringCase, *, approved_by: str) -> EngineeringCase:
    """Explicitly approve the two basic static proposals and verify the solve gate."""
    if not approved_by.strip():
        raise ModelPreparationError("engineer approval requires a non-empty approver")
    try:
        case.approve("fixed-support-1", approved_by=approved_by)
        case.approve("resultant-force-1", approved_by=approved_by)
    except CaseValidationError as exc:
        raise ModelPreparationError(str(exc)) from exc
    gate = case.solve_gate()
    if not gate["ready"]:
        raise ModelPreparationError(f"approved case did not pass solve gate: {gate['issues']}")
    return case


def preparation_summary(case: EngineeringCase) -> dict[str, Any]:
    """Stable UI/report payload describing approval state without solving anything."""
    gate = case.solve_gate()
    approved = [proposal.id for proposal in case.proposals if proposal.approved]
    pending = [proposal.id for proposal in case.proposals if not proposal.approved]
    return {
        "case_id": case.case_id,
        "geometry": dict(case.geometry),
        "assumptions": list(case.assumptions),
        "proposals": [asdict(item) for item in case.proposals],
        "approved_proposal_ids": approved,
        "pending_proposal_ids": pending,
        "solve_gate": gate,
        "engineering_intent_sha256": case.fingerprint(),
    }


def write_preparation_evidence(case: EngineeringCase, output_dir: str | Path) -> dict[str, Any]:
    """Write deterministic pre-solve evidence that can be reviewed independently."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    payload = preparation_summary(case)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    evidence_sha = sha256(canonical.encode("utf-8")).hexdigest()
    payload["preparation_evidence_sha256"] = evidence_sha
    path = root / "model_preparation.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"path": path, "summary": payload}
