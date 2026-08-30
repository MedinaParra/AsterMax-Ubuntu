from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .engineering_validator import EngineeringValidationV1, verify_validation_contract


def _sha(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class CorrectiveActionCandidateV1:
    schema: str
    validation_sha256: str
    action_type: str
    rationale: tuple[str, ...]
    requires_human_approval: bool
    auto_execution_allowed: bool
    requires_element_localization: bool
    modifies_physics: bool
    candidate_sha256: str


def propose_corrective_action(report: EngineeringValidationV1) -> CorrectiveActionCandidateV1:
    """Create a recommendation only; never modify mesh, BCs or solver state."""
    verify_validation_contract(report)
    blockers = set(report.blockers)

    if report.status == "PASS":
        action_type = "NONE"
        rationale = ("CURRENT_EXPLICIT_VALIDATION_CRITERIA_PASS",)
        localization = False
    elif "MESH_QUALITY_BELOW_EXPLICIT_CRITERION" in blockers:
        action_type = "LOCAL_MESH_REFINEMENT_REVIEW"
        rationale = (
            "MESH_QUALITY_BELOW_EXPLICIT_CRITERION",
            "LOCATE_WORST_ELEMENTS_BEFORE_ANY_REFINEMENT",
            "RE_SOLVE_AND_COMPARE_EXPLICIT_QOI_BEFORE_CONVERGENCE_CLAIM",
        )
        localization = True
    elif blockers & {
        "FORCE_RESIDUAL_ABOVE_EXPLICIT_CRITERION",
        "MOMENT_RESIDUAL_ABOVE_EXPLICIT_CRITERION",
    }:
        action_type = "EQUILIBRIUM_AND_BC_REVIEW"
        rationale = tuple(sorted(blockers)) + (
            "VERIFY_SUPPORTS_LOAD_TRANSFER_AND_REACTION_BALANCE_BEFORE_RE_SOLVE",
        )
        localization = False
    else:
        action_type = "HUMAN_ENGINEERING_REVIEW"
        rationale = tuple(sorted(blockers)) or ("UNCLASSIFIED_VALIDATION_FAILURE",)
        localization = False

    core = {
        "schema": "AsterMaxCorrectiveActionCandidateV1",
        "validation_sha256": report.validation_sha256,
        "action_type": action_type,
        "rationale": list(rationale),
        "requires_human_approval": action_type != "NONE",
        "auto_execution_allowed": False,
        "requires_element_localization": localization,
        "modifies_physics": False,
    }
    return CorrectiveActionCandidateV1(
        schema=core["schema"],
        validation_sha256=report.validation_sha256,
        action_type=action_type,
        rationale=tuple(rationale),
        requires_human_approval=core["requires_human_approval"],
        auto_execution_allowed=False,
        requires_element_localization=localization,
        modifies_physics=False,
        candidate_sha256=_sha(core),
    )


def verify_corrective_action_boundary(candidate: CorrectiveActionCandidateV1) -> None:
    if candidate.schema != "AsterMaxCorrectiveActionCandidateV1":
        raise ValueError("CORRECTIVE_ACTION_SCHEMA")
    if candidate.auto_execution_allowed:
        raise ValueError("CORRECTIVE_ACTION_AUTO_EXECUTION_FORBIDDEN")
    if candidate.modifies_physics:
        raise ValueError("CORRECTIVE_ACTION_PHYSICS_MUTATION_FORBIDDEN")
    if candidate.action_type != "NONE" and not candidate.requires_human_approval:
        raise ValueError("CORRECTIVE_ACTION_HUMAN_GATE_REQUIRED")
