"""Auditable Coulomb stick/slip kernel for AsterMax PMV.

This increment intentionally isolates the local tangential constitutive law before
coupling it into the nonlinear global contact solver.  Given an active frictionless
normal-contact state, a tangential penalty predictor is projected into the contact
plane and capped by the Coulomb limit ``mu * Fn``.

State convention:
- OPEN: no compressive normal force, therefore no friction traction.
- STICK: trial tangential force magnitude <= mu * Fn.
- SLIP: trial force exceeds the Coulomb limit and is returned to the friction cone.

The returned force opposes the supplied relative tangential displacement increment.
This is a small-increment verification kernel, not a production finite-sliding
friction algorithm.
"""

from dataclasses import dataclass
import math
from typing import Sequence


class FrictionError(ValueError):
    pass


@dataclass(frozen=True)
class CoulombFrictionState:
    regime: str
    normal_force_n: float
    friction_limit_n: float
    trial_force_n: tuple[float, float, float]
    tangential_force_n: tuple[float, float, float]
    trial_magnitude_n: float
    tangential_force_magnitude_n: float
    relative_tangential_increment_mm: tuple[float, float, float]


def _vec3(values: Sequence[float], name: str) -> tuple[float, float, float]:
    if len(values) != 3:
        raise FrictionError(f"{name} must contain three components")
    result = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in result):
        raise FrictionError(f"{name} must be finite")
    return result


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _norm(a):
    return math.sqrt(_dot(a, a))


def _scale(a, factor):
    return tuple(factor * a[i] for i in range(3))


def _sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _unit_normal(normal: Sequence[float]) -> tuple[float, float, float]:
    n = _vec3(normal, "contact normal")
    magnitude = _norm(n)
    if magnitude <= 0.0:
        raise FrictionError("contact normal must be non-zero")
    return _scale(n, 1.0 / magnitude)


def project_tangential(
    vector: Sequence[float], normal: Sequence[float]
) -> tuple[float, float, float]:
    """Project a 3D vector onto the plane orthogonal to the contact normal."""
    v = _vec3(vector, "relative displacement increment")
    n = _unit_normal(normal)
    return _sub(v, _scale(n, _dot(v, n)))


def evaluate_coulomb_friction(
    relative_displacement_increment_mm: Sequence[float],
    normal: Sequence[float],
    *,
    normal_force_n: float,
    friction_coefficient: float,
    tangential_penalty_n_per_mm: float,
    tolerance_n: float = 1e-10,
) -> CoulombFrictionState:
    """Evaluate one local elastic-predictor/Coulomb-return tangential contact state."""
    fn = float(normal_force_n)
    mu = float(friction_coefficient)
    kt = float(tangential_penalty_n_per_mm)
    tol = float(tolerance_n)
    for value, name in (
        (fn, "normal force"),
        (mu, "friction coefficient"),
        (kt, "tangential penalty"),
        (tol, "force tolerance"),
    ):
        if not math.isfinite(value):
            raise FrictionError(f"{name} must be finite")
    if fn < 0.0:
        raise FrictionError("normal force must be compression-only and non-negative")
    if mu < 0.0:
        raise FrictionError("friction coefficient must be non-negative")
    if kt <= 0.0:
        raise FrictionError("tangential penalty must be positive")
    if tol < 0.0:
        raise FrictionError("force tolerance must be non-negative")

    n = _unit_normal(normal)
    tangential_increment = project_tangential(relative_displacement_increment_mm, n)
    # Oppose relative tangential motion.
    trial_force = _scale(tangential_increment, -kt)
    trial_magnitude = _norm(trial_force)
    limit = mu * fn

    if fn <= tol or limit <= tol:
        return CoulombFrictionState(
            regime="OPEN" if fn <= tol else "SLIP",
            normal_force_n=fn,
            friction_limit_n=limit,
            trial_force_n=trial_force,
            tangential_force_n=(0.0, 0.0, 0.0),
            trial_magnitude_n=trial_magnitude,
            tangential_force_magnitude_n=0.0,
            relative_tangential_increment_mm=tangential_increment,
        )

    if trial_magnitude <= limit + tol:
        force = trial_force
        regime = "STICK"
    else:
        if trial_magnitude <= 0.0:
            force = (0.0, 0.0, 0.0)
        else:
            force = _scale(trial_force, limit / trial_magnitude)
        regime = "SLIP"

    return CoulombFrictionState(
        regime=regime,
        normal_force_n=fn,
        friction_limit_n=limit,
        trial_force_n=trial_force,
        tangential_force_n=force,
        trial_magnitude_n=trial_magnitude,
        tangential_force_magnitude_n=_norm(force),
        relative_tangential_increment_mm=tangential_increment,
    )


def friction_force_is_tangential(
    state: CoulombFrictionState,
    normal: Sequence[float],
) -> float:
    """Return |Ft dot n| as an auditable tangency invariant (N)."""
    n = _unit_normal(normal)
    return abs(_dot(state.tangential_force_n, n))
