from __future__ import annotations

from dataclasses import dataclass
import math

from .circular_torsion import CircularTorsionError, CircularTorsionWitness


@dataclass(frozen=True)
class TorsionShearPoint:
    u_mm: float
    v_mm: float
    radius_mm: float
    tau_u_mpa: float
    tau_v_mpa: float
    tau_magnitude_mpa: float


def torsion_shear_point(
    witness: CircularTorsionWitness,
    *,
    u_mm: float,
    v_mm: float,
    radial_tolerance_mm: float = 1.0e-9,
) -> TorsionShearPoint:
    u = float(u_mm); v = float(v_mm); tolerance = float(radial_tolerance_mm)
    if not all(math.isfinite(x) for x in (u, v, tolerance)):
        raise CircularTorsionError("TORSION_FIELD_INPUT_MUST_BE_FINITE")
    if tolerance < 0.0:
        raise CircularTorsionError("radial_tolerance_mm must be nonnegative")

    radius = math.hypot(u, v)
    if radius > witness.radius_mm + tolerance:
        raise CircularTorsionError(
            f"TORSION_FIELD_POINT_OUTSIDE_SECTION:{radius:.17g}>{witness.radius_mm:.17g}"
        )

    k = witness.shear_gradient_mpa_per_mm
    tau_u = -k * v
    tau_v = k * u
    magnitude = math.hypot(tau_u, tau_v)
    expected = abs(k) * radius
    if abs(magnitude - expected) > 1.0e-12 * max(expected, 1.0):
        raise CircularTorsionError("TORSION_FIELD_MAGNITUDE_IDENTITY_FAILED")

    return TorsionShearPoint(
        u_mm=u,
        v_mm=v,
        radius_mm=radius,
        tau_u_mpa=tau_u,
        tau_v_mpa=tau_v,
        tau_magnitude_mpa=magnitude,
    )
