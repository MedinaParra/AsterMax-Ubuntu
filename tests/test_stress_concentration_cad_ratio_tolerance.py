from astermax.fea.shaft_shoulder import build_shaft_shoulder_geometry
from astermax.fea.stress_concentration_applicability import (
    assess_stress_concentration_applicability,
    build_stress_concentration_applicability_domain,
)
from astermax.fea.stress_concentration_source import naca_tn_2442_source_metadata


def _domain(source):
    return build_stress_concentration_applicability_domain(
        domain_id="NACA_TN2442_TENSION_FILLET_SCOPE",
        source_provenance_sha256=source.provenance_sha256,
        load_mode="AXIAL_TENSION",
        allowed_diameter_ratios=(1.5, 2.0),
        radius_ratio_min=0.011,
        radius_ratio_max=0.08,
        source_locator="NACA TN-2442 published investigation scope",
    )


def test_step_scale_ratio_jitter_still_resolves_declared_1p5_curve():
    source = naca_tn_2442_source_metadata()
    domain = _domain(source)
    geometry = build_shaft_shoulder_geometry(
        geometry_id="STEP_JITTER",
        small_diameter_mm=20.0000002,
        large_diameter_mm=30.0000002,
        fillet_radius_mm=1.0,
    )
    result = assess_stress_concentration_applicability(
        source, domain, geometry, requested_load_mode="AXIAL_TENSION"
    )
    assert abs(geometry.diameter_ratio - 1.5) < 1.0e-6
    assert result.diameter_ratio_match is True
    assert result.matched_diameter_ratio == 1.5
    assert result.applicable is True


def test_materially_different_ratio_is_not_absorbed_by_identity_tolerance():
    source = naca_tn_2442_source_metadata()
    domain = _domain(source)
    geometry = build_shaft_shoulder_geometry(
        geometry_id="NOT_IDENTITY",
        small_diameter_mm=20.0,
        large_diameter_mm=30.00004,
        fillet_radius_mm=1.0,
    )
    result = assess_stress_concentration_applicability(
        source, domain, geometry, requested_load_mode="AXIAL_TENSION"
    )
    assert abs(geometry.diameter_ratio - 1.5) > 1.0e-6
    assert result.diameter_ratio_match is False
    assert "DIAMETER_RATIO_OUTSIDE_EMPIRICAL_DOMAIN" in result.blockers
