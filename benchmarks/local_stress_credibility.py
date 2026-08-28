from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from astermax.credibility import (
    ClaimEngine,
    ClaimState,
    ConsequenceLevel,
    ContextOfUse,
    EvidenceGraph,
    build_analysis_passport,
    canonical_sha256,
)
from astermax.fea.kirsch import (
    build_kirsch_hole_witness,
    kirsch_boundary_kt,
    kirsch_polar_stress_mpa,
    kirsch_witness_evidence,
)
from astermax.fea.local_corroboration import (
    analytical_local_neighborhood_claim,
    local_neighborhood_binding_evidence,
    local_peak_convergence_evidence,
    local_peak_reliability_claim,
)
from astermax.fea.neighborhood_verification import (
    NeighborhoodSample,
    compare_local_neighborhood,
    neighborhood_comparison_evidence,
)
from astermax.fea.physics_guided_refinement import (
    recommend_local_refinement,
    refinement_recommendation_evidence,
)
from astermax.fea.singularity_diagnostic import (
    RefinementFieldSample,
    diagnose_local_singularity,
    singularity_diagnostic_evidence,
)
from astermax.fea.stress_concentration_source import shigley_2024_release_source_metadata


OUTPUT = Path("local_stress_credibility.json")


def main() -> int:
    context = ContextOfUse(
        context_id="LOCAL_STRESS_CREDIBILITY_SOFTWARE_VERIFICATION",
        engineering_question=(
            "Does the deterministic credibility pipeline distinguish a corroborated neighborhood "
            "from a non-claimable mesh-sensitive peak?"
        ),
        intended_decision="Permit the software-verification neighborhood claim and block the peak claim",
        quantities_of_interest=("local stress neighborhood", "local peak convergence"),
        acceptance_criteria=(
            "Kirsch boundary Kt equals 3 within floating-point tolerance",
            "synthetic spatial profile remains within 2 percent of Kirsch witness",
            "growing peak with stable neighborhood is classified LIKELY_SINGULARITY",
            "local peak claim is blocked",
        ),
        consequence_level=ConsequenceLevel.LOW,
        assumptions=(
            "SYNTHETIC_SOFTWARE_VERIFICATION_FIXTURE_NOT_FEA_RESULT",
            "linear elasticity",
            "Kirsch infinite-plate approximation with declared boundary clearance",
        ),
    )
    graph = EvidenceGraph(context)

    kirsch = build_kirsch_hole_witness(
        witness_id="KIRSCH_SOFTWARE_FIXTURE",
        hole_radius_mm=10.0,
        far_field_stress_mpa=100.0,
        boundary_clearance_over_diameter=4.0,
    )
    kirsch_evidence = kirsch_witness_evidence(kirsch)
    graph.add(kirsch_evidence)

    distances = (0.5, 1.0, 2.0, 4.0, 8.0)
    perturbations = (0.010, -0.008, 0.005, -0.004, 0.002)
    samples = []
    synthetic_profile = []
    for distance, perturbation in zip(distances, perturbations):
        _, hoop, _ = kirsch_polar_stress_mpa(
            kirsch,
            radius_mm=kirsch.hole_radius_mm + distance,
            theta_rad=0.5 * math.pi,
        )
        synthetic = hoop * (1.0 + perturbation)
        samples.append(NeighborhoodSample(distance, synthetic, hoop))
        synthetic_profile.append(
            {
                "distance_mm": distance,
                "synthetic_observation_mpa": synthetic,
                "kirsch_witness_mpa": hoop,
                "declared_perturbation": perturbation,
            }
        )

    comparison = compare_local_neighborhood(
        comparison_id="KIRSCH_SYNTHETIC_PROFILE",
        samples=samples,
        max_allowed_relative_error=0.02,
        min_samples=5,
    )
    graph.add(neighborhood_comparison_evidence(comparison))

    synthetic_payload = {
        "schema": "AsterMaxSyntheticLocalProfileV1",
        "classification": "SYNTHETIC_SOFTWARE_VERIFICATION_FIXTURE_NOT_FEA_RESULT",
        "samples": synthetic_profile,
    }
    synthetic_result_sha = hashlib.sha256(
        json.dumps(synthetic_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    binding = local_neighborhood_binding_evidence(
        binding_id="KIRSCH_SYNTHETIC_BINDING",
        comparison=comparison,
        witness_evidence=kirsch_evidence,
        fea_result_sha256=synthetic_result_sha,
    )
    graph.add(binding)

    diagnostic = diagnose_local_singularity(
        diagnostic_id="SYNTHETIC_SINGULAR_PATTERN",
        samples=(
            RefinementFieldSample(4.0, 210.0, 165.0),
            RefinementFieldSample(2.0, 285.0, 164.0),
            RefinementFieldSample(1.0, 395.0, 163.5),
            RefinementFieldSample(0.5, 545.0, 163.3),
        ),
    )
    graph.add(singularity_diagnostic_evidence(diagnostic))
    peak_gate = local_peak_convergence_evidence(diagnostic)
    graph.add(peak_gate)

    recommendation = recommend_local_refinement(
        recommendation_id="SYNTHETIC_LOCAL_REFINEMENT",
        neighborhood=comparison,
        singularity=diagnostic,
    )
    graph.add(refinement_recommendation_evidence(recommendation))

    neighborhood_decision = ClaimEngine.evaluate(
        analytical_local_neighborhood_claim(context.context_id), graph
    )
    peak_decision = ClaimEngine.evaluate(local_peak_reliability_claim(context.context_id), graph)
    passport = build_analysis_passport(graph, (neighborhood_decision, peak_decision))

    shigley_metadata = shigley_2024_release_source_metadata()
    report = {
        "schema": "AsterMaxLocalStressCredibilityBenchmarkV1",
        "classification": "SYNTHETIC_SOFTWARE_VERIFICATION_FIXTURE_NOT_FEA_RESULT",
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
        "shigley_adapter": {
            "source_id": shigley_metadata.source_id,
            "edition_or_release": shigley_metadata.edition_or_release,
            "provenance_sha256": shigley_metadata.provenance_sha256,
            "calculation_data_embedded": shigley_metadata.calculation_data_embedded,
            "dataset_sha256": shigley_metadata.dataset_sha256,
            "rights_note": shigley_metadata.rights_note,
            "used_to_calculate_this_benchmark": False,
        },
        "kirsch": {
            "witness_sha256": kirsch.witness_sha256,
            "hole_radius_mm": kirsch.hole_radius_mm,
            "far_field_stress_mpa": kirsch.far_field_stress_mpa,
            "boundary_kt": kirsch_boundary_kt(kirsch),
        },
        "synthetic_result_sha256": synthetic_result_sha,
        "neighborhood": {
            "comparison_sha256": comparison.comparison_sha256,
            "passed": comparison.passed,
            "max_relative_error": comparison.max_relative_error,
            "mean_relative_error": comparison.mean_relative_error,
            "sample_count": comparison.sample_count,
        },
        "singularity": {
            "diagnostic_sha256": diagnostic.diagnostic_sha256,
            "classification": diagnostic.classification,
            "peak_growth_factor": diagnostic.peak_growth_factor,
            "peak_last_change": diagnostic.peak_last_change,
            "neighborhood_last_change": diagnostic.neighborhood_last_change,
        },
        "refinement": {
            "recommendation_sha256": recommendation.recommendation_sha256,
            "action": recommendation.action,
            "target_size_factor": recommendation.target_size_factor,
        },
        "claims": {
            "neighborhood_state": neighborhood_decision.state.value,
            "peak_state": peak_decision.state.value,
            "peak_blockers": list(peak_decision.blockers),
        },
        "evidence_graph_sha256": graph.fingerprint_sha256,
        "passport_sha256": canonical_sha256(passport),
    }
    report["benchmark_sha256"] = canonical_sha256(report)

    assert abs(kirsch_boundary_kt(kirsch) - 3.0) <= 1.0e-12
    assert comparison.passed is True
    assert diagnostic.classification == "LIKELY_SINGULARITY"
    assert recommendation.action == "REFINE_NEIGHBORHOOD_DO_NOT_CHASE_PEAK"
    assert neighborhood_decision.state is ClaimState.PERMITTED
    assert peak_decision.state is ClaimState.BLOCKED
    assert shigley_metadata.calculation_data_embedded is False

    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"wrote {OUTPUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
