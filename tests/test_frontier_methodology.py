from astermax.harness.evidence import (
    EvidenceEdgeV1,
    EvidenceGraph,
    EvidenceNodeKind,
    EvidenceNodeV1,
)
from astermax.harness.meta import (
    HarnessMetricsV1,
    MetaDecision,
    compare_harness_candidate,
)
from astermax.harness.system_manifest import EvaluationRunManifestV1, SystemUnderTestV1


SUITE_HASH = "a" * 64


def test_evidence_claim_without_machine_support_is_orphan():
    graph = EvidenceGraph()
    graph.add_node(EvidenceNodeV1(node_id="claim:1", kind=EvidenceNodeKind.CLAIM, label="solver path is valid"))
    graph.add_node(EvidenceNodeV1(node_id="agent:1", kind=EvidenceNodeKind.AGENT_OUTPUT, label="agent review"))
    graph.add_edge(EvidenceEdgeV1(source="claim:1", target="agent:1", relation="supported_by"))
    assert graph.orphan_claims() == ["claim:1"]
    assert graph.release_ready() is False


def test_evidence_claim_with_benchmark_path_is_release_eligible():
    graph = EvidenceGraph()
    graph.add_node(EvidenceNodeV1(node_id="claim:1", kind=EvidenceNodeKind.CLAIM, label="solver path is valid"))
    graph.add_node(EvidenceNodeV1(node_id="test:1", kind=EvidenceNodeKind.TEST, label="unit tests"))
    graph.add_node(EvidenceNodeV1(node_id="benchmark:1", kind=EvidenceNodeKind.BENCHMARK, label="reference benchmark"))
    graph.add_edge(EvidenceEdgeV1(source="claim:1", target="test:1", relation="supported_by"))
    graph.add_edge(EvidenceEdgeV1(source="test:1", target="benchmark:1", relation="corroborated_by"))
    assert graph.orphan_claims() == []
    assert graph.release_ready() is True


def test_system_manifest_records_full_evaluated_system():
    system = SystemUnderTestV1(
        model_provider="OpenAI",
        model_id="test-model",
        reasoning_setting="test",
        tool_access=["github", "shell"],
        harness_commit="abcdef1234567",
        safeguards=["bounded_scope", "human_merge_gate"],
        evaluation_budget={"max_tool_calls": 20, "max_retries": 2},
    )
    manifest = EvaluationRunManifestV1(
        run_id="eval-001",
        workpackage_id="W2-SOLVER-BRIDGE-001",
        suite_id="ASTERMAX-FRONTIER-001",
        suite_sha256=SUITE_HASH,
        system=system,
    )
    assert manifest.system.tool_access == ["github", "shell"]
    assert manifest.system.evaluation_budget.max_tool_calls == 20
    assert manifest.suite_sha256 == SUITE_HASH


def test_meta_candidate_rolls_back_on_mandatory_regression():
    baseline = HarnessMetricsV1(
        suite_sha256=SUITE_HASH,
        mandatory_pass_rate=1.0,
        aggregate_score=0.80,
        wall_clock_seconds=100,
    )
    candidate = HarnessMetricsV1(
        suite_sha256=SUITE_HASH,
        mandatory_pass_rate=0.9,
        aggregate_score=0.95,
        failed_mandatory_cases=["provenance_guard"],
        wall_clock_seconds=90,
    )
    result = compare_harness_candidate(baseline, candidate)
    assert result.decision == MetaDecision.ROLLBACK
    assert any("mandatory" in reason.lower() for reason in result.reasons)


def test_meta_candidate_rolls_back_if_budget_growth_masks_improvement():
    baseline = HarnessMetricsV1(
        suite_sha256=SUITE_HASH,
        mandatory_pass_rate=1.0,
        aggregate_score=0.80,
        wall_clock_seconds=100,
    )
    candidate = HarnessMetricsV1(
        suite_sha256=SUITE_HASH,
        mandatory_pass_rate=1.0,
        aggregate_score=0.90,
        wall_clock_seconds=140,
    )
    result = compare_harness_candidate(baseline, candidate, max_budget_ratio=1.25)
    assert result.decision == MetaDecision.ROLLBACK
    assert any("budget ratio" in reason.lower() for reason in result.reasons)


def test_meta_candidate_is_retained_only_on_same_suite_without_regression():
    baseline = HarnessMetricsV1(
        suite_sha256=SUITE_HASH,
        mandatory_pass_rate=1.0,
        aggregate_score=0.80,
        wall_clock_seconds=100,
    )
    candidate = HarnessMetricsV1(
        suite_sha256=SUITE_HASH,
        mandatory_pass_rate=1.0,
        aggregate_score=0.84,
        wall_clock_seconds=105,
    )
    result = compare_harness_candidate(baseline, candidate)
    assert result.decision == MetaDecision.RETAIN
    assert result.reasons == []
