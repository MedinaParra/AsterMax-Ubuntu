"""Coupled bolt-pretension + updated node-to-TRI3 friction contact verification.

This bridge composes two independently harnessed AsterMax kernels without hiding
preload as a post-processing number. Bolt connectors augment the structural tangent
and contribute their initial-force equivalent load before the updated-geometry
Coulomb contact solve. Because

    (Ks + Kb) u + r_contact = Fext - q P0

is algebraically identical to

    Ks u + q(P0 + kb q^T u) + r_contact = Fext,

the residual returned by the contact solver is already the physical joint residual.
Units: mm, N, MPa. This remains a verification-level connector/contact formulation,
not a production solid-bolt or pretension-section implementation.
"""

from dataclasses import dataclass
from typing import Mapping, Sequence

from .bolt_pretension import (
    BoltPretensionConnector,
    BoltPretensionError,
    BoltPretensionState,
    _connector_q,
    _unit,
)
from .global_static import assemble_stiffness
from .updated_surface_friction import (
    UpdatedSurfaceFrictionError,
    UpdatedSurfaceFrictionResult,
    solve_updated_surface_coulomb_from_stiffness,
)


class PreloadedSurfaceJointError(ValueError):
    """Raised when the coupled preloaded frictional joint definition is invalid."""


@dataclass(frozen=True)
class PreloadedSurfaceJointResult:
    displacements: tuple[float, ...]
    reactions: tuple[float, ...]
    residual: tuple[float, ...]
    connector_states: tuple[BoltPretensionState, ...]
    contact_result: UpdatedSurfaceFrictionResult


def solve_preloaded_surface_joint_from_stiffness(
    nodes: Sequence[Sequence[float]],
    structural_stiffness: Sequence[Sequence[float]],
    constraints: Mapping[int, float],
    loads: Mapping[int, float],
    connectors: Sequence[BoltPretensionConnector],
    **contact_kwargs,
) -> PreloadedSurfaceJointResult:
    """Solve pretension connectors and updated Coulomb surface contact together."""
    ndof = len(structural_stiffness)
    if ndof == 0 or ndof % 3 or any(len(row) != ndof for row in structural_stiffness):
        raise PreloadedSurfaceJointError("structural stiffness must be square with 3 DOFs per node")
    if len(nodes) * 3 != ndof:
        raise PreloadedSurfaceJointError("nodes must match structural stiffness size")
    if not connectors:
        raise PreloadedSurfaceJointError("at least one bolt pretension connector is required")

    node_count = len(nodes)
    k_aug = [list(map(float, row)) for row in structural_stiffness]
    equivalent_loads = {int(d): float(v) for d, v in loads.items()}
    prepared = []
    try:
        for connector in connectors:
            q = _connector_q(connector, node_count)
            n = _unit(connector.direction)
            kb = float(connector.axial_stiffness_n_per_mm)
            p0 = float(connector.preload_n)
            for i, qi in enumerate(q):
                if qi == 0.0:
                    continue
                equivalent_loads[i] = equivalent_loads.get(i, 0.0) - p0 * qi
                for j, qj in enumerate(q):
                    if qj != 0.0:
                        k_aug[i][j] += kb * qi * qj
            prepared.append((connector, tuple(q), n))
    except BoltPretensionError as exc:
        raise PreloadedSurfaceJointError(str(exc)) from exc

    try:
        contact = solve_updated_surface_coulomb_from_stiffness(
            nodes, k_aug, constraints, equivalent_loads, **contact_kwargs
        )
    except UpdatedSurfaceFrictionError as exc:
        raise PreloadedSurfaceJointError(str(exc)) from exc

    u = contact.displacements
    states = []
    for connector, q, n in prepared:
        extension = sum(q[i] * u[i] for i in range(ndof))
        axial_force = float(connector.preload_n) + float(connector.axial_stiffness_n_per_mm) * extension
        states.append(BoltPretensionState(
            node_a=connector.node_a,
            node_b=connector.node_b,
            relative_extension_mm=extension,
            axial_force_n=axial_force,
            force_on_a_n=tuple(axial_force * n[c] for c in range(3)),
            force_on_b_n=tuple(-axial_force * n[c] for c in range(3)),
        ))

    return PreloadedSurfaceJointResult(
        displacements=contact.displacements,
        reactions=contact.reactions,
        residual=contact.residual,
        connector_states=tuple(states),
        contact_result=contact,
    )


def solve_tet4_preloaded_surface_joint(
    nodes: Sequence[Sequence[float]],
    elements: Sequence[Sequence[int]],
    young: float,
    poisson: float,
    constraints: Mapping[int, float],
    loads: Mapping[int, float],
    connectors: Sequence[BoltPretensionConnector],
    **contact_kwargs,
) -> PreloadedSurfaceJointResult:
    """Bridge verified TET4 assembly to the coupled preloaded frictional joint."""
    try:
        stiffness = assemble_stiffness(nodes, elements, young, poisson)
    except Exception as exc:
        raise PreloadedSurfaceJointError(str(exc)) from exc
    return solve_preloaded_surface_joint_from_stiffness(
        nodes, stiffness, constraints, loads, connectors, **contact_kwargs
    )
