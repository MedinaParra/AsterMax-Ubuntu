import pytest

from astermax.credibility import (
    ClaimDefinition,
    ClaimEngine,
    ClaimRequirement,
    ClaimState,
    ConsequenceLevel,
    ContextOfUse,
    EvidenceGraph,
    EvidenceRecord,
    EvidenceSource,
    EvidenceStatus,
    build_analysis_passport,
)


def _context() -> ContextOfUse:
    return ContextOfUse(
        context_id="COU_SHAFT_001",
        engineering_question="Can the shaft region support the declared operating load?",
        intended_decision="Accept or redesign the shaft region.",
        quantities_of_interest=("von Mises stress", "displacement"),
        acceptance_criteria=("stress below declared allowable", "solution verification passed"),
        consequence_level=ConsequenceLevel.HIGH,
        assumptions=("linear elastic response",),
    )


def _claim() -> ClaimDefinition:
    return ClaimDefinition(
        claim_id="CLAIM_NUMERICAL_001",
        context_id="COU_SHAFT_001",
        statement="The reported stress is numerically supported for the declared context of use.",
        requirements=(
            ClaimRequirement("CAD_PROVENANCE"),
            ClaimRequirement("LOAD_PROVENANCE"),
            ClaimRequirement("SOLUTION_VERIFICATION", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
        ),
    )


def _verified(evidence_id: str, kind: str, source: EvidenceSource = EvidenceSource.DETERMINISTIC_CHECK):
    return EvidenceRecord(
        evidence_id=evidence_id,
        kind=kind,
        status=EvidenceStatus.VERIFIED,
        source=source,
        description=f"Verified {kind}",
    )


def test_context_of_use_fails_closed_when_decision_basis_is_missing():
    with pytest.raises(ValueError, match="acceptance_criteria"):
        ContextOfUse(
            context_id="COU_BAD",
            engineering_question="Is it acceptable?",
            intended_decision="Accept or reject.",
            quantities_of_interest=("stress",),
            acceptance_criteria=(),
            consequence_level=ConsequenceLevel.HIGH,
        )


def test_evidence_graph_fingerprint_is_stable_across_insertion_order():
    a = _verified("EV_A", "CAD_PROVENANCE", EvidenceSource.DOCUMENT)
    b = _verified("EV_B", "LOAD_PROVENANCE", EvidenceSource.HUMAN_CONFIRMED)

    g1 = EvidenceGraph(_context())
    g1.add(a)
    g1.add(b)
    g1.link("EV_B", "EV_A", "USES_GEOMETRY")

    g2 = EvidenceGraph(_context())
    g2.add(b)
    g2.add(a)
    g2.link("EV_B", "EV_A", "USES_GEOMETRY")

    assert g1.fingerprint_sha256 == g2.fingerprint_sha256


def test_evidence_metadata_is_a_deep_immutable_snapshot():
    caller_owned = {
        "source": {"revision": 1, "document": "LOAD_CASE_A"},
        "tags": ["controlled", "reviewed"],
    }
    record = EvidenceRecord(
        evidence_id="EV_SNAPSHOT",
        kind="LOAD_PROVENANCE",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DOCUMENT,
        description="Controlled load definition.",
        metadata=caller_owned,
    )
    graph = EvidenceGraph(_context())
    graph.add(record)
    fingerprint_before = graph.fingerprint_sha256

    caller_owned["source"]["revision"] = 99
    caller_owned["tags"].append("mutated-after-construction")

    assert record.canonical()["metadata"] == {
        "source": {"document": "LOAD_CASE_A", "revision": 1},
        "tags": ["controlled", "reviewed"],
    }
    assert graph.fingerprint_sha256 == fingerprint_before
    with pytest.raises(TypeError):
        record.metadata["new"] = "not allowed"
    with pytest.raises(TypeError):
        record.metadata["source"]["revision"] = 2


def test_evidence_graph_rejects_provenance_cycles():
    graph = EvidenceGraph(_context())
    graph.add(_verified("EV_A", "CAD_PROVENANCE", EvidenceSource.DOCUMENT))
    graph.add(_verified("EV_B", "LOAD_PROVENANCE", EvidenceSource.DOCUMENT))
    graph.add(_verified("EV_C", "SOLUTION_VERIFICATION"))

    graph.link("EV_A", "EV_B")
    graph.link("EV_B", "EV_C")
    with pytest.raises(ValueError, match="acyclic"):
        graph.link("EV_C", "EV_A")

    assert len(graph.edges) == 2


def test_ai_proposal_cannot_promote_itself_to_verified_evidence():
    with pytest.raises(ValueError, match="AI_PROPOSAL cannot create VERIFIED evidence"):
        EvidenceRecord(
            evidence_id="EV_AI",
            kind="LOAD_PROVENANCE",
            status=EvidenceStatus.VERIFIED,
            source=EvidenceSource.AI_PROPOSAL,
            description="AI guessed the load source.",
        )


def test_claim_is_blocked_until_all_required_evidence_is_verified():
    graph = EvidenceGraph(_context())
    graph.add(_verified("EV_CAD", "CAD_PROVENANCE", EvidenceSource.DOCUMENT))
    graph.add(
        EvidenceRecord(
            evidence_id="EV_LOAD",
            kind="LOAD_PROVENANCE",
            status=EvidenceStatus.ASSUMED,
            source=EvidenceSource.HUMAN_CONFIRMED,
            description="Load entered as an assumption.",
        )
    )
    graph.add(_verified("EV_SOLVER", "SOLUTION_VERIFICATION"))

    decision = ClaimEngine.evaluate(_claim(), graph)
    assert decision.state is ClaimState.BLOCKED
    assert any("LOAD_PROVENANCE:INSUFFICIENT_VERIFIED_EVIDENCE" in blocker for blocker in decision.blockers)

    graph2 = EvidenceGraph(_context())
    graph2.add(_verified("EV_CAD", "CAD_PROVENANCE", EvidenceSource.DOCUMENT))
    graph2.add(_verified("EV_LOAD", "LOAD_PROVENANCE", EvidenceSource.HUMAN_CONFIRMED))
    graph2.add(_verified("EV_SOLVER", "SOLUTION_VERIFICATION"))

    decision2 = ClaimEngine.evaluate(_claim(), graph2)
    assert decision2.state is ClaimState.PERMITTED
    assert set(decision2.evidence_ids) == {"EV_CAD", "EV_LOAD", "EV_SOLVER"}


def test_contradictory_or_out_of_domain_evidence_blocks_even_with_a_verified_record():
    graph = EvidenceGraph(_context())
    graph.add(_verified("EV_CAD", "CAD_PROVENANCE", EvidenceSource.DOCUMENT))
    graph.add(_verified("EV_LOAD_OK", "LOAD_PROVENANCE", EvidenceSource.HUMAN_CONFIRMED))
    graph.add(
        EvidenceRecord(
            evidence_id="EV_LOAD_CONFLICT",
            kind="LOAD_PROVENANCE",
            status=EvidenceStatus.CONTRADICTED,
            source=EvidenceSource.DOCUMENT,
            description="A second controlled document gives a different load.",
        )
    )
    graph.add(_verified("EV_SOLVER", "SOLUTION_VERIFICATION"))

    decision = ClaimEngine.evaluate(_claim(), graph)
    assert decision.state is ClaimState.BLOCKED
    assert any("LOAD_PROVENANCE:BLOCKING_EVIDENCE" in blocker for blocker in decision.blockers)


def test_context_mismatch_blocks_claim():
    graph = EvidenceGraph(_context())
    graph.add(_verified("EV_CAD", "CAD_PROVENANCE", EvidenceSource.DOCUMENT))
    graph.add(_verified("EV_LOAD", "LOAD_PROVENANCE", EvidenceSource.HUMAN_CONFIRMED))
    graph.add(_verified("EV_SOLVER", "SOLUTION_VERIFICATION"))
    wrong = ClaimDefinition(
        claim_id="CLAIM_OTHER",
        context_id="COU_OTHER",
        statement="This belongs to another engineering decision.",
        requirements=(ClaimRequirement("CAD_PROVENANCE"),),
    )
    decision = ClaimEngine.evaluate(wrong, graph)
    assert decision.state is ClaimState.BLOCKED
    assert "CONTEXT_MISMATCH" in decision.blockers


def test_analysis_passport_is_vector_based_and_contains_no_trust_score():
    graph = EvidenceGraph(_context())
    graph.add(_verified("EV_CAD", "CAD_PROVENANCE", EvidenceSource.DOCUMENT))
    graph.add(_verified("EV_LOAD", "LOAD_PROVENANCE", EvidenceSource.HUMAN_CONFIRMED))
    graph.add(_verified("EV_SOLVER", "SOLUTION_VERIFICATION"))
    decision = ClaimEngine.evaluate(_claim(), graph)

    passport = build_analysis_passport(graph, [decision])
    assert passport["schema"] == "AsterMaxAnalysisPassportV1"
    assert passport["claims"][0]["state"] == "PERMITTED"
    assert passport["credibility_vector"]["SOLUTION_VERIFICATION"][0]["status"] == "VERIFIED"
    assert "trust_score" not in passport
    assert "confidence_score" not in passport
    assert len(passport["passport_sha256"]) == 64
