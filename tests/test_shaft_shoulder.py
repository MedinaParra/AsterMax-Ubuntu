import pytest

from astermax.fea.shaft_shoulder import (
    ShaftShoulderError,
    build_shaft_shoulder_geometry,
    shaft_shoulder_geometry_evidence,
)


def test_shaft_shoulder_ratios_and_hash_are_deterministic():
    g = build_shaft_shoulder_geometry(
        geometry_id="S1",
        small_diameter_mm=80.0,
        large_diameter_mm=100.0,
        fillet_radius_mm=5.0,
    )
    assert g.radial_step_mm == pytest.approx(10.0)
    assert g.diameter_ratio == pytest.approx(1.25)
    assert g.radius_ratio == pytest.approx(0.0625)
    assert g.geometry_sha256 == build_shaft_shoulder_geometry(
        geometry_id="S1",
        small_diameter_mm=80.0,
        large_diameter_mm=100.0,
        fillet_radius_mm=5.0,
    ).geometry_sha256
    assert shaft_shoulder_geometry_evidence(g).claim_grade is True


def test_shaft_shoulder_rejects_inverted_diameters():
    with pytest.raises(ShaftShoulderError, match="LARGE_DIAMETER"):
        build_shaft_shoulder_geometry(
            geometry_id="BAD",
            small_diameter_mm=100.0,
            large_diameter_mm=80.0,
            fillet_radius_mm=2.0,
        )


def test_shaft_shoulder_rejects_radius_larger_than_step():
    with pytest.raises(ShaftShoulderError, match="FILLET_RADIUS"):
        build_shaft_shoulder_geometry(
            geometry_id="BAD",
            small_diameter_mm=80.0,
            large_diameter_mm=100.0,
            fillet_radius_mm=11.0,
        )
