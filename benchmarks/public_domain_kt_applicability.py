from __future__ import annotations

from dataclasses import asdict
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
from astermax.fea.axisymmetric_shoulder import recognize_x_axis_shaft_shoulder
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.shaft_shoulder import build_shaft_shoulder_geometry, shaft_shoulder_geometry_evidence
from astermax.fea.stress_concentration_applicability import (
    applicability_assessment_evidence,
    applicability_domain_evidence,
    assess_stress_concentration_applicability,
    build_stress_concentration_applicability_domain,
    empirical_kt_source_applicability_claim,
)
from astermax.fea.stress_concentration_source import (
    naca_tn_2442_source_metadata,
    source_provenance_evidence,
)


STEP = Path("public_domain_kt_applicability.step")
OUT = Path("public_domain_kt_applicability.json")


def _write_fixture() -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("public_domain_kt_applicability")
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


def main() -> int:
    _write_fixture()
    feature = recognize_x_axis_shaft_shoulder(STEP, feature_id="C14_PUBLIC_DOMAIN_KT")
    geometry = build_shaft_shoulder_geometry(
        geometry_id="C14_CAD_R10_R15_R2",
        small_diameter_mm=2.0 * feature.small_radius_mm,
        large_diameter_mm=2.0 * feature.large_radius_mm,
        fillet_radius_mm=feature.fillet_radius_mm,
    )

    source = naca_tn_2442_source_metadata()
    domain = build_stress_concentration_applicability_domain(
        domain_id="NACA_TN2442_TENSION_FILLET_SCOPE",
        source_provenance_sha256=source.provenance_sha256,
        load_mode="AXIAL_TENSION",
        allowed_diameter_ratios=(1.5, 2.0),
        radius_ratio_min=0.011,
        radius_ratio_max=0.08,
        source_locator=(
            "NACA TN-2442 published investigation scope: r/d approximately 0.011 to 0.08 "
            "for D/d = 1.5 and 2.0"
        ),
    )
    assessment = assess_stress_concentration_applicability(
        source,
        domain,
        geometry,
        requested_load_mode="AXIAL_TENSION",
    )

    context = ContextOfUse(
        context_id="COU_C14_PUBLIC_DOMAIN_KT_APPLICABILITY",
        engineering_question=(
            "May the public NACA TN-2442 shoulder-fillet tension source be used for the exact C13 verification geometry?"
        ),
        intended_decision=(
            "Permit only source-domain applicability. Never calculate or validate Kt without an authorized hash-bound factor dataset."
        ),
        quantities_of_interest=("D/d", "r/d", "empirical source applicability"),
        acceptance_criteria=(
            "load mode matches",
            "D/d is one of the explicitly declared source ratios",
            "r/d lies inside the published investigation range",
            "no extrapolation",
        ),
        consequence_level=ConsequenceLevel.HIGH,
        assumptions=(
            "NACA TN-2442 scope metadata is represented without digitized factor values",
            "fixture geometry is recognized deterministically from the generated STEP source",
        ),
    )
    graph = EvidenceGraph(context)
    records = (
        source_provenance_evidence(source),
        shaft_shoulder_geometry_evidence(geometry),
        applicability_domain_evidence(domain),
        applicability_assessment_evidence(assessment),
    )
    for record in records:
        graph.add(record)

    decision = ClaimEngine.evaluate(empirical_kt_source_applicability_claim(context.context_id), graph)
    if assessment.applicable:
        raise RuntimeError("C14 fixture unexpectedly entered NACA TN-2442 empirical domain")
    if assessment.classification != "OUTSIDE_EMPIRICAL_DOMAIN":
        raise RuntimeError(f"unexpected C14 classification: {assessment.classification}")
    if assessment.blockers != ("RADIUS_RATIO_OUTSIDE_EMPIRICAL_DOMAIN",):
        raise RuntimeError(f"unexpected C14 blockers: {assessment.blockers}")
    if decision.state is not ClaimState.BLOCKED:
        raise RuntimeError(f"C14 claim must be blocked, got {decision.state.value}")

    passport = build_analysis_passport(graph, (decision,))
    payload = {
        "schema": "AsterMaxPublicDomainKtApplicabilityBenchmarkV1",
        "classification": "EMPIRICAL_KT_SOURCE_OUTSIDE_DOMAIN_EXPECTED_FAIL_CLOSED",
        "source_sha256": feature.source_sha256,
        "feature_sha256": feature.feature_sha256,
        "source_metadata": source.canonical_without_hash(),
        "source_provenance_sha256": source.provenance_sha256,
        "geometry": asdict(geometry),
        "domain": asdict(domain),
        "assessment": asdict(assessment),
        "claim_state": decision.state.value,
        "claim_blockers": list(decision.blockers),
        "claim_decision_sha256": decision.decision_sha256,
        "analysis_passport_sha256": passport["passport_sha256"],
        "evidence_graph_sha256": graph.fingerprint_sha256,
        "empirical_kt_source_applicability_claim": False,
        "empirical_kt_value_available": False,
        "empirical_kt_validation_claim": False,
        "experimental_validation_claim": False,
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
        "interpretation_boundary": (
            "NACA TN-2442 is public-domain source metadata with a published tension-fillets investigation scope. "
            "The exact C14 CAD geometry has D/d=1.5 but r/d=0.10, outside the declared approximate r/d upper bound 0.08. "
            "AsterMax therefore blocks the source-applicability claim and does not extrapolate or invent a Kt value. "
            "No digitized NACA factor values are embedded in this study."
        ),
    }
    payload["benchmark_sha256"] = canonical_sha256(payload)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "classification": payload["classification"],
        "D_over_d": geometry.diameter_ratio,
        "r_over_d": geometry.radius_ratio,
        "domain_r_over_d": [domain.radius_ratio_min, domain.radius_ratio_max],
        "assessment": assessment.classification,
        "blockers": list(assessment.blockers),
        "claim_state": decision.state.value,
        "empirical_kt_value_available": False,
        "benchmark_sha256": payload["benchmark_sha256"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
