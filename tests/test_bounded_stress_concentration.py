import pytest

from astermax.fea.bounded_stress_concentration import (
    StressConcentrationGridError,
    build_stress_concentration_grid,
    evaluate_stress_concentration,
)
from astermax.fea.shaft_shoulder import build_shaft_shoulder_geometry
from astermax.fea.stress_concentration_source import build_stress_concentration_source


def _source():
    return build_stress_concentration_source(
        source_id="SYNTHETIC_GRID_SOURCE",
        title="Synthetic verification source",
        edition_or_release="1",
        publisher="AsterMax verification",
        locator="synthetic-grid",
        source_url="https://example.invalid/synthetic-grid",
        rights_note="SYNTHETIC_SOFTWARE_VERIFICATION_DATA",
    )


def _grid():
    source = _source()
    return build_stress_concentration_grid(
        dataset_id="SYNTHETIC_KT_GRID",
        factor_name="Kt",
        load_mode="BENDING",
        source_provenance_sha256=source.provenance_sha256,
        diameter_ratios=(1.1, 1.3),
        radius_ratios=(0.02, 0.10),
        factors=((2.0, 1.5), (2.5, 1.8)),
    )


def test_bilinear_interpolation_inside_declared_domain():
    grid = _grid()
    g = build_shaft_shoulder_geometry(
        geometry_id="MID",
        small_diameter_mm=100.0,
        large_diameter_mm=120.0,
        fillet_radius_mm=6.0,
    )
    result = evaluate_stress_concentration(grid, g)
    assert g.diameter_ratio == pytest.approx(1.2)
    assert g.radius_ratio == pytest.approx(0.06)
    assert result.factor == pytest.approx((2.0 + 1.5 + 2.5 + 1.8) / 4.0)
    assert result.interpolation == "BOUNDED_BILINEAR_NO_EXTRAPOLATION"


def test_outside_ratio_domain_fails_closed():
    grid = _grid()
    g = build_shaft_shoulder_geometry(
        geometry_id="OUT",
        small_diameter_mm=100.0,
        large_diameter_mm=140.0,
        fillet_radius_mm=5.0,
    )
    with pytest.raises(StressConcentrationGridError, match="OUT_OF_DOMAIN"):
        evaluate_stress_concentration(grid, g)


def test_grid_rejects_non_monotonic_axes():
    source = _source()
    with pytest.raises(StressConcentrationGridError, match="strictly increasing"):
        build_stress_concentration_grid(
            dataset_id="BAD",
            factor_name="Kt",
            load_mode="BENDING",
            source_provenance_sha256=source.provenance_sha256,
            diameter_ratios=(1.2, 1.1),
            radius_ratios=(0.02, 0.10),
            factors=((2.0, 1.5), (2.5, 1.8)),
        )
