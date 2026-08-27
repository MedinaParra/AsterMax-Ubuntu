from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np

from astermax.fea.solver import assemble_global_stiffness_sparse_tet10
from astermax.fea.tet4 import IsotropicMaterial

from .multiface_surface_contact import Tri6SourceFace, _face_id, _source_face_data
from .tet10_unilateral import _recover_tet10_stress, _solve_with_prescribed_dofs
from .tri6_surface_contact import TRI6_GAUSS_BARYCENTRIC, tri6_shape_functions
from .unilateral import ContactState


@dataclass(frozen=True)
class DeformableTri6TargetFace:
    face_id: str
    node_indices: np.ndarray


@dataclass(frozen=True)
class DeformableSurfacePairingRecord:
    source_face_id: str
    source_face_index: int
    integration_point_index: int
    target_face_id: str
    target_face_index: int
    source_point_mm: np.ndarray
    target_point_mm: np.ndarray
    current_gap_mm: float
    source_normal: np.ndarray
    target_normal: np.ndarray
    target_barycentric: np.ndarray
    newton_iterations: int
    newton_residual_mm: float


@dataclass(frozen=True)
class Tet10DeformableSurfaceContactResult:
    schema_version: str
    result_class: str
    displacement_mm: np.ndarray
    support_reactions_n: np.ndarray
    integration_point_stress_mpa: np.ndarray
    integration_point_von_mises_mpa: np.ndarray
    pairing_records: tuple[DeformableSurfacePairingRecord, ...]
    pairing_target_history: tuple[tuple[str, ...], ...]
    pairing_barycentric_history: tuple[np.ndarray, ...]
    source_operator: np.ndarray
    target_operator: np.ndarray
    relative_operator: np.ndarray
    integration_weights_mm2: np.ndarray
    reference_gaps_mm: np.ndarray
    free_relative_closure_mm: np.ndarray
    relative_closure_mm: np.ndarray
    signed_gaps_mm: np.ndarray
    contact_pressure_mpa: np.ndarray
    contact_point_forces_n: np.ndarray
    source_contact_generalized_force_n: np.ndarray
    target_contact_generalized_force_n: np.ndarray
    total_contact_generalized_force_n: np.ndarray
    net_contact_resultant_n: np.ndarray
    pressure_influence_mm_per_mpa: np.ndarray
    states: tuple[ContactState, ...]
    active_contact_indices: tuple[int, ...]
    active_set_history: tuple[tuple[int, ...], ...]
    inner_iterations: int
    outer_iterations: int
    penetration_mm: np.ndarray
    complementarity_mpa_mm: np.ndarray
    free_equilibrium_residual_norm_n: float
    max_pairing_barycentric_delta: float
    max_geometric_gap_consistency_error_mm: float
    converged: bool
    exact_no_penetration: bool
    pressure_is_primary_contact_unknown: bool
    geometric_surface_search_executed: bool
    target_surfaces_deformable: bool
    equal_and_opposite_contact_traction: bool
    pairing_updated_iteratively: bool
    contact_pressure_recovered_from_nodal_reactions: bool
    penalty_method_used: bool
    friction_solved: bool
    large_sliding_claimed: bool
    finite_strain_claimed: bool
    industrial_validation_claimed: bool
    ot1613_result_claimed: bool
    ansys_equivalence_claimed: bool


def _tri6_shape_derivatives_rs(barycentric: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    l1, l2, l3 = np.asarray(barycentric, dtype=float).reshape(3)
    dndr = np.asarray(
        [
            -(4.0 * l1 - 1.0),
            4.0 * l2 - 1.0,
            0.0,
            4.0 * (l1 - l2),
            4.0 * l3,
            -4.0 * l3,
        ],
        dtype=float,
    )
    dnds = np.asarray(
        [
            -(4.0 * l1 - 1.0),
            0.0,
            4.0 * l3 - 1.0,
            -4.0 * l2,
            4.0 * l2,
            4.0 * (l1 - l3),
        ],
        dtype=float,
    )
    return dndr, dnds


def _validated_face_nodes(
    nodes_mm: np.ndarray,
    node_indices: np.ndarray,
    *,
    face_id: str,
    role: str,
) -> np.ndarray:
    indices = np.asarray(node_indices, dtype=int).reshape(-1)
    if indices.size != 6 or np.unique(indices).size != 6:
        raise ValueError(f"{role} face {face_id} must contain six unique node indices")
    if np.any(indices < 0) or np.any(indices >= nodes_mm.shape[0]):
        raise ValueError(f"{role} face {face_id} contains an out-of-range node index")
    return indices


def _target_interpolation_row(
    *,
    ndof: int,
    target_nodes: np.ndarray,
    barycentric: np.ndarray,
    contact_normal: np.ndarray,
) -> np.ndarray:
    shape = tri6_shape_functions(barycentric)
    row = np.zeros(ndof, dtype=float)
    normal = np.asarray(contact_normal, dtype=float).reshape(3)
    for local_index, node in enumerate(np.asarray(target_nodes, dtype=int)):
        row[3 * int(node) : 3 * int(node) + 3] = shape[local_index] * normal
    return row


def _intersect_ray_with_deformed_tri6(
    *,
    source_point_mm: np.ndarray,
    source_normal: np.ndarray,
    target_xyz_mm: np.ndarray,
    max_tracking_distance_mm: float,
    containment_tolerance: float,
    minimum_opposed_normal_cosine: float,
    newton_tolerance_mm: float,
    max_newton_iterations: int,
) -> tuple[float, np.ndarray, np.ndarray, np.ndarray, int, float] | None:
    """Intersect a fixed-normal source ray with a genuinely deformed TRI6 target.

    Unknowns are target natural coordinates (r, s) and signed ray distance t.
    The nonlinear equation is

        X_target(r, s) - X_source - t*n_source = 0.

    Negative t is deliberately accepted within the tracking distance so a free
    trial penetration can still be paired and subsequently corrected by the
    Signorini solve. This is a tracking rule, not permission for final penetration.
    """

    source = np.asarray(source_point_mm, dtype=float).reshape(3)
    normal = np.asarray(source_normal, dtype=float).reshape(3)
    xyz = np.asarray(target_xyz_mm, dtype=float)
    if xyz.shape != (6, 3) or not np.all(np.isfinite(xyz)):
        raise ValueError("deformable TRI6 target geometry must be a finite (6, 3) array")

    corners = xyz[:3]
    corner_cross = np.cross(corners[1] - corners[0], corners[2] - corners[0])
    corner_norm = float(np.linalg.norm(corner_cross))
    if not math.isfinite(corner_norm) or corner_norm <= 0.0:
        raise ValueError("deformable TRI6 target corner triangle is degenerate")
    corner_normal = corner_cross / corner_norm
    alignment = float(normal @ corner_normal)
    if alignment > -minimum_opposed_normal_cosine:
        return None

    denominator = alignment
    t0 = float((corners[0] - source) @ corner_normal) / denominator
    projected = source + t0 * normal
    a, b, c = corners
    v0 = b - a
    v1 = c - a
    v2 = projected - a
    d00 = float(v0 @ v0)
    d01 = float(v0 @ v1)
    d11 = float(v1 @ v1)
    d20 = float(v2 @ v0)
    d21 = float(v2 @ v1)
    det = d00 * d11 - d01 * d01
    if not math.isfinite(det) or det <= 0.0:
        return None
    r0 = (d11 * d20 - d01 * d21) / det
    s0 = (d00 * d21 - d01 * d20) / det
    x = np.asarray([r0, s0, t0], dtype=float)

    residual_norm = math.inf
    for iteration in range(1, max_newton_iterations + 1):
        r, s, t = x
        bary = np.asarray([1.0 - r - s, r, s], dtype=float)
        shape = tri6_shape_functions(bary)
        dndr, dnds = _tri6_shape_derivatives_rs(bary)
        target_point = shape @ xyz
        residual = target_point - source - t * normal
        residual_norm = float(np.linalg.norm(residual))
        if residual_norm <= newton_tolerance_mm:
            break
        dxdr = dndr @ xyz
        dxds = dnds @ xyz
        jacobian = np.column_stack([dxdr, dxds, -normal])
        if not np.all(np.isfinite(jacobian)):
            return None
        try:
            delta = np.linalg.solve(jacobian, -residual)
        except np.linalg.LinAlgError:
            return None
        x += delta
        if not np.all(np.isfinite(x)):
            return None
    else:
        return None

    r, s, t = x
    bary = np.asarray([1.0 - r - s, r, s], dtype=float)
    if np.any(bary < -containment_tolerance) or np.any(bary > 1.0 + containment_tolerance):
        return None
    if abs(float(t)) > max_tracking_distance_mm:
        return None

    shape = tri6_shape_functions(bary)
    dndr, dnds = _tri6_shape_derivatives_rs(bary)
    target_point = shape @ xyz
    dxdr = dndr @ xyz
    dxds = dnds @ xyz
    local_cross = np.cross(dxdr, dxds)
    local_norm = float(np.linalg.norm(local_cross))
    if not math.isfinite(local_norm) or local_norm <= 0.0:
        return None
    target_normal = local_cross / local_norm
    if float(normal @ target_normal) > -minimum_opposed_normal_cosine:
        return None
    final_residual = float(np.linalg.norm(target_point - source - float(t) * normal))
    if final_residual > newton_tolerance_mm:
        return None
    return float(t), bary, target_point, target_normal, iteration, final_residual


def find_deformable_tri6_surface_pairs(
    *,
    nodes_mm: np.ndarray,
    displacement_mm: np.ndarray,
    source_faces: Sequence[Tri6SourceFace],
    target_faces: Sequence[DeformableTri6TargetFace],
    max_tracking_distance_mm: float,
    ambiguity_tolerance_mm: float = 1.0e-10,
    containment_tolerance: float = 1.0e-10,
    minimum_opposed_normal_cosine: float = 0.95,
    newton_tolerance_mm: float = 1.0e-11,
    max_newton_iterations: int = 25,
) -> tuple[DeformableSurfacePairingRecord, ...]:
    """Search deformable TRI6 targets on the current deformed geometry.

    The source integration points are evaluated on their deformed TRI6 geometry,
    while the declared source contact normal is held fixed for this small-strain
    verification gate. Target intersection uses the full quadratic TRI6 mapping.
    Equal-distance candidates fail closed.
    """

    nodes = np.asarray(nodes_mm, dtype=float)
    displacement = np.asarray(displacement_mm, dtype=float)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise ValueError("nodes_mm must be a finite (n, 3) array")
    if displacement.shape == (nodes.shape[0] * 3,):
        displacement = displacement.reshape((-1, 3))
    if displacement.shape != nodes.shape or not np.all(np.isfinite(displacement)):
        raise ValueError("displacement_mm must match nodes_mm shape or flattened DOFs")
    if not source_faces or not target_faces:
        raise ValueError("at least one source and one deformable target face are required")

    max_distance = float(max_tracking_distance_mm)
    ambiguity = float(ambiguity_tolerance_mm)
    containment = float(containment_tolerance)
    opposed_cosine = float(minimum_opposed_normal_cosine)
    newton_tol = float(newton_tolerance_mm)
    if not math.isfinite(max_distance) or max_distance <= 0.0:
        raise ValueError("max_tracking_distance_mm must be finite and positive")
    if not math.isfinite(ambiguity) or ambiguity < 0.0:
        raise ValueError("ambiguity_tolerance_mm must be finite and non-negative")
    if not math.isfinite(containment) or containment < 0.0:
        raise ValueError("containment_tolerance must be finite and non-negative")
    if not math.isfinite(opposed_cosine) or opposed_cosine <= 0.0 or opposed_cosine > 1.0:
        raise ValueError("minimum_opposed_normal_cosine must lie in (0, 1]")
    if not math.isfinite(newton_tol) or newton_tol <= 0.0:
        raise ValueError("newton_tolerance_mm must be finite and positive")
    if not isinstance(max_newton_iterations, int) or max_newton_iterations <= 0:
        raise ValueError("max_newton_iterations must be a positive integer")

    source_ids = [_face_id(face.face_id, "source face_id") for face in source_faces]
    target_ids = [_face_id(face.face_id, "target face_id") for face in target_faces]
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("source face IDs must be unique")
    if len(set(target_ids)) != len(target_ids):
        raise ValueError("target face IDs must be unique")

    deformed = nodes + displacement
    target_nodes_list: list[np.ndarray] = []
    target_xyz_list: list[np.ndarray] = []
    for target in target_faces:
        indices = _validated_face_nodes(
            nodes, target.node_indices, face_id=target.face_id, role="target"
        )
        target_nodes_list.append(indices)
        target_xyz_list.append(deformed[indices])

    records: list[DeformableSurfacePairingRecord] = []
    for source_index, source in enumerate(source_faces):
        source_id = _face_id(source.face_id, "source face_id")
        source_nodes = _validated_face_nodes(
            nodes, source.node_indices, face_id=source_id, role="source"
        )
        normal = np.asarray(source.contact_normal, dtype=float).reshape(-1)
        if normal.size != 3 or not np.all(np.isfinite(normal)):
            raise ValueError(f"source face {source_id} contact_normal must contain three finite values")
        norm = float(np.linalg.norm(normal))
        if norm <= 0.0:
            raise ValueError(f"source face {source_id} contact_normal must be non-zero")
        normal = normal / norm
        source_xyz = deformed[source_nodes]
        for ip_index, bary in enumerate(TRI6_GAUSS_BARYCENTRIC):
            source_point = tri6_shape_functions(bary) @ source_xyz
            candidates: list[
                tuple[
                    float,
                    float,
                    int,
                    np.ndarray,
                    np.ndarray,
                    np.ndarray,
                    int,
                    float,
                ]
            ] = []
            for target_index, target_xyz in enumerate(target_xyz_list):
                hit = _intersect_ray_with_deformed_tri6(
                    source_point_mm=source_point,
                    source_normal=normal,
                    target_xyz_mm=target_xyz,
                    max_tracking_distance_mm=max_distance,
                    containment_tolerance=containment,
                    minimum_opposed_normal_cosine=opposed_cosine,
                    newton_tolerance_mm=newton_tol,
                    max_newton_iterations=max_newton_iterations,
                )
                if hit is None:
                    continue
                gap, target_bary, target_point, target_normal, iterations, residual = hit
                candidates.append(
                    (
                        abs(gap),
                        gap,
                        target_index,
                        target_bary,
                        target_point,
                        target_normal,
                        iterations,
                        residual,
                    )
                )
            if not candidates:
                raise ValueError(
                    f"no admissible deformable target for source face {source_id} integration point {ip_index}"
                )
            candidates.sort(key=lambda item: (item[0], target_ids[item[2]]))
            if len(candidates) > 1 and abs(candidates[1][0] - candidates[0][0]) <= ambiguity:
                raise ValueError(
                    f"ambiguous deformable target pairing for source face {source_id} integration point {ip_index}"
                )
            _, gap, target_index, target_bary, target_point, target_normal, iterations, residual = candidates[0]
            records.append(
                DeformableSurfacePairingRecord(
                    source_face_id=source_id,
                    source_face_index=source_index,
                    integration_point_index=ip_index,
                    target_face_id=target_faces[target_index].face_id,
                    target_face_index=target_index,
                    source_point_mm=np.asarray(source_point, dtype=float),
                    target_point_mm=np.asarray(target_point, dtype=float),
                    current_gap_mm=float(gap),
                    source_normal=normal.copy(),
                    target_normal=np.asarray(target_normal, dtype=float).copy(),
                    target_barycentric=np.asarray(target_bary, dtype=float),
                    newton_iterations=int(iterations),
                    newton_residual_mm=float(residual),
                )
            )
    return tuple(records)


def _build_relative_contact_operators(
    *,
    nodes_mm: np.ndarray,
    source_faces: Sequence[Tri6SourceFace],
    target_faces: Sequence[DeformableTri6TargetFace],
    pairing_records: Sequence[DeformableSurfacePairingRecord],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    nodes = np.asarray(nodes_mm, dtype=float)
    ndof = nodes.shape[0] * 3
    source_rows: list[np.ndarray] = []
    target_rows: list[np.ndarray] = []
    weights: list[float] = []
    reference_gaps: list[float] = []
    expected_records = 3 * len(source_faces)
    if len(pairing_records) != expected_records:
        raise ArithmeticError("deformable pair count does not match source integration points")

    cursor = 0
    for source in source_faces:
        source_operator, source_weights, _, source_normal = _source_face_data(nodes, source)
        source_nodes = np.asarray(source.node_indices, dtype=int)
        source_ref_xyz = nodes[source_nodes]
        for local_ip, source_bary in enumerate(TRI6_GAUSS_BARYCENTRIC):
            record = pairing_records[cursor]
            if record.source_face_id != source.face_id or record.integration_point_index != local_ip:
                raise ArithmeticError("deformable pair ordering mismatch")
            target = target_faces[record.target_face_index]
            target_nodes = _validated_face_nodes(
                nodes, target.node_indices, face_id=target.face_id, role="target"
            )
            target_row = _target_interpolation_row(
                ndof=ndof,
                target_nodes=target_nodes,
                barycentric=record.target_barycentric,
                contact_normal=source_normal,
            )
            source_row = np.asarray(source_operator[local_ip], dtype=float)
            source_ref_point = tri6_shape_functions(source_bary) @ source_ref_xyz
            target_ref_point = tri6_shape_functions(record.target_barycentric) @ nodes[target_nodes]
            reference_gap = float((target_ref_point - source_ref_point) @ source_normal)
            source_rows.append(source_row)
            target_rows.append(target_row)
            weights.append(float(source_weights[local_ip]))
            reference_gaps.append(reference_gap)
            cursor += 1

    source_matrix = np.asarray(source_rows, dtype=float)
    target_matrix = np.asarray(target_rows, dtype=float)
    relative = source_matrix - target_matrix
    return (
        source_matrix,
        target_matrix,
        relative,
        np.asarray(weights, dtype=float),
        np.asarray(reference_gaps, dtype=float),
    )


def _solve_pressure_active_set(
    *,
    stiffness,
    free_u: np.ndarray,
    free_dofs: np.ndarray,
    fixed: np.ndarray,
    relative_operator: np.ndarray,
    weights: np.ndarray,
    reference_gaps: np.ndarray,
    pressure_tolerance_mpa: float,
    gap_tolerance_mm: float,
    max_iterations: int,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    tuple[int, ...],
    tuple[tuple[int, ...], ...],
    int,
]:
    ncontact = relative_operator.shape[0]
    ndof = free_u.size
    free_closure = np.asarray(relative_operator @ free_u, dtype=float).reshape(-1)
    influence_fields = np.zeros((ndof, ncontact), dtype=float)
    pressure_influence = np.zeros((ncontact, ncontact), dtype=float)
    for q in range(ncontact):
        unit_closing_load = relative_operator[q] * weights[q]
        unit_u, _, _ = _solve_with_prescribed_dofs(
            stiffness,
            unit_closing_load,
            fixed,
            np.zeros(fixed.size, dtype=float),
        )
        influence_fields[:, q] = unit_u
        pressure_influence[:, q] = relative_operator @ unit_u
    if not np.all(np.isfinite(pressure_influence)):
        raise ArithmeticError("deformable-master pressure influence matrix is non-finite")
    if np.any(np.diag(pressure_influence) <= 0.0):
        raise ArithmeticError("deformable-master pressure influence has non-positive diagonal compliance")

    active: set[int] = {
        int(index)
        for index in np.flatnonzero(free_closure > reference_gaps + gap_tolerance_mm)
    }
    history: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    pressure = np.zeros(ncontact, dtype=float)
    displacement = free_u.copy()

    for iteration in range(1, max_iterations + 1):
        signature = tuple(sorted(active))
        if signature in seen:
            raise ArithmeticError(f"deformable-master active-set cycle detected at {signature}")
        seen.add(signature)
        history.append(signature)
        pressure = np.zeros(ncontact, dtype=float)
        if active:
            indices = np.asarray(sorted(active), dtype=int)
            block = pressure_influence[np.ix_(indices, indices)]
            rhs = free_closure[indices] - reference_gaps[indices]
            try:
                pressure[indices] = np.linalg.solve(block, rhs)
            except np.linalg.LinAlgError as exc:
                raise ArithmeticError("active deformable-master pressure block is singular") from exc

        displacement = free_u - influence_fields @ pressure
        closure = np.asarray(relative_operator @ displacement, dtype=float).reshape(-1)
        signed_gaps = reference_gaps - closure
        to_add = {
            int(index)
            for index in np.flatnonzero(signed_gaps < -gap_tolerance_mm)
            if int(index) not in active
        }
        to_remove = {
            int(index)
            for index in active
            if pressure[index] < -pressure_tolerance_mpa
        }
        updated = (active | to_add) - to_remove
        if updated == active:
            pressure[np.abs(pressure) <= pressure_tolerance_mpa] = 0.0
            closure = np.asarray(relative_operator @ displacement, dtype=float).reshape(-1)
            signed_gaps = reference_gaps - closure
            signed_gaps[np.abs(signed_gaps) <= gap_tolerance_mm] = 0.0
            return (
                displacement,
                pressure,
                pressure_influence,
                free_closure,
                tuple(int(i) for i in np.flatnonzero(pressure > pressure_tolerance_mpa)),
                tuple(history),
                iteration,
            )
        active = updated

    raise ArithmeticError("deformable-master pressure active set did not converge")


def solve_tet10_deformable_surface_contact(
    *,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    material: IsotropicMaterial,
    loads_n: np.ndarray,
    fixed_dofs: list[int] | np.ndarray,
    source_faces: Sequence[Tri6SourceFace],
    target_faces: Sequence[DeformableTri6TargetFace],
    max_tracking_distance_mm: float,
    ambiguity_tolerance_mm: float = 1.0e-10,
    pressure_tolerance_mpa: float = 1.0e-9,
    gap_tolerance_mm: float = 1.0e-10,
    equilibrium_tolerance_n: float = 1.0e-6,
    pairing_barycentric_tolerance: float = 1.0e-9,
    pairing_displacement_tolerance_mm: float = 1.0e-9,
    geometric_gap_tolerance_mm: float = 1.0e-9,
    max_active_set_iterations: int = 50,
    max_pairing_iterations: int = 20,
) -> Tet10DeformableSurfaceContactResult:
    """Small-strain TET10/TRI6 contact with a deformable master and pair updates.

    GAP-I keeps pressure as the primary integration-point unknown, applies equal
    and opposite consistent normal tractions to both deformable sides, and
    re-searches the quadratic TRI6 master on the current deformed geometry until
    the pairing barycentrics and total displacement stabilize.

    The source normal is fixed and source-side quadrature is one-pass. Therefore
    this gate does not claim finite-strain or general large-sliding contact.
    """

    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=int)
    loads = np.asarray(loads_n, dtype=float).reshape(-1)
    fixed = np.unique(np.asarray(fixed_dofs, dtype=int).reshape(-1))
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise ValueError("nodes_mm must be a finite (n, 3) array")
    if elems.ndim != 2 or elems.shape[1] != 10:
        raise ValueError("elements must have shape (m, 10)")
    ndof = nodes.shape[0] * 3
    if loads.size != ndof or not np.all(np.isfinite(loads)):
        raise ValueError("loads_n must be finite and contain 3 DOFs per node")
    if fixed.size == 0 or np.any(fixed < 0) or np.any(fixed >= ndof):
        raise ValueError("fixed_dofs must contain valid support DOFs")
    if not source_faces or not target_faces:
        raise ValueError("at least one source and one deformable target are required")
    if not isinstance(max_active_set_iterations, int) or max_active_set_iterations <= 0:
        raise ValueError("max_active_set_iterations must be positive")
    if not isinstance(max_pairing_iterations, int) or max_pairing_iterations <= 0:
        raise ValueError("max_pairing_iterations must be positive")

    pressure_tol = float(pressure_tolerance_mpa)
    gap_tol = float(gap_tolerance_mm)
    equilibrium_tol = float(equilibrium_tolerance_n)
    bary_tol = float(pairing_barycentric_tolerance)
    displacement_tol = float(pairing_displacement_tolerance_mm)
    geometry_gap_tol = float(geometric_gap_tolerance_mm)
    for value, name in (
        (pressure_tol, "pressure_tolerance_mpa"),
        (gap_tol, "gap_tolerance_mm"),
        (equilibrium_tol, "equilibrium_tolerance_n"),
        (bary_tol, "pairing_barycentric_tolerance"),
        (displacement_tol, "pairing_displacement_tolerance_mm"),
        (geometry_gap_tol, "geometric_gap_tolerance_mm"),
    ):
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"{name} must be finite and non-negative")

    stiffness = assemble_global_stiffness_sparse_tet10(nodes, elems, material)
    free_u, _, free_dofs = _solve_with_prescribed_dofs(
        stiffness,
        loads,
        fixed,
        np.zeros(fixed.size, dtype=float),
    )
    current_u = free_u.copy()
    pairing_target_history: list[tuple[str, ...]] = []
    pairing_bary_history: list[np.ndarray] = []
    last_records: tuple[DeformableSurfacePairingRecord, ...] | None = None
    max_bary_delta = math.inf
    max_gap_consistency = math.inf
    final_source_operator = np.empty((0, ndof), dtype=float)
    final_target_operator = np.empty((0, ndof), dtype=float)
    final_relative_operator = np.empty((0, ndof), dtype=float)
    final_weights = np.empty(0, dtype=float)
    final_reference_gaps = np.empty(0, dtype=float)
    final_pressure_influence = np.empty((0, 0), dtype=float)
    final_free_closure = np.empty(0, dtype=float)
    final_pressure = np.empty(0, dtype=float)
    final_active: tuple[int, ...] = ()
    final_active_history: tuple[tuple[int, ...], ...] = ()
    final_inner_iterations = 0
    final_u = current_u.copy()

    for outer_iteration in range(1, max_pairing_iterations + 1):
        records = find_deformable_tri6_surface_pairs(
            nodes_mm=nodes,
            displacement_mm=current_u,
            source_faces=source_faces,
            target_faces=target_faces,
            max_tracking_distance_mm=max_tracking_distance_mm,
            ambiguity_tolerance_mm=ambiguity_tolerance_mm,
        )
        target_signature = tuple(record.target_face_id for record in records)
        bary_snapshot = np.asarray([record.target_barycentric for record in records], dtype=float)
        pairing_target_history.append(target_signature)
        pairing_bary_history.append(bary_snapshot.copy())

        source_operator, target_operator, relative_operator, weights, reference_gaps = (
            _build_relative_contact_operators(
                nodes_mm=nodes,
                source_faces=source_faces,
                target_faces=target_faces,
                pairing_records=records,
            )
        )
        (
            solved_u,
            pressure,
            pressure_influence,
            free_closure,
            active,
            active_history,
            inner_iterations,
        ) = _solve_pressure_active_set(
            stiffness=stiffness,
            free_u=free_u,
            free_dofs=free_dofs,
            fixed=fixed,
            relative_operator=relative_operator,
            weights=weights,
            reference_gaps=reference_gaps,
            pressure_tolerance_mpa=pressure_tol,
            gap_tolerance_mm=gap_tol,
            max_iterations=max_active_set_iterations,
        )

        updated_records = find_deformable_tri6_surface_pairs(
            nodes_mm=nodes,
            displacement_mm=solved_u,
            source_faces=source_faces,
            target_faces=target_faces,
            max_tracking_distance_mm=max_tracking_distance_mm,
            ambiguity_tolerance_mm=ambiguity_tolerance_mm,
        )
        updated_signature = tuple(record.target_face_id for record in updated_records)
        if updated_signature == target_signature:
            updated_bary = np.asarray(
                [record.target_barycentric for record in updated_records], dtype=float
            )
            max_bary_delta = float(np.max(np.abs(updated_bary - bary_snapshot)))
        else:
            max_bary_delta = math.inf

        closure = np.asarray(relative_operator @ solved_u, dtype=float).reshape(-1)
        signed_gaps = reference_gaps - closure
        searched_current_gaps = np.asarray(
            [record.current_gap_mm for record in updated_records], dtype=float
        )
        if updated_signature == target_signature and searched_current_gaps.size == signed_gaps.size:
            max_gap_consistency = float(np.max(np.abs(searched_current_gaps - signed_gaps)))
        else:
            max_gap_consistency = math.inf
        displacement_change = float(np.max(np.abs(solved_u - current_u)))

        final_source_operator = source_operator
        final_target_operator = target_operator
        final_relative_operator = relative_operator
        final_weights = weights
        final_reference_gaps = reference_gaps
        final_pressure_influence = pressure_influence
        final_free_closure = free_closure
        final_pressure = pressure
        final_active = active
        final_active_history = active_history
        final_inner_iterations = inner_iterations
        final_u = solved_u
        last_records = records

        pairing_stable = (
            updated_signature == target_signature
            and max_bary_delta <= bary_tol
            and max_gap_consistency <= geometry_gap_tol
            and displacement_change <= displacement_tol
        )
        if pairing_stable:
            break
        current_u = solved_u
    else:
        raise ArithmeticError("deformable-master pairing iteration did not converge")

    assert last_records is not None
    closure = np.asarray(final_relative_operator @ final_u, dtype=float).reshape(-1)
    signed_gaps = final_reference_gaps - closure
    signed_gaps[np.abs(signed_gaps) <= gap_tol] = 0.0
    penetration = np.maximum(-signed_gaps, 0.0)
    complementarity = signed_gaps * final_pressure
    if np.any(final_pressure < -pressure_tol):
        raise ArithmeticError("deformable-master contact produced tensile pressure")
    if np.any(signed_gaps < -gap_tol):
        raise ArithmeticError("deformable-master contact violated no-penetration")
    comp_tol = np.maximum(
        pressure_tol * np.maximum(np.abs(final_reference_gaps), gap_tol),
        gap_tol * np.maximum(final_pressure, 1.0),
    )
    if np.any(np.abs(complementarity) > comp_tol):
        raise ArithmeticError("deformable-master Signorini complementarity failed")

    point_forces = final_weights * final_pressure
    source_actual_force = -(final_source_operator.T @ point_forces)
    target_actual_force = final_target_operator.T @ point_forces
    total_contact_force = source_actual_force + target_actual_force
    net_contact_resultant = total_contact_force.reshape((-1, 3)).sum(axis=0)
    equal_opposite_tol = equilibrium_tol * max(1.0, math.sqrt(float(point_forces.size)))
    equal_and_opposite = float(np.linalg.norm(net_contact_resultant)) <= equal_opposite_tol
    if not equal_and_opposite:
        raise ArithmeticError("deformable-master contact traction is not globally equal and opposite")

    equilibrium = np.asarray(
        stiffness @ final_u - loads - total_contact_force,
        dtype=float,
    ).reshape(-1)
    free_residual = float(np.linalg.norm(equilibrium[free_dofs]))
    if free_residual > equilibrium_tol * max(1.0, math.sqrt(float(free_dofs.size))):
        raise ArithmeticError("deformable-master free-DOF equilibrium residual exceeded tolerance")

    states: list[ContactState] = []
    for gap, pressure in zip(signed_gaps, final_pressure):
        if pressure > pressure_tol:
            states.append(ContactState.ACTIVE)
        elif gap <= gap_tol:
            states.append(ContactState.TOUCHING_ZERO_REACTION)
        else:
            states.append(ContactState.OPEN)

    displacement = final_u.reshape((-1, 3))
    ip_stress, ip_mises = _recover_tet10_stress(nodes, elems, displacement, material)
    return Tet10DeformableSurfaceContactResult(
        schema_version="AsterMaxTet10DeformableSurfaceContactV1",
        result_class="SYNTHETIC_TET10_TRI6_DEFORMABLE_MASTER_UPDATED_PAIRING_NOT_INDUSTRIAL_RESULT",
        displacement_mm=displacement,
        support_reactions_n=equilibrium.reshape((-1, 3)),
        integration_point_stress_mpa=ip_stress,
        integration_point_von_mises_mpa=ip_mises,
        pairing_records=last_records,
        pairing_target_history=tuple(pairing_target_history),
        pairing_barycentric_history=tuple(pairing_bary_history),
        source_operator=final_source_operator,
        target_operator=final_target_operator,
        relative_operator=final_relative_operator,
        integration_weights_mm2=final_weights,
        reference_gaps_mm=final_reference_gaps,
        free_relative_closure_mm=final_free_closure,
        relative_closure_mm=closure,
        signed_gaps_mm=signed_gaps,
        contact_pressure_mpa=final_pressure,
        contact_point_forces_n=point_forces,
        source_contact_generalized_force_n=source_actual_force.reshape((-1, 3)),
        target_contact_generalized_force_n=target_actual_force.reshape((-1, 3)),
        total_contact_generalized_force_n=total_contact_force.reshape((-1, 3)),
        net_contact_resultant_n=net_contact_resultant,
        pressure_influence_mm_per_mpa=final_pressure_influence,
        states=tuple(states),
        active_contact_indices=final_active,
        active_set_history=final_active_history,
        inner_iterations=final_inner_iterations,
        outer_iterations=outer_iteration,
        penetration_mm=penetration,
        complementarity_mpa_mm=complementarity,
        free_equilibrium_residual_norm_n=free_residual,
        max_pairing_barycentric_delta=max_bary_delta,
        max_geometric_gap_consistency_error_mm=max_gap_consistency,
        converged=True,
        exact_no_penetration=bool(np.all(penetration <= gap_tol)),
        pressure_is_primary_contact_unknown=True,
        geometric_surface_search_executed=True,
        target_surfaces_deformable=True,
        equal_and_opposite_contact_traction=equal_and_opposite,
        pairing_updated_iteratively=outer_iteration > 1,
        contact_pressure_recovered_from_nodal_reactions=False,
        penalty_method_used=False,
        friction_solved=False,
        large_sliding_claimed=False,
        finite_strain_claimed=False,
        industrial_validation_claimed=False,
        ot1613_result_claimed=False,
        ansys_equivalence_claimed=False,
    )
