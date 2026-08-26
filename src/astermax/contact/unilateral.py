from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
from typing import Iterable


class ContactState(StrEnum):
    OPEN = "OPEN"
    TOUCHING_ZERO_REACTION = "TOUCHING_ZERO_REACTION"
    ACTIVE = "ACTIVE"


@dataclass(frozen=True)
class UnilateralSpringContactProblem:
    """One elastic DOF constrained by a frictionless rigid obstacle.

    Sign convention:
    - positive displacement closes the initial gap;
    - positive applied load acts in the closing direction;
    - current signed gap is ``g = g0 - u`` and must remain non-negative;
    - contact reaction is a non-negative magnitude opposing closure;
    - equilibrium is ``k*u + R = F``;
    - exact Signorini complementarity is ``g >= 0, R >= 0, g*R = 0``.
    """

    stiffness_n_per_mm: float
    initial_gap_mm: float
    applied_load_n: float

    def __post_init__(self) -> None:
        values = (
            self.stiffness_n_per_mm,
            self.initial_gap_mm,
            self.applied_load_n,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("contact problem inputs must be finite")
        if self.stiffness_n_per_mm <= 0.0:
            raise ValueError("spring stiffness must be positive")
        if self.initial_gap_mm < 0.0:
            raise ValueError("initial gap must be non-negative")


@dataclass(frozen=True)
class UnilateralSpringContactResult:
    schema_version: str
    result_class: str
    state: ContactState
    displacement_mm: float
    signed_gap_mm: float
    contact_reaction_n: float
    spring_force_n: float
    applied_load_n: float
    force_residual_n: float
    complementarity_n_mm: float
    unconstrained_displacement_mm: float
    activation_load_n: float
    penetration_mm: float
    exact_no_penetration: bool
    friction_solved: bool
    contact_fea_executed: bool
    industrial_validation_claimed: bool


def solve_unilateral_spring_contact(
    problem: UnilateralSpringContactProblem,
    *,
    force_tolerance_n: float = 1.0e-9,
    gap_tolerance_mm: float = 1.0e-12,
) -> UnilateralSpringContactResult:
    """Solve the scalar Signorini problem exactly by an active-set decision.

    This verification kernel intentionally has no penalty stiffness and therefore
    does not permit artificial penetration. It is an analytical contact-law gate,
    not a finite-element contact implementation.
    """

    if not math.isfinite(force_tolerance_n) or force_tolerance_n < 0.0:
        raise ValueError("force_tolerance_n must be finite and non-negative")
    if not math.isfinite(gap_tolerance_mm) or gap_tolerance_mm < 0.0:
        raise ValueError("gap_tolerance_mm must be finite and non-negative")

    k = problem.stiffness_n_per_mm
    g0 = problem.initial_gap_mm
    load = problem.applied_load_n
    free_u = load / k
    activation_load = k * g0
    load_delta = load - activation_load

    if load_delta < -force_tolerance_n:
        displacement = free_u
        reaction = 0.0
        state = ContactState.OPEN
    elif abs(load_delta) <= force_tolerance_n:
        displacement = g0
        reaction = 0.0
        state = ContactState.TOUCHING_ZERO_REACTION
    else:
        displacement = g0
        reaction = load_delta
        if reaction < -force_tolerance_n:
            raise ArithmeticError("active-set solution produced a tensile contact reaction")
        reaction = max(reaction, 0.0)
        state = ContactState.ACTIVE

    gap = g0 - displacement
    if abs(gap) <= gap_tolerance_mm:
        gap = 0.0
    spring_force = k * displacement
    force_residual = spring_force + reaction - load
    if abs(force_residual) <= force_tolerance_n:
        force_residual = 0.0
    complementarity = gap * reaction
    penetration = max(-gap, 0.0)

    if gap < -gap_tolerance_mm:
        raise ArithmeticError("Signorini solution violated the no-penetration constraint")
    if reaction < -force_tolerance_n:
        raise ArithmeticError("Signorini solution produced a tensile contact reaction")
    complementarity_tolerance = max(
        force_tolerance_n * max(g0, gap_tolerance_mm),
        gap_tolerance_mm * max(abs(load), abs(reaction), 1.0),
    )
    if abs(complementarity) > complementarity_tolerance:
        raise ArithmeticError("Signorini complementarity residual exceeded tolerance")

    return UnilateralSpringContactResult(
        schema_version="AsterMaxUnilateralSpringContactV1",
        result_class="SYNTHETIC_CONTACT_LAW_VERIFICATION_NOT_FEA",
        state=state,
        displacement_mm=displacement,
        signed_gap_mm=gap,
        contact_reaction_n=reaction,
        spring_force_n=spring_force,
        applied_load_n=load,
        force_residual_n=force_residual,
        complementarity_n_mm=complementarity,
        unconstrained_displacement_mm=free_u,
        activation_load_n=activation_load,
        penetration_mm=penetration,
        exact_no_penetration=penetration <= gap_tolerance_mm,
        friction_solved=False,
        contact_fea_executed=False,
        industrial_validation_claimed=False,
    )


def solve_unilateral_spring_contact_sweep(
    *,
    stiffness_n_per_mm: float,
    initial_gap_mm: float,
    applied_loads_n: Iterable[float],
    force_tolerance_n: float = 1.0e-9,
    gap_tolerance_mm: float = 1.0e-12,
) -> tuple[UnilateralSpringContactResult, ...]:
    loads = tuple(float(load) for load in applied_loads_n)
    if not loads:
        raise ValueError("contact load sweep must contain at least one load")
    return tuple(
        solve_unilateral_spring_contact(
            UnilateralSpringContactProblem(
                stiffness_n_per_mm=stiffness_n_per_mm,
                initial_gap_mm=initial_gap_mm,
                applied_load_n=load,
            ),
            force_tolerance_n=force_tolerance_n,
            gap_tolerance_mm=gap_tolerance_mm,
        )
        for load in loads
    )
