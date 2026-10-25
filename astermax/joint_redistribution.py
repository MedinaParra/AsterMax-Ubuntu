"""Auditable multi-bolt / multi-contact redistribution diagnostics for AsterMax.

This module does not solve new physics.  It converts a converged coupled
``PreloadedSurfaceJointResult`` into engineering evidence about how preload and
contact capacity are redistributed across a joint.  The intent is to make asymmetric
load paths visible and testable instead of hiding them behind contour plots.

Units follow the PMV convention: mm, N, MPa.
"""

from dataclasses import dataclass
import math
from typing import Sequence

from .bolt_pretension import BoltPretensionConnector
from .preloaded_surface_joint import PreloadedSurfaceJointResult


class JointRedistributionError(ValueError):
    """Raised when a coupled-joint result cannot support trustworthy diagnostics."""


@dataclass(frozen=True)
class BoltRedistributionState:
    bolt_index: int
    node_a: int
    node_b: int
    preload_n: float
    final_axial_force_n: float
    force_change_n: float
    preload_retention_ratio: float | None
    tensile_load_share: float


@dataclass(frozen=True)
class JointRedistributionReport:
    bolt_states: tuple[BoltRedistributionState, ...]
    total_initial_preload_n: float
    total_final_bolt_tension_n: float
    max_bolt_force_n: float
    min_bolt_force_n: float
    bolt_force_spread_n: float
    bolt_imbalance_ratio: float
    bolts_in_compression: int
    contact_slave_count: int
    active_contact_count: int
    open_contact_count: int
    contact_active_fraction: float
    total_normal_contact_force_n: float
    total_friction_capacity_n: float
    master_switch_count: int
    solver_iterations: int
    solver_converged: bool


def evaluate_joint_redistribution(
    connectors: Sequence[BoltPretensionConnector],
    result: PreloadedSurfaceJointResult,
) -> JointRedistributionReport:
    """Create deterministic load-redistribution evidence from a coupled joint solve.

    ``tensile_load_share`` is based only on positive final bolt tension.  A connector
    that has relaxed into compression is reported explicitly and receives zero tensile
    share; this diagnostic never silently clips the underlying solver state.
    """
    if not connectors:
        raise JointRedistributionError("at least one bolt connector is required")
    if len(connectors) != len(result.connector_states):
        raise JointRedistributionError("connector definitions and recovered states must have equal length")

    final_forces = [float(s.axial_force_n) for s in result.connector_states]
    if any(not math.isfinite(v) for v in final_forces):
        raise JointRedistributionError("bolt forces must be finite")
    preloads = [float(c.preload_n) for c in connectors]
    if any((not math.isfinite(v)) or v < 0.0 for v in preloads):
        raise JointRedistributionError("bolt preloads must be finite and non-negative")

    total_tension = sum(max(0.0, v) for v in final_forces)
    bolt_states = []
    for index, (connector, state, preload, final_force) in enumerate(
        zip(connectors, result.connector_states, preloads, final_forces)
    ):
        retention = None if preload == 0.0 else final_force / preload
        share = 0.0 if total_tension == 0.0 else max(0.0, final_force) / total_tension
        bolt_states.append(BoltRedistributionState(
            bolt_index=index,
            node_a=state.node_a,
            node_b=state.node_b,
            preload_n=preload,
            final_axial_force_n=final_force,
            force_change_n=final_force - preload,
            preload_retention_ratio=retention,
            tensile_load_share=share,
        ))

    contact = result.contact_result
    contact_states = tuple(contact.contact_states)
    slave_count = len(contact_states) + len(contact.unmatched_slave_nodes)
    if slave_count <= 0:
        raise JointRedistributionError("contact result contains no slave nodes")
    active = [state for state in contact_states if state.active]
    for state in contact_states:
        values = (
            float(state.normal_force_n),
            float(state.friction_limit_n),
            float(state.penetration_mm),
            float(state.signed_gap_mm),
        )
        if any(not math.isfinite(v) for v in values):
            raise JointRedistributionError("contact diagnostic values must be finite")
        if state.normal_force_n < -1e-12 or state.friction_limit_n < -1e-12:
            raise JointRedistributionError("contact force/capacity cannot be negative")
        if not state.active and (state.normal_force_n > 1e-9 or state.friction_limit_n > 1e-9):
            raise JointRedistributionError("inactive contact cannot carry normal force or friction capacity")

    total_preload = sum(preloads)
    max_force = max(final_forces)
    min_force = min(final_forces)
    mean_tension = total_tension / len(final_forces) if final_forces else 0.0
    imbalance = 0.0 if mean_tension == 0.0 else max(0.0, max_force) / mean_tension

    return JointRedistributionReport(
        bolt_states=tuple(bolt_states),
        total_initial_preload_n=total_preload,
        total_final_bolt_tension_n=total_tension,
        max_bolt_force_n=max_force,
        min_bolt_force_n=min_force,
        bolt_force_spread_n=max_force - min_force,
        bolt_imbalance_ratio=imbalance,
        bolts_in_compression=sum(1 for v in final_forces if v < 0.0),
        contact_slave_count=slave_count,
        active_contact_count=len(active),
        open_contact_count=slave_count - len(active),
        contact_active_fraction=len(active) / slave_count,
        total_normal_contact_force_n=sum(float(s.normal_force_n) for s in active),
        total_friction_capacity_n=sum(float(s.friction_limit_n) for s in active),
        master_switch_count=int(contact.master_switch_count),
        solver_iterations=int(contact.iterations),
        solver_converged=bool(contact.converged),
    )
