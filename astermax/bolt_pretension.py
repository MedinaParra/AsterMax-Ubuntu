"""Auditable bolt-pretension connector for AsterMax verification cases.

The connector represents a preloaded axial member between two structural nodes.
It is intentionally small and solver-agnostic: a positive ``preload_n`` means
initial bolt tension at zero relative displacement.  The element contributes

    r_b = q * (P0 + k * q^T u)
    K_b = k * q q^T

where q=[-n,+n].  Global equilibrium is therefore

    (K_struct + K_b) u = F_ext - q P0.

Units are the AsterMax PMV convention: mm, N, MPa.  This is a verification-level
pretension connector, not a production bolt solid/contact formulation.
"""

from dataclasses import dataclass
from math import sqrt
from typing import Mapping, Sequence

from .global_static import GlobalStaticError, _solve_dense, assemble_stiffness


class BoltPretensionError(ValueError):
    """Raised when a pretension connector or solve definition is invalid."""


@dataclass(frozen=True)
class BoltPretensionConnector:
    node_a: int
    node_b: int
    direction: tuple[float, float, float]
    axial_stiffness_n_per_mm: float
    preload_n: float


@dataclass(frozen=True)
class BoltPretensionState:
    node_a: int
    node_b: int
    relative_extension_mm: float
    axial_force_n: float
    force_on_a_n: tuple[float, float, float]
    force_on_b_n: tuple[float, float, float]


@dataclass(frozen=True)
class BoltPretensionResult:
    displacements: tuple[float, ...]
    reactions: tuple[float, ...]
    residual: tuple[float, ...]
    connector_states: tuple[BoltPretensionState, ...]


def _unit(vector: Sequence[float]) -> tuple[float, float, float]:
    if len(vector) != 3:
        raise BoltPretensionError("bolt direction must be a 3D vector")
    values = tuple(float(v) for v in vector)
    norm = sqrt(sum(v * v for v in values))
    if norm <= 0.0:
        raise BoltPretensionError("bolt direction must be non-zero")
    return tuple(v / norm for v in values)


def _connector_q(connector: BoltPretensionConnector, node_count: int) -> list[float]:
    if connector.node_a == connector.node_b:
        raise BoltPretensionError("bolt connector nodes must be distinct")
    if connector.node_a < 0 or connector.node_a >= node_count or connector.node_b < 0 or connector.node_b >= node_count:
        raise BoltPretensionError("bolt connector references an unknown node")
    if connector.axial_stiffness_n_per_mm <= 0.0:
        raise BoltPretensionError("bolt axial stiffness must be positive")
    if connector.preload_n < 0.0:
        raise BoltPretensionError("bolt preload must be non-negative")
    n = _unit(connector.direction)
    q = [0.0] * (3 * node_count)
    for component in range(3):
        q[3 * connector.node_a + component] = -n[component]
        q[3 * connector.node_b + component] = n[component]
    return q


def solve_with_bolt_pretension(
    structural_stiffness: Sequence[Sequence[float]],
    constraints: Mapping[int, float],
    loads: Mapping[int, float],
    connectors: Sequence[BoltPretensionConnector],
) -> BoltPretensionResult:
    """Solve a small structural system with preloaded axial bolt connectors.

    ``structural_stiffness`` excludes bolt connectors.  Reactions and residuals
    include both structural and bolt internal forces.  Positive axial force is
    tension; a sufficiently negative relative extension may relax the bolt to
    compression, which this verification kernel reports rather than clipping.
    Contact/opening logic belongs to the joint/contact model, not this connector.
    """
    ndof = len(structural_stiffness)
    if ndof == 0 or ndof % 3 != 0 or any(len(row) != ndof for row in structural_stiffness):
        raise BoltPretensionError("structural stiffness must be a non-empty square 3-DOF/node matrix")
    if not connectors:
        raise BoltPretensionError("at least one bolt pretension connector is required")
    if not constraints:
        raise BoltPretensionError("at least one Dirichlet constraint is required")
    node_count = ndof // 3
    fixed = {int(dof): float(value) for dof, value in constraints.items()}
    for dof in (*fixed.keys(), *loads.keys()):
        if dof < 0 or dof >= ndof:
            raise BoltPretensionError("constraint/load references an unknown DOF")

    k_total = [list(map(float, row)) for row in structural_stiffness]
    force = [0.0] * ndof
    for dof, value in loads.items():
        force[int(dof)] += float(value)

    q_vectors: list[list[float]] = []
    normalized: list[tuple[float, float, float]] = []
    for connector in connectors:
        q = _connector_q(connector, node_count)
        n = _unit(connector.direction)
        q_vectors.append(q)
        normalized.append(n)
        k = float(connector.axial_stiffness_n_per_mm)
        p0 = float(connector.preload_n)
        for i in range(ndof):
            force[i] -= p0 * q[i]
            if q[i] == 0.0:
                continue
            for j in range(ndof):
                if q[j] != 0.0:
                    k_total[i][j] += k * q[i] * q[j]

    free = [dof for dof in range(ndof) if dof not in fixed]
    if not free:
        raise BoltPretensionError("model has no free DOFs to solve")
    reduced_k = [[k_total[i][j] for j in free] for i in free]
    reduced_f = [force[i] - sum(k_total[i][j] * value for j, value in fixed.items()) for i in free]
    try:
        solved = _solve_dense(reduced_k, reduced_f)
    except GlobalStaticError as exc:
        raise BoltPretensionError(str(exc)) from exc

    displacement = [0.0] * ndof
    for dof, value in fixed.items():
        displacement[dof] = value
    for dof, value in zip(free, solved):
        displacement[dof] = value

    # Recover residual using the physical external load, not the equivalent
    # pretension RHS used during solution.
    physical_external = [0.0] * ndof
    for dof, value in loads.items():
        physical_external[int(dof)] += float(value)
    structural_internal = [
        sum(float(structural_stiffness[i][j]) * displacement[j] for j in range(ndof))
        for i in range(ndof)
    ]
    total_internal = structural_internal[:]
    states: list[BoltPretensionState] = []
    for connector, q, n in zip(connectors, q_vectors, normalized):
        extension = sum(q[i] * displacement[i] for i in range(ndof))
        axial_force = float(connector.preload_n) + float(connector.axial_stiffness_n_per_mm) * extension
        for i in range(ndof):
            total_internal[i] += q[i] * axial_force
        # Forces exerted by the connector on the structure are opposite to the
        # connector internal residual q*F.
        force_a = tuple(axial_force * n[c] for c in range(3))
        force_b = tuple(-axial_force * n[c] for c in range(3))
        states.append(BoltPretensionState(
            node_a=connector.node_a,
            node_b=connector.node_b,
            relative_extension_mm=extension,
            axial_force_n=axial_force,
            force_on_a_n=force_a,
            force_on_b_n=force_b,
        ))

    residual = [total_internal[i] - physical_external[i] for i in range(ndof)]
    reactions = [residual[i] if i in fixed else 0.0 for i in range(ndof)]
    return BoltPretensionResult(
        displacements=tuple(displacement),
        reactions=tuple(reactions),
        residual=tuple(residual),
        connector_states=tuple(states),
    )


def solve_tet4_with_bolt_pretension(
    nodes: Sequence[Sequence[float]],
    elements: Sequence[Sequence[int]],
    young: float,
    poisson: float,
    constraints: Mapping[int, float],
    loads: Mapping[int, float],
    connectors: Sequence[BoltPretensionConnector],
) -> BoltPretensionResult:
    """Bridge the verified TET4 structural assembly to bolt pretension."""
    try:
        structural_k = assemble_stiffness(nodes, elements, young, poisson)
    except GlobalStaticError as exc:
        raise BoltPretensionError(str(exc)) from exc
    return solve_with_bolt_pretension(structural_k, constraints, loads, connectors)
