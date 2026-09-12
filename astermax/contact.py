"""Auditable frictionless normal-contact primitives for AsterMax verification.

This module intentionally starts with the smallest contact model that can be
verified independently: a slave point against a rigid plane and a one-degree-
of-freedom spring against a rigid stop.  Gap is positive while open and negative
when penetrated.  Contact is compression-only and uses a penalty stiffness in
N/mm.  It is a verification core, not yet a production surface-to-surface solver.
"""

from dataclasses import dataclass
import math
from typing import Sequence


class ContactError(ValueError):
    """Raised when a contact definition or benchmark input is invalid."""


@dataclass(frozen=True)
class NormalContactState:
    gap_mm: float
    penetration_mm: float
    contact_force_n: float
    active: bool


@dataclass(frozen=True)
class PenaltyStopResult:
    displacement_mm: float
    gap_mm: float
    penetration_mm: float
    contact_force_n: float
    spring_force_n: float
    residual_n: float
    active: bool


@dataclass(frozen=True)
class RigidStopReference:
    displacement_mm: float
    contact_force_n: float
    active: bool


def _vector3(values: Sequence[float], name: str) -> tuple[float, float, float]:
    if len(values) != 3:
        raise ContactError(f"{name} must contain exactly three components")
    vector = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in vector):
        raise ContactError(f"{name} must contain finite values")
    return vector


def _unit_normal(normal: Sequence[float]) -> tuple[float, float, float]:
    n = _vector3(normal, "normal")
    length = math.sqrt(sum(value * value for value in n))
    if length <= 0.0:
        raise ContactError("contact normal must have non-zero length")
    return tuple(value / length for value in n)


def point_plane_gap_mm(
    slave_point_mm: Sequence[float],
    plane_point_mm: Sequence[float],
    normal: Sequence[float],
) -> float:
    """Return signed slave-to-plane gap; positive means separated/open."""
    slave = _vector3(slave_point_mm, "slave point")
    plane = _vector3(plane_point_mm, "plane point")
    n = _unit_normal(normal)
    return sum((slave[i] - plane[i]) * n[i] for i in range(3))


def evaluate_normal_penalty_contact(
    gap_mm: float,
    penalty_stiffness_n_per_mm: float,
) -> NormalContactState:
    """Evaluate unilateral frictionless penalty contact from a signed gap."""
    gap = float(gap_mm)
    penalty = float(penalty_stiffness_n_per_mm)
    if not math.isfinite(gap):
        raise ContactError("gap must be finite")
    if not math.isfinite(penalty) or penalty <= 0.0:
        raise ContactError("penalty stiffness must be finite and positive")
    penetration = max(0.0, -gap)
    force = penalty * penetration
    return NormalContactState(
        gap_mm=gap,
        penetration_mm=penetration,
        contact_force_n=force,
        active=penetration > 0.0,
    )


def rigid_stop_reference(
    structural_stiffness_n_per_mm: float,
    initial_gap_mm: float,
    compressive_load_n: float,
) -> RigidStopReference:
    """Closed-form solution for a linear spring loaded toward a rigid stop.

    Displacement is positive toward the stop.  The stop is located at u=gap.
    """
    k = float(structural_stiffness_n_per_mm)
    gap = float(initial_gap_mm)
    load = float(compressive_load_n)
    if not math.isfinite(k) or k <= 0.0:
        raise ContactError("structural stiffness must be finite and positive")
    if not math.isfinite(gap) or gap < 0.0:
        raise ContactError("initial gap must be finite and non-negative")
    if not math.isfinite(load) or load < 0.0:
        raise ContactError("compressive load must be finite and non-negative")

    free_displacement = load / k
    if free_displacement <= gap:
        return RigidStopReference(free_displacement, 0.0, False)
    return RigidStopReference(gap, load - k * gap, True)


def solve_penalty_stop(
    structural_stiffness_n_per_mm: float,
    penalty_stiffness_n_per_mm: float,
    initial_gap_mm: float,
    compressive_load_n: float,
) -> PenaltyStopResult:
    """Solve the scalar spring/rigid-stop penalty benchmark exactly by active set.

    Open branch: P = k_s u.
    Closed branch: P = k_s u + k_p (u-g0).
    """
    k_s = float(structural_stiffness_n_per_mm)
    k_p = float(penalty_stiffness_n_per_mm)
    gap0 = float(initial_gap_mm)
    load = float(compressive_load_n)
    if not math.isfinite(k_s) or k_s <= 0.0:
        raise ContactError("structural stiffness must be finite and positive")
    if not math.isfinite(k_p) or k_p <= 0.0:
        raise ContactError("penalty stiffness must be finite and positive")
    if not math.isfinite(gap0) or gap0 < 0.0:
        raise ContactError("initial gap must be finite and non-negative")
    if not math.isfinite(load) or load < 0.0:
        raise ContactError("compressive load must be finite and non-negative")

    free_displacement = load / k_s
    if free_displacement <= gap0:
        displacement = free_displacement
        penetration = 0.0
        contact_force = 0.0
        active = False
    else:
        displacement = (load + k_p * gap0) / (k_s + k_p)
        penetration = max(0.0, displacement - gap0)
        contact_force = k_p * penetration
        active = penetration > 0.0

    spring_force = k_s * displacement
    residual = spring_force + contact_force - load
    return PenaltyStopResult(
        displacement_mm=displacement,
        gap_mm=gap0 - displacement,
        penetration_mm=penetration,
        contact_force_n=contact_force,
        spring_force_n=spring_force,
        residual_n=residual,
        active=active,
    )
