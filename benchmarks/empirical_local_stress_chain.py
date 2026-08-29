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
from astermax.fea.analytical_witness import (
    analytical_section_chain_evidence,
    analytical_section_witness_evidence,
    build_linear_normal_stress_witness,
)
from astermax.fea.authorized_empirical_dataset import (
    authorization_declaration_evidence,
    authorized_dataset_intake_evidence,
    build_authorized_dataset_manifest,
    ingest_authorized_stress_concentration_dataset,
)
from astermax.fea.empirical_kt_evaluation import evaluate_domain_bound_stress_concentration
from astermax.fea.empirical_local_stress import (
    build_empirical_local_stress_prediction,
    empirical_evaluation_evidence,
    empirical_local_prediction_evidence,
    empirical_local_stress_chain_evidence,
    empirical_local_stress_computation_claim,
)
from astermax.fea.axisymmetric_shoulder import recognize_x_axis_shaft_shoulder
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.persistent_geometry import capture_face_selection, list_face_signatures, resolve_face_selection
from astermax.fea.section_evidence import (
    persistent_face_identity_evidence,
    planar_section_properties,
    section_properties_evidence,
)
from astermax.fea.shaft_shoulder import build_shaft_shoulder_geometry, shaft_shoulder_geometry_evidence
from astermax.fea.stress_concentration_applicability import (
    applicability_assessment_evidence,
    applicability_domain_evidence,
    assess_stress_concentration_applicability,
    build_stress_concentration_applicability_domain,
)
from astermax.fea.stress_concentration_source import build_stress_concentration_source, source_provenance_evidence


STEP = Path("empirical_local_stress_chain.step")
DATASET = Path("empirical_local_stress_chain_synthetic_dataset.json")
OUT = Path("empirical_local_stress_chain.json")


def _write_fixture() -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("empirical_local_stress_chain")
        small = gmsh.model.occ.addCylinder(0.0, 0.0, 0.0, 40.0, 0.0, 0.0, 10.0)
        large = gmsh.model.occ.addCylinder(40.0, 0.0, 0.0, 40.0, 0.0, 0.0, 15.0)
        gmsh.model.occ.fuse([(3, small)], [(3, large)])
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        edges = []
        for _, tag in gmsh.model.getEntities(1):
            box = tuple(float(v) for v in gmsh.model.getBoundingBox(1, int(tag)))
            x_mid = 0.5 * (box[0] + box[3])
            if (
                abs(x_mid - 40.0) <= 1.0e-4
                and box[3] - box[0] <= 1.0e-4
                and abs(0.5 * (box[4] - box[1]) - 10.0) <= 1.0e-4
                and abs(0.5 * (box[5] - box[2]) - 10.0) <= 1.0e-4
            ):
                edges.append(int(tag))
        if len(volumes) != 1 or len(edges) != 1:
            raise RuntimeError(f"fixture topology unexpected: volumes={volumes}, fillet_edges={edges}")
        gmsh.model.occ.fillet([int(volumes[0][1])], [edges[0]], [2.0], removeVolume=True)
        gmsh.model.occ.synchronize()
        gmsh.write(str(STEP))
    finally:
        gmsh.finalize()


def _x_min_face_tag() -> int:
    matches = [
        tag for tag, signature in list_face_signatures(STEP)
        if signature.surface_type.strip().lower() == "plane"
        and abs(signature.center_mm[0]) <= 1.0e-6
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected one x-min planar face, got {matches}")
    return int(matches[0])


def main() -> int:
    _write_fixture()
    feature = recognize_x_axis_shaft_shoulder(STEP, feature_id="C16_EMPIRICAL_LOCAL_STRESS")
    geometry = build_shaft_shoulder_geometry(
        geometry_id="C16_CAD_R10_R15_R2",
        small_diameter_mm=2.0 * feature.small_radius_mm,
        large_diameter_mm=2.0 * feature.large_radius_mm,
        fillet_radius_mm=feature.fillet_radius_mm,
    )

    selection = capture_face_selection(STEP, _x_min_face_tag(), "C16_SMALL_DIAMETER_SECTION")
    resolution = resolve_face_selection(STEP, selection)
    section = planar_section_properties(STEP, selection)
    witness = build_linear_normal_stress_witness(
        section,
        axial_force_n=1000.0,
        moment_u_nmm=0.0,
        moment_v_nmm=0.0,
    )
    face_ev = persistent_face_identity_evidence(selection, resolution)
    section_ev = section_properties_evidence(section)
    witness_ev = analytical_section_witness_evidence(witness)
    section_chain_ev = analytical_section_chain_evidence(face_ev, section_ev, witness_ev)

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
    dataset_payload = {
        "schema": "AsterMaxStressConcentrationDatasetV1",
        "dataset_id": "C16_SYNTHETIC_KT_GRID",
        "factor_name": "Kt_SYNTHETIC_NOT_PHYSICAL",
        "load_mode": "AXIAL_TENSION",
        "source_provenance_sha256": source.provenance_sha256,
        "diameter_ratios": [1.5, 2.0],
        "radius_ratios": [0.05, 0.10, 0.15],
        "factors": [[101.0, 102.0, 103.0], [201.0, 202.0, 203.0]],
    }
    raw = (json.dumps(dataset_payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    DATASET.write_bytes(raw)
    raw_sha = hashlib.sha256(raw).hexdigest()
    manifest = build_authorized_dataset_manifest(
        manifest_id="C16_SYNTHETIC_MANIFEST",
        dataset_filename=DATASET.name,
        expected_file_sha256=raw_sha,
        source_provenance_sha256=source.provenance_sha256,
        authorization_basis="SYNTHETIC_VERIFICATION",
        rights_reference="AsterMax-generated synthetic CI fixture; no physical Kt values",
        attested_by="ASTERMAX_TEST_SUITE",
        authorized_for_calculation=True,
    )
    intake, grid = ingest_authorized_stress_concentration_dataset(DATASET, manifest, source)

    domain = build_stress_concentration_applicability_domain(
        domain_id="C16_SYNTHETIC_DOMAIN",
        source_provenance_sha256=source.provenance_sha256,
        load_mode="AXIAL_TENSION",
        allowed_diameter_ratios=(1.5, 2.0),
        radius_ratio_min=0.05,
        radius_ratio_max=0.15,
        source_locator="synthetic C16 domain for software verification only",
        diameter_ratio_absolute_tolerance=1.0e-6,
    )
    applicability = assess_stress_concentration_applicability(
        source, domain, geometry, requested_load_mode="AXIAL_TENSION"
    )
    if not applicability.applicable:
        raise RuntimeError(f"C16 synthetic domain unexpectedly rejected CAD geometry: {applicability.blockers}")
    evaluation = evaluate_domain_bound_stress_concentration(grid, applicability, geometry)
    prediction = build_empirical_local_stress_prediction(
        intake, grid, applicability, geometry, witness, evaluation
    )
    if prediction.uses_non_synthetic_authorized_data:
        raise RuntimeError("C16 synthetic dataset became non-synthetic")

    context = ContextOfUse(
        context_id="COU_C16_EMPIRICAL_LOCAL_STRESS_CHAIN",
        engineering_question=(
            "Can AsterMax deterministically bind one empirical Kt evaluation to the matching CAD nominal section and geometry?"
        ),
        intended_decision=(
            "Permit the empirical local-stress computation software chain only. Synthetic Kt must not become physical engineering evidence."
        ),
        quantities_of_interest=("CAD nominal axial stress", "synthetic Kt", "synthetic local axial stress"),
        acceptance_criteria=(
            "persistent CAD section chain verified",
            "authorized dataset intake verified",
            "source domain applicable",
            "D/d resolved only to an explicitly declared dataset curve",
            "nominal section area matches small CAD diameter",
            "pure axial load only",
        ),
        consequence_level=ConsequenceLevel.HIGH,
        assumptions=("synthetic Kt values are intentionally nonphysical",),
    )
    graph = EvidenceGraph(context)
    records = {
        "source": source_provenance_evidence(source),
        "authorization": authorization_declaration_evidence(manifest),
        "intake": authorized_dataset_intake_evidence(intake),
        "geometry": shaft_shoulder_geometry_evidence(geometry),
        "domain": applicability_domain_evidence(domain),
        "applicability": applicability_assessment_evidence(applicability),
        "face": face_ev,
        "section": section_ev,
        "witness": witness_ev,
        "section_chain": section_chain_ev,
        "evaluation": empirical_evaluation_evidence(intake, evaluation),
        "prediction": empirical_local_prediction_evidence(prediction),
        "empirical_chain": empirical_local_stress_chain_evidence(
            intake, applicability, witness, evaluation, prediction
        ),
    }
    for record in records.values():
        graph.add(record)
    graph.link(records["intake"].evidence_id, records["authorization"].evidence_id, "REQUIRES_AUTHORIZATION")
    graph.link(records["intake"].evidence_id, records["source"].evidence_id, "BOUND_TO_SOURCE")
    graph.link(records["applicability"].evidence_id, records["domain"].evidence_id, "ASSESSED_AGAINST_DOMAIN")
    graph.link(records["applicability"].evidence_id, records["geometry"].evidence_id, "ASSESSES_GEOMETRY")
    graph.link(records["section_chain"].evidence_id, records["face"].evidence_id, "BINDS_CAD_FACE")
    graph.link(records["section_chain"].evidence_id, records["section"].evidence_id, "BINDS_SECTION")
    graph.link(records["section_chain"].evidence_id, records["witness"].evidence_id, "BINDS_WITNESS")
    graph.link(records["evaluation"].evidence_id, records["intake"].evidence_id, "USES_DATASET")
    graph.link(records["evaluation"].evidence_id, records["applicability"].evidence_id, "REQUIRES_APPLICABILITY")
    graph.link(records["prediction"].evidence_id, records["evaluation"].evidence_id, "USES_KT")
    graph.link(records["prediction"].evidence_id, records["witness"].evidence_id, "USES_NOMINAL_STRESS")
    graph.link(records["empirical_chain"].evidence_id, records["prediction"].evidence_id, "BINDS_PREDICTION")
    graph.link(records["empirical_chain"].evidence_id, records["section_chain"].evidence_id, "REQUIRES_CAD_SECTION_CHAIN")

    decision = ClaimEngine.evaluate(empirical_local_stress_computation_claim(context.context_id), graph)
    if decision.state is not ClaimState.PERMITTED:
        raise RuntimeError(f"C16 computation claim unexpectedly blocked: {decision.blockers}")
    passport = build_analysis_passport(graph, (decision,))

    report = {
        "schema": "AsterMaxEmpiricalLocalStressChainBenchmarkV1",
        "classification": "SYNTHETIC_EMPIRICAL_LOCAL_STRESS_CHAIN_SOFTWARE_VERIFICATION_NOT_PHYSICAL_RESULT",
        "source_sha256": feature.source_sha256,
        "feature_sha256": feature.feature_sha256,
        "geometry": asdict(geometry),
        "persistent_section_selection_sha256": selection.selection_sha256,
        "section_sha256": section.section_sha256,
        "analytical_witness": asdict(witness),
        "source_provenance_sha256": source.provenance_sha256,
        "manifest_sha256": manifest.manifest_sha256,
        "intake_sha256": intake.intake_sha256,
        "grid_dataset_sha256": grid.dataset_sha256,
        "domain": asdict(domain),
        "applicability": asdict(applicability),
        "evaluation": asdict(evaluation),
        "prediction": asdict(prediction),
        "claim_state": decision.state.value,
        "claim_blockers": list(decision.blockers),
        "claim_decision_sha256": decision.decision_sha256,
        "evidence_graph_sha256": graph.fingerprint_sha256,
        "analysis_passport_sha256": passport["passport_sha256"],
        "empirical_local_stress_chain_computation_claim": True,
        "empirical_kt_physical_value_available": False,
        "empirical_fea_corroboration_claim": False,
        "empirical_kt_validation_claim": False,
        "experimental_validation_claim": False,
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
        "interpretation_boundary": (
            "C16 proves only the deterministic software chain from persistent CAD nominal section through an authorized, applicable Kt dataset "
            "to an empirical local-stress calculation. The Kt values in this benchmark are synthetic and nonphysical; therefore the predicted "
            "local stress is also synthetic and must not be compared to C12b as physical corroboration."
        ),
    }
    report["benchmark_sha256"] = canonical_sha256(report)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "classification": report["classification"],
        "D_over_d_actual": geometry.diameter_ratio,
        "D_over_d_evaluated": evaluation.evaluated_diameter_ratio,
        "D_over_d_snap": evaluation.diameter_ratio_snap_absolute,
        "r_over_d": geometry.radius_ratio,
        "synthetic_kt": evaluation.factor,
        "nominal_stress_mpa": witness.sigma0_mpa,
        "synthetic_local_stress_mpa": prediction.predicted_local_axial_stress_mpa,
        "nominal_area_relative_mismatch": prediction.nominal_area_relative_mismatch,
        "claim_state": decision.state.value,
        "empirical_kt_physical_value_available": False,
        "benchmark_sha256": report["benchmark_sha256"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
