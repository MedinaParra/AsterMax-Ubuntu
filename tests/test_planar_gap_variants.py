import pytest

from astermax.geometry.planar_gap import (
    GapVariantEvidenceClass,
    GapVariantManifestV1,
    GapVariantRecordV1,
    PlanarInterfaceEvidenceV1,
    PlanarInterfaceError,
    PlanarSegmentSupportV1,
    _derive_outward_normal,
    translation_for_gap,
)


def interface_fixture() -> PlanarInterfaceEvidenceV1:
    supports = [
        PlanarSegmentSupportV1(
            solid_index_1based=index,
            face_index_1based=face,
            support_area_mm2=22840.35781787,
        )
        for index, face in [(1, 13), (2, 41), (4, 8), (5, 26), (6, 33)]
    ]
    total = sum(item.support_area_mm2 for item in supports)
    return PlanarInterfaceEvidenceV1(
        source_sha256="a" * 64,
        source_byte_size=3117839,
        plane_x_mm=-951.0,
        outward_normal_xyz=(-1.0, 0.0, 0.0),
        hub_solid_index_1based=3,
        hub_face_index_1based=112,
        segment_supports=supports,
        support_area_total_mm2=total,
        support_area_mean_per_segment_mm2=total / 5.0,
        unique_shared_plane=True,
        nominal_step_gap_mm=0.0,
    )


def test_outward_normal_points_from_hub_toward_segment_side() -> None:
    normal = _derive_outward_normal(
        plane_x_mm=-951.0,
        hub_center_x_mm=-873.6,
        segment_center_x_values_mm=[-952.5] * 5,
    )
    assert normal == (-1.0, 0.0, 0.0)


def test_outward_normal_rejects_segments_on_both_sides() -> None:
    with pytest.raises(PlanarInterfaceError, match="consistently on one side"):
        _derive_outward_normal(
            plane_x_mm=-951.0,
            hub_center_x_mm=-873.6,
            segment_center_x_values_mm=[-952.5, -950.0],
        )


def test_translation_for_measured_gap_is_axial_and_outward() -> None:
    interface = interface_fixture()
    assert translation_for_gap(interface, 0.10) == (-0.10, 0.0, 0.0)
    assert translation_for_gap(interface, 0.40) == (-0.40, 0.0, 0.0)


def test_translation_rejects_zero_or_negative_gap() -> None:
    interface = interface_fixture()
    with pytest.raises(ValueError, match="positive separation"):
        translation_for_gap(interface, 0.0)
    with pytest.raises(ValueError, match="positive separation"):
        translation_for_gap(interface, -0.1)


def test_manifest_keeps_measured_and_derived_evidence_distinct() -> None:
    interface = interface_fixture()
    manifest = GapVariantManifestV1(
        source_sha256=interface.source_sha256,
        source_byte_size=interface.source_byte_size,
        interface=interface,
        variants=[
            GapVariantRecordV1(
                scenario_id="GAP_MIN_MEASURED",
                gap_mm=0.10,
                evidence_class=GapVariantEvidenceClass.MEASURED_ENDPOINT,
                translation_xyz_mm=(-0.10, 0.0, 0.0),
                output_file="min.step",
                output_sha256="b" * 64,
                output_byte_size=100,
                solid_count=6,
            ),
            GapVariantRecordV1(
                scenario_id="GAP_MID_DERIVED",
                gap_mm=0.25,
                evidence_class=GapVariantEvidenceClass.DERIVED_SENSITIVITY,
                translation_xyz_mm=(-0.25, 0.0, 0.0),
                output_file="mid.step",
                output_sha256="c" * 64,
                output_byte_size=100,
                solid_count=6,
            ),
            GapVariantRecordV1(
                scenario_id="GAP_MAX_MEASURED",
                gap_mm=0.40,
                evidence_class=GapVariantEvidenceClass.MEASURED_ENDPOINT,
                translation_xyz_mm=(-0.40, 0.0, 0.0),
                output_file="max.step",
                output_sha256="d" * 64,
                output_byte_size=100,
                solid_count=6,
            ),
        ],
    )
    assert manifest.fea is False
    assert manifest.solver_result_claimed is False
    assert manifest.cad_bytes_committed is False
    assert manifest.variants[1].evidence_class == GapVariantEvidenceClass.DERIVED_SENSITIVITY


def test_interface_fixture_encodes_exact_five_segment_supports() -> None:
    interface = interface_fixture()
    assert interface.hub_face_index_1based == 112
    assert [item.face_index_1based for item in interface.segment_supports] == [13, 41, 8, 26, 33]
    assert interface.support_area_mean_per_segment_mm2 == pytest.approx(22840.35781787)
