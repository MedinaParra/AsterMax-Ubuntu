import pytest

from astermax.fea.bounded_stress_concentration import build_stress_concentration_grid
from astermax.fea.empirical_kt_evaluation import (
    EmpiricalKtEvaluationError,
    evaluate_domain_bound_stress_concentration,
)
from astermax.fea.shaft_shoulder import build_shaft_shoulder_geometry
from astermax.fea.stress_concentration_applicability import (
    assess_stress_concentration_applicability,
    build_stress_concentration_applicability_domain,
)
from astermax.fea.stress_concentration_source import build_stress_concentration_source


def _source_grid_domain(radius_max=0.15):
    source = build_stress_concentration_source(
        source_id="C16_DOMAIN_TEST",
        title="Synthetic C16 domain test",
        edition_or_release="1",
        publisher="AsterMax tests",
        locator="test_empirical_kt_evaluation.py",
        source_url="https://example.invalid/c16-domain",
        rights_note="SYNTHETIC_NOT_PHYSICAL",
    )
    grid = build_stress_concentration_grid(
        dataset_id="C16_DOMAIN_GRID",
        factor_name="Kt_SYNTHETIC_NOT_PHYSICAL",
        load_mode="AXIAL_TENSION",
        source_provenance_sha256=source.provenance_sha256,
        diameter_ratios=(1.5, 2.0),
        radius_ratios=(0.05, 0.10, 0.15),
        factors=((101.0, 102.0, 103.0), (201.0, 202.0, 203.0)),
    )
    domain = build_stress_concentration_applicability_domain(
        domain_id="C16_DOMAIN",
        source_provenance_sha256=source.provenance_sha256,
        load_mode="AXIAL_TENSION",
        allowed_diameter_ratios=(1.5, 2.0),
        radius_ratio_min=0.05,
        radius_ratio_max=radius_max,
        source_locator="synthetic C16 domain",
        diameter_ratio_absolute_tolerance=1e-6,
    )
    return source, grid, domain


def test_step_scale_diameter_jitter_snaps_only_to_declared_curve():
    source, grid, domain = _source_grid_domain()
    geometry = build_shaft_shoulder_geometry(
        geometry_id="CAD_JITTER",
        small_diameter_mm=20.0000002,
        large_diameter_mm=30.0000002,
        fillet_radius_mm=1.9999998,
    )
    applicability = assess_stress_concentration_applicability(
        source, domain, geometry, requested_load_mode="AXIAL_TENSION"
    )
    result = evaluate_domain_bound_stress_concentration(grid, applicability, geometry)
    assert applicability.matched_diameter_ratio == 1.5
    assert result.evaluated_diameter_ratio == 1.5
    assert result.diameter_ratio_snap_absolute < 1e-6
    assert 101.9 < result.factor < 102.1
    assert "NO_EXTRAPOLATION" in result.interpolation


def test_undeclared_diameter_curve_cannot_be_interpolated():
    source, grid, domain = _source_grid_domain()
    geometry = build_shaft_shoulder_geometry(
        geometry_id="NO_D_INTERPOLATION",
        small_diameter_mm=20.0,
        large_diameter_mm=34.0,
        fillet_radius_mm=2.0,
    )
    applicability = assess_stress_concentration_applicability(
        source, domain, geometry, requested_load_mode="AXIAL_TENSION"
    )
    assert applicability.applicable is False
    with pytest.raises(EmpiricalKtEvaluationError, match="OUTSIDE_GEOMETRY_DOMAIN"):
        evaluate_domain_bound_stress_concentration(grid, applicability, geometry)


def test_domain_may_allow_radius_but_dataset_still_fails_closed():
    source, grid, domain = _source_grid_domain(radius_max=0.20)
    geometry = build_shaft_shoulder_geometry(
        geometry_id="GRID_RADIUS_LIMIT",
        small_diameter_mm=20.0,
        large_diameter_mm=30.0,
        fillet_radius_mm=3.6,
    )
    applicability = assess_stress_concentration_applicability(
        source, domain, geometry, requested_load_mode="AXIAL_TENSION"
    )
    assert applicability.applicable is True
    with pytest.raises(EmpiricalKtEvaluationError, match="RADIUS_RATIO_OUTSIDE_DATASET"):
        evaluate_domain_bound_stress_concentration(grid, applicability, geometry)
