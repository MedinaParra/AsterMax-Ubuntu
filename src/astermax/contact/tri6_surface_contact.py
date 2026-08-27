from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from astermax.fea.solver import assemble_global_stiffness_sparse_tet10
from astermax.fea.tet4 import IsotropicMaterial

from .tet10_unilateral import _recover_tet10_stress, _solve_with_prescribed_dofs
from .tri6_pressure import triangle_area_mm2
from .unilateral import ContactState


TRI6_GAUSS_BARYCENTRIC = np.asarray(
    [
        [2.0 / 3.0, 1.0 / 6.0, 1.0 / 6.0],
        [1.0 / 6.0, 2.0 / 3.0, 1.0 / 6.0],
        [1.0 / 6.0, 1.0 / 6.0, 2.0 / 3.0],
    ],
    dtype=float,
)


@dataclass(frozen=True)
class Tet10Tri6SurfacePressureContactResult:
    schema_version: str
    result_class: str
    displacement_mm: np.ndarray
    support_reactions_n: np.ndarray
    integration_point_stress_mpa: np.ndarray
    integration_point_von_mises_mpa: np.ndarray
    face_nodes: np.ndarray
    contact_normal: np.ndarray
    integration_barycentric: np.ndarray
    integration_weights_mm2: np.ndarray
    initial_gaps_mm: np.ndarray
    free_integration_displacements_mm: np.ndarray
    integration_displacements_mm: np.ndarray
    signed_gaps_mm: np.ndarray
    contact_pressure_mpa: np.ndarray
    contact_point_forces_n: np.ndarray
    contact_generalized_force_n: np.ndarray
    pressure_influence_mm_per_mpa: np.ndarray
    states: tuple[ContactState, ...]
    active_contact_indices: tuple[int, ...]
    active_set_history: tuple[tuple[int, ...], ...]
    iterations: int
    penetration_mm: np.ndarray
    complementarity_mpa_mm: np.ndarray
    free_equilibrium_residual_norm_n: float
    converged: bool
    exact_no_penetration: bool
    pressure_is_primary_contact_unknown: bool
    contact_pressure_recovered_from_nodal_reactions: bool
    surface_integration_contact_executed: bool
    deformable_tet10_contact: bool
    penalty_method_used: bool
    friction_solved: bool
    industrial_validation_claimed: bool
    ot1613_result_claimed: bool
    ansys_equivalence_claimed: bool


def tri6_shape_functions(barycentric: np.ndarray) -> np.ndarray:
    l = np.asarray(barycentric, dtype=float).reshape(-1)
    if l.size != 3 or not np.all(np.isfinite(l)):
        raise ValueError("barycentric must contain three finite values")
    if np.any(l < -1.0e-12) or abs(float(np.sum(l)) - 1.0) > 1.0e-10:
        raise ValueError("barycentric coordinates must lie in the triangle and sum to one")
    l1, l2, l3 = l
    return np.asarray(
        [
            l1 * (2.0 * l1 - 1.0),
            l2 * (2.0 * l2 - 1.0),
            l3 * (2.0 * l3 - 1.0),
            4.0 * l1 * l2,
            4.0 * l2 * l3,
            4.0 * l3 * l1,
        ],
        dtype=float,
    )


def _validate_surface_geometry(
    nodes_mm: np.ndarray,
    face_nodes: np.ndarray,
    contact_normal: np.ndarray,
) -> tuple[np.ndarray, float]:
    nodes = np.asarray(nodes_mm, dtype=float)
    face = np.asarray(face_nodes, dtype=int).reshape(-1)
    normal = np.asarray(contact_normal, dtype=float).reshape(-1)
    if face.size != 6 or np.unique(face).size != 6:
        raise ValueError("face_nodes must contain six unique TRI6 node indices")
    if np.any(face < 0) or np.any(face >= nodes.shape[0]):
        raise ValueError("face_nodes contains an out-of-range node index")
    if normal.size != 3 or not np.all(np.isfinite(normal)):
        raise ValueError("contact_normal must contain three finite components")
    normal_norm = float(np.linalg.norm(normal))
    if not math.isfinite(normal_norm) or normal_norm <= 0.0:
        raise ValueError("contact_normal must be non-zero")
    normal = normal / normal_norm

    xyz = nodes[face]
    corners = xyz[:3]
    area = triangle_area_mm2(corners)
    expected_mid = np.asarray(
        [
            0.5 * (corners[0] + corners[1]),
            0.5 * (corners[1] + corners[2]),
            0.5 * (corners[2] + corners[0]),
        ],
        dtype=float,
    )
    scale = max(float(np.linalg.norm(corners.max(axis=0) - corners.min(axis=0))), 1.0)
    if not np.allclose(xyz[3:], expected_mid, rtol=0.0, atol=scale * 1.0e-10):
        raise ValueError("GAP-G is limited to a straight-sided TRI6 face")

    geometric_normal = np.cross(corners[1] - corners[0], corners[2] - corners[0])
    geometric_normal /= np.linalg.norm(geometric_normal)
    alignment = abs(float(geometric_normal @ normal))
    if alignment < 1.0 - 1.0e-10:
        raise ValueError("contact_normal must be perpendicular to the TRI6 face")
    return normal, area


def tri6_surface_operator(
    *,
    nodes_mm: np.ndarray,
    face_nodes: list[int] | np.ndarray,
    contact_normal: list[float] | np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return H, barycentric points and physical integration weights.

    ``H @ u`` is the normal closing displacement at the three quadratic-triangle
    integration points. The three-point rule integrates all quadratic TRI6 shape
    functions exactly on a straight-sided planar face.
    """

    nodes = np.asarray(nodes_mm, dtype=float)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise ValueError("nodes_mm must be a finite (n, 3) array")
    face = np.asarray(face_nodes, dtype=int).reshape(-1)
    normal, area = _validate_surface_geometry(nodes, face, np.asarray(contact_normal, dtype=float))
    ndof = nodes.shape[0] * 3
    operator = np.zeros((3, ndof), dtype=float)
    for q, bary in enumerate(TRI6_GAUSS_BARYCENTRIC):
        shape = tri6_shape_functions(bary)
        for local_index, node in enumerate(face):
            operator[q, 3 * int(node) : 3 * int(node) + 3] += shape[local_index] * normal
    weights = np.full(3, area / 3.0, dtype=float)
    return operator, TRI6_GAUSS_BARYCENTRIC.copy(), weights


def tri6_surface_pressure_generalized_force(
    *,
    nodes_mm: np.ndarray,
    face_nodes: list[int] | np.ndarray,
    contact_normal: list[float] | np.ndarray,
    pressure_mpa: list[float] | np.ndarray,
) -> np.ndarray:
    """Consistent closing generalized force generated by three IP pressures.

    Because 1 MPa = 1 N/mm^2, ``H.T @ (w * p)`` is directly in newtons.
    This function returns the *closing* force direction. Contact applies its
    negative to the deformable body.
    """

    pressure = np.asarray(pressure_mpa, dtype=float).reshape(-1)
    if pressure.size != 3 or not np.all(np.isfinite(pressure)):
        raise ValueError("pressure_mpa must contain three finite integration-point values")
    operator, _, weights = tri6_surface_operator(
        nodes_mm=nodes_mm,
        face_nodes=face_nodes,
        contact_normal=contact_normal,
    )
    return np.asarray(operator.T @ (weights * pressure), dtype=float).reshape(-1)


def _validate_tolerance(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return value


def solve_tet10_tri6_surface_pressure_contact(
    *,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    material: IsotropicMaterial,
    loads_n: np.ndarray,
    fixed_dofs: list[int] | np.ndarray,
    face_nodes: list[int] | np.ndarray,
    contact_normal: list[float] | np.ndarray,
    initial_gaps_mm: list[float] | np.ndarray,
    pressure_tolerance_mpa: float = 1.0e-9,
    gap_tolerance_mm: float = 1.0e-10,
    equilibrium_tolerance_n: float = 1.0e-6,
    max_iterations: int = 30,
) -> Tet10Tri6SurfacePressureContactResult:
    """Solve frictionless TRI6 normal contact with pressure primary at surface IPs.

    The unknowns are three non-negative normal pressures at the standard
    three-point quadratic-triangle integration rule. They enter equilibrium as
    physical surface tractions, not as post-processed nodal reactions::

        K u = F - H^T W p
        g = g0 - H u >= 0
        p >= 0
        g * p = 0

    The deterministic active set solves the condensed pressure equations exactly
    for the current active integration points. No penalty stiffness and no
    artificial penetration are introduced.

    This is a synthetic single-face verification kernel. It is not yet a
    multi-face surface-to-surface industrial contact implementation.
    """

    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=int)
    loads = np.asarray(loads_n, dtype=float).reshape(-1)
    fixed = np.unique(np.asarray(fixed_dofs, dtype=int).reshape(-1))
    face = np.asarray(face_nodes, dtype=int).reshape(-1)
    gaps = np.asarray(initial_gaps_mm, dtype=float).reshape(-1)
    pressure_tol = _validate_tolerance(pressure_tolerance_mpa, "pressure_tolerance_mpa")
    gap_tol = _validate_tolerance(gap_tolerance_mm, "gap_tolerance_mm")
    equilibrium_tol = _validate_tolerance(equilibrium_tolerance_n, "equilibrium_tolerance_n")

    if not isinstance(max_iterations, int) or max_iterations <= 0:
        raise ValueError("max_iterations must be a positive integer")
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise ValueError("nodes_mm must be a finite (n, 3) array")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("elements must have shape (m, 10)")
    ndof = nodes.shape[0] * 3
    if loads.size != ndof or not np.all(np.isfinite(loads)):
        raise ValueError("loads_n must be finite and contain 3 DOFs per node")
    if fixed.size == 0 or np.any(fixed < 0) or np.any(fixed >= ndof):
        raise ValueError("fixed_dofs must contain valid support DOFs")
    if gaps.size != 3 or not np.all(np.isfinite(gaps)) or np.any(gaps < 0.0):
        raise ValueError("initial_gaps_mm must contain three finite non-negative values")

    operator, barycentric, weights = tri6_surface_operator(
        nodes_mm=nodes,
        face_nodes=face,
        contact_normal=contact_normal,
    )
    normal, _ = _validate_surface_geometry(nodes, face, np.asarray(contact_normal, dtype=float))
    stiffness = assemble_global_stiffness_sparse_tet10(nodes, elems, material)

    free_u, _, free_dofs = _solve_with_prescribed_dofs(
        stiffness,
        loads,
        fixed,
        np.zeros(fixed.size, dtype=float),
    )
    free_ip = np.asarray(operator @ free_u, dtype=float).reshape(-1)

    # One column is the displacement field caused by +1 MPa closing pressure at
    # one surface integration point. Contact uses the negative of this field.
    influence_fields = np.zeros((ndof, 3), dtype=float)
    pressure_influence = np.zeros((3, 3), dtype=float)
    for q in range(3):
        unit_pressure_load = operator[q] * weights[q]
        unit_u, _, _ = _solve_with_prescribed_dofs(
            stiffness,
            unit_pressure_load,
            fixed,
            np.zeros(fixed.size, dtype=float),
        )
        influence_fields[:, q] = unit_u
        pressure_influence[:, q] = np.asarray(operator @ unit_u, dtype=float).reshape(-1)

    if not np.all(np.isfinite(pressure_influence)):
        raise ArithmeticError("surface pressure influence matrix is non-finite")
    if np.any(np.diag(pressure_influence) <= 0.0):
        raise ArithmeticError("surface pressure influence matrix has non-positive diagonal compliance")

    active: set[int] = {
        int(index)
        for index in np.flatnonzero(free_ip > gaps + gap_tol)
    }
    history: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    pressure = np.zeros(3, dtype=float)
    displacement_vector = free_u.copy()
    converged = False

    for iteration in range(1, max_iterations + 1):
        signature = tuple(sorted(active))
        if signature in seen:
            raise ArithmeticError(f"surface pressure active-set cycle detected at {signature}")
        seen.add(signature)
        history.append(signature)

        pressure = np.zeros(3, dtype=float)
        if active:
            indices = np.asarray(sorted(active), dtype=int)
            block = pressure_influence[np.ix_(indices, indices)]
            rhs = free_ip[indices] - gaps[indices]
            try:
                pressure[indices] = np.linalg.solve(block, rhs)
            except np.linalg.LinAlgError as exc:
                raise ArithmeticError("active surface pressure block is singular") from exc

        displacement_vector = free_u - influence_fields @ pressure
        ip_displacement = np.asarray(operator @ displacement_vector, dtype=float).reshape(-1)
        signed_gaps = gaps - ip_displacement

        to_add = {
            int(index)
            for index in np.flatnonzero(signed_gaps < -gap_tol)
            if int(index) not in active
        }
        to_remove = {
            int(index)
            for index in active
            if pressure[index] < -pressure_tol
        }
        updated = (active | to_add) - to_remove
        if updated == active:
            converged = True
            break
        active = updated
    else:
        iteration = max_iterations

    if not converged:
        raise ArithmeticError("surface pressure active set did not converge")

    pressure[np.abs(pressure) <= pressure_tol] = 0.0
    ip_displacement = np.asarray(operator @ displacement_vector, dtype=float).reshape(-1)
    signed_gaps = gaps - ip_displacement
    signed_gaps[np.abs(signed_gaps) <= gap_tol] = 0.0
    penetration = np.maximum(-signed_gaps, 0.0)
    complementarity = signed_gaps * pressure

    if np.any(pressure < -pressure_tol):
        raise ArithmeticError("surface contact produced tensile pressure")
    if np.any(signed_gaps < -gap_tol):
        raise ArithmeticError("surface contact violated no-penetration")
    comp_tol = np.maximum(
        pressure_tol * np.maximum(gaps, gap_tol),
        gap_tol * np.maximum(pressure, 1.0),
    )
    if np.any(np.abs(complementarity) > comp_tol):
        raise ArithmeticError("surface pressure Signorini complementarity failed")

    contact_point_forces = weights * pressure
    closing_contact_force = np.asarray(operator.T @ contact_point_forces, dtype=float).reshape(-1)
    equilibrium = np.asarray(stiffness @ displacement_vector - loads + closing_contact_force, dtype=float).reshape(-1)
    free_residual = float(np.linalg.norm(equilibrium[free_dofs]))
    if free_residual > equilibrium_tol * max(1.0, math.sqrt(float(free_dofs.size))):
        raise ArithmeticError("surface contact free-DOF equilibrium residual exceeded tolerance")

    states: list[ContactState] = []
    for gap, value in zip(signed_gaps, pressure):
        if value > pressure_tol:
            states.append(ContactState.ACTIVE)
        elif gap <= gap_tol:
            states.append(ContactState.TOUCHING_ZERO_REACTION)
        else:
            states.append(ContactState.OPEN)

    displacement = displacement_vector.reshape((-1, 3))
    ip_stress, ip_mises = _recover_tet10_stress(nodes, elems, displacement, material)

    return Tet10Tri6SurfacePressureContactResult(
        schema_version="AsterMaxTet10Tri6SurfacePressureContactV1",
        result_class="SYNTHETIC_TET10_TRI6_INTEGRATION_POINT_NORMAL_CONTACT_NOT_INDUSTRIAL_RESULT",
        displacement_mm=displacement,
        support_reactions_n=equilibrium.reshape((-1, 3)),
        integration_point_stress_mpa=ip_stress,
        integration_point_von_mises_mpa=ip_mises,
        face_nodes=face.copy(),
        contact_normal=normal.copy(),
        integration_barycentric=barycentric,
        integration_weights_mm2=weights,
        initial_gaps_mm=gaps.copy(),
        free_integration_displacements_mm=free_ip,
        integration_displacements_mm=ip_displacement,
        signed_gaps_mm=signed_gaps,
        contact_pressure_mpa=pressure,
        contact_point_forces_n=contact_point_forces,
        contact_generalized_force_n=closing_contact_force.reshape((-1, 3)),
        pressure_influence_mm_per_mpa=pressure_influence,
        states=tuple(states),
        active_contact_indices=tuple(int(i) for i in np.flatnonzero(pressure > pressure_tol)),
        active_set_history=tuple(history),
        iterations=iteration,
        penetration_mm=penetration,
        complementarity_mpa_mm=complementarity,
        free_equilibrium_residual_norm_n=free_residual,
        converged=True,
        exact_no_penetration=bool(np.all(penetration <= gap_tol)),
        pressure_is_primary_contact_unknown=True,
        contact_pressure_recovered_from_nodal_reactions=False,
        surface_integration_contact_executed=True,
        deformable_tet10_contact=True,
        penalty_method_used=False,
        friction_solved=False,
        industrial_validation_claimed=False,
        ot1613_result_claimed=False,
        ansys_equivalence_claimed=False,
    )
