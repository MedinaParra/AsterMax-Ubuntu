from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np

from astermax.fea.solver import assemble_global_stiffness_sparse_tet10
from astermax.fea.tet4 import IsotropicMaterial

from .tet10_unilateral import _recover_tet10_stress, _solve_with_prescribed_dofs
from .tri6_surface_contact import (
    TRI6_GAUSS_BARYCENTRIC,
    tri6_shape_functions,
    tri6_surface_operator,
)
from .unilateral import ContactState


@dataclass(frozen=True)
class Tri6SourceFace:
    face_id: str
    node_indices: np.ndarray
    contact_normal: np.ndarray


@dataclass(frozen=True)
class RigidTri6TargetFace:
    face_id: str
    nodes_mm: np.ndarray


@dataclass(frozen=True)
class SurfacePairingRecord:
    source_face_id: str
    source_face_index: int
    integration_point_index: int
    target_face_id: str
    target_face_index: int
    source_point_mm: np.ndarray
    target_point_mm: np.ndarray
    initial_gap_mm: float
    source_normal: np.ndarray
    target_normal: np.ndarray
    target_barycentric: np.ndarray


@dataclass(frozen=True)
class Tet10MultifaceSurfaceContactResult:
    schema_version: str
    result_class: str
    displacement_mm: np.ndarray
    support_reactions_n: np.ndarray
    integration_point_stress_mpa: np.ndarray
    integration_point_von_mises_mpa: np.ndarray
    pairing_records: tuple[SurfacePairingRecord, ...]
    source_face_ids: tuple[str, ...]
    contact_operator: np.ndarray
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
    geometric_surface_search_executed: bool
    multiple_source_faces_executed: bool
    target_surfaces_rigid: bool
    pairing_frozen_small_displacement: bool
    contact_pressure_recovered_from_nodal_reactions: bool
    penalty_method_used: bool
    friction_solved: bool
    industrial_validation_claimed: bool
    ot1613_result_claimed: bool
    ansys_equivalence_claimed: bool


def _face_id(value: str, name: str) -> str:
    value = str(value).strip()
    if not value:
        raise ValueError(f"{name} must be non-empty")
    return value


def _straight_tri6_geometry(nodes_mm: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    xyz = np.asarray(nodes_mm, dtype=float)
    if xyz.shape != (6, 3) or not np.all(np.isfinite(xyz)):
        raise ValueError("TRI6 face geometry must be a finite (6, 3) array")
    corners = xyz[:3]
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
        raise ValueError("GAP-H is limited to straight-sided TRI6 faces")
    cross = np.cross(corners[1] - corners[0], corners[2] - corners[0])
    norm = float(np.linalg.norm(cross))
    if not math.isfinite(norm) or norm <= 0.0:
        raise ValueError("TRI6 target face is degenerate")
    normal = cross / norm
    return corners, normal, 0.5 * norm


def _point_barycentric_on_triangle(point: np.ndarray, corners: np.ndarray) -> np.ndarray:
    a, b, c = np.asarray(corners, dtype=float)
    p = np.asarray(point, dtype=float)
    v0 = b - a
    v1 = c - a
    v2 = p - a
    d00 = float(v0 @ v0)
    d01 = float(v0 @ v1)
    d11 = float(v1 @ v1)
    d20 = float(v2 @ v0)
    d21 = float(v2 @ v1)
    denominator = d00 * d11 - d01 * d01
    if not math.isfinite(denominator) or denominator <= 0.0:
        raise ValueError("triangle barycentric denominator is non-positive")
    l2 = (d11 * d20 - d01 * d21) / denominator
    l3 = (d00 * d21 - d01 * d20) / denominator
    l1 = 1.0 - l2 - l3
    return np.asarray([l1, l2, l3], dtype=float)


def _source_face_data(
    nodes_mm: np.ndarray,
    source: Tri6SourceFace,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    face_id = _face_id(source.face_id, "source face_id")
    face_nodes = np.asarray(source.node_indices, dtype=int).reshape(-1)
    if face_nodes.size != 6 or np.unique(face_nodes).size != 6:
        raise ValueError(f"source face {face_id} must contain six unique node indices")
    if np.any(face_nodes < 0) or np.any(face_nodes >= nodes_mm.shape[0]):
        raise ValueError(f"source face {face_id} contains an out-of-range node index")
    normal = np.asarray(source.contact_normal, dtype=float).reshape(-1)
    if normal.size != 3 or not np.all(np.isfinite(normal)):
        raise ValueError(f"source face {face_id} contact_normal must contain three finite values")
    norm = float(np.linalg.norm(normal))
    if norm <= 0.0:
        raise ValueError(f"source face {face_id} contact_normal must be non-zero")
    normal = normal / norm
    operator, barycentric, weights = tri6_surface_operator(
        nodes_mm=nodes_mm,
        face_nodes=face_nodes,
        contact_normal=normal,
    )
    source_xyz = np.asarray(nodes_mm, dtype=float)[face_nodes]
    points = np.asarray(
        [tri6_shape_functions(bary) @ source_xyz for bary in barycentric],
        dtype=float,
    )
    return operator, weights, points, normal


def find_tri6_surface_pairs(
    *,
    nodes_mm: np.ndarray,
    source_faces: Sequence[Tri6SourceFace],
    target_faces: Sequence[RigidTri6TargetFace],
    max_search_distance_mm: float,
    ambiguity_tolerance_mm: float = 1.0e-10,
    containment_tolerance: float = 1.0e-10,
    minimum_opposed_normal_cosine: float = 0.95,
) -> tuple[SurfacePairingRecord, ...]:
    """Pair each source TRI6 integration point to the nearest admissible target.

    Search is a forward ray projection along each declared source contact normal.
    A candidate target must be straight-sided, face the source, intersect the ray
    in front of the source within ``max_search_distance_mm`` and contain the
    projected point inside its corner triangle. Equal-distance candidates within
    ``ambiguity_tolerance_mm`` fail closed instead of being tie-broken silently.
    """

    nodes = np.asarray(nodes_mm, dtype=float)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise ValueError("nodes_mm must be a finite (n, 3) array")
    if not source_faces:
        raise ValueError("at least one source face is required")
    if not target_faces:
        raise ValueError("at least one target face is required")
    max_distance = float(max_search_distance_mm)
    ambiguity = float(ambiguity_tolerance_mm)
    containment = float(containment_tolerance)
    opposed_cosine = float(minimum_opposed_normal_cosine)
    if not math.isfinite(max_distance) or max_distance <= 0.0:
        raise ValueError("max_search_distance_mm must be finite and positive")
    if not math.isfinite(ambiguity) or ambiguity < 0.0:
        raise ValueError("ambiguity_tolerance_mm must be finite and non-negative")
    if not math.isfinite(containment) or containment < 0.0:
        raise ValueError("containment_tolerance must be finite and non-negative")
    if not math.isfinite(opposed_cosine) or opposed_cosine <= 0.0 or opposed_cosine > 1.0:
        raise ValueError("minimum_opposed_normal_cosine must lie in (0, 1]")

    source_ids = [_face_id(face.face_id, "source face_id") for face in source_faces]
    target_ids = [_face_id(face.face_id, "target face_id") for face in target_faces]
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("source face IDs must be unique")
    if len(set(target_ids)) != len(target_ids):
        raise ValueError("target face IDs must be unique")

    target_geometry: list[tuple[np.ndarray, np.ndarray]] = []
    for target in target_faces:
        corners, normal, _ = _straight_tri6_geometry(target.nodes_mm)
        target_geometry.append((corners, normal))

    records: list[SurfacePairingRecord] = []
    for source_index, source in enumerate(source_faces):
        _, _, source_points, source_normal = _source_face_data(nodes, source)
        for ip_index, source_point in enumerate(source_points):
            candidates: list[tuple[float, int, np.ndarray, np.ndarray, np.ndarray]] = []
            for target_index, target in enumerate(target_faces):
                corners, target_normal = target_geometry[target_index]
                alignment = float(source_normal @ target_normal)
                if alignment > -opposed_cosine:
                    continue
                denominator = alignment
                numerator = float((corners[0] - source_point) @ target_normal)
                gap = numerator / denominator
                if gap < -ambiguity or gap > max_distance:
                    continue
                if abs(gap) <= ambiguity:
                    gap = 0.0
                projected = source_point + gap * source_normal
                barycentric = _point_barycentric_on_triangle(projected, corners)
                if np.any(barycentric < -containment) or np.any(barycentric > 1.0 + containment):
                    continue
                plane_error = abs(float((projected - corners[0]) @ target_normal))
                geometry_scale = max(float(np.linalg.norm(corners.max(axis=0) - corners.min(axis=0))), 1.0)
                if plane_error > geometry_scale * 1.0e-10:
                    continue
                candidates.append((gap, target_index, projected, target_normal, barycentric))

            if not candidates:
                raise ValueError(
                    f"no admissible target for source face {source.face_id} integration point {ip_index}"
                )
            candidates.sort(key=lambda item: (item[0], target_ids[item[1]]))
            if len(candidates) > 1 and abs(candidates[1][0] - candidates[0][0]) <= ambiguity:
                raise ValueError(
                    f"ambiguous target pairing for source face {source.face_id} integration point {ip_index}"
                )
            gap, target_index, projected, target_normal, barycentric = candidates[0]
            records.append(
                SurfacePairingRecord(
                    source_face_id=source.face_id,
                    source_face_index=source_index,
                    integration_point_index=ip_index,
                    target_face_id=target_faces[target_index].face_id,
                    target_face_index=target_index,
                    source_point_mm=np.asarray(source_point, dtype=float),
                    target_point_mm=np.asarray(projected, dtype=float),
                    initial_gap_mm=float(gap),
                    source_normal=source_normal.copy(),
                    target_normal=np.asarray(target_normal, dtype=float).copy(),
                    target_barycentric=np.asarray(barycentric, dtype=float),
                )
            )
    return tuple(records)


def solve_tet10_multiface_surface_contact(
    *,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    material: IsotropicMaterial,
    loads_n: np.ndarray,
    fixed_dofs: list[int] | np.ndarray,
    source_faces: Sequence[Tri6SourceFace],
    target_faces: Sequence[RigidTri6TargetFace],
    max_search_distance_mm: float,
    ambiguity_tolerance_mm: float = 1.0e-10,
    pressure_tolerance_mpa: float = 1.0e-9,
    gap_tolerance_mm: float = 1.0e-10,
    equilibrium_tolerance_n: float = 1.0e-6,
    max_iterations: int = 50,
) -> Tet10MultifaceSurfaceContactResult:
    """Small-displacement multiface TET10/TRI6 frictionless contact verification.

    Multiple deformable source TRI6 faces are geometrically paired to rigid TRI6
    target faces in the undeformed configuration. The pair map is then frozen for
    this small-displacement gate. A single global pressure complementarity problem
    is solved across all source integration points using primary pressures in MPa.

    This deliberately does not claim large-sliding pair updates or deformable
    master surfaces; those remain subsequent verification gates.
    """

    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=int)
    loads = np.asarray(loads_n, dtype=float).reshape(-1)
    fixed = np.unique(np.asarray(fixed_dofs, dtype=int).reshape(-1))
    pressure_tol = float(pressure_tolerance_mpa)
    gap_tol = float(gap_tolerance_mm)
    equilibrium_tol = float(equilibrium_tolerance_n)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise ValueError("nodes_mm must be a finite (n, 3) array")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("elements must have shape (m, 10)")
    ndof = nodes.shape[0] * 3
    if loads.size != ndof or not np.all(np.isfinite(loads)):
        raise ValueError("loads_n must be finite and contain 3 DOFs per node")
    if fixed.size == 0 or np.any(fixed < 0) or np.any(fixed >= ndof):
        raise ValueError("fixed_dofs must contain valid support DOFs")
    for value, name in (
        (pressure_tol, "pressure_tolerance_mpa"),
        (gap_tol, "gap_tolerance_mm"),
        (equilibrium_tol, "equilibrium_tolerance_n"),
    ):
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"{name} must be finite and non-negative")
    if not isinstance(max_iterations, int) or max_iterations <= 0:
        raise ValueError("max_iterations must be a positive integer")

    pairing_records = find_tri6_surface_pairs(
        nodes_mm=nodes,
        source_faces=source_faces,
        target_faces=target_faces,
        max_search_distance_mm=max_search_distance_mm,
        ambiguity_tolerance_mm=ambiguity_tolerance_mm,
    )

    operators: list[np.ndarray] = []
    weights: list[float] = []
    source_ids: list[str] = []
    for source in source_faces:
        operator, source_weights, _, _ = _source_face_data(nodes, source)
        operators.extend(operator)
        weights.extend(source_weights.tolist())
        source_ids.append(source.face_id)
    contact_operator = np.asarray(operators, dtype=float)
    integration_weights = np.asarray(weights, dtype=float)
    initial_gaps = np.asarray([record.initial_gap_mm for record in pairing_records], dtype=float)
    ncontact = contact_operator.shape[0]
    if ncontact != len(pairing_records) or integration_weights.size != ncontact:
        raise ArithmeticError("surface search/order mismatch with contact operator")

    stiffness = assemble_global_stiffness_sparse_tet10(nodes, elems, material)
    free_u, _, free_dofs = _solve_with_prescribed_dofs(
        stiffness,
        loads,
        fixed,
        np.zeros(fixed.size, dtype=float),
    )
    free_ip = np.asarray(contact_operator @ free_u, dtype=float).reshape(-1)

    influence_fields = np.zeros((ndof, ncontact), dtype=float)
    pressure_influence = np.zeros((ncontact, ncontact), dtype=float)
    for q in range(ncontact):
        unit_pressure_load = contact_operator[q] * integration_weights[q]
        unit_u, _, _ = _solve_with_prescribed_dofs(
            stiffness,
            unit_pressure_load,
            fixed,
            np.zeros(fixed.size, dtype=float),
        )
        influence_fields[:, q] = unit_u
        pressure_influence[:, q] = contact_operator @ unit_u
    if not np.all(np.isfinite(pressure_influence)):
        raise ArithmeticError("multiface pressure influence matrix is non-finite")
    if np.any(np.diag(pressure_influence) <= 0.0):
        raise ArithmeticError("multiface pressure influence has non-positive diagonal compliance")

    active: set[int] = {
        int(index) for index in np.flatnonzero(free_ip > initial_gaps + gap_tol)
    }
    history: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    pressure = np.zeros(ncontact, dtype=float)
    displacement_vector = free_u.copy()
    converged = False

    for iteration in range(1, max_iterations + 1):
        signature = tuple(sorted(active))
        if signature in seen:
            raise ArithmeticError(f"multiface surface active-set cycle detected at {signature}")
        seen.add(signature)
        history.append(signature)
        pressure = np.zeros(ncontact, dtype=float)
        if active:
            indices = np.asarray(sorted(active), dtype=int)
            block = pressure_influence[np.ix_(indices, indices)]
            rhs = free_ip[indices] - initial_gaps[indices]
            try:
                pressure[indices] = np.linalg.solve(block, rhs)
            except np.linalg.LinAlgError as exc:
                raise ArithmeticError("active multiface pressure block is singular") from exc

        displacement_vector = free_u - influence_fields @ pressure
        ip_displacement = contact_operator @ displacement_vector
        signed_gaps = initial_gaps - ip_displacement
        to_add = {
            int(index)
            for index in np.flatnonzero(signed_gaps < -gap_tol)
            if int(index) not in active
        }
        to_remove = {
            int(index) for index in active if pressure[index] < -pressure_tol
        }
        updated = (active | to_add) - to_remove
        if updated == active:
            converged = True
            break
        active = updated
    else:
        iteration = max_iterations

    if not converged:
        raise ArithmeticError("multiface surface active set did not converge")

    pressure[np.abs(pressure) <= pressure_tol] = 0.0
    ip_displacement = np.asarray(contact_operator @ displacement_vector, dtype=float).reshape(-1)
    signed_gaps = initial_gaps - ip_displacement
    signed_gaps[np.abs(signed_gaps) <= gap_tol] = 0.0
    penetration = np.maximum(-signed_gaps, 0.0)
    complementarity = signed_gaps * pressure
    if np.any(pressure < -pressure_tol):
        raise ArithmeticError("multiface contact produced tensile pressure")
    if np.any(signed_gaps < -gap_tol):
        raise ArithmeticError("multiface contact violated no-penetration")
    comp_tol = np.maximum(
        pressure_tol * np.maximum(initial_gaps, gap_tol),
        gap_tol * np.maximum(pressure, 1.0),
    )
    if np.any(np.abs(complementarity) > comp_tol):
        raise ArithmeticError("multiface Signorini complementarity failed")

    contact_point_forces = integration_weights * pressure
    closing_contact_force = contact_operator.T @ contact_point_forces
    equilibrium = np.asarray(
        stiffness @ displacement_vector - loads + closing_contact_force,
        dtype=float,
    ).reshape(-1)
    free_residual = float(np.linalg.norm(equilibrium[free_dofs]))
    if free_residual > equilibrium_tol * max(1.0, math.sqrt(float(free_dofs.size))):
        raise ArithmeticError("multiface free-DOF equilibrium residual exceeded tolerance")

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
    return Tet10MultifaceSurfaceContactResult(
        schema_version="AsterMaxTet10MultifaceSurfaceContactV1",
        result_class="SYNTHETIC_TET10_MULTIFACE_TRI6_RIGID_TARGET_CONTACT_NOT_INDUSTRIAL_RESULT",
        displacement_mm=displacement,
        support_reactions_n=equilibrium.reshape((-1, 3)),
        integration_point_stress_mpa=ip_stress,
        integration_point_von_mises_mpa=ip_mises,
        pairing_records=pairing_records,
        source_face_ids=tuple(source_ids),
        contact_operator=contact_operator,
        integration_weights_mm2=integration_weights,
        initial_gaps_mm=initial_gaps,
        free_integration_displacements_mm=free_ip,
        integration_displacements_mm=ip_displacement,
        signed_gaps_mm=signed_gaps,
        contact_pressure_mpa=pressure,
        contact_point_forces_n=contact_point_forces,
        contact_generalized_force_n=np.asarray(closing_contact_force, dtype=float).reshape((-1, 3)),
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
        geometric_surface_search_executed=True,
        multiple_source_faces_executed=len(source_faces) > 1,
        target_surfaces_rigid=True,
        pairing_frozen_small_displacement=True,
        contact_pressure_recovered_from_nodal_reactions=False,
        penalty_method_used=False,
        friction_solved=False,
        industrial_validation_claimed=False,
        ot1613_result_claimed=False,
        ansys_equivalence_claimed=False,
    )
