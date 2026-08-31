"""Coupled small-sliding frictionless node-to-TRI3 contact for AsterMax PMV.

This module bridges the verified node/TRI3 geometry kernel to the global structural
assembler.  It intentionally implements a *small-sliding* penalty formulation: the
master TRI3 normal and barycentric projection are frozen from the reference geometry
for each candidate pair.  The active set is updated from the current displacement.

For one slave node s and master TRI3 nodes m_i, define

    g(u) = g0 + q^T u
    q = [ n, -N1*n, -N2*n, -N3*n ]

where g0 is the signed reference gap, n is the oriented master normal and N_i are the
reference barycentric coordinates of the orthogonal projection.  Contact is active
only for an inside-triangle candidate with g < 0.  The penalty potential gives

    r_c = k_p * g * q
    K_c = k_p * q*q^T

so for a fixed active set

    (K + K_c) u = F - k_p*g0*q.

The physical contact force vector is -r_c and therefore has equal/opposite slave and
master resultants.  This is an auditable verification solver, not a production
large-sliding or frictional contact algorithm.
"""

from dataclasses import dataclass
import math
from typing import Mapping, Sequence

from .global_static import GlobalStaticError, _solve_dense, assemble_stiffness
from .surface_contact import SurfaceContactError, project_point_to_triangle


class GlobalSurfaceContactError(ValueError):
    """Raised when a coupled surface-contact verification model is invalid."""


@dataclass(frozen=True)
class NodeTriangleContactPair:
    slave_node: int
    master_nodes: tuple[int, int, int]
    penalty_stiffness_n_per_mm: float


@dataclass(frozen=True)
class SurfaceContactState:
    slave_node: int
    master_nodes: tuple[int, int, int]
    reference_gap_mm: float
    signed_gap_mm: float
    penetration_mm: float
    normal_force_n: float
    active: bool
    barycentric: tuple[float, float, float]
    normal: tuple[float, float, float]
    slave_force_n: tuple[float, float, float]
    master_nodal_forces_n: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]


@dataclass(frozen=True)
class GlobalSurfaceContactResult:
    displacements: tuple[float, ...]
    reactions: tuple[float, ...]
    residual: tuple[float, ...]
    contact_states: tuple[SurfaceContactState, ...]
    iterations: int
    converged: bool


@dataclass(frozen=True)
class _PreparedPair:
    definition: NodeTriangleContactPair
    reference_gap_mm: float
    barycentric: tuple[float, float, float]
    normal: tuple[float, float, float]
    q: tuple[float, ...]
    inside_triangle: bool


def _validate_matrix(stiffness: Sequence[Sequence[float]]) -> int:
    ndof = len(stiffness)
    if ndof == 0 or any(len(row) != ndof for row in stiffness):
        raise GlobalSurfaceContactError("stiffness matrix must be non-empty and square")
    if ndof % 3 != 0:
        raise GlobalSurfaceContactError("surface contact requires 3 translational DOFs per node")
    if any(not math.isfinite(float(value)) for row in stiffness for value in row):
        raise GlobalSurfaceContactError("stiffness matrix entries must be finite")
    return ndof


def _prepare_pair(
    nodes: Sequence[Sequence[float]],
    pair: NodeTriangleContactPair,
    ndof: int,
) -> _PreparedPair:
    node_count = ndof // 3
    slave = int(pair.slave_node)
    masters = tuple(int(value) for value in pair.master_nodes)
    if slave < 0 or slave >= node_count or any(value < 0 or value >= node_count for value in masters):
        raise GlobalSurfaceContactError("surface contact references an unknown node")
    if len(set(masters)) != 3:
        raise GlobalSurfaceContactError("master TRI3 must reference three distinct nodes")
    if slave in masters:
        raise GlobalSurfaceContactError("slave node cannot also belong to its master TRI3")
    penalty = float(pair.penalty_stiffness_n_per_mm)
    if not math.isfinite(penalty) or penalty <= 0.0:
        raise GlobalSurfaceContactError("contact penalty stiffness must be finite and positive")
    try:
        projection = project_point_to_triangle(
            nodes[slave], nodes[masters[0]], nodes[masters[1]], nodes[masters[2]]
        )
    except (SurfaceContactError, IndexError) as exc:
        raise GlobalSurfaceContactError(str(exc)) from exc

    q = [0.0] * ndof
    for component in range(3):
        q[3 * slave + component] = projection.normal[component]
    for weight, master in zip(projection.barycentric, masters):
        for component in range(3):
            q[3 * master + component] -= weight * projection.normal[component]
    definition = NodeTriangleContactPair(slave, masters, penalty)
    return _PreparedPair(
        definition=definition,
        reference_gap_mm=projection.signed_gap_mm,
        barycentric=projection.barycentric,
        normal=projection.normal,
        q=tuple(q),
        inside_triangle=projection.inside_triangle,
    )


def _gap(pair: _PreparedPair, displacement: Sequence[float]) -> float:
    return pair.reference_gap_mm + sum(qi * ui for qi, ui in zip(pair.q, displacement))


def _state(pair: _PreparedPair, displacement: Sequence[float], active: bool) -> SurfaceContactState:
    gap = _gap(pair, displacement)
    penetration = max(0.0, -gap) if active else 0.0
    normal_force = pair.definition.penalty_stiffness_n_per_mm * penetration
    slave_force = tuple(normal_force * value for value in pair.normal)
    master_forces = tuple(
        tuple(-weight * value for value in slave_force)
        for weight in pair.barycentric
    )
    return SurfaceContactState(
        slave_node=pair.definition.slave_node,
        master_nodes=pair.definition.master_nodes,
        reference_gap_mm=pair.reference_gap_mm,
        signed_gap_mm=gap,
        penetration_mm=penetration,
        normal_force_n=normal_force,
        active=active,
        barycentric=pair.barycentric,
        normal=pair.normal,
        slave_force_n=slave_force,
        master_nodal_forces_n=master_forces,
    )


def solve_small_sliding_surface_contact_from_stiffness(
    nodes: Sequence[Sequence[float]],
    stiffness: Sequence[Sequence[float]],
    constraints: Mapping[int, float],
    loads: Mapping[int, float],
    contacts: Sequence[NodeTriangleContactPair],
    *,
    max_iterations: int = 30,
    activation_tolerance_mm: float = 1e-10,
) -> GlobalSurfaceContactResult:
    """Solve a small linear structure with unilateral coupled node/TRI3 contacts."""
    ndof = _validate_matrix(stiffness)
    if len(nodes) * 3 != ndof or any(len(node) != 3 for node in nodes):
        raise GlobalSurfaceContactError("nodes must match stiffness size and contain 3D coordinates")
    if max_iterations <= 0:
        raise GlobalSurfaceContactError("max_iterations must be positive")
    if not math.isfinite(activation_tolerance_mm) or activation_tolerance_mm < 0.0:
        raise GlobalSurfaceContactError("activation tolerance must be finite and non-negative")

    fixed = {int(dof): float(value) for dof, value in constraints.items()}
    force = [0.0] * ndof
    for dof, value in loads.items():
        if dof < 0 or dof >= ndof or not math.isfinite(float(value)):
            raise GlobalSurfaceContactError("load references an unknown DOF or is non-finite")
        force[int(dof)] += float(value)
    for dof, value in fixed.items():
        if dof < 0 or dof >= ndof or not math.isfinite(value):
            raise GlobalSurfaceContactError("constraint references an unknown DOF or is non-finite")

    prepared = tuple(_prepare_pair(nodes, pair, ndof) for pair in contacts)
    free = [dof for dof in range(ndof) if dof not in fixed]
    if not free:
        raise GlobalSurfaceContactError("model has no free DOFs to solve")

    displacement = [0.0] * ndof
    for dof, value in fixed.items():
        displacement[dof] = value
    active = [False] * len(prepared)

    for iteration in range(1, max_iterations + 1):
        k_eff = [list(map(float, row)) for row in stiffness]
        f_eff = list(force)
        for is_active, pair in zip(active, prepared):
            if not is_active:
                continue
            kp = pair.definition.penalty_stiffness_n_per_mm
            q = pair.q
            for i in range(ndof):
                if q[i] == 0.0:
                    continue
                f_eff[i] -= kp * pair.reference_gap_mm * q[i]
                for j in range(ndof):
                    if q[j] != 0.0:
                        k_eff[i][j] += kp * q[i] * q[j]

        reduced_k = [[k_eff[i][j] for j in free] for i in free]
        reduced_f = [
            f_eff[i] - sum(k_eff[i][j] * value for j, value in fixed.items())
            for i in free
        ]
        try:
            solved = _solve_dense(reduced_k, reduced_f)
        except GlobalStaticError as exc:
            raise GlobalSurfaceContactError(str(exc)) from exc

        displacement = [0.0] * ndof
        for dof, value in fixed.items():
            displacement[dof] = value
        for dof, value in zip(free, solved):
            displacement[dof] = value

        updated = [
            pair.inside_triangle and _gap(pair, displacement) < -activation_tolerance_mm
            for pair in prepared
        ]
        if updated == active:
            break
        active = updated
    else:
        states = tuple(_state(pair, displacement, flag) for pair, flag in zip(prepared, active))
        return GlobalSurfaceContactResult(
            tuple(displacement),
            tuple(0.0 for _ in range(ndof)),
            tuple(float("nan") for _ in range(ndof)),
            states,
            max_iterations,
            False,
        )

    contact_internal = [0.0] * ndof
    states = []
    for pair, is_active in zip(prepared, active):
        state = _state(pair, displacement, is_active)
        states.append(state)
        if is_active:
            coefficient = pair.definition.penalty_stiffness_n_per_mm * state.signed_gap_mm
            for i, qi in enumerate(pair.q):
                contact_internal[i] += coefficient * qi

    ku = [sum(float(stiffness[i][j]) * displacement[j] for j in range(ndof)) for i in range(ndof)]
    residual = [ku[i] + contact_internal[i] - force[i] for i in range(ndof)]
    reactions = [residual[i] if i in fixed else 0.0 for i in range(ndof)]
    return GlobalSurfaceContactResult(
        displacements=tuple(displacement),
        reactions=tuple(reactions),
        residual=tuple(residual),
        contact_states=tuple(states),
        iterations=iteration,
        converged=True,
    )


def solve_tet4_with_surface_contacts(
    nodes: Sequence[Sequence[float]],
    elements: Sequence[Sequence[int]],
    young: float,
    poisson: float,
    constraints: Mapping[int, float],
    loads: Mapping[int, float],
    contacts: Sequence[NodeTriangleContactPair],
    *,
    max_iterations: int = 30,
) -> GlobalSurfaceContactResult:
    """Assemble TET4 stiffness and solve with coupled small-sliding surface contact."""
    stiffness = assemble_stiffness(nodes, elements, young, poisson)
    return solve_small_sliding_surface_contact_from_stiffness(
        nodes,
        stiffness,
        constraints,
        loads,
        contacts,
        max_iterations=max_iterations,
    )
