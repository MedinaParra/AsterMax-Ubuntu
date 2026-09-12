from __future__ import annotations

from collections.abc import Callable

from astermax.domain.models import EvidenceClass, WorkflowEvent, WorkflowState


class InvalidTransition(RuntimeError):
    pass


ALLOWED_TRANSITIONS: dict[WorkflowState, frozenset[WorkflowState]] = {
    WorkflowState.NEW: frozenset({WorkflowState.INTENT_STRUCTURED}),
    WorkflowState.INTENT_STRUCTURED: frozenset({WorkflowState.GEOMETRY_READY}),
    WorkflowState.GEOMETRY_READY: frozenset({WorkflowState.PHYSICS_PROPOSED}),
    WorkflowState.PHYSICS_PROPOSED: frozenset({WorkflowState.MODEL_REVIEW}),
    WorkflowState.MODEL_REVIEW: frozenset(
        {WorkflowState.PHYSICS_PROPOSED, WorkflowState.MESH_READY}
    ),
    WorkflowState.MESH_READY: frozenset(
        {WorkflowState.MODEL_REVIEW, WorkflowState.SOLVER_READY}
    ),
    WorkflowState.SOLVER_READY: frozenset(
        {WorkflowState.MESH_READY, WorkflowState.SOLVING}
    ),
    WorkflowState.SOLVING: frozenset({WorkflowState.VERIFYING}),
    WorkflowState.VERIFYING: frozenset(
        {WorkflowState.ACCEPTED, WorkflowState.REJECTED}
    ),
    WorkflowState.REJECTED: frozenset(
        {WorkflowState.MODEL_REVIEW, WorkflowState.MESH_READY}
    ),
    WorkflowState.ACCEPTED: frozenset({WorkflowState.EXPERIMENTING}),
    WorkflowState.EXPERIMENTING: frozenset({WorkflowState.DATASET_READY}),
    WorkflowState.DATASET_READY: frozenset({WorkflowState.SURROGATE_READY}),
    WorkflowState.SURROGATE_READY: frozenset({WorkflowState.RCA_READY}),
    WorkflowState.RCA_READY: frozenset({WorkflowState.REPORT_READY}),
    WorkflowState.REPORT_READY: frozenset(),
}

HUMAN_REVIEW_BOUNDARIES = {
    (WorkflowState.PHYSICS_PROPOSED, WorkflowState.MODEL_REVIEW),
}


class WorkflowStateMachine:
    """Deterministic workflow controller.

    Agents may request transitions, but this object is the sole authority that
    decides whether a transition is legal. Verification cannot be bypassed.
    """

    def __init__(
        self,
        project_id: str,
        *,
        initial_state: WorkflowState = WorkflowState.NEW,
        event_sink: Callable[[WorkflowEvent], None] | None = None,
    ) -> None:
        self.project_id = project_id
        self.state = initial_state
        self._event_sink = event_sink

    def can_transition(self, to_state: WorkflowState) -> bool:
        return to_state in ALLOWED_TRANSITIONS[self.state]

    def transition(
        self,
        to_state: WorkflowState,
        *,
        actor: str,
        evidence_class: EvidenceClass,
        reason: str,
        human_approved: bool = False,
        metadata: dict | None = None,
    ) -> WorkflowEvent:
        from_state = self.state
        if not self.can_transition(to_state):
            raise InvalidTransition(
                f"Illegal workflow transition: {from_state} -> {to_state}"
            )

        if (
            (from_state, to_state) in HUMAN_REVIEW_BOUNDARIES
            and not human_approved
        ):
            raise InvalidTransition(
                "Physics proposal requires explicit human approval before MODEL_REVIEW."
            )

        event = WorkflowEvent(
            project_id=self.project_id,
            from_state=from_state,
            to_state=to_state,
            actor=actor,
            evidence_class=evidence_class,
            reason=reason,
            metadata=metadata or {},
        )
        self.state = to_state
        if self._event_sink is not None:
            self._event_sink(event)
        return event
