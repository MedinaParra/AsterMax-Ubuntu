"""Traceable multi-GAP partial-opening diagnostics for preloaded joints.

This layer adds no hidden physics. It evaluates a ``GappedPreloadedJointResult`` and
makes the causal chain GAP -> support loss -> contact capacity -> bolt redistribution
explicit for professional demo/reporting. Units: mm, N, MPa.
"""

from dataclasses import dataclass
import math
from typing import Sequence

from .bolt_pretension import BoltPretensionConnector
from .gapped_preloaded_joint import GappedPreloadedJointResult
from .joint_redistribution import JointRedistributionReport, evaluate_joint_redistribution


class GappedJointDiagnosticsError(ValueError):
    """Raised when a gapped-joint result cannot support trustworthy diagnostics."""


@dataclass(frozen=True)
class GapZoneState:
    slave_node: int
    initial_gap_mm: float
    final_signed_gap_mm: float
    closure_mm: float
    penetration_mm: float
    active: bool
    regime: str
    normal_force_n: float
    friction_capacity_n: float


@dataclass(frozen=True)
class GappedJointDiagnostics:
    zones: tuple[GapZoneState, ...]
    redistribution: JointRedistributionReport
    max_initial_gap_mm: float
    mean_initial_gap_mm: float
    active_zone_count: int
    open_zone_count: int
    support_loss_fraction: float
    total_normal_contact_force_n: float
    total_friction_capacity_n: float


def evaluate_gapped_joint(
    connectors: Sequence[BoltPretensionConnector],
    result: GappedPreloadedJointResult,
) -> GappedJointDiagnostics:
    """Evaluate spatial GAP closure/opening and coupled bolt/contact redistribution."""
    gap_map = {int(node): float(value) for node, value in result.gap.gap_by_slave_mm}
    contact = result.joint.contact_result
    state_map = {int(state.slave_node): state for state in contact.contact_states}
    unmatched = set(int(node) for node in contact.unmatched_slave_nodes)

    if not gap_map:
        raise GappedJointDiagnosticsError("GAP field contains no slave nodes")
    if set(gap_map) != set(state_map) | unmatched:
        raise GappedJointDiagnosticsError("GAP field and contact slave states do not match")
    if unmatched:
        raise GappedJointDiagnosticsError(
            "unmatched slave nodes cannot be used for partial-opening diagnostics"
        )

    zones = []
    for slave in sorted(gap_map):
        initial = gap_map[slave]
        state = state_map[slave]
        final_gap = float(state.signed_gap_mm)
        penetration = float(state.penetration_mm)
        normal_force = float(state.normal_force_n)
        friction_capacity = float(state.friction_limit_n)
        values = (initial, final_gap, penetration, normal_force, friction_capacity)
        if any(not math.isfinite(v) for v in values):
            raise GappedJointDiagnosticsError("GAP/contact diagnostics must be finite")
        if initial < 0.0 or penetration < -1e-12 or normal_force < -1e-12 or friction_capacity < -1e-12:
            raise GappedJointDiagnosticsError("GAP/contact diagnostics contain non-physical negative values")
        if not state.active and (normal_force > 1e-9 or friction_capacity > 1e-9):
            raise GappedJointDiagnosticsError("open contact cannot carry normal force or friction capacity")
        zones.append(GapZoneState(
            slave_node=slave,
            initial_gap_mm=initial,
            final_signed_gap_mm=final_gap,
            closure_mm=initial - final_gap,
            penetration_mm=penetration,
            active=bool(state.active),
            regime=str(state.regime),
            normal_force_n=normal_force,
            friction_capacity_n=friction_capacity,
        ))

    redistribution = evaluate_joint_redistribution(connectors, result.joint)
    active = sum(1 for zone in zones if zone.active)
    total = len(zones)
    initial_gaps = [zone.initial_gap_mm for zone in zones]

    return GappedJointDiagnostics(
        zones=tuple(zones),
        redistribution=redistribution,
        max_initial_gap_mm=max(initial_gaps),
        mean_initial_gap_mm=sum(initial_gaps) / total,
        active_zone_count=active,
        open_zone_count=total - active,
        support_loss_fraction=(total - active) / total,
        total_normal_contact_force_n=sum(zone.normal_force_n for zone in zones),
        total_friction_capacity_n=sum(zone.friction_capacity_n for zone in zones),
    )
