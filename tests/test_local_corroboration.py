import hashlib

import pytest

from astermax.credibility import (
    ClaimEngine,
    ClaimState,
    ConsequenceLevel,
    ContextOfUse,
    EvidenceGraph,
)
from astermax.fea.bounded_stress_concentration import (
    build_stress_concentration_grid,
    stress_concentration_dataset_evidence,
)
from astermax.fea.local_corroboration import (
    LocalCorroborationError,
    empirical_local_chain_evidence,
    empirical_local_neighborhood_claim,
    local_neighborhood_binding_evidence,
    local_peak_convergence_evidence,
    local_peak_reliability_claim,
    synthetic_dataset_authorization_evidence,
)
from astermax.fea.neighborhood_verification import NeighborhoodSample, compare_local_neighborhood
from astermax.fea.notch_witness import build_notch_stress_witness, notch_witness_evidence
from astermax.fea.shaft_shoulder import build_shaft_shoulder_geometry, shaft_shoulder_geometry_evidence
from astermax.fea.singularity_diagnostic import RefinementFieldSample, diagnose_local_singularity
from astermax.fea.stress_concentration_source import (
    build_stress_concentration_source,
    source_provenance_evidence,
)


def _context():
    return ContextOfUse(
        context_id="LOCAL_NOTCH_VERIFICATION",
        engineering_question="Does the local verification neighborhood agree with its independent witness?",
        intended_decision="Permit or block a local software-verification claim",
        quantities_of_interest=("local von Mises stress",),
        acceptance_criteria=("declared neighborhood error tolerance passes",),
        consequence_level=ConsequenceLevel.LOW,
        assumptions=("synthetic verification dataset",),
    )


def _empirical_bundle():
    source = build_stress_concentration_source(
        source_id="SYNTHETIC",
        title="Synthetic local verification source",
        edition_or_release="1",
        publisher="AsterMax verification",
        locator="synthetic",
        source_url="https://example.invalid/local",
        rights_note="SYNTHETIC_SOFTWARE_VERIFICATION_DATA",
    )
    geometry = build_shaft_shoulder_geometry(
        geometry_id="S1",
        small_diameter_mm=100.0,
        large_diameter_mm=120.0,
        fillet_radius_mm=6.0,
    )
    common = dict(
        source_provenance_sha256=source.provenance_sha256,
        diameter_ratios=(1.1, 1.3),
        radius_ratios=(0.02, 0.10),
    )
    kt = build_stress_concentration_grid(
        dataset_id="KT",
        factor_name="Kt",
        load_mode="BENDING",
        factors=((2.0, 1.5), (2.4, 1.7)),
        **common,
    )
    kts = build_stress_concentration_grid(
        dataset_id="KTS",
        factor_name="Kts",
        load_mode="TORSION",
        factors=((1.8, 1.3), (2.0, 1.5)),
        **common,
    )
    witness = build_notch_stress_witness(
        geometry,
        bending_grid=kt,
        torsion_grid=kts,
        nominal_normal_stress_mpa=100.0,
        nominal_shear_stress_mpa=40.0,
    )
    neighborhood = compare_local_neighborhood(
        comparison_id="N1",
        samples=(
            NeighborhoodSample(1.0, 201.0, 200.0),
            NeighborhoodSample(2.0, 181.0, 180.0),
            NeighborhoodSample(3.0, 159.0, 160.0),
        ),
        max_allowed_relative_error=0.02,
    )

    source_ev = source_provenance_evidence(source)
    geometry_ev = shaft_shoulder_geometry_evidence(geometry)
    kt_ev = stress_concentration_dataset_evidence(kt)
    kts_ev = stress_concentration_dataset_evidence(kts)
    kt_auth = synthetic_dataset_authorization_evidence(source_ev, kt_ev)
    kts_auth = synthetic_dataset_authorization_evidence(source_ev, kts_ev)
    witness_ev = notch_witness_evidence(witness)
    binding = local_neighborhood_binding_evidence(
        binding_id="B1",
        comparison=neighborhood,
        witness_evidence=witness_ev,
        fea_result_sha256=hashlib.sha256(b"synthetic-fea-result").hexdigest(),
    )
    chain = empirical_local_chain_evidence(
        chain_id="CHAIN1",
        source_evidence=source_ev,
        geometry_evidence=geometry_ev,
        dataset_evidences=(kt_ev, kts_ev),
        authorization_evidences=(kt_auth, kts_auth),
        witness_evidence=witness_ev,
        binding_evidence=binding,
    )
    return {
        "source": source,
        "geometry": geometry,
        "kt": kt,
        "kts": kts,
        "records": (
            source_ev,
            geometry_ev,
            kt_ev,
            kts_ev,
            kt_auth,
            kts_auth,
            witness_ev,
            binding,
            chain,
        ),
    }


def test_empirical_neighborhood_claim_is_permitted_with_complete_bound_chain():
    graph = EvidenceGraph(_context())
    for evidence in _empirical_bundle()["records"]:
        graph.add(evidence)
    decision = ClaimEngine.evaluate(empirical_local_neighborhood_claim(graph.context.context_id), graph)
    assert decision.state is ClaimState.PERMITTED


def test_empirical_claim_without_authorizations_and_chain_is_blocked():
    graph = EvidenceGraph(_context())
    records = _empirical_bundle()["records"]
    for evidence in records[:4] + records[6:8]:
        graph.add(evidence)
    decision = ClaimEngine.evaluate(empirical_local_neighborhood_claim(graph.context.context_id), graph)
    assert decision.state is ClaimState.BLOCKED
    assert any("STRESS_CONCENTRATION_DATASET_AUTHORIZATION" in blocker for blocker in decision.blockers)
    assert any("LOCAL_EMPIRICAL_CHAIN" in blocker for blocker in decision.blockers)


def test_published_metadata_only_cannot_receive_synthetic_dataset_authorization():
    published = build_stress_concentration_source(
        source_id="PUBLISHED_METADATA_ONLY",
        title="Published source metadata",
        edition_or_release="1",
        publisher="Publisher",
        locator="exact locator required later",
        source_url="https://example.invalid/published",
        rights_note="METADATA_ONLY_NO_CALCULATION_AUTHORIZATION",
    )
    published_ev = source_provenance_evidence(published)
    synthetic_dataset = _empirical_bundle()["records"][2]
    with pytest.raises(LocalCorroborationError, match="EXPLICIT_AUTHORIZATION"):
        synthetic_dataset_authorization_evidence(published_ev, synthetic_dataset)


def test_cross_mixing_dataset_from_another_source_is_rejected():
    bundle = _empirical_bundle()
    foreign_source = build_stress_concentration_source(
        source_id="FOREIGN",
        title="Foreign synthetic verification source",
        edition_or_release="1",
        publisher="AsterMax verification",
        locator="foreign",
        source_url="https://example.invalid/foreign",
        rights_note="SYNTHETIC_SOFTWARE_VERIFICATION_DATA",
    )
    foreign_grid = build_stress_concentration_grid(
        dataset_id="FOREIGN_KT",
        factor_name="Kt",
        load_mode="BENDING",
        source_provenance_sha256=foreign_source.provenance_sha256,
        diameter_ratios=(1.1, 1.3),
        radius_ratios=(0.02, 0.10),
        factors=((2.0, 1.5), (2.4, 1.7)),
    )
    foreign_ev = stress_concentration_dataset_evidence(foreign_grid)
    records = bundle["records"]
    with pytest.raises(LocalCorroborationError, match="DATASET_SOURCE_MISMATCH"):
        empirical_local_chain_evidence(
            chain_id="MIXED",
            source_evidence=records[0],
            geometry_evidence=records[1],
            dataset_evidences=(foreign_ev, records[3]),
            authorization_evidences=(records[4], records[5]),
            witness_evidence=records[6],
            binding_evidence=records[7],
        )


def test_likely_singularity_blocks_peak_claim_but_not_neighborhood_claim():
    context = _context()
    graph = EvidenceGraph(context)
    for evidence in _empirical_bundle()["records"]:
        graph.add(evidence)
    neighborhood_decision = ClaimEngine.evaluate(empirical_local_neighborhood_claim(context.context_id), graph)
    assert neighborhood_decision.state is ClaimState.PERMITTED

    diagnostic = diagnose_local_singularity(
        diagnostic_id="SING",
        samples=(
            RefinementFieldSample(4.0, 200.0, 160.0),
            RefinementFieldSample(2.0, 270.0, 162.0),
            RefinementFieldSample(1.0, 380.0, 163.0),
        ),
    )
    graph.add(local_peak_convergence_evidence(diagnostic))
    peak_decision = ClaimEngine.evaluate(local_peak_reliability_claim(context.context_id), graph)
    assert peak_decision.state is ClaimState.BLOCKED
    assert any("OUT_OF_DOMAIN" in blocker for blocker in peak_decision.blockers)


def test_converged_local_peak_can_pass_separate_peak_claim():
    context = _context()
    graph = EvidenceGraph(context)
    diagnostic = diagnose_local_singularity(
        diagnostic_id="CONV",
        samples=(
            RefinementFieldSample(4.0, 205.0, 160.0),
            RefinementFieldSample(2.0, 210.0, 162.0),
            RefinementFieldSample(1.0, 212.0, 163.0),
        ),
    )
    graph.add(local_peak_convergence_evidence(diagnostic))
    decision = ClaimEngine.evaluate(local_peak_reliability_claim(context.context_id), graph)
    assert decision.state is ClaimState.PERMITTED
