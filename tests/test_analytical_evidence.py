from __future__ import annotations

from math import pi, sqrt
from pathlib import Path

import pytest

from astermax.credibility import (
    ClaimDefinition,
    ClaimEngine,
    ClaimRequirement,
    ClaimState,
    ConsequenceLevel,
    ContextOfUse,
    EvidenceGraph,
    EvidenceSource,
    EvidenceStatus,
)
from astermax.fea.analytical_evidence import (
    AnalyticalEvidenceError,
    analytical_stress_evidence,
    axial_normal_stress_mpa,
    circular_torsion_max_shear_mpa,
    circular_torsion_shear_at_radius_mpa,
    combined_principal_bending_circular_torsion_witness,
    principal_bending_normal_stress_mpa,
    von_mises_from_normal_and_shear_mpa,
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


def _section(*, area: float, iu: float, iv: float, iuv: float, polar: float, sha: str = "a" * 64) -> PlanarSectionProperties:
    return PlanarSectionProperties(
        schema="AsterMaxPlanarSectionPropertiesV1",
        selection_id="fixture.section",
        source_sha256="b" * 64,
        face_signature_sha256="c" * 64,
        area_mm2=area,
        centroid_mm=(0.0, 0.0, 0.0),
        normal=(1.0, 0.0, 0.0),
        axis_u=(0.0, 1.0, 0.0),
        axis_v=(0.0, 0.0, 1.0),
        i_u_mm4=iu,
        i_v_mm4=iv,
        i_uv_mm4=iuv,
        principal_i_min_mm4=min(iu, iv),
        principal_i_max_mm4=max(iu, iv),
        polar_i_n_mm4=polar,
        polar_identity_relative_residual=0.0,
        method="INDEPENDENT_CLOSED_FORM_TEST_FIXTURE",
        section_sha256=sha,
    )


def _circle(radius_mm: float = 10.0) -> PlanarSectionProperties:
    area = pi * radius_mm**2
    inertia = pi * radius_mm**4 / 4.0
    return _section(area=area, iu=inertia, iv=inertia, iuv=0.0, polar=2.0 * inertia)


def _write_x_cylinder(path: Path, *, length_mm: float = 40.0, radius_mm: float = 10.0) -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c2_cylinder")
        gmsh.model.occ.addCylinder(0.0, 0.0, 0.0, length_mm, 0.0, 0.0, radius_mm)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def _planar_face_at_x(path: Path, x_mm: float) -> int:
    matches = [
        tag
        for tag, signature in list_face_signatures(path)
        if signature.surface_type.strip().lower() == "plane"
        and signature.center_mm[0] == pytest.approx(x_mm, abs=1.0e-6)
    ]
    assert len(matches) == 1
    return matches[0]


def test_axial_stress_uses_n_mm_mpa_contract() -> None:
    assert axial_normal_stress_mpa(10_000.0, 200.0) == pytest.approx(50.0)


def test_principal_bending_matches_rectangle_closed_form() -> None:
    sigma = principal_bending_normal_stress_mpa(
        moment_u_nmm=100_000.0,
        moment_v_nmm=0.0,
        u_mm=0.0,
        v_mm=5.0,
        i_u_mm4=20.0 * 10.0**3 / 12.0,
        i_v_mm4=10.0 * 20.0**3 / 12.0,
        i_uv_mm4=0.0,
    )
    assert sigma == pytest.approx(-300.0)


def test_bending_fails_closed_when_axes_are_not_principal() -> None:
    with pytest.raises(AnalyticalEvidenceError, match="REQUIRES_PRINCIPAL_AXES"):
        principal_bending_normal_stress_mpa(
            moment_u_nmm=1.0,
            moment_v_nmm=2.0,
            u_mm=3.0,
            v_mm=4.0,
            i_u_mm4=100.0,
            i_v_mm4=200.0,
            i_uv_mm4=1.0,
        )


def test_solid_circle_torsion_matches_closed_form() -> None:
    section = _circle(10.0)
    torque = 100_000.0
    tau, residual = circular_torsion_max_shear_mpa(torque, section)
    expected = 2.0 * torque / (pi * 10.0**3)
    assert residual < 1.0e-14
    assert tau == pytest.approx(expected, rel=1.0e-13)


def test_circular_torsion_is_pointwise_not_always_maximum() -> None:
    section = _circle(10.0)
    torque = 100_000.0
    tau_center, _ = circular_torsion_shear_at_radius_mpa(torque, section, 0.0)
    tau_half, _ = circular_torsion_shear_at_radius_mpa(torque, section, 5.0)
    tau_max, _ = circular_torsion_max_shear_mpa(torque, section)
    assert tau_center == pytest.approx(0.0)
    assert tau_half == pytest.approx(0.5 * tau_max)


def test_torsion_rejects_point_outside_circle() -> None:
    with pytest.raises(AnalyticalEvidenceError, match="POINT_OUTSIDE_SECTION"):
        circular_torsion_shear_at_radius_mpa(10.0, _circle(10.0), 10.1)


def test_rectangular_section_is_rejected_by_circular_torsion_witness() -> None:
    b = 20.0
    h = 10.0
    rectangle = _section(
        area=b * h,
        iu=b * h**3 / 12.0,
        iv=h * b**3 / 12.0,
        iuv=0.0,
        polar=b * h**3 / 12.0 + h * b**3 / 12.0,
    )
    with pytest.raises(AnalyticalEvidenceError, match="CIRCULAR_TORSION_OUT_OF_DOMAIN"):
        circular_torsion_max_shear_mpa(100_000.0, rectangle)


def test_von_mises_combination_matches_independent_formula() -> None:
    assert von_mises_from_normal_and_shear_mpa(80.0, 30.0) == pytest.approx(
        sqrt(80.0**2 + 3.0 * 30.0**2)
    )


def test_combined_witness_is_deterministic_and_claim_grade() -> None:
    section = _circle(10.0)
    kwargs = dict(
        axial_force_n=10_000.0,
        moment_u_nmm=50_000.0,
        moment_v_nmm=0.0,
        u_mm=0.0,
        v_mm=10.0,
        torque_nmm=100_000.0,
    )
    first = combined_principal_bending_circular_torsion_witness(section, **kwargs)
    second = combined_principal_bending_circular_torsion_witness(section, **kwargs)

    expected_axial = 10_000.0 / (pi * 10.0**2)
    expected_bending = -(50_000.0 * 10.0) / (pi * 10.0**4 / 4.0)
    expected_tau = 2.0 * 100_000.0 / (pi * 10.0**3)
    expected_vm = sqrt((expected_axial + expected_bending) ** 2 + 3.0 * expected_tau**2)

    assert first.witness_sha256 == second.witness_sha256
    assert first.normal_stress_mpa == pytest.approx(expected_axial + expected_bending)
    assert first.shear_stress_mpa == pytest.approx(expected_tau)
    assert first.von_mises_mpa == pytest.approx(expected_vm)
    assert first.inputs["radial_position_mm"] == pytest.approx(10.0)

    evidence = analytical_stress_evidence(first)
    assert evidence.status is EvidenceStatus.VERIFIED
    assert evidence.source is EvidenceSource.ANALYTICAL_WITNESS
    assert evidence.payload_sha256 == first.witness_sha256
    assert evidence.metadata["ansys_equivalence"] is False
    assert evidence.metadata["industrial_validation"] is False


def test_exact_step_section_can_feed_analytical_claim_chain(tmp_path: Path) -> None:
    path = tmp_path / "c2_cylinder.step"
    _write_x_cylinder(path, length_mm=40.0, radius_mm=10.0)
    selection = capture_face_selection(path, _planar_face_at_x(path, 40.0), "C2_SECTION")
    resolution = resolve_face_selection(path, selection)
    section = planar_section_properties(path, selection)

    witness = combined_principal_bending_circular_torsion_witness(
        section,
        axial_force_n=0.0,
        moment_u_nmm=0.0,
        moment_v_nmm=0.0,
        u_mm=0.0,
        v_mm=10.0,
        torque_nmm=100_000.0,
    )
    expected_tau = 2.0 * 100_000.0 / (pi * 10.0**3)
    assert section.area_mm2 == pytest.approx(pi * 10.0**2, rel=1.0e-9)
    assert witness.shear_stress_mpa == pytest.approx(expected_tau, rel=1.0e-8)
    assert witness.von_mises_mpa == pytest.approx(sqrt(3.0) * expected_tau, rel=1.0e-8)

    graph = EvidenceGraph(
        ContextOfUse(
            context_id="COU_C2_CIRCLE_001",
            engineering_question="Is the analytical circular-shaft stress witness traceable to the exact CAD section?",
            intended_decision="Permit this bounded analytical witness as corroborating evidence for later FEA comparison.",
            quantities_of_interest=("torsional shear stress", "von Mises stress"),
            acceptance_criteria=("exact CAD section verified", "closed-form witness verified"),
            consequence_level=ConsequenceLevel.HIGH,
        )
    )
    face_record = persistent_face_identity_evidence(selection, resolution)
    section_record = section_properties_evidence(section)
    analytical_record = analytical_stress_evidence(witness)
    graph.add(face_record)
    graph.add(section_record)
    graph.add(analytical_record)
    graph.link(section_record.evidence_id, face_record.evidence_id, "DERIVED_FROM")
    graph.link(analytical_record.evidence_id, section_record.evidence_id, "DERIVED_FROM")

    claim = ClaimDefinition(
        claim_id="CLAIM_C2_ANALYTICAL_WITNESS_READY",
        context_id="COU_C2_CIRCLE_001",
        statement="This bounded analytical stress result is traceable to the exact verified CAD section.",
        requirements=(
            ClaimRequirement("CAD_FACE_IDENTITY", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
            ClaimRequirement("CAD_SECTION_PROPERTIES", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
            ClaimRequirement("ANALYTICAL_STRESS_WITNESS", allowed_sources=(EvidenceSource.ANALYTICAL_WITNESS,)),
        ),
    )
    decision = ClaimEngine.evaluate(claim, graph)
    assert decision.state is ClaimState.PERMITTED
    assert analytical_record.evidence_id in decision.evidence_ids
