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
from astermax.fea.authorized_empirical_dataset import (
    authorization_declaration_evidence,
    authorized_dataset_intake_evidence,
    build_authorized_dataset_manifest,
    empirical_dataset_intake_claim,
    ingest_authorized_stress_concentration_dataset,
)
from astermax.fea.bounded_stress_concentration import evaluate_stress_concentration
from astermax.fea.shaft_shoulder import build_shaft_shoulder_geometry
from astermax.fea.stress_concentration_source import build_stress_concentration_source, source_provenance_evidence


DATASET = Path("authorized_synthetic_stress_concentration_dataset.json")
OUT = Path("authorized_empirical_dataset_intake.json")


def main() -> int:
    source = build_stress_concentration_source(
        source_id="C15_SYNTHETIC_SOURCE",
        title="C15 synthetic stress-concentration software verification dataset",
        edition_or_release="1",
        publisher="AsterMax verification suite",
        locator="benchmarks/authorized_empirical_dataset_intake.py",
        source_url="https://example.invalid/astermax-c15-synthetic",
        rights_note="SYNTHETIC_SOFTWARE_VERIFICATION_DATA_NOT_PHYSICAL",
        calculation_data_embedded=False,
    )
    dataset_payload = {
        "schema": "AsterMaxStressConcentrationDatasetV1",
        "dataset_id": "C15_SYNTHETIC_KT_GRID",
        "factor_name": "Kt_SYNTHETIC_NOT_PHYSICAL",
        "load_mode": "AXIAL_TENSION",
        "source_provenance_sha256": source.provenance_sha256,
        "diameter_ratios": [1.5, 2.0],
        "radius_ratios": [0.05, 0.10],
        "factors": [[101.0, 102.0], [201.0, 202.0]],
    }
    raw = (json.dumps(dataset_payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    DATASET.write_bytes(raw)
    raw_sha = hashlib.sha256(raw).hexdigest()

    manifest = build_authorized_dataset_manifest(
        manifest_id="C15_SYNTHETIC_MANIFEST",
        dataset_filename=DATASET.name,
        expected_file_sha256=raw_sha,
        source_provenance_sha256=source.provenance_sha256,
        authorization_basis="SYNTHETIC_VERIFICATION",
        rights_reference="AsterMax-generated synthetic CI fixture; no empirical physical factors",
        attested_by="ASTERMAX_TEST_SUITE",
        authorized_for_calculation=True,
    )
    intake, grid = ingest_authorized_stress_concentration_dataset(DATASET, manifest, source)
    geometry = build_shaft_shoulder_geometry(
        geometry_id="C15_SYNTHETIC_EVALUATION_POINT",
        small_diameter_mm=20.0,
        large_diameter_mm=30.0,
        fillet_radius_mm=2.0,
    )
    evaluation = evaluate_stress_concentration(grid, geometry)
    if evaluation.factor != 102.0:
        raise RuntimeError(f"synthetic C15 exact-grid evaluation mismatch: {evaluation.factor}")
    if not intake.synthetic_verification_only:
        raise RuntimeError("C15 synthetic fixture lost synthetic-only marker")

    context = ContextOfUse(
        context_id="COU_C15_AUTHORIZED_DATASET_INTAKE",
        engineering_question="Can AsterMax accept an exact rights-declared stress-concentration dataset without losing byte/source provenance?",
        intended_decision=(
            "Permit the dataset intake software capability only. The synthetic factors must never become physical Kt evidence."
        ),
        quantities_of_interest=("raw file integrity", "source binding", "authorization provenance", "semantic grid identity"),
        acceptance_criteria=(
            "exact SHA-256 bytes",
            "strict schema",
            "source provenance match",
            "declared calculation authorization",
            "bounded grid semantics",
        ),
        consequence_level=ConsequenceLevel.HIGH,
        assumptions=("all numerical factor values in this benchmark are synthetic and intentionally nonphysical",),
    )
    graph = EvidenceGraph(context)
    records = (
        source_provenance_evidence(source),
        authorization_declaration_evidence(manifest),
        authorized_dataset_intake_evidence(intake),
    )
    for record in records:
        graph.add(record)
    graph.link(records[1].evidence_id, records[0].evidence_id, "DECLARES_RIGHTS_FOR_SOURCE")
    graph.link(records[2].evidence_id, records[1].evidence_id, "REQUIRES_AUTHORIZATION")
    graph.link(records[2].evidence_id, records[0].evidence_id, "BOUND_TO_SOURCE")

    decision = ClaimEngine.evaluate(empirical_dataset_intake_claim(context.context_id), graph)
    if decision.state is not ClaimState.PERMITTED:
        raise RuntimeError(f"C15 intake claim unexpectedly blocked: {decision.blockers}")
    passport = build_analysis_passport(graph, (decision,))

    report = {
        "schema": "AsterMaxAuthorizedEmpiricalDatasetIntakeBenchmarkV1",
        "classification": "SYNTHETIC_DATASET_INTAKE_SOFTWARE_VERIFICATION_NOT_PHYSICAL_RESULT",
        "source": source.canonical_without_hash(),
        "source_provenance_sha256": source.provenance_sha256,
        "manifest": asdict(manifest),
        "intake": asdict(intake),
        "grid_dataset_sha256": grid.dataset_sha256,
        "synthetic_evaluation": asdict(evaluation),
        "claim_state": decision.state.value,
        "claim_blockers": list(decision.blockers),
        "claim_decision_sha256": decision.decision_sha256,
        "analysis_passport_sha256": passport["passport_sha256"],
        "evidence_graph_sha256": graph.fingerprint_sha256,
        "dataset_intake_capability_claim": True,
        "empirical_kt_physical_value_available": False,
        "empirical_kt_validation_claim": False,
        "experimental_validation_claim": False,
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
        "interpretation_boundary": (
            "The factor value 102.0 is deliberately synthetic software-verification data. "
            "C15 verifies the authorized-dataset intake mechanism only: byte hash, strict schema, source binding, "
            "authorization provenance and deterministic conversion to a bounded grid. It provides no physical Kt value."
        ),
    }
    report["benchmark_sha256"] = canonical_sha256(report)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "classification": report["classification"],
        "raw_file_sha256": intake.raw_file_sha256,
        "manifest_sha256": manifest.manifest_sha256,
        "grid_dataset_sha256": grid.dataset_sha256,
        "intake_sha256": intake.intake_sha256,
        "claim_state": decision.state.value,
        "synthetic_evaluation_factor": evaluation.factor,
        "empirical_kt_physical_value_available": False,
        "benchmark_sha256": report["benchmark_sha256"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
