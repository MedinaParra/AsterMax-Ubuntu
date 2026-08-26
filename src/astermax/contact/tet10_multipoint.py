from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from astermax.fea.solver import assemble_global_stiffness_sparse_tet10
from astermax.fea.tet4 import IsotropicMaterial

from .unilateral import ContactState
from .tet10_unilateral import _recover_tet10_stress, _solve_with_prescribed_dofs


@dataclass(frozen=True)
class Tet10MultipointContactResult:
    schema_version: str
    result_class: str
    displacement_mm: np.ndarray
    reactions_n: np.ndarray
    integration_point_stress_mpa: np.ndarray
    integration_point_von_mises_mpa: np.ndarray
    contact_dofs: np.ndarray
    initial_gaps_mm: np.ndarray
    signed_gaps_mm: np.ndarray
    contact_reactions_n: np.ndarray
    raw_constraint_reactions_n: np.ndarray
    states: tuple[ContactState, ...]
    active_contact_indices: tuple[int, ...]
    active_set_history: tuple[tuple[int, ...], ...]
    iterations: int
    penetration_mm: np.ndarray
    complementarity_n_mm: np.ndarray
    free_equilibrium_residual_norm_n: float
    converged: bool
    exact_no_penetration: bool
    finite_element_contact_executed: bool
    deformable_tet10_contact: bool
    multipoint_contact: bool
    surface_patch_constraint_set: bool
    contact_pressure_recovered: bool
    friction_solved: bool
    industrial_validation_claimed: bool
    ot1613_result_claimed: bool
    ansys_equivalence_claimed: bool


def _validate_tolerance(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return value


def solve_tet10_multipoint_unilateral_contact(
    *,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    material: IsotropicMaterial,
    loads_n: np.ndarray,
    fixed_dofs: list[int] | np.ndarray,
    contact_dofs: list[int] | np.ndarray,
    initial_gaps_mm: list[float] | np.ndarray,
    force_tolerance_n: float = 1.0e-7,
    gap_tolerance_mm: float = 1.0e-10,
    max_iterations: int = 50,
) -> Tet10MultipointContactResult:
    """Solve several frictionless nodal Signorini constraints on deformable TET10.

    Every contact DOF follows the same convention as the verified GAP-D scalar
    coupling: positive displacement closes its obstacle gap, and physical
    contact reaction opposes closure. The TET10 stiffness/assembly is unchanged.

    The active-set iteration is deterministic:
    1. solve with the current active constraints prescribed exactly at their gaps;
    2. add every inactive contact whose displacement violates its gap;
    3. remove every active contact whose exact constraint reaction is tensile;
    4. repeat until the active set is unchanged.

    Repeated active sets before convergence are treated as a cycle and fail
    closed. This is a nodal multipoint verification kernel, not yet a mortar or
    surface-to-surface contact formulation and it does not infer pressure.
    """

    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=int)
    loads = np.asarray(loads_n, dtype=float).reshape(-1)
    fixed = np.unique(np.asarray(fixed_dofs, dtype=int).reshape(-1))
    contacts = np.asarray(contact_dofs, dtype=int).reshape(-1)
    gaps = np.asarray(initial_gaps_mm, dtype=float).reshape(-1)
    force_tol = _validate_tolerance(force_tolerance_n, "force_tolerance_n")
    gap_tol = _validate_tolerance(gap_tolerance_mm, "gap_tolerance_mm")

    if not isinstance(max_iterations, int) or max_iterations <= 0:
        raise ValueError("max_iterations must be a positive integer")
    if nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("nodes_mm must have shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("elements must have shape (m, 10)")
    ndof = nodes.shape[0] * 3
    if loads.size != ndof or not np.all(np.isfinite(loads)):
        raise ValueError("loads_n must be finite and contain 3 DOFs per node")
    if fixed.size == 0:
        raise ValueError("fixed_dofs must contain at least one support DOF")
    if np.any(fixed < 0) or np.any(fixed >= ndof):
        raise ValueError("fixed_dofs contains an out-of-range DOF")
    if contacts.size < 2:
        raise ValueError("multipoint contact requires at least two contact DOFs")
    if np.unique(contacts).size != contacts.size:
        raise ValueError("contact_dofs must be unique")
    if np.any(contacts < 0) or np.any(contacts >= ndof):
        raise ValueError("contact_dofs contains an out-of-range DOF")
    if gaps.size != contacts.size:
        raise ValueError("initial_gaps_mm must match contact_dofs length")
    if not np.all(np.isfinite(gaps)) or np.any(gaps < 0.0):
        raise ValueError("initial_gaps_mm must be finite and non-negative")
    fixed_set = set(int(dof) for dof in fixed)
    if any(int(dof) in fixed_set for dof in contacts):
        raise ValueError("contact DOFs cannot overlap fixed support DOFs")

    stiffness = assemble_global_stiffness_sparse_tet10(nodes, elems, material)

    # Begin from the free TET10 trial so the first active set contains all
    # independently visible penetrations. Subsequent solves account for coupling.
    trial_u, trial_reactions, trial_free = _solve_with_prescribed_dofs(
        stiffness,
        loads,
        fixed,
        np.zeros(fixed.size, dtype=float),
    )
    active: set[int] = {
        index
        for index, (dof, gap) in enumerate(zip(contacts, gaps))
        if float(trial_u[int(dof)]) > float(gap) + gap_tol
    }

    history: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    displacement_vector = trial_u
    reactions = trial_reactions
    free_dofs = trial_free
    converged = False

    for iteration in range(1, max_iterations + 1):
        signature = tuple(sorted(active))
        if signature in seen:
            raise ArithmeticError(f"multipoint contact active-set cycle detected at {signature}")
        seen.add(signature)
        history.append(signature)

        if active:
            active_indices = np.asarray(sorted(active), dtype=int)
            active_dofs = contacts[active_indices]
            prescribed_dofs = np.concatenate([fixed, active_dofs])
            prescribed_values = np.concatenate(
                [np.zeros(fixed.size, dtype=float), gaps[active_indices]]
            )
            displacement_vector, reactions, free_dofs = _solve_with_prescribed_dofs(
                stiffness,
                loads,
                prescribed_dofs,
                prescribed_values,
            )
        else:
            displacement_vector, reactions, free_dofs = _solve_with_prescribed_dofs(
                stiffness,
                loads,
                fixed,
                np.zeros(fixed.size, dtype=float),
            )

        to_add = {
            index
            for index, (dof, gap) in enumerate(zip(contacts, gaps))
            if index not in active
            and float(displacement_vector[int(dof)]) > float(gap) + gap_tol
        }
        to_remove = {
            index
            for index in active
            if float(reactions[int(contacts[index])]) > force_tol
        }
        updated = (active | to_add) - to_remove

        if updated == active:
            converged = True
            break
        active = updated
    else:
        iteration = max_iterations

    if not converged:
        raise ArithmeticError("multipoint contact active set did not converge")

    contact_u = displacement_vector[contacts]
    signed_gaps = gaps - contact_u
    signed_gaps[np.abs(signed_gaps) <= gap_tol] = 0.0
    raw_constraint_reactions = np.zeros(contacts.size, dtype=float)
    contact_reactions = np.zeros(contacts.size, dtype=float)
    for index in active:
        raw = float(reactions[int(contacts[index])])
        if raw > force_tol:
            raise ArithmeticError("converged active set contains tensile contact")
        raw_constraint_reactions[index] = raw
        contact_reactions[index] = max(-raw, 0.0)

    penetration = np.maximum(-signed_gaps, 0.0)
    complementarity = signed_gaps * contact_reactions

    states: list[ContactState] = []
    for gap, reaction in zip(signed_gaps, contact_reactions):
        if reaction > force_tol:
            states.append(ContactState.ACTIVE)
        elif gap <= gap_tol:
            states.append(ContactState.TOUCHING_ZERO_REACTION)
        else:
            states.append(ContactState.OPEN)

    if np.any(signed_gaps < -gap_tol):
        raise ArithmeticError("multipoint TET10 contact violated no-penetration")
    if np.any(contact_reactions < -force_tol):
        raise ArithmeticError("multipoint TET10 contact produced tensile reaction")
    comp_tolerance = np.maximum(
        force_tol * np.maximum(gaps, gap_tol),
        gap_tol * np.maximum(contact_reactions, 1.0),
    )
    if np.any(np.abs(complementarity) > comp_tolerance):
        raise ArithmeticError("multipoint TET10 Signorini complementarity failed")

    free_residual = float(np.linalg.norm(reactions[free_dofs]))
    if free_residual > force_tol * max(1.0, math.sqrt(float(free_dofs.size))):
        raise ArithmeticError("multipoint TET10 free-DOF equilibrium residual exceeded tolerance")

    displacement = displacement_vector.reshape((-1, 3))
    ip_stress, ip_mises = _recover_tet10_stress(nodes, elems, displacement, material)

    return Tet10MultipointContactResult(
        schema_version="AsterMaxTet10MultipointContactV1",
        result_class="SYNTHETIC_TET10_MULTIPOINT_SURFACE_PATCH_CONTACT_NOT_INDUSTRIAL_RESULT",
        displacement_mm=displacement,
        reactions_n=reactions.reshape((-1, 3)),
        integration_point_stress_mpa=ip_stress,
        integration_point_von_mises_mpa=ip_mises,
        contact_dofs=contacts.copy(),
        initial_gaps_mm=gaps.copy(),
        signed_gaps_mm=signed_gaps,
        contact_reactions_n=contact_reactions,
        raw_constraint_reactions_n=raw_constraint_reactions,
        states=tuple(states),
        active_contact_indices=tuple(sorted(active)),
        active_set_history=tuple(history),
        iterations=iteration,
        penetration_mm=penetration,
        complementarity_n_mm=complementarity,
        free_equilibrium_residual_norm_n=free_residual,
        converged=True,
        exact_no_penetration=bool(np.all(penetration <= gap_tol)),
        finite_element_contact_executed=True,
        deformable_tet10_contact=True,
        multipoint_contact=True,
        surface_patch_constraint_set=True,
        contact_pressure_recovered=False,
        friction_solved=False,
        industrial_validation_claimed=False,
        ot1613_result_claimed=False,
        ansys_equivalence_claimed=False,
    )
