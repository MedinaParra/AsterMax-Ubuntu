from __future__ import annotations

from astermax.fea.demo_readiness_contract import (
    DemoStageEvidenceV1,
    REQUIRED_DEMO_STAGES,
    build_demo_readiness_manifest,
)


def _chain(*, workspace: str = "workspace-v", unit: str = "mm"):
    items = []
    parent = None
    for index, stage in enumerate(REQUIRED_DEMO_STAGES):
        sha = f"sha-{index:02d}-{stage.lower()}"
        items.append(
            DemoStageEvidenceV1(
                stage=stage,
                status="READY",
                workspace_sha256=workspace,
                evidence_sha256=sha,
                parent_evidence_sha256=parent,
                length_unit=unit,
            )
        )
        parent = sha
    return items


def test_complete_mm_chain_is_demo_ready_and_deterministic() -> None:
    stages = _chain()
    a = build_demo_readiness_manifest(stages, expected_workspace_sha256="workspace-v")
    b = build_demo_readiness_manifest(stages, expected_workspace_sha256="workspace-v")
    assert a.status == "READY"
    assert not a.blockers
    assert a.stage_count == len(REQUIRED_DEMO_STAGES)
    assert a.completed_stage_count == len(REQUIRED_DEMO_STAGES)
    assert a.terminal_evidence_sha256 == stages[-1].evidence_sha256
    assert a.manifest_sha256 == b.manifest_sha256
    assert a.length_unit == "mm"


def test_missing_stage_fails_closed() -> None:
    stages = _chain()
    stages.pop(2)
    result = build_demo_readiness_manifest(stages, expected_workspace_sha256="workspace-v")
    assert result.status == "BLOCKED"
    assert "MISSING_STAGE:MESH" in result.blockers
    assert result.terminal_evidence_sha256 == ""


def test_broken_parent_chain_fails_closed() -> None:
    stages = _chain()
    item = stages[4]
    stages[4] = DemoStageEvidenceV1(
        stage=item.stage,
        status=item.status,
        workspace_sha256=item.workspace_sha256,
        evidence_sha256=item.evidence_sha256,
        parent_evidence_sha256="stale-parent",
        length_unit=item.length_unit,
    )
    result = build_demo_readiness_manifest(stages, expected_workspace_sha256="workspace-v")
    assert result.status == "BLOCKED"
    assert "BROKEN_EVIDENCE_CHAIN:SOLVE" in result.blockers


def test_non_mm_stage_fails_closed() -> None:
    result = build_demo_readiness_manifest(_chain(unit="m"), expected_workspace_sha256="workspace-v")
    assert result.status == "BLOCKED"
    assert any(code.startswith("LENGTH_UNIT_NOT_MM:") for code in result.blockers)


def test_workspace_mismatch_fails_closed() -> None:
    stages = _chain()
    item = stages[5]
    stages[5] = DemoStageEvidenceV1(
        stage=item.stage,
        status=item.status,
        workspace_sha256="other-workspace",
        evidence_sha256=item.evidence_sha256,
        parent_evidence_sha256=item.parent_evidence_sha256,
        length_unit=item.length_unit,
    )
    result = build_demo_readiness_manifest(stages, expected_workspace_sha256="workspace-v")
    assert result.status == "BLOCKED"
    assert "WORKSPACE_MISMATCH:RESULTS" in result.blockers


def test_blocked_stage_cannot_be_advertised_as_ready() -> None:
    stages = _chain()
    item = stages[6]
    stages[6] = DemoStageEvidenceV1(
        stage=item.stage,
        status="BLOCKED",
        workspace_sha256=item.workspace_sha256,
        evidence_sha256=item.evidence_sha256,
        parent_evidence_sha256=item.parent_evidence_sha256,
        length_unit=item.length_unit,
        blockers=("SECTION_TOPOLOGY_NOT_VERIFIED",),
    )
    result = build_demo_readiness_manifest(stages, expected_workspace_sha256="workspace-v")
    assert result.status == "BLOCKED"
    assert "STAGE_NOT_READY:SECTION" in result.blockers
    assert "STAGE_HAS_BLOCKERS:SECTION" in result.blockers


def test_manifest_does_not_claim_simulation_or_ansys_equivalence() -> None:
    result = build_demo_readiness_manifest(_chain(), expected_workspace_sha256="workspace-v")
    text = (result.schema + " " + result.semantics).lower()
    forbidden = ("ansys_equivalence", "synthetic_result", "stress_recovery", "industrial_validation")
    assert not any(token in text for token in forbidden)
