from __future__ import annotations

import math


class FarFieldApplicabilityError(ValueError):
    pass


def distance_ratio_requirement_satisfied(
    *,
    distance_mm: float,
    diameter_mm: float,
    minimum_distance_over_diameter: float,
    geometry_relative_tolerance: float = 1.0e-8,
) -> bool:
    """Check a nominal distance/diameter rule without failing on CAD-kernel noise.

    The engineering requirement itself is not relaxed: ``distance >= ratio * D``.
    A very small absolute tolerance derived from the recognized diameter is added
    only to account for geometric reconstruction noise (for example OCC bounding
    boxes/radii that differ from the nominal CAD dimension by ~1e-7 mm).
    """
    distance = float(distance_mm)
    diameter = float(diameter_mm)
    ratio = float(minimum_distance_over_diameter)
    relative_tolerance = float(geometry_relative_tolerance)

    if not all(math.isfinite(value) for value in (distance, diameter, ratio, relative_tolerance)):
        raise FarFieldApplicabilityError("far-field applicability inputs must be finite")
    if distance < 0.0:
        raise FarFieldApplicabilityError("distance_mm must be nonnegative")
    if diameter <= 0.0:
        raise FarFieldApplicabilityError("diameter_mm must be positive")
    if ratio < 0.0:
        raise FarFieldApplicabilityError("minimum_distance_over_diameter must be nonnegative")
    if relative_tolerance < 0.0:
        raise FarFieldApplicabilityError("geometry_relative_tolerance must be nonnegative")

    required_distance = ratio * diameter
    absolute_tolerance_mm = max(1.0e-12, diameter * relative_tolerance)
    return bool(distance + absolute_tolerance_mm >= required_distance)
