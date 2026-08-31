"""Minimal active-set normal contact coupled to AsterMax global stiffness.

This module is deliberately narrow: each rigid-stop contact acts on one global
translational DOF, with positive displacement directed toward a rigid stop at
``u = initial_gap_mm``.  The contact law is unilateral and frictionless:

    f_c = k_p * max(0, u - g0)

For a fixed active set, the tangent system is linear:

    (K + Kc) u = F + Kc * g0

The active set is updated until it is unchanged.  This is a verification bridge
between the scalar contact oracle and the TET4 global assembler; it is NOT yet a
general surface-to-surface contact formulation.
"""

from dataclasses import dataclass
import math
from typing import Mapping, Sequence

from .global_static import GlobalStaticError, _solve_dense, assemble_stiffness


class GlobalContactError(ValueError):
    """Raised when a contact-coupled verification model is invalid."""


@dataclass(frozen=True)
class RigidStopContact:
    dof: int
    initial_gap_mm: float
    penalty_stiffness_n_per_mm: float


@dataclass(frozen=True)
class GlobalContactResult:
    displacements: tuple[float, ...]
    reactions: tuple[float, ...]
    residual: tuple[float, ...]
    contact_forces_n: tuple[float, ...]
    active_contacts: tuple[bool, ...]
    iterations: int
    converged: bool


def _validate_contacts(contacts: Sequence[RigidStopContact], ndof: int) -> tuple[RigidStopContact, ...]:
    validated = []
    seen = set()
    for contact in contacts:
        dof = int(contact.dof)
        gap = float(contact.initial_gap_mm)
        penalty = float(contact.penalty_stiffness_n_per_mm)
        if dof < 0 or dof >= ndof:
            raise GlobalContactError("contact references an unknown DOF")
        if dof in seen:
            raise GlobalContactError("only one rigid-stop contact per DOF is supported")
        if not math.isfinite(gap) or gap < 0.0:
            raise GlobalContactError("initial contact gap must be finite and non-negative")
        if not math.isfinite(penalty) or penalty <= 0.0:
            raise GlobalContactError("contact penalty stiffness must be finite and positive")
        seen.add(dof)
        validated.append(RigidStopContact(dof, gap, penalty))
    return tuple(validated)


def solve_active_set_from_stiffness(
    stiffness: Sequence[Sequence[float]],
    constraints: Mapping[int, float],
    loads: Mapping[int, float],
    contacts: Sequence[RigidStopContact],
    *,
    max_iterations: int = 20,
    activation_tolerance_mm: float = 1e-12,
) -> GlobalContactResult:
    """Solve a small linear structure with unilateral rigid-stop penalty contacts."""
    ndof = len(stiffness)
    if ndof == 0 or any(len(row) != ndof for row in stiffness):
        raise GlobalContactError("stiffness matrix must be non-empty and square")
    if max_iterations <= 0:
        raise GlobalContactError("max_iterations must be positive")
    if activation_tolerance_mm < 0.0 or not math.isfinite(activation_tolerance_mm):
        raise GlobalContactError("activation tolerance must be finite and non-negative")

    fixed = {int(dof): float(value) for dof, value in constraints.items()}
    force = [0.0] * ndof
    for dof, value in loads.items():
        if dof < 0 or dof >= ndof:
            raise GlobalContactError("load references an unknown DOF")
        force[int(dof)] += float(value)
    for dof in fixed:
        if dof < 0 or dof >= ndof:
            raise GlobalContactError("constraint references an unknown DOF")

    contact_defs = _validate_contacts(contacts, ndof)
    if any(contact.dof in fixed for contact in contact_defs):
        raise GlobalContactError("contact DOF cannot also be Dirichlet constrained")

    free = [dof for dof in range(ndof) if dof not in fixed]
    if not free:
        raise GlobalContactError("model has no free DOFs to solve")

    active = [False] * len(contact_defs)
    displacement = [0.0] * ndof
    for iteration in range(1, max_iterations + 1):
        k_eff = [list(map(float, row)) for row in stiffness]
        f_eff = list(force)
        for is_active, contact in zip(active, contact_defs):
            if is_active:
                k_eff[contact.dof][contact.dof] += contact.penalty_stiffness_n_per_mm
                f_eff[contact.dof] += contact.penalty_stiffness_n_per_mm * contact.initial_gap_mm

        reduced_k = [[k_eff[i][j] for j in free] for i in free]
        reduced_f = [
            f_eff[i] - sum(k_eff[i][j] * value for j, value in fixed.items())
            for i in free
        ]
        try:
            solved = _solve_dense(reduced_k, reduced_f)
        except GlobalStaticError as exc:
            raise GlobalContactError(str(exc)) from exc

        displacement = [0.0] * ndof
        for dof, value in fixed.items():
            displacement[dof] = value
        for dof, value in zip(free, solved):
            displacement[dof] = value

        updated = [
            displacement[contact.dof] > contact.initial_gap_mm + activation_tolerance_mm
            for contact in contact_defs
        ]
        if updated == active:
            break
        active = updated
    else:
        return GlobalContactResult(
            displacements=tuple(displacement),
            reactions=tuple(0.0 for _ in range(ndof)),
            residual=tuple(float("nan") for _ in range(ndof)),
            contact_forces_n=tuple(0.0 for _ in contact_defs),
            active_contacts=tuple(active),
            iterations=max_iterations,
            converged=False,
        )

    contact_force_vector = [0.0] * ndof
    contact_forces = []
    for is_active, contact in zip(active, contact_defs):
        penetration = max(0.0, displacement[contact.dof] - contact.initial_gap_mm) if is_active else 0.0
        value = contact.penalty_stiffness_n_per_mm * penetration
        contact_forces.append(value)
        contact_force_vector[contact.dof] += value

    ku = [sum(float(stiffness[i][j]) * displacement[j] for j in range(ndof)) for i in range(ndof)]
    residual = [ku[i] + contact_force_vector[i] - force[i] for i in range(ndof)]
    reactions = [residual[i] if i in fixed else 0.0 for i in range(ndof)]

    return GlobalContactResult(
        displacements=tuple(displacement),
        reactions=tuple(reactions),
        residual=tuple(residual),
        contact_forces_n=tuple(contact_forces),
        active_contacts=tuple(active),
        iterations=iteration,
        converged=True,
    )


def solve_tet4_with_rigid_stops(
    nodes: Sequence[Sequence[float]],
    elements: Sequence[Sequence[int]],
    young: float,
    poisson: float,
    constraints: Mapping[int, float],
    loads: Mapping[int, float],
    contacts: Sequence[RigidStopContact],
    *,
    max_iterations: int = 20,
) -> GlobalContactResult:
    """Assemble a TET4 stiffness matrix and solve it with scalar rigid-stop contacts."""
    stiffness = assemble_stiffness(nodes, elements, young, poisson)
    return solve_active_set_from_stiffness(
        stiffness,
        constraints,
        loads,
        contacts,
        max_iterations=max_iterations,
    )
