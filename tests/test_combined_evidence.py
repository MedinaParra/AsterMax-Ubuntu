from dataclasses import replace
import math

import pytest

from astermax.credibility import (
    ClaimEngine,
    ClaimState,
    ConsequenceLevel,
    ContextOfUse,
    EvidenceGraph,
    canonical_sha256,
)
from astermax.fea.analytical_load_case import build_analytical_load_case, build_load_case_witnesses
from astermax.fea.analytical_witness import analytical_section_witness_evidence
from astermax.fea.circular_section import CircularSectionApplicability, circular_section_applicability_evidence
from astermax.fea.circular_torsion import circular_torsion_witness_evidence
from astermax.fea.combined_evidence import (
    CombinedEvidenceError,
    analytical_load_case_evidence,
    combined_analytical_chain_evidence,
    combined_analytical_claim,
    combined_envelope_evidence,
)
from astermax.fea.section_evidence import PlanarSectionProperties, section_properties_evidence


def _fixture():
    area = math.pi * 10.0**2
    i = math.pi * 10.0**4 / 4.0
    payload = {
        "schema": "AsterMaxPlanarSectionPropertiesV1", "selection_id": "S",
        "source_sha256": "1" * 64, "face_signature_sha256": "2" * 64,
        "area_mm2": area, "centroid_mm": (0.0, 0.0, 0.0),
        "normal": (1.0, 0.0, 0.0), "axis_u": (0.0, 1.0, 0.0), "axis_v": (0.0, 0.0, 1.0),
        "i_u_mm4": i, "i_v_mm4": i, "i_uv_mm4": 0.0,
        "principal_i_min_mm4": i, "principal_i_max_mm4": i,
        "polar_i_n_mm4": 2.0 * i, "polar_identity_relative_residual": 0.0, "method": "TEST",
    }
    section = PlanarSectionProperties(**payload, section_sha256=canonical_sha256(payload))
    app_payload = {
        "schema": "AsterMaxCircularSectionApplicabilityV1", "selection_id": "S",
        "source_sha256": section.source_sha256, "section_sha256": section.section_sha256,
        "face_signature_sha256": section.face_signature_sha256, "radius_mm": 10.0,
        "area_mm2": area, "polar_j_mm4": 2.0 * i, "boundary_curve_count": 1,
        "boundary_curve_types": ("Circle",), "inertia_isotropy_relative_residual": 0.0,
        "product_inertia_relative_residual": 0.0, "circular_polar_identity_relative_residual": 0.0,
        "method": "TEST",
    }
    app = CircularSectionApplicability(**app_payload, applicability_sha256=canonical_sha256(app_payload))
    load = build_analytical_load_case(
        load_case_id="LC1", selection_id="S", section_sha256=section.section_sha256,
        axial_force_n=1000.0, moment_u_nmm=2000.0, moment_v_nmm=-3000.0, torque_nmm=4000.0,
    )
    normal, torsion, envelope = build_load_case_witnesses(section, app, load)
    return section, app, load, normal, torsion, envelope


def _context():
    return ContextOfUse(
        context_id="COU_COMBINED_001",
        engineering_question="Are combined circular-section analytical stresses supported by a complete bound evidence chain?",
        intended_decision="Permit the analytical combined-stress verification claim only for this exact section and load case.",
        quantities_of_interest=("normal stress", "torsional shear", "von Mises stress"),
        acceptance_criteria=("all evidence hashes bound", "all analytical resultants reconstructed"),
        consequence_level=ConsequenceLevel.HIGH,
    )


def test_combined_claim_is_blocked_until_chain_is_complete():
    section, app, load, normal, torsion, envelope = _fixture()
    graph = EvidenceGraph(_context())
    records = [
        section_properties_evidence(section),
        circular_section_applicability_evidence(app),
        analytical_load_case_evidence(load),
        analytical_section_witness_evidence(normal),
        circular_torsion_witness_evidence(torsion),
        combined_envelope_evidence(envelope),
    ]
    for record in records:
        graph.add(record)
    blocked = ClaimEngine.evaluate(combined_analytical_claim(graph.context.context_id), graph)
    assert blocked.state is ClaimState.BLOCKED
    assert any("ANALYTICAL_COMBINED_CHAIN" in blocker for blocker in blocked.blockers)

    graph.add(combined_analytical_chain_evidence(load, app, normal, torsion, envelope))
    permitted = ClaimEngine.evaluate(combined_analytical_claim(graph.context.context_id), graph)
    assert permitted.state is ClaimState.PERMITTED


def test_combined_chain_rejects_cross_section_torsion_witness():
    _, app, load, normal, torsion, envelope = _fixture()
    bad = replace(torsion, section_sha256="9" * 64)
    with pytest.raises(CombinedEvidenceError, match="SECTION_SHA_MISMATCH"):
        combined_analytical_chain_evidence(load, app, normal, bad, envelope)
