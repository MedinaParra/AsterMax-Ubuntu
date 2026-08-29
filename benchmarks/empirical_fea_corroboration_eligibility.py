from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
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
from astermax.fea.analytical_witness import LinearNormalStressWitness
from astermax.fea.authorized_empirical_dataset import (
    authorized_dataset_intake_evidence,
    build_authorized_dataset_manifest,
    ingest_authorized_stress_concentration_dataset,
)
from astermax.fea.empirical_fea_corroboration import (
    assess_empirical_fea_corroboration_eligibility,
    build_fea_local_stress_verification_summary,
    empirical_fea_corroboration_eligibility_claim,
    empirical_fea_corroboration_eligibility_evidence,
    fea_local_stress_verification_summary_evidence,
)
from astermax.fea.empirical_kt_evaluation import DomainBoundStressConcentrationEvaluation
from astermax.fea.empirical_local_stress import (
    EmpiricalLocalStressPrediction,
    empirical_local_prediction_evidence,
    empirical_local_stress_chain_evidence,
)
from astermax.fea.shaft_shoulder import ShaftShoulderGeometry
from astermax.fea.stress_concentration_applicability import (
    StressConcentrationApplicabilityAssessment,
    applicability_assessment_evidence,
)
from astermax.fea.stress_concentration_source import build_stress_concentration_source


C16_REPORT = Path("empirical_local_stress_chain.json")
C16_DATASET = Path("empirical_local_stress_chain_synthetic_dataset.json")
OUT = Path("empirical_fea_corroboration_eligibility.json")

# Exact C12b evidence replayed successfully on C16 head 4af7abca3cb7bec7e1087d1b01c6e9c8687e4bae.
C12B_WORKFLOW_RUN_ID = 33237582688
C12B_BENCHMARK_SHA256 = "4cd996ff010fc39c61f12cbdfc457c3c3f91470d33e107331b798ada212b426f"
C12B_ARTIFACT_ZIP_SHA256 = "fe522b65c7aff5b09df389361508490dd6f3dea9c3a02d8466c4c2454f9638a1"
C12B_DECISION_SHA256 = "516db1296545dfb9fe7ce487f99adb9167fd577d266c1db022705b2a88389db6"
C12B_SINGULARITY_SHA256 = "254463343e6ffb27267ed5733a8934f6698387d8213c51c484dfc6943e6d885d"


def _load_c16_chain():
    if not C16_REPORT.is_file() or not C16_DATASET.is_file():
        raise RuntimeError("C17 requires C16 benchmark outputs in the current workspace")
    report = json.loads(C16_REPORT.read_text(encoding="utf-8"))
    if report.get("classification") != "SYNTHETIC_EMPIRICAL_LOCAL_STRESS_CHAIN_SOFTWARE_VERIFICATION_NOT_PHYSICAL_RESULT":
        raise RuntimeError("C17 received an unexpected C16 classification")
    if report.get("claim_state") != "PERMITTED" or not report.get("empirical_local_stress_chain_computation_claim"):
        raise RuntimeError("C17 requires the C16 software-chain claim to be permitted")
    if report.get("empirical_kt_physical_value_available") is not False:
        raise RuntimeError("C16 synthetic Kt unexpectedly became physical evidence")

    source = build_stress_concentration_source(
        source_id="C16_SYNTHETIC_SOURCE",
        title="C16 synthetic empirical local stress software verification dataset",
        edition_or_release="1",
        publisher="AsterMax verification suite",
        locator="benchmarks/empirical_local_stress_chain.py",
        source_url="https://example.invalid/astermax-c16-synthetic",
        rights_note="SYNTHETIC_SOFTWARE_VERIFICATION_DATA_NOT_PHYSICAL",
        calculation_data_embedded=False,
    )
    raw = C16_DATASET.read_bytes()
    raw_sha = hashlib.sha256(raw).hexdigest()
    manifest = build_authorized_dataset_manifest(
        manifest_id="C16_SYNTHETIC_MANIFEST",
        dataset_filename=C16_DATASET.name,
        expected_file_sha256=raw_sha,
        source_provenance_sha256=source.provenance_sha256,
        authorization_basis="SYNTHETIC_VERIFICATION",
        rights_reference="AsterMax-generated synthetic CI fixture; no physical Kt values",
        attested_by="ASTERMAX_TEST_SUITE",
        authorized_for_calculation=True,
    )
    intake, grid = ingest_authorized_stress_concentration_dataset(C16_DATASET, manifest, source)

    geometry = ShaftShoulderGeometry(**report["geometry"])
    applicability = StressConcentrationApplicabilityAssessment(**report["applicability"])
    witness = LinearNormalStressWitness(**report["analytical_witness"])
    evaluation = DomainBoundStressConcentrationEvaluation(**report["evaluation"])
    prediction = EmpiricalLocalStressPrediction(**report["prediction"])

    exact_checks = {
        "source_provenance_sha256": source.provenance_sha256 == report["source_provenance_sha256"],
        "manifest_sha256": manifest.manifest_sha256 == report["manifest_sha256"],
        "intake_sha256": intake.intake_sha256 == report["intake_sha256"],
        "grid_dataset_sha256": grid.dataset_sha256 == report["grid_dataset_sha256"],
        "applicability_sha256": applicability.assessment_sha256 == report["applicability"]["assessment_sha256"],
        "evaluation_sha256": evaluation.evaluation_sha256 == report["evaluation"]["evaluation_sha256"],
        "prediction_sha256": prediction.prediction_sha256 == report["prediction"]["prediction_sha256"],
    }
    if not all(exact_checks.values()):
        raise RuntimeError(f"C17 could not reconstruct exact C16 chain: {exact_checks}")
    if prediction.uses_non_synthetic_authorized_data or not intake.synthetic_verification_only:
        raise RuntimeError("C17 expected exact C16 synthetic provenance")
    return report, intake, geometry, applicability, witness, evaluation, prediction, exact_checks


def main() -> int:
    c16, intake, geometry, applicability, witness, evaluation, prediction, reconstruction_checks = _load_c16_chain()

    fea = build_fea_local_stress_verification_summary(
        upstream_benchmark_sha256=C12B_BENCHMARK_SHA256,
        upstream_artifact_zip_sha256=C12B_ARTIFACT_ZIP_SHA256,
        upstream_decision_sha256=C12B_DECISION_SHA256,
        upstream_singularity_diagnostic_sha256=C12B_SINGULARITY_SHA256,
        small_diameter_mm=20.0000002,
        large_diameter_mm=30.0000002,
        fillet_radius_mm=1.9999997999999977,
        axial_force_n=1000.0,
        local_stress_convergence_claim=True,
        singularity_classification="LOCALLY_CONVERGED_FIELD",
        qoi_id="VON_MISES_IP_MAX_MPA",
        qoi_location="ACTUAL_DUFFY_GL4_INTERIOR_INTEGRATION_POINTS",
        qoi_stress_measure="VON_MISES",
        measurement_operator="MAX_ACTUAL_DUFFY_GL4_IP_INSIDE_FIXED_SHOULDER_BOX_PLUS_R_OVER_4_VOLUME_INTEGRAL",
        nodal_recovery=False,
        surface_extrapolation=False,
    )
    eligibility = assess_empirical_fea_corroboration_eligibility(
        prediction,
        intake,
        geometry,
        fea,
    )
    expected_blockers = (
        "EMPIRICAL_DATASET_SYNTHETIC_NOT_PHYSICAL",
        "FEA_QOI_NOT_COMPATIBLE_WITH_EMPIRICAL_SURFACE_PEAK_AXIAL_STRESS",
    )
    if eligibility.eligible:
        raise RuntimeError("C17 synthetic C16 data became eligible for physical FEA corroboration")
    if eligibility.classification != "BLOCKED_SYNTHETIC_EMPIRICAL_DATA_NOT_PHYSICAL":
        raise RuntimeError(f"unexpected C17 classification: {eligibility.classification}")
    if eligibility.blockers != expected_blockers:
        raise RuntimeError(f"unexpected C17 blockers: {eligibility.blockers}")
    if not eligibility.geometry_match or not eligibility.axial_load_scale_match:
        raise RuntimeError("C17 should not hide synthetic/QOI blockers behind geometry or load mismatch")
    if not eligibility.fea_converged or not eligibility.fea_locally_converged_field:
        raise RuntimeError("C17 requires the real C12b numerical convergence result to remain valid")

    context = ContextOfUse(
        context_id="COU_C17_EMPIRICAL_FEA_CORROBORATION_ELIGIBILITY",
        engineering_question="Are the current C16 empirical result and C12b FEA result eligible for a physical corroboration comparison?",
        intended_decision="Block any numerical comparison unless empirical provenance is physical and the FEA QOI is semantically equivalent.",
        quantities_of_interest=("empirical surface peak axial normal stress", "C12b interior integration-point von Mises stress"),
        acceptance_criteria=(
            "non-synthetic empirical dataset",
            "matching geometry and nominal load scale",
            "verified locally converged FEA field",
            "same stress measure, location and measurement operator semantics",
        ),
        consequence_level=ConsequenceLevel.HIGH,
        assumptions=("C12b hashes come from Windows run 33237582688 on exact C16 head",),
    )
    graph = EvidenceGraph(context)
    records = {
        "intake": authorized_dataset_intake_evidence(intake),
        "applicability": applicability_assessment_evidence(applicability),
        "prediction": empirical_local_prediction_evidence(prediction),
        "chain": empirical_local_stress_chain_evidence(intake, applicability, witness, evaluation, prediction),
        "fea": fea_local_stress_verification_summary_evidence(fea),
        "eligibility": empirical_fea_corroboration_eligibility_evidence(eligibility),
    }
    for record in records.values():
        graph.add(record)
    graph.link(records["prediction"].evidence_id, records["intake"].evidence_id, "USES_DATASET")
    graph.link(records["chain"].evidence_id, records["prediction"].evidence_id, "BINDS_PREDICTION")
    graph.link(records["chain"].evidence_id, records["applicability"].evidence_id, "REQUIRES_APPLICABILITY")
    graph.link(records["eligibility"].evidence_id, records["chain"].evidence_id, "ASSESSES_EMPIRICAL_CHAIN")
    graph.link(records["eligibility"].evidence_id, records["fea"].evidence_id, "ASSESSES_FEA_QOI")

    decision = ClaimEngine.evaluate(
        empirical_fea_corroboration_eligibility_claim(context.context_id),
        graph,
    )
    if decision.state is not ClaimState.BLOCKED:
        raise RuntimeError("C17 eligibility claim must remain blocked for current evidence")
    passport = build_analysis_passport(graph, (decision,))

    report = {
        "schema": "AsterMaxEmpiricalFeaCorroborationEligibilityBenchmarkV1",
        "classification": eligibility.classification,
        "c16_benchmark_sha256": c16["benchmark_sha256"],
        "c16_reconstruction_checks": reconstruction_checks,
        "c16_prediction_sha256": prediction.prediction_sha256,
        "c16_intake_sha256": intake.intake_sha256,
        "c12b_workflow_run_id": C12B_WORKFLOW_RUN_ID,
        "c12b_benchmark_sha256": C12B_BENCHMARK_SHA256,
        "c12b_artifact_zip_sha256": C12B_ARTIFACT_ZIP_SHA256,
        "c12b_decision_sha256": C12B_DECISION_SHA256,
        "c12b_singularity_diagnostic_sha256": C12B_SINGULARITY_SHA256,
        "fea_summary": asdict(fea),
        "eligibility": asdict(eligibility),
        "claim_state": decision.state.value,
        "claim_blockers": list(decision.blockers),
        "claim_decision_sha256": decision.decision_sha256,
        "evidence_graph_sha256": graph.fingerprint_sha256,
        "analysis_passport_sha256": passport["passport_sha256"],
        "empirical_fea_corroboration_eligible": False,
        "empirical_fea_corroboration_performed": False,
        "empirical_kt_validation_claim": False,
        "experimental_validation_claim": False,
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
        "interpretation_boundary": (
            "C17 is an eligibility gate only. Current C16 Kt data are synthetic and nonphysical. C12b verifies a locally converged interior "
            "integration-point von Mises field plus a fixed physical volume integral, not a CAD-surface peak axial normal stress. Therefore no "
            "numerical empirical-vs-FEA corroboration is permitted, regardless of apparent numerical proximity or difference."
        ),
    }
    report["benchmark_sha256"] = canonical_sha256(report)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "classification": report["classification"],
        "eligibility_blockers": list(eligibility.blockers),
        "geometry_match": eligibility.geometry_match,
        "axial_load_scale_match": eligibility.axial_load_scale_match,
        "fea_converged": eligibility.fea_converged,
        "fea_locally_converged_field": eligibility.fea_locally_converged_field,
        "empirical_data_non_synthetic": eligibility.empirical_data_non_synthetic,
        "qoi_compatible": eligibility.qoi_compatible,
        "claim_state": decision.state.value,
        "corroboration_performed": False,
        "benchmark_sha256": report["benchmark_sha256"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
