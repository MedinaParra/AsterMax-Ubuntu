from __future__ import annotations

import math

import pytest

from astermax.fea.far_field_applicability import (
    FarFieldApplicabilityError,
    distance_ratio_requirement_satisfied,
)


def test_exact_nominal_three_quarter_diameter_passes_with_occ_scale_noise() -> None:
    assert distance_ratio_requirement_satisfied(
        distance_mm=15.0,
        diameter_mm=20.0000002,
        minimum_distance_over_diameter=0.75,
        geometry_relative_tolerance=1.0e-8,
    )


def test_material_distance_violation_is_not_hidden_by_geometry_tolerance() -> None:
    assert not distance_ratio_requirement_satisfied(
        distance_mm=14.999,
        diameter_mm=20.0000002,
        minimum_distance_over_diameter=0.75,
        geometry_relative_tolerance=1.0e-8,
    )


def test_zero_tolerance_preserves_strict_comparison() -> None:
    assert not distance_ratio_requirement_satisfied(
        distance_mm=15.0,
        diameter_mm=20.0000002,
        minimum_distance_over_diameter=0.75,
        geometry_relative_tolerance=0.0,
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(distance_mm=-1.0, diameter_mm=20.0, minimum_distance_over_diameter=0.75),
        dict(distance_mm=15.0, diameter_mm=0.0, minimum_distance_over_diameter=0.75),
        dict(distance_mm=15.0, diameter_mm=20.0, minimum_distance_over_diameter=-0.1),
        dict(distance_mm=15.0, diameter_mm=20.0, minimum_distance_over_diameter=0.75, geometry_relative_tolerance=-1e-8),
        dict(distance_mm=math.nan, diameter_mm=20.0, minimum_distance_over_diameter=0.75),
    ],
)
def test_invalid_applicability_inputs_fail_closed(kwargs) -> None:
    with pytest.raises(FarFieldApplicabilityError):
        distance_ratio_requirement_satisfied(**kwargs)
