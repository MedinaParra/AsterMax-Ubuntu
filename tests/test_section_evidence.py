import math
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
)
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.persistent_geometry import (
    PersistentGeometryError,
    capture_face_selection,
    list_face_signatures,
    resolve_face_selection,
)
from astermax.fea.section_evidence import (
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


def _write_x_cylinder(path: Path, *, length=40.0, radius=10.0):
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("cylinder")
        gmsh.model.occ.addCylinder(0, 0, 0, length, 0, 0, radius)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def _face_by_center_x(path: Path, x: float, *, planar_only=True):
    matches = []
    for tag, sig in list_face_signatures(path):
        if planar_only and sig.surface_type.strip().lower() != "plane":
            continue
        if sig.center_mm[0] == pytest.approx(x, abs=1e-6):
            matches.append(tag)
    assert len(matches) == 1
    return matches[0]


def test_rectangular_end_face_section_integrals_match_closed_form(tmp_path):
    path = tmp_path / "box.step"
    _write_box(path)
    selection = capture_face_selection(path, _face_by_center_x(path, 100.0), "SECTION_X_MAX")
    section = planar_section_properties(path, selection)

    assert section.area_mm2 == pytest.approx(200.0, rel=1e-10)
    assert section.centroid_mm == pytest.approx((100.0, 10.0, 5.0), abs=1e-6)
    expected = sorted((10.0 * 20.0**3 / 12.0, 20.0 * 10.0**3 / 12.0))
    actual = sorted((section.principal_i_min_mm4, section.principal_i_max_mm4))
    assert actual == pytest.approx(expected, rel=1e-9, abs=1e-8)
    assert section.i_uv_mm4 == pytest.approx(0.0, abs=1e-8)
    assert section.polar_i_n_mm4 == pytest.approx(sum(expected), rel=1e-9)
    assert section.polar_identity_relative_residual <= 1e-12


def test_circular_end_face_section_integrals_match_closed_form(tmp_path):
    path = tmp_path / "cylinder.step"
    _write_x_cylinder(path, length=40.0, radius=10.0)
    selection = capture_face_selection(path, _face_by_center_x(path, 40.0), "CIRCULAR_SECTION")
    section = planar_section_properties(path, selection)

    expected_area = math.pi * 10.0**2
    expected_i = math.pi * 10.0**4 / 4.0
    assert section.area_mm2 == pytest.approx(expected_area, rel=1e-9)
    assert section.principal_i_min_mm4 == pytest.approx(expected_i, rel=1e-8)
    assert section.principal_i_max_mm4 == pytest.approx(expected_i, rel=1e-8)
    assert section.i_uv_mm4 == pytest.approx(0.0, abs=1e-7)


def test_curved_cylinder_face_is_out_of_domain_for_planar_section_witness(tmp_path):
    path = tmp_path / "cylinder.step"
    _write_x_cylinder(path)
    curved = [(tag, sig) for tag, sig in list_face_signatures(path) if sig.surface_type.strip().lower() != "plane"]
    assert len(curved) == 1
    selection = capture_face_selection(path, curved[0][0], "CURVED_WALL")
    with pytest.raises(PersistentGeometryError, match="SECTION_WITNESS_OUT_OF_DOMAIN"):
        planar_section_properties(path, selection)


def test_section_and_face_identity_feed_c0_claim_engine(tmp_path):
    path = tmp_path / "box.step"
    _write_box(path)
    selection = capture_face_selection(path, _face_by_center_x(path, 100.0), "SECTION_X_MAX")
    resolution = resolve_face_selection(path, selection)
    section = planar_section_properties(path, selection)

    graph = EvidenceGraph(
        ContextOfUse(
            context_id="COU_SECTION_001",
            engineering_question="Are section properties independently known from CAD?",
            intended_decision="Permit analytical mechanics witnesses to use this section.",
            quantities_of_interest=("area", "second moments"),
            acceptance_criteria=("persistent face identity verified", "CAD section properties verified"),
            consequence_level=ConsequenceLevel.HIGH,
        )
    )
    face_evidence = persistent_face_identity_evidence(selection, resolution)
    section_evidence = section_properties_evidence(section)
    graph.add(face_evidence)
    graph.add(section_evidence)
    graph.link(section_evidence.evidence_id, face_evidence.evidence_id, "DERIVED_FROM")

    claim = ClaimDefinition(
        claim_id="CLAIM_CAD_SECTION_READY",
        context_id="COU_SECTION_001",
        statement="The resolved CAD face is suitable as verified geometric input to analytical section mechanics.",
        requirements=(
            ClaimRequirement("CAD_FACE_IDENTITY", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
            ClaimRequirement("CAD_SECTION_PROPERTIES", allowed_sources=(EvidenceSource.DETERMINISTIC_CHECK,)),
        ),
    )
    decision = ClaimEngine.evaluate(claim, graph)
    assert decision.state is ClaimState.PERMITTED
    assert set(decision.evidence_ids) == {face_evidence.evidence_id, section_evidence.evidence_id}
