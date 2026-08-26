from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import spsolve

from astermax.fea.solver import assemble_global_stiffness_sparse_tet10
from astermax.fea.tet10 import tet10_integration_point_results
from astermax.fea.tet4 import IsotropicMaterial

from .unilateral import ContactState


@dataclass(frozen=True)
class Tet10SingleDofContactResult:
    schema_version: str
    result_class: str
    state: ContactState
    displacement_mm: np.ndarray
    reactions_n: np.ndarray
    integration_point_stress_mpa: np.ndarray
    integration_point_von_mises_mpa: np.ndarray
    contact_dof: int
    initial_gap_mm: float
    signed_gap_mm: float
    contact_reaction_n: float
    raw_constraint_reaction_n: float
    free_trial_contact_displacement_mm: float
    penetration_mm: float
    complementarity_n_mm: float
    free_equilibrium_residual_norm_n: float
    exact_no_penetration: bool
    finite_element_contact_executed: bool
    deformable_tet10_contact: bool
    contact_pressure_recovered: bool
    friction_solved: bool
    industrial_validation_claimed: bool
    ot1613_result_claimed: bool
    ansys_equivalence_claimed: bool


def _validate_scalar_tolerance(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return value


def _solve_with_prescribed_dofs(
    stiffness: csr_matrix,
    loads_n: np.ndarray,
    prescribed_dofs: np.ndarray,
    prescribed_values_mm: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Solve a sparse linear system with explicit non-zero prescribed DOFs.

    The existing linear-static PMV path only needs zero fixed supports. Contact
    activation requires one additional non-zero displacement constraint, so this
    bounded helper performs the standard partitioned solve without changing the
    verified TET10 element formulation or global assembly.
    """

    loads = np.asarray(loads_n, dtype=float).reshape(-1)
    prescribed = np.asarray(prescribed_dofs, dtype=int).reshape(-1)
    values = np.asarray(prescribed_values_mm, dtype=float).reshape(-1)
    ndof = int(stiffness.shape[0])

    if stiffness.shape[1] != ndof:
        raise ValueError("stiffness matrix must be square")
    if loads.size != ndof:
        raise ValueError("loads_n size must match the stiffness matrix")
    if prescribed.size != values.size:
        raise ValueError("prescribed_dofs and prescribed_values_mm must have equal length")
    if prescribed.size == 0:
        raise ValueError("at least one prescribed DOF is required")
    if np.any(prescribed < 0) or np.any(prescribed >= ndof):
        raise ValueError("prescribed DOF is out of range")
    if np.unique(prescribed).size != prescribed.size:
        raise ValueError("prescribed DOFs must be unique")
    if not np.all(np.isfinite(loads)) or not np.all(np.isfinite(values)):
        raise ValueError("loads and prescribed values must be finite")

    free = np.setdiff1d(np.arange(ndof, dtype=int), prescribed)
    if free.size == 0:
        raise ValueError("no free DOFs remain after prescribing constraints")

    displacement = np.zeros(ndof, dtype=float)
    displacement[prescribed] = values
    kff = stiffness[free][:, free]
    kfp = stiffness[free][:, prescribed]
    rhs = loads[free] - np.asarray(kfp @ values, dtype=float).reshape(-1)
    solved = np.asarray(spsolve(kff, rhs), dtype=float).reshape(-1)
    if solved.size != free.size or not np.all(np.isfinite(solved)):
        raise np.linalg.LinAlgError("partitioned TET10 contact solve did not return a finite field")
    displacement[free] = solved
    reactions = np.asarray(stiffness @ displacement - loads, dtype=float).reshape(-1)
    if not np.all(np.isfinite(reactions)):
        raise np.linalg.LinAlgError("partitioned TET10 contact reactions are non-finite")
    return displacement, reactions, free


def _recover_tet10_stress(
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    displacement_mm: np.ndarray,
    material: IsotropicMaterial,
) -> tuple[np.ndarray, np.ndarray]:
    ip_stress: list[list[np.ndarray]] = []
    ip_mises: list[list[float]] = []
    for conn in np.asarray(elements, dtype=int):
        points = tet10_integration_point_results(
            np.asarray(nodes_mm, dtype=float)[conn],
            np.asarray(displacement_mm, dtype=float)[conn],
            material,
        )
        ip_stress.append([point.stress_mpa for point in points])
        ip_mises.append([point.von_mises_mpa for point in points])
    return np.asarray(ip_stress, dtype=float), np.asarray(ip_mises, dtype=float)


def solve_tet10_single_dof_unilateral_contact(
    *,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    material: IsotropicMaterial,
    loads_n: np.ndarray,
    fixed_dofs: list[int] | np.ndarray,
    contact_dof: int,
    initial_gap_mm: float,
    force_tolerance_n: float = 1.0e-7,
    gap_tolerance_mm: float = 1.0e-10,
) -> Tet10SingleDofContactResult:
    """Couple one exact frictionless unilateral constraint to deformable TET10.

    The obstacle limits the selected positive DOF to ``u_contact <= g0``.
    A free TET10 solve is performed first. If the free trial does not cross the
    gap, that solution is retained. Otherwise the contact DOF is prescribed
    exactly at ``g0`` and the remaining sparse system is re-solved. The contact
    reaction is recovered from ``K*u - F`` and must oppose positive closure.

    This is a synthetic single-node verification gate. It is not a surface
    contact discretization and does not recover contact pressure.
    """

    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=int)
    loads = np.asarray(loads_n, dtype=float).reshape(-1)
    force_tol = _validate_scalar_tolerance(force_tolerance_n, "force_tolerance_n")
    gap_tol = _validate_scalar_tolerance(gap_tolerance_mm, "gap_tolerance_mm")
    gap0 = float(initial_gap_mm)
    if not math.isfinite(gap0) or gap0 < 0.0:
        raise ValueError("initial_gap_mm must be finite and non-negative")
    if nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("nodes_mm must have shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("elements must have shape (m, 10)")
    ndof = nodes.shape[0] * 3
    if loads.size != ndof or not np.all(np.isfinite(loads)):
        raise ValueError("loads_n must be finite and contain 3 DOFs per node")

    contact = int(contact_dof)
    if contact < 0 or contact >= ndof:
        raise ValueError("contact_dof is out of range")
    fixed = np.unique(np.asarray(fixed_dofs, dtype=int).reshape(-1))
    if fixed.size == 0:
        raise ValueError("fixed_dofs must contain at least one support DOF")
    if np.any(fixed < 0) or np.any(fixed >= ndof):
        raise ValueError("fixed_dofs contains an out-of-range DOF")
    if contact in set(fixed.tolist()):
        raise ValueError("contact_dof cannot already be a fixed support DOF")

    stiffness = assemble_global_stiffness_sparse_tet10(nodes, elems, material)

    trial_values = np.zeros(fixed.size, dtype=float)
    trial_u, trial_reactions, trial_free = _solve_with_prescribed_dofs(
        stiffness,
        loads,
        fixed,
        trial_values,
    )
    free_trial = float(trial_u[contact])

    use_open_trial = free_trial < gap0 - gap_tol
    if use_open_trial:
        state = ContactState.OPEN
        displacement_vector = trial_u
        reactions = trial_reactions
        active_free = trial_free
        raw_contact_reaction = 0.0
        contact_reaction = 0.0
    else:
        prescribed = np.concatenate([fixed, np.asarray([contact], dtype=int)])
        values = np.concatenate([np.zeros(fixed.size, dtype=float), np.asarray([gap0])])
        constrained_u, constrained_reactions, constrained_free = _solve_with_prescribed_dofs(
            stiffness,
            loads,
            prescribed,
            values,
        )
        raw = float(constrained_reactions[contact])

        # ``K*u - F`` is the force supplied by the displacement constraint.
        # For a positive closing DOF, physical frictionless contact must oppose
        # closure, so the admissible constraint reaction is non-positive.
        if raw > force_tol:
            if free_trial <= gap0 + gap_tol:
                state = ContactState.OPEN
                displacement_vector = trial_u
                reactions = trial_reactions
                active_free = trial_free
                raw_contact_reaction = 0.0
                contact_reaction = 0.0
            else:
                raise ArithmeticError("active TET10 constraint would require tensile contact")
        else:
            displacement_vector = constrained_u
            reactions = constrained_reactions
            active_free = constrained_free
            raw_contact_reaction = raw
            contact_reaction = max(-raw, 0.0)
            state = (
                ContactState.TOUCHING_ZERO_REACTION
                if contact_reaction <= force_tol
                else ContactState.ACTIVE
            )
            if state == ContactState.TOUCHING_ZERO_REACTION:
                contact_reaction = 0.0
                raw_contact_reaction = 0.0

    displacement = displacement_vector.reshape((-1, 3))
    signed_gap = gap0 - float(displacement_vector[contact])
    if abs(signed_gap) <= gap_tol:
        signed_gap = 0.0
    penetration = max(-signed_gap, 0.0)
    complementarity = signed_gap * contact_reaction
    free_residual = float(np.linalg.norm(reactions[active_free]))

    if signed_gap < -gap_tol:
        raise ArithmeticError("TET10 contact solution violated no-penetration")
    if contact_reaction < -force_tol:
        raise ArithmeticError("TET10 contact reaction became tensile")
    complementarity_tol = max(
        force_tol * max(gap0, gap_tol),
        gap_tol * max(contact_reaction, 1.0),
    )
    if abs(complementarity) > complementarity_tol:
        raise ArithmeticError("TET10 contact complementarity residual exceeded tolerance")
    if free_residual > force_tol * max(1.0, math.sqrt(float(active_free.size))):
        raise ArithmeticError("TET10 contact free-DOF equilibrium residual exceeded tolerance")

    ip_stress, ip_mises = _recover_tet10_stress(nodes, elems, displacement, material)

    return Tet10SingleDofContactResult(
        schema_version="AsterMaxTet10SingleDofUnilateralContactV1",
        result_class="SYNTHETIC_DEFORMABLE_TET10_CONTACT_VERIFICATION_NOT_INDUSTRIAL_RESULT",
        state=state,
        displacement_mm=displacement,
        reactions_n=reactions.reshape((-1, 3)),
        integration_point_stress_mpa=ip_stress,
        integration_point_von_mises_mpa=ip_mises,
        contact_dof=contact,
        initial_gap_mm=gap0,
        signed_gap_mm=signed_gap,
        contact_reaction_n=contact_reaction,
        raw_constraint_reaction_n=raw_contact_reaction,
        free_trial_contact_displacement_mm=free_trial,
        penetration_mm=penetration,
        complementarity_n_mm=complementarity,
        free_equilibrium_residual_norm_n=free_residual,
        exact_no_penetration=penetration <= gap_tol,
        finite_element_contact_executed=True,
        deformable_tet10_contact=True,
        contact_pressure_recovered=False,
        friction_solved=False,
        industrial_validation_claimed=False,
        ot1613_result_claimed=False,
        ansys_equivalence_claimed=False,
    )
