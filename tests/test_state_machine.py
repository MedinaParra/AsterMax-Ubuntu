import pytest

from astermax.domain.models import EvidenceClass, WorkflowState
from astermax.orchestrator.state_machine import (
    InvalidTransition,
    WorkflowStateMachine,
)


def test_mock_path_reaches_model_review_only_with_human_gate():
    machine = WorkflowStateMachine("project-1")
    machine.transition(
        WorkflowState.INTENT_STRUCTURED,
        actor="A1",
        evidence_class=EvidenceClass.AGENT_PROPOSAL,
        reason="intent",
    )
    machine.transition(
        WorkflowState.GEOMETRY_READY,
        actor="A2",
        evidence_class=EvidenceClass.AGENT_PROPOSAL,
        reason="geometry",
    )
    machine.transition(
        WorkflowState.PHYSICS_PROPOSED,
        actor="A3",
        evidence_class=EvidenceClass.AGENT_PROPOSAL,
        reason="physics",
    )

    with pytest.raises(InvalidTransition):
        machine.transition(
            WorkflowState.MODEL_REVIEW,
            actor="A0",
            evidence_class=EvidenceClass.AGENT_PROPOSAL,
            reason="attempted bypass",
        )

    machine.transition(
        WorkflowState.MODEL_REVIEW,
        actor="HUMAN",
        evidence_class=EvidenceClass.USER_INPUT,
        reason="reviewed",
        human_approved=True,
    )
    assert machine.state == WorkflowState.MODEL_REVIEW


def test_verification_gate_cannot_be_skipped():
    machine = WorkflowStateMachine(
        "project-2", initial_state=WorkflowState.SOLVING
    )

    with pytest.raises(InvalidTransition):
        machine.transition(
            WorkflowState.ACCEPTED,
            actor="A7",
            evidence_class=EvidenceClass.AGENT_PROPOSAL,
            reason="illegal direct accept",
        )

    machine.transition(
        WorkflowState.VERIFYING,
        actor="A6",
        evidence_class=EvidenceClass.SOLVER_RESULT,
        reason="solver finished",
    )
    machine.transition(
        WorkflowState.ACCEPTED,
        actor="verification_gate",
        evidence_class=EvidenceClass.DETERMINISTIC_CALCULATION,
        reason="all deterministic checks passed",
    )
    assert machine.state == WorkflowState.ACCEPTED
