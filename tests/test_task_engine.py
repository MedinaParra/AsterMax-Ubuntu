from pathlib import Path

import pytest

from astermax.agents.registry import AgentRegistry
from astermax.audit.store import AuditStore
from astermax.domain.models import AgentResultV1, AgentResultStatus, EvidenceClass
from astermax.orchestrator.task_engine import AgentTaskEngine, ContractViolation


def build_engine(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    registry = AgentRegistry.from_yaml(repo_root / "config" / "agents.v1.yaml")
    return AgentTaskEngine(registry, AuditStore(tmp_path / "audit.db"))


def test_task_result_and_artifact_are_audited(tmp_path):
    engine = build_engine(tmp_path)
    task = engine.create_task(
        project_id="p1",
        agent_id="A1",
        objective="Structure the engineering intent.",
        expected_output_contract="SimulationIntentV1",
        acceptance_criteria=["Question is explicit."],
        prohibited_actions=["invent_solver_result"],
    )

    artifact = engine.register_artifact(
        project_id="p1",
        task_id=task.task_id,
        evidence_class=EvidenceClass.AGENT_PROPOSAL,
        uri="astermax://p1/intent.json",
        sha256="a" * 64,
    )
    result = engine.success_result(
        task,
        summary="Intent proposal created.",
        artifact_ids=[artifact.artifact_id],
    )
    engine.record_result(result)

    assert engine.audit_store.get_task(task.task_id) == task
    assert engine.audit_store.list_results(task.task_id) == [result]
    assert engine.audit_store.list_artifacts("p1") == [artifact]


def test_result_cannot_spoof_another_agent_or_contract(tmp_path):
    engine = build_engine(tmp_path)
    task = engine.create_task(
        project_id="p1",
        agent_id="A3",
        objective="Propose physical model.",
        expected_output_contract="PhysicsProposalV1",
        acceptance_criteria=["All assumptions are explicit."],
    )

    spoofed = AgentResultV1(
        task_id=task.task_id,
        project_id="p1",
        agent_id="A4",
        status=AgentResultStatus.SUCCESS,
        output_contract="PhysicsProposalV1",
        evidence_class=EvidenceClass.AGENT_PROPOSAL,
        summary="invalid actor",
    )
    with pytest.raises(ContractViolation):
        engine.record_result(spoofed)

    wrong_contract = spoofed.model_copy(
        update={"agent_id": "A3", "output_contract": "SolverResultV1"}
    )
    with pytest.raises(ContractViolation):
        engine.record_result(wrong_contract)
