import hashlib

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
    empirical_local_neighborhood_claim,
    local_neighborhood_binding_evidence,
    local_peak_convergence_evidence,
    local_peak_reliability_claim,
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


def _empirical_evidence():
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
    witness_ev = notch_witness_evidence(witness)
    binding = local_neighborhood_binding_evidence(
        binding_id="B1",
        comparison=neighborhood,
        witness_evidence=witness_ev,
        fea_result_sha256=hashlib.sha256(b"synthetic-fea-result").hexdigest(),
    )
    return (
        source_provenance_evidence(source),
        shaft_shoulder_geometry_evidence(geometry),
        stress_concentration_dataset_evidence(kt),
        stress_concentration_dataset_evidence(kts),
        witness_ev,
        binding,
    )


def test_empirical_neighborhood_claim_is_permitted_with_complete_bound_chain():
    graph = EvidenceGraph(_context())
    for evidence in _empirical_evidence():
        graph.add(evidence)
    decision = ClaimEngine.evaluate(empirical_local_neighborhood_claim(graph.context.context_id), graph)
    assert decision.state is ClaimState.PERMITTED


def test_likely_singularity_blocks_peak_claim_but_not_neighborhood_claim():
    context = _context()
    graph = EvidenceGraph(context)
    for evidence in _empirical_evidence():
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
