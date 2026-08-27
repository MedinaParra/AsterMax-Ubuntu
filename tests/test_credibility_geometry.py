import pytest

from astermax.credibility.geometry import (
    CadArtifact,
    FaceMatchPolicy,
    FaceSignature,
    SectionProperties,
    cad_artifact_evidence,
    persistent_face_evidence,
    resolve_persistent_face,
    section_properties_evidence,
)


CAD_SHA = "1" * 64


def _face(*, x=0.0, area=200.0):
    return FaceSignature(
        surface_type="PLANE",
        area_mm2=area,
        centroid_mm=(x, 5.0, 2.0),
        normal=(1.0, 0.0, 0.0),
        bbox_mm=(x, 0.0, 0.0, x, 10.0, 4.0),
        edge_count=4,
    )


def test_cad_artifact_is_step_mm_and_has_stable_identity():
    a = CadArtifact(CAD_SHA, length_unit="mm", format="stp")
    b = CadArtifact(CAD_SHA, length_unit="mm", format="STEP")
    assert a.format == "STEP"
    assert a.identity_sha256 == b.identity_sha256
    assert cad_artifact_evidence("cad.step", a).claim_grade


def test_non_mm_cad_fails_closed():
    with pytest.raises(ValueError, match="millimetre"):
        CadArtifact(CAD_SHA, length_unit="m")


def test_persistent_face_resolves_unique_geometric_match_not_list_position():
    reference = _face(x=0.0)
    wrong = _face(x=100.0)
    resolved = resolve_persistent_face(reference, [wrong, reference])
    assert resolved.fingerprint_sha256 == reference.fingerprint_sha256
    evidence = persistent_face_evidence("face.support", CadArtifact(CAD_SHA), resolved)
    assert evidence.metadata["cad_sha256"] == CAD_SHA
    assert evidence.payload_sha256 == reference.fingerprint_sha256


def test_persistent_face_ambiguity_fails_closed():
    reference = _face()
    nearly_same = FaceSignature(
        surface_type="PLANE",
        area_mm2=200.0,
        centroid_mm=(5e-7, 5.0, 2.0),
        normal=(1.0, 0.0, 0.0),
        bbox_mm=(5e-7, 0.0, 0.0, 5e-7, 10.0, 4.0),
        edge_count=4,
    )
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_persistent_face(reference, [reference, nearly_same], FaceMatchPolicy())


def test_persistent_face_missing_after_geometry_change_fails_closed():
    reference = _face()
    changed = _face(area=220.0)
    with pytest.raises(ValueError, match="could not be resolved"):
        resolve_persistent_face(reference, [changed])


def test_section_properties_create_claim_grade_cad_derived_evidence():
    section = SectionProperties(
        area_mm2=200.0,
        centroid_mm=(50.0, 0.0, 0.0),
        ixx_mm4=1666.6666666667,
        iyy_mm4=26666.666666667,
        ixy_mm4=0.0,
        section_normal=(1.0, 0.0, 0.0),
    )
    evidence = section_properties_evidence("section.root", CadArtifact(CAD_SHA), section)
    assert evidence.claim_grade
    assert evidence.kind == "CAD_SECTION_PROPERTIES"
    assert evidence.metadata["unit"] == "mm"
    assert evidence.metadata["section"]["area_mm2"] == pytest.approx(200.0)


def test_invalid_section_inertia_tensor_fails_closed():
    with pytest.raises(ValueError, match="positive definite"):
        SectionProperties(
            area_mm2=10.0,
            centroid_mm=(0.0, 0.0, 0.0),
            ixx_mm4=1.0,
            iyy_mm4=1.0,
            ixy_mm4=2.0,
            section_normal=(1.0, 0.0, 0.0),
        )
