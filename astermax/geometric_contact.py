"""Geometric frictionless node-to-rigid-plane penalty contact for verification.

The plane normal points into the admissible half-space.  For an undeformed node x0
and displacement u, the signed deformed gap is

    g = n . (x0 + u - p)

where p is a point on the rigid plane and n is a unit normal.  g >= 0 is open or
just touching; g < 0 is penetration.  An active penalty contact contributes

    Kc = kp * (n tensor n)

and the fixed-active-set equilibrium is

    (K + Kc) u = F - kp * g0 * n

with g0 = n . (x0 - p).  Contact is unilateral and frictionless.  This module is
still a verification formulation: node-to-rigid-plane only, no master triangles,
search, friction, large sliding or consistent nonlinear tangent.
"""

from dataclasses import dataclass
import math
from typing import Mapping, Sequence

from .global_static import GlobalStaticError, _solve_dense, assemble_stiffness


class GeometricContactError(ValueError):
    """Raised when geometric contact input or solve state is invalid."""


@dataclass(frozen=True)
class NodePlaneContact:
    node: int
    plane_point_mm: tuple[float, float, float]
    normal: tuple[float, float, float]
    penalty_stiffness_n_per_mm: float


@dataclass(frozen=True)
class NodePlaneState:
    node: int
    signed_gap_mm: float
    penetration_mm: float
    normal_force_n: float
    active: bool
    force_vector_n: tuple[float, float, float]


@dataclass(frozen=True)
class GeometricContactResult:
    displacements: tuple[float, ...]
    reactions: tuple[float, ...]
    residual: tuple[float, ...]
    contacts: tuple[NodePlaneState, ...]
    iterations: int
    converged: bool


def _vec3(values: Sequence[float], name: str) -> tuple[float, float, float]:
    if len(values) != 3:
        raise GeometricContactError(f"{name} must contain three components")
    result = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in result):
        raise GeometricContactError(f"{name} components must be finite")
    return result


def _unit(values: Sequence[float]) -> tuple[float, float, float]:
    vector = _vec3(values, "contact normal")
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude <= 0.0:
        raise GeometricContactError("contact normal must be non-zero")
    return tuple(value / magnitude for value in vector)


def signed_node_plane_gap(
    node_position_mm: Sequence[float],
    displacement_mm: Sequence[float],
    plane_point_mm: Sequence[float],
    normal: Sequence[float],
) -> float:
    """Return signed deformed gap; negative means penetration."""
    x0 = _vec3(node_position_mm, "node position")
    u = _vec3(displacement_mm, "node displacement")
    p = _vec3(plane_point_mm, "plane point")
    n = _unit(normal)
    return sum(n[i] * (x0[i] + u[i] - p[i]) for i in range(3))


def _validate_contacts(
    nodes: Sequence[Sequence[float]], contacts: Sequence[NodePlaneContact]
) -> tuple[NodePlaneContact, ...]:
    validated = []
    seen = set()
    for definition in contacts:
        node = int(definition.node)
        if node < 0 or node >= len(nodes):
            raise GeometricContactError("contact references an unknown node")
        if node in seen:
            raise GeometricContactError("only one rigid-plane contact per node is supported")
        point = _vec3(definition.plane_point_mm, "plane point")
        normal = _unit(definition.normal)
        penalty = float(definition.penalty_stiffness_n_per_mm)
        if not math.isfinite(penalty) or penalty <= 0.0:
            raise GeometricContactError("contact penalty stiffness must be finite and positive")
        seen.add(node)
        validated.append(NodePlaneContact(node, point, normal, penalty))
    return tuple(validated)


def solve_node_plane_contacts_from_stiffness(
    stiffness: Sequence[Sequence[float]],
    nodes: Sequence[Sequence[float]],
    constraints: Mapping[int, float],
    loads: Mapping[int, float],
    contacts: Sequence[NodePlaneContact],
    *,
    max_iterations: int = 30,
    activation_tolerance_mm: float = 1e-10,
) -> GeometricContactResult:
    """Solve small-displacement frictionless node-to-plane contact by active set."""
    ndof = len(stiffness)
    if ndof == 0 or ndof != 3 * len(nodes) or any(len(row) != ndof for row in stiffness):
        raise GeometricContactError("stiffness must be square with three DOFs per node")
    if max_iterations <= 0:
        raise GeometricContactError("max_iterations must be positive")
    if not math.isfinite(activation_tolerance_mm) or activation_tolerance_mm < 0.0:
        raise GeometricContactError("activation tolerance must be finite and non-negative")
    node_xyz = tuple(_vec3(node, "node position") for node in nodes)
    definitions = _validate_contacts(node_xyz, contacts)

    fixed = {int(dof): float(value) for dof, value in constraints.items()}
    force = [0.0] * ndof
    for dof, value in loads.items():
        dof = int(dof)
        if dof < 0 or dof >= ndof:
            raise GeometricContactError("load references an unknown DOF")
        force[dof] += float(value)
    for dof, value in fixed.items():
        if dof < 0 or dof >= ndof or not math.isfinite(value):
            raise GeometricContactError("constraint references an invalid DOF/value")

    free = [dof for dof in range(ndof) if dof not in fixed]
    if not free:
        raise GeometricContactError("model has no free DOFs to solve")

    # Initial classification uses the undeformed geometry.  Initially penetrating
    # nodes are active from the first iteration; otherwise contact activates after
    # the unconstrained structural trial solve crosses the plane.
    active = []
    for contact in definitions:
        gap0 = signed_node_plane_gap(node_xyz[contact.node], (0.0, 0.0, 0.0), contact.plane_point_mm, contact.normal)
        active.append(gap0 < -activation_tolerance_mm)

    displacement = [0.0] * ndof
    for iteration in range(1, max_iterations + 1):
        k_eff = [list(map(float, row)) for row in stiffness]
        f_eff = list(force)
        for is_active, contact in zip(active, definitions):
            if not is_active:
                continue
            base = 3 * contact.node
            n = contact.normal
            kp = contact.penalty_stiffness_n_per_mm
            gap0 = sum(n[i] * (node_xyz[contact.node][i] - contact.plane_point_mm[i]) for i in range(3))
            for i in range(3):
                gi = base + i
                f_eff[gi] -= kp * gap0 * n[i]
                for j in range(3):
                    k_eff[gi][base + j] += kp * n[i] * n[j]

        reduced_k = [[k_eff[i][j] for j in free] for i in free]
        reduced_f = [
            f_eff[i] - sum(k_eff[i][j] * value for j, value in fixed.items())
            for i in free
        ]
        try:
            solved = _solve_dense(reduced_k, reduced_f)
        except GlobalStaticError as exc:
            raise GeometricContactError(str(exc)) from exc

        displacement = [0.0] * ndof
        for dof, value in fixed.items():
            displacement[dof] = value
        for dof, value in zip(free, solved):
            displacement[dof] = value

        updated = []
        for contact in definitions:
            base = 3 * contact.node
            gap = signed_node_plane_gap(
                node_xyz[contact.node], displacement[base : base + 3],
                contact.plane_point_mm, contact.normal,
            )
            updated.append(gap < -activation_tolerance_mm)
        if updated == active:
            break
        active = updated
    else:
        return GeometricContactResult(
            tuple(displacement), tuple(0.0 for _ in range(ndof)),
            tuple(float("nan") for _ in range(ndof)), tuple(), max_iterations, False,
        )

    contact_internal = [0.0] * ndof
    states = []
    for is_active, contact in zip(active, definitions):
        base = 3 * contact.node
        gap = signed_node_plane_gap(
            node_xyz[contact.node], displacement[base : base + 3],
            contact.plane_point_mm, contact.normal,
        )
        penetration = max(0.0, -gap) if is_active else 0.0
        normal_force = contact.penalty_stiffness_n_per_mm * penetration
        # In the residual convention contact contributes +kp*g*n; for penetration
        # g<0 this is opposite the physical external contact force.
        internal_vector = tuple(-normal_force * value for value in contact.normal)
        physical_vector = tuple(normal_force * value for value in contact.normal)
        for i in range(3):
            contact_internal[base + i] += internal_vector[i]
        states.append(NodePlaneState(contact.node, gap, penetration, normal_force, is_active, physical_vector))

    ku = [sum(float(stiffness[i][j]) * displacement[j] for j in range(ndof)) for i in range(ndof)]
    residual = [ku[i] + contact_internal[i] - force[i] for i in range(ndof)]
    reactions = [residual[i] if i in fixed else 0.0 for i in range(ndof)]
    return GeometricContactResult(
        tuple(displacement), tuple(reactions), tuple(residual), tuple(states), iteration, True,
    )


def solve_tet4_with_node_plane_contacts(
    nodes: Sequence[Sequence[float]],
    elements: Sequence[Sequence[int]],
    young: float,
    poisson: float,
    constraints: Mapping[int, float],
    loads: Mapping[int, float],
    contacts: Sequence[NodePlaneContact],
    *,
    max_iterations: int = 30,
) -> GeometricContactResult:
    """Assemble AsterMax TET4 stiffness and solve node-to-rigid-plane contacts."""
    stiffness = assemble_stiffness(nodes, elements, young, poisson)
    return solve_node_plane_contacts_from_stiffness(
        stiffness, nodes, constraints, loads, contacts, max_iterations=max_iterations
    )
