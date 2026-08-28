from __future__ import annotations

from dataclasses import asdict
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
from astermax.fea.analytical_load_case import build_analytical_load_case, build_load_case_witnesses
from astermax.fea.analytical_witness import analytical_section_witness_evidence
from astermax.fea.circular_section import (
    circular_section_applicability_evidence,
    prove_solid_circular_section,
)
from astermax.fea.circular_torsion import circular_torsion_witness_evidence
from astermax.fea.combined_evidence import (
    analytical_load_case_evidence,
    combined_analytical_chain_evidence,
    combined_analytical_claim,
    combined_envelope_evidence,
)
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.load_uncertainty import LoadUncertaintyBounds, bounded_load_uncertainty_envelope
from astermax.fea.persistent_geometry import capture_face_selection, list_face_signatures
from astermax.fea.section_evidence import planar_section_properties, section_properties_evidence


OUT = Path("analytical_circular_shaft_evidence.json")
STEP = Path("analytical_circular_shaft.step")


def _write_fixture() -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("analytical_circular_shaft")
        gmsh.model.occ.addCylinder(0, 0, 0, 40.0, 0, 0, 10.0)
        gmsh.model.occ.synchronize()
        gmsh.write(str(STEP))
    finally:
        gmsh.finalize()


def _end_face() -> int:
    matches = [
        tag for tag, signature in list_face_signatures(STEP)
        if signature.surface_type.strip().lower() == "plane"
        and abs(signature.center_mm[0] - 40.0) <= 1.0e-6
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected one x-max circular end face, got {matches}")
    return matches[0]


def main() -> int:
    _write_fixture()
    selection = capture_face_selection(STEP, _end_face(), "CIRCULAR_SHAFT_X_MAX")
    section = planar_section_properties(STEP, selection)
    applicability = prove_solid_circular_section(STEP, selection)
    load = build_analytical_load_case(
        load_case_id="C2K_VERIFY_LC1",
        selection_id=selection.selection_id,
        section_sha256=section.section_sha256,
        axial_force_n=12000.0,
        moment_u_nmm=150000.0,
        moment_v_nmm=-80000.0,
        torque_nmm=100000.0,
    )
    normal, torsion, envelope = build_load_case_witnesses(section, applicability, load)
    uncertainty = bounded_load_uncertainty_envelope(
        section,
        applicability,
        load,
        LoadUncertaintyBounds(
            axial_force_delta_n=500.0,
            moment_u_delta_nmm=5000.0,
            moment_v_delta_nmm=5000.0,
            torque_delta_nmm=5000.0,
        ),
    )

    context = ContextOfUse(
        context_id="COU_C2K_CIRCULAR_SHAFT_VERIFY",
        engineering_question="Does the exact STEP circular section support a hash-bound independent combined analytical stress witness?",
        intended_decision="Permit this verification benchmark claim only; do not infer industrial validation or ANSYS equivalence.",
        quantities_of_interest=("normal stress", "torsional shear", "von Mises envelope"),
        acceptance_criteria=("circular CAD applicability proven", "section resultants reconstructed", "combined chain complete"),
        consequence_level=ConsequenceLevel.HIGH,
        assumptions=("linear elasticity", "solid circular Saint-Venant torsion", "small deformation section mechanics"),
    )
    graph = EvidenceGraph(context)
    records = {
        "section": section_properties_evidence(section),
        "applicability": circular_section_applicability_evidence(applicability),
        "load": analytical_load_case_evidence(load),
        "normal": analytical_section_witness_evidence(normal),
        "torsion": circular_torsion_witness_evidence(torsion),
        "envelope": combined_envelope_evidence(envelope),
        "chain": combined_analytical_chain_evidence(load, applicability, normal, torsion, envelope),
    }
    for record in records.values():
        graph.add(record)
    graph.link(records["applicability"].evidence_id, records["section"].evidence_id, "USES_SECTION")
    graph.link(records["load"].evidence_id, records["section"].evidence_id, "BOUND_TO_SECTION")
    graph.link(records["normal"].evidence_id, records["section"].evidence_id, "USES_SECTION")
    graph.link(records["torsion"].evidence_id, records["applicability"].evidence_id, "REQUIRES_DOMAIN_PROOF")
    graph.link(records["envelope"].evidence_id, records["normal"].evidence_id, "USES_NORMAL_WITNESS")
    graph.link(records["envelope"].evidence_id, records["torsion"].evidence_id, "USES_TORSION_WITNESS")
    graph.link(records["chain"].evidence_id, records["envelope"].evidence_id, "BINDS_ENVELOPE")
    graph.link(records["chain"].evidence_id, records["load"].evidence_id, "BINDS_LOAD_CASE")

    decision = ClaimEngine.evaluate(combined_analytical_claim(context.context_id), graph)
    if decision.state is not ClaimState.PERMITTED:
        raise RuntimeError(f"combined analytical claim unexpectedly blocked: {decision.blockers}")
    passport = build_analysis_passport(graph, (decision,))

    payload = {
        "schema": "AsterMaxAnalyticalCircularShaftBenchmarkV1",
        "classification": "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT",
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
        "step_path": STEP.name,
        "source_sha256": selection.source_sha256,
        "selection_sha256": selection.selection_sha256,
        "section": asdict(section),
        "circular_applicability": asdict(applicability),
        "load_case": asdict(load),
        "normal_witness": asdict(normal),
        "torsion_witness": asdict(torsion),
        "combined_envelope": asdict(envelope),
        "load_uncertainty_envelope": asdict(uncertainty),
        "claim_state": decision.state.value,
        "claim_decision_sha256": decision.decision_sha256,
        "analysis_passport_sha256": passport["passport_sha256"],
        "evidence_graph_sha256": graph.fingerprint_sha256,
    }
    payload["benchmark_sha256"] = canonical_sha256(payload)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps({
        "classification": payload["classification"],
        "claim_state": payload["claim_state"],
        "radius_mm": applicability.radius_mm,
        "polar_j_mm4": section.polar_i_n_mm4,
        "tau_max_mpa": torsion.tau_max_mpa,
        "max_von_mises_mpa": envelope.max_von_mises_mpa,
        "uncertainty_worst_case_von_mises_mpa": uncertainty.worst_case_max_von_mises_mpa,
        "benchmark_sha256": payload["benchmark_sha256"],
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
