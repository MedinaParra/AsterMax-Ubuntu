from pathlib import Path

from astermax.agents.registry import AgentRegistry
from astermax.audit.store import AuditStore
from astermax.domain.models import EvidenceClass, WorkflowState
from astermax.orchestrator.state_machine import WorkflowStateMachine


def test_audit_store_records_transition(tmp_path):
    store = AuditStore(tmp_path / "audit.db")
    machine = WorkflowStateMachine("project-1", event_sink=store.append_event)
    machine.transition(
        WorkflowState.INTENT_STRUCTURED,
        actor="A1",
        evidence_class=EvidenceClass.AGENT_PROPOSAL,
        reason="intent structured",
    )

    events = store.list_events("project-1")
    assert len(events) == 1
    assert events[0]["to_state"] == "INTENT_STRUCTURED"
    assert events[0]["evidence_class"] == "AGENT_PROPOSAL"


def test_agent_registry_loads_all_required_agents():
    repo_root = Path(__file__).resolve().parents[1]
    registry = AgentRegistry.from_yaml(repo_root / "config" / "agents.v1.yaml")
    assert len(registry.all()) == 13
    assert registry.get("A7").name == "verification"
