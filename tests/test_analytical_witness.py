from pathlib import Path

import pytest

from astermax.credibility import (
    ClaimEngine,
    ClaimState,
    ConsequenceLevel,
    ContextOfUse,
    EvidenceGraph,
    canonical_sha256,
)
from astermax.fea.analytical_witness import (
    AnalyticalWitnessError,
    analytical_section_chain_evidence,
    analytical_section_claim,
    analytical_section_witness_evidence,
    build_linear_normal_stress_witness,
    normal_stress_mpa,
)
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.persistent_geometry import (
    capture_face_selection,
    list_face_signatures,
    resolve_face_selection,
)
from astermax.fea.section_evidence import (
    PlanarSectionProperties,
    persistent_face_identity_evidence,
    planar_section_properties,
    section_properties_evidence,
)


def _write_box(path: Path):
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("box")
        gmsh.model.occ.addBox(0, 0, 0, 100, 20, 10)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def _x_max_face(path: Path) -> int:
    matches = []
    for tag, signature in list_face_signatures(path):
        if signature.surface_type.strip().lower() != "plane":
            continue
        if signature.center_mm[0] == pytest.approx(100.0, abs=1e-6):
            matches.append(tag)
    assert len(matches) == 1
    return matches[0]


def _synthetic_section(*, selection_id="SYNTHETIC_SECTION", i_u=5000.0, i_v=8000.0, i_uv=2000.0):
    payload = {
        "schema": "AsterMaxPlanarSectionPropertiesV1",
        "selection_id": selection_id,
        "source_sha256": "1" * 64,
        "face_signature_sha256": "2" * 64,
        "area_mm2": 400.0,
        "centroid_mm": (0.0, 0.0, 0.0),
        "normal": (0.0, 0.0, 1.0),
        "axis_u": (1.0, 0.0, 0.0),
        "axis_v": (0.0, 1.0, 0.0),
        "i_u_mm4": float(i_u),
        "i_v_mm4": float(i_v),
        "i_uv_mm4": float(i_uv),
        "principal_i_min_mm4": 0.0,
        "principal_i_max_mm4": 0.0,
        "polar_i_n_mm4": float(i_u + i_v),
        "polar_identity_relative_residual": 0.0,
        "method": "SYNTHETIC_TEST_SECTION",
    }
    return PlanarSectionProperties(**payload, section_sha256=canonical_sha256(payload))


def test_general_biaxial_witness_recovers_known_nonprincipal_field():
    section = _synthetic_section()
    expected_sigma0 = 50.0
    expected_a = 0.2
    expected_b = -0.1
    n_force = expected_sigma0 * section.area_mm2
    m_u = expected_a * section.i_uv_mm4 + expected_b * section.i_u_mm4
    m_v = -(expected_a * section.i_v_mm4 + expected_b * section.i_uv_mm4)

    witness = build_linear_normal_stress_witness(
        section,
        axial_force_n=n_force,
        moment_u_nmm=m_u,
        moment_v_nmm=m_v,
    )

    assert witness.sigma0_mpa == pytest.approx(expected_sigma0, rel=1e-14)
    assert witness.gradient_u_mpa_per_mm == pytest.approx(expected_a, rel=1e-14)
    assert witness.gradient_v_mpa_per_mm == pytest.approx(expected_b, rel=1e-14)
    assert witness.reconstructed_axial_force_n == pytest.approx(n_force, abs=1e-10)
    assert witness.reconstructed_moment_u_nmm == pytest.approx(m_u, abs=1e-10)
    assert witness.reconstructed_moment_v_nmm == pytest.approx(m_v, abs=1e-10)
    assert witness.max_relative_resultant_residual <= 1e-14
    assert normal_stress_mpa(witness, u_mm=3.0, v_mm=-4.0) == pytest.approx(51.0)


def test_cad_rectangle_axial_and_bending_use_c1_section_properties(tmp_path):
    path = tmp_path / "box.step"
    _write_box(path)
    selection = capture_face_selection(path, _x_max_face(path), "C2_SECTION_X_MAX")
    section = planar_section_properties(path, selection)

    n_force = 20000.0
    m_u = 12500.0
    m_v = -7500.0
    witness = build_linear_normal_stress_witness(
        section,
        axial_force_n=n_force,
        moment_u_nmm=m_u,
        moment_v_nmm=m_v,
    )

    assert witness.section_sha256 == section.section_sha256
    assert witness.sigma0_mpa == pytest.approx(n_force / section.area_mm2, rel=1e-12)
    assert witness.reconstructed_axial_force_n == pytest.approx(n_force, abs=1e-9)
    assert witness.reconstructed_moment_u_nmm == pytest.approx(m_u, abs=1e-9)
    assert witness.reconstructed_moment_v_nmm == pytest.approx(m_v, abs=1e-9)
    if abs(section.i_uv_mm4) <= 1e-8:
        assert witness.gradient_u_mpa_per_mm == pytest.approx(-m_v / section.i_v_mm4, rel=1e-10)
        assert witness.gradient_v_mpa_per_mm == pytest.approx(m_u / section.i_u_mm4, rel=1e-10)


def test_singular_or_near_singular_section_is_rejected():
    section = _synthetic_section(i_u=100.0, i_v=400.0, i_uv=200.0)
    with pytest.raises(AnalyticalWitnessError, match="SINGULAR_INERTIA"):
        build_linear_normal_stress_witness(
            section,
            axial_force_n=1.0,
            moment_u_nmm=2.0,
            moment_v_nmm=3.0,
        )


def test_nonfinite_load_is_rejected():
    section = _synthetic_section()
    with pytest.raises(AnalyticalWitnessError, match="must be finite"):
        build_linear_normal_stress_witness(
            section,
            axial_force_n=float("nan"),
            moment_u_nmm=0.0,
            moment_v_nmm=0.0,
        )


def test_c2_witness_feeds_c0_claim_engine_only_with_bound_cad_chain(tmp_path):
    path = tmp_path / "box.step"
    _write_box(path)
    selection = capture_face_selection(path, _x_max_face(path), "C2_CLAIM_SECTION")
    resolution = resolve_face_selection(path, selection)
    section = planar_section_properties(path, selection)
    witness = build_linear_normal_stress_witness(
        section,
        axial_force_n=10000.0,
        moment_u_nmm=5000.0,
        moment_v_nmm=-3000.0,
    )

    context = ContextOfUse(
        context_id="COU_C2_SECTION_001",
        engineering_question="Does an independent analytical stress field reconstruct the declared section resultants?",
        intended_decision="Permit this analytical section witness as supporting evidence, not as industrial validation.",
        quantities_of_interest=("normal stress", "axial force", "biaxial bending moments"),
        acceptance_criteria=(
            "persistent CAD face identity verified",
            "CAD section integrals verified",
            "section resultants reconstructed within deterministic tolerance",
            "analytical witness bound to the exact CAD section payload",
        ),
        consequence_level=ConsequenceLevel.HIGH,
    )
    claim = analytical_section_claim(context.context_id)

    face_evidence = persistent_face_identity_evidence(selection, resolution)
    section_evidence = section_properties_evidence(section)
    witness_evidence = analytical_section_witness_evidence(witness)

    incomplete = EvidenceGraph(context)
    incomplete.add(face_evidence)
    incomplete.add(section_evidence)
    incomplete.add(witness_evidence)
    incomplete.link(section_evidence.evidence_id, face_evidence.evidence_id, "DERIVED_FROM")
    incomplete.link(witness_evidence.evidence_id, section_evidence.evidence_id, "USES_SECTION")
    blocked = ClaimEngine.evaluate(claim, incomplete)
    assert blocked.state is ClaimState.BLOCKED
    assert any("ANALYTICAL_SECTION_CHAIN" in item for item in blocked.blockers)

    chain_evidence = analytical_section_chain_evidence(
        face_evidence,
        section_evidence,
        witness_evidence,
    )
    graph = EvidenceGraph(context)
    for record in (face_evidence, section_evidence, witness_evidence, chain_evidence):
        graph.add(record)
    graph.link(section_evidence.evidence_id, face_evidence.evidence_id, "DERIVED_FROM")
    graph.link(witness_evidence.evidence_id, section_evidence.evidence_id, "USES_SECTION")
    graph.link(chain_evidence.evidence_id, face_evidence.evidence_id, "BINDS_FACE")
    graph.link(chain_evidence.evidence_id, section_evidence.evidence_id, "BINDS_SECTION")
    graph.link(chain_evidence.evidence_id, witness_evidence.evidence_id, "BINDS_WITNESS")

    decision = ClaimEngine.evaluate(claim, graph)
    assert decision.state is ClaimState.PERMITTED
    assert set(decision.evidence_ids) == {
        face_evidence.evidence_id,
        section_evidence.evidence_id,
        witness_evidence.evidence_id,
        chain_evidence.evidence_id,
    }


def test_chain_rejects_witness_from_different_section(tmp_path):
    path = tmp_path / "box.step"
    _write_box(path)
    selection = capture_face_selection(path, _x_max_face(path), "C2_BINDING_SECTION")
    resolution = resolve_face_selection(path, selection)
    section = planar_section_properties(path, selection)
    face_evidence = persistent_face_identity_evidence(selection, resolution)
    section_evidence = section_properties_evidence(section)

    other_section = _synthetic_section(selection_id=selection.selection_id)
    other_witness = build_linear_normal_stress_witness(
        other_section,
        axial_force_n=100.0,
        moment_u_nmm=20.0,
        moment_v_nmm=30.0,
    )
    other_witness_evidence = analytical_section_witness_evidence(other_witness)
    with pytest.raises(AnalyticalWitnessError, match="SECTION_SHA_MISMATCH"):
        analytical_section_chain_evidence(
            face_evidence,
            section_evidence,
            other_witness_evidence,
        )


def test_witness_hash_is_deterministic_for_same_section_and_loads():
    section = _synthetic_section()
    first = build_linear_normal_stress_witness(
        section,
        axial_force_n=1234.5,
        moment_u_nmm=-678.9,
        moment_v_nmm=456.7,
    )
    second = build_linear_normal_stress_witness(
        section,
        axial_force_n=1234.5,
        moment_u_nmm=-678.9,
        moment_v_nmm=456.7,
    )
    assert first == second
    assert first.witness_sha256 == second.witness_sha256
