"""Auditable diagnostics for AsterMax updated-geometry contact results.

This module does not change the nonlinear/contact solve.  It evaluates whether a
result is trustworthy enough to present by checking convergence, free-DOF residual,
penetration, unmatched slaves, master switching, and total normal contact force.
All thresholds are explicit engineering inputs; no hidden acceptance criteria are
applied.
"""

from dataclasses import dataclass
import math
from typing import Mapping, Sequence

from .updated_surface_contact import UpdatedSurfaceContactResult


class ContactDiagnosticsError(ValueError):
    pass


@dataclass(frozen=True)
class ContactAcceptanceCriteria:
    max_penetration_mm: float
    max_free_residual_n: float
    max_unmatched_fraction: float = 0.0
    max_master_switches: int | None = None
    require_solver_converged: bool = True


@dataclass(frozen=True)
class ContactDiagnostics:
    solver_converged: bool
    accepted: bool
    reasons: tuple[str, ...]
    slave_count: int
    active_contact_count: int
    unmatched_slave_count: int
    unmatched_fraction: float
    max_penetration_mm: float
    mean_active_penetration_mm: float
    total_normal_force_n: float
    max_normal_force_n: float
    max_free_residual_n: float
    residual_l2_n: float
    master_switch_count: int
    iterations: int


def _finite_nonnegative(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ContactDiagnosticsError(f"{name} must be finite and non-negative")
    return value


def validate_contact_acceptance_criteria(criteria: ContactAcceptanceCriteria) -> None:
    _finite_nonnegative(criteria.max_penetration_mm, "max penetration")
    _finite_nonnegative(criteria.max_free_residual_n, "max free residual")
    unmatched = float(criteria.max_unmatched_fraction)
    if not math.isfinite(unmatched) or unmatched < 0.0 or unmatched > 1.0:
        raise ContactDiagnosticsError("max unmatched fraction must be between 0 and 1")
    if criteria.max_master_switches is not None and criteria.max_master_switches < 0:
        raise ContactDiagnosticsError("max master switches must be non-negative or None")


def diagnose_updated_surface_contact(
    result: UpdatedSurfaceContactResult,
    constraints: Mapping[int, float] | Sequence[int],
    criteria: ContactAcceptanceCriteria,
) -> ContactDiagnostics:
    """Evaluate explicit confidence diagnostics for an updated contact solve."""
    validate_contact_acceptance_criteria(criteria)

    fixed = set(int(d) for d in (constraints.keys() if hasattr(constraints, "keys") else constraints))
    if any(d < 0 or d >= len(result.residual) for d in fixed):
        raise ContactDiagnosticsError("constraint references an unknown residual DOF")

    residual = tuple(float(v) for v in result.residual)
    if any(not math.isfinite(v) for v in residual):
        raise ContactDiagnosticsError("result residual contains non-finite values")

    states = tuple(result.contact_states)
    slaves = {int(state.slave_node) for state in states}.union(int(i) for i in result.unmatched_slave_nodes)
    slave_count = len(slaves)
    unmatched_count = len(set(int(i) for i in result.unmatched_slave_nodes))
    unmatched_fraction = (unmatched_count / slave_count) if slave_count else 0.0

    penetrations = tuple(float(state.penetration_mm) for state in states if state.active)
    normal_forces = tuple(float(state.normal_force_n) for state in states if state.active)
    if any(not math.isfinite(v) or v < 0.0 for v in penetrations + normal_forces):
        raise ContactDiagnosticsError("contact state contains invalid penetration/normal force")

    max_penetration = max(penetrations, default=0.0)
    mean_penetration = sum(penetrations) / len(penetrations) if penetrations else 0.0
    total_normal_force = sum(normal_forces)
    max_normal_force = max(normal_forces, default=0.0)

    free_residuals = tuple(abs(v) for i, v in enumerate(residual) if i not in fixed)
    max_free_residual = max(free_residuals, default=0.0)
    residual_l2 = math.sqrt(sum(v*v for v in free_residuals))

    reasons = []
    if criteria.require_solver_converged and not result.converged:
        reasons.append("solver_not_converged")
    if max_penetration > criteria.max_penetration_mm:
        reasons.append("penetration_limit_exceeded")
    if max_free_residual > criteria.max_free_residual_n:
        reasons.append("free_residual_limit_exceeded")
    if unmatched_fraction > criteria.max_unmatched_fraction:
        reasons.append("unmatched_slave_limit_exceeded")
    if (criteria.max_master_switches is not None and
            result.master_switch_count > criteria.max_master_switches):
        reasons.append("master_switch_limit_exceeded")

    return ContactDiagnostics(
        solver_converged=bool(result.converged),
        accepted=not reasons,
        reasons=tuple(reasons),
        slave_count=slave_count,
        active_contact_count=sum(1 for state in states if state.active),
        unmatched_slave_count=unmatched_count,
        unmatched_fraction=unmatched_fraction,
        max_penetration_mm=max_penetration,
        mean_active_penetration_mm=mean_penetration,
        total_normal_force_n=total_normal_force,
        max_normal_force_n=max_normal_force,
        max_free_residual_n=max_free_residual,
        residual_l2_n=residual_l2,
        master_switch_count=int(result.master_switch_count),
        iterations=int(result.iterations),
    )
