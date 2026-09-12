"""Auditable global rigid-plane Coulomb contact verification solver.

This increment couples the verified local Coulomb law to an arbitrary structural
stiffness matrix. One structural node contacts a rigid plane. Normal contact uses a
penalty active set; tangential contact uses an elastic predictor with Coulomb cap.

The formulation is intentionally small-increment/small-sliding. It is a verification
bridge before coupling friction to the updated node-to-TRI3 search solver.
"""

from dataclasses import dataclass
import math
from typing import Mapping, Sequence

from .friction import evaluate_coulomb_friction
from .global_static import GlobalStaticError, _solve_dense, assemble_stiffness


class GlobalFrictionError(ValueError):
    pass


@dataclass(frozen=True)
class RigidPlaneFrictionContact:
    node: int
    plane_point_mm: tuple[float, float, float]
    normal: tuple[float, float, float]
    normal_penalty_n_per_mm: float
    tangential_penalty_n_per_mm: float
    friction_coefficient: float


@dataclass(frozen=True)
class GlobalFrictionState:
    node: int
    signed_gap_mm: float
    penetration_mm: float
    normal_force_n: float
    tangential_force_n: tuple[float, float, float]
    tangential_force_magnitude_n: float
    regime: str
    active: bool


@dataclass(frozen=True)
class GlobalFrictionResult:
    displacements: tuple[float, ...]
    reactions: tuple[float, ...]
    residual: tuple[float, ...]
    contact_state: GlobalFrictionState
    iterations: int
    converged: bool


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _norm(a):
    return math.sqrt(_dot(a, a))


def _unit(v):
    if len(v) != 3:
        raise GlobalFrictionError("contact normal must contain three components")
    x = tuple(float(a) for a in v)
    if not all(math.isfinite(a) for a in x):
        raise GlobalFrictionError("contact normal must be finite")
    m = _norm(x)
    if m <= 0.0:
        raise GlobalFrictionError("contact normal must be non-zero")
    return tuple(a / m for a in x)


def _solve_linear(k, f, fixed):
    ndof = len(k)
    free = [i for i in range(ndof) if i not in fixed]
    if not free:
        raise GlobalFrictionError("model has no free DOFs to solve")
    kr = [[k[i][j] for j in free] for i in free]
    fr = [f[i] - sum(k[i][j] * v for j, v in fixed.items()) for i in free]
    try:
        ur = _solve_dense(kr, fr)
    except GlobalStaticError as exc:
        raise GlobalFrictionError(str(exc)) from exc
    u = [0.0] * ndof
    for d, v in fixed.items():
        u[d] = v
    for d, v in zip(free, ur):
        u[d] = v
    return u


def _projector(n):
    return tuple(tuple((1.0 if i == j else 0.0) - n[i] * n[j] for j in range(3)) for i in range(3))


def solve_rigid_plane_coulomb_from_stiffness(
    nodes: Sequence[Sequence[float]],
    stiffness: Sequence[Sequence[float]],
    constraints: Mapping[int, float],
    loads: Mapping[int, float],
    contact: RigidPlaneFrictionContact,
    *,
    max_iterations: int = 50,
    displacement_tolerance_mm: float = 1e-10,
    activation_tolerance_mm: float = 1e-10,
) -> GlobalFrictionResult:
    """Solve one-node rigid-plane penalty contact with Coulomb stick/slip."""
    ndof = len(stiffness)
    if ndof == 0 or any(len(row) != ndof for row in stiffness) or ndof % 3:
        raise GlobalFrictionError("stiffness matrix must be square with 3 DOFs per node")
    if len(nodes) * 3 != ndof or any(len(x) != 3 for x in nodes):
        raise GlobalFrictionError("nodes must match stiffness size and be 3D")
    if any(not math.isfinite(float(v)) for row in stiffness for v in row):
        raise GlobalFrictionError("stiffness entries must be finite")
    node = int(contact.node)
    if node < 0 or node >= len(nodes):
        raise GlobalFrictionError("contact references an unknown node")
    p0 = tuple(float(x) for x in contact.plane_point_mm)
    if len(p0) != 3 or not all(math.isfinite(x) for x in p0):
        raise GlobalFrictionError("plane point must be finite 3D coordinates")
    n = _unit(contact.normal)
    kp = float(contact.normal_penalty_n_per_mm)
    kt = float(contact.tangential_penalty_n_per_mm)
    mu = float(contact.friction_coefficient)
    if not math.isfinite(kp) or kp <= 0.0:
        raise GlobalFrictionError("normal penalty must be finite and positive")
    if not math.isfinite(kt) or kt <= 0.0:
        raise GlobalFrictionError("tangential penalty must be finite and positive")
    if not math.isfinite(mu) or mu < 0.0:
        raise GlobalFrictionError("friction coefficient must be finite and non-negative")
    if max_iterations <= 0:
        raise GlobalFrictionError("max_iterations must be positive")

    fixed = {int(d): float(v) for d, v in constraints.items()}
    force = [0.0] * ndof
    for d, v in loads.items():
        d, v = int(d), float(v)
        if d < 0 or d >= ndof or not math.isfinite(v):
            raise GlobalFrictionError("load references an unknown DOF or is non-finite")
        force[d] += v
    for d, v in fixed.items():
        if d < 0 or d >= ndof or not math.isfinite(v):
            raise GlobalFrictionError("constraint references an unknown DOF or is non-finite")

    base_k = [list(map(float, row)) for row in stiffness]
    u = _solve_linear(base_k, force, fixed)
    xref = tuple(float(x) for x in nodes[node])
    g0 = _dot(n, tuple(xref[i] - p0[i] for i in range(3)))
    P = _projector(n)
    previous_regime = None

    for iteration in range(1, max_iterations + 1):
        un = tuple(u[3 * node + i] for i in range(3))
        gap = g0 + _dot(n, un)
        active = gap < -activation_tolerance_mm
        fn = kp * max(0.0, -gap) if active else 0.0
        friction = evaluate_coulomb_friction(
            un, n, normal_force_n=fn, friction_coefficient=mu,
            tangential_penalty_n_per_mm=kt,
        )

        k_eff = [row[:] for row in base_k]
        f_eff = force[:]
        if active:
            # Normal penalty: K += kp*n*n^T, rhs -= kp*g0*n.
            for i in range(3):
                gi = 3 * node + i
                f_eff[gi] -= kp * g0 * n[i]
                for j in range(3):
                    gj = 3 * node + j
                    k_eff[gi][gj] += kp * n[i] * n[j]

            if friction.regime == "STICK":
                for i in range(3):
                    gi = 3 * node + i
                    for j in range(3):
                        gj = 3 * node + j
                        k_eff[gi][gj] += kt * P[i][j]
            elif friction.regime == "SLIP":
                # Friction is an external reaction opposing motion; move the known
                # force to the RHS for this fixed-point iteration.
                for i in range(3):
                    f_eff[3 * node + i] += friction.tangential_force_n[i]

        u_new = _solve_linear(k_eff, f_eff, fixed)
        delta = max(abs(a - b) for a, b in zip(u_new, u))
        regime = friction.regime if active else "OPEN"
        u = u_new
        if regime == previous_regime and delta <= displacement_tolerance_mm:
            break
        previous_regime = regime
    else:
        return _finish(nodes, base_k, force, fixed, contact, n, g0, u, max_iterations, False)

    return _finish(nodes, base_k, force, fixed, contact, n, g0, u, iteration, True)


def _finish(nodes, base_k, force, fixed, contact, n, g0, u, iteration, converged):
    node = int(contact.node)
    kp = float(contact.normal_penalty_n_per_mm)
    kt = float(contact.tangential_penalty_n_per_mm)
    mu = float(contact.friction_coefficient)
    un = tuple(u[3 * node + i] for i in range(3))
    gap = g0 + _dot(n, un)
    active = gap < -1e-10
    penetration = max(0.0, -gap) if active else 0.0
    fn = kp * penetration
    friction = evaluate_coulomb_friction(
        un, n, normal_force_n=fn, friction_coefficient=mu,
        tangential_penalty_n_per_mm=kt,
    )
    regime = friction.regime if active else "OPEN"

    # Structural residual plus contact internal force. Normal penalty internal force
    # is kp*gap*n. Tangential internal reaction is the opposite of physical Ft.
    contact_internal = [0.0] * len(u)
    if active:
        for i in range(3):
            contact_internal[3 * node + i] += kp * gap * n[i] - friction.tangential_force_n[i]
    ku = [sum(base_k[i][j] * u[j] for j in range(len(u))) for i in range(len(u))]
    residual = [ku[i] + contact_internal[i] - force[i] for i in range(len(u))]
    reactions = [residual[i] if i in fixed else 0.0 for i in range(len(u))]
    state = GlobalFrictionState(
        node=node, signed_gap_mm=gap, penetration_mm=penetration,
        normal_force_n=fn, tangential_force_n=friction.tangential_force_n,
        tangential_force_magnitude_n=friction.tangential_force_magnitude_n,
        regime=regime, active=active,
    )
    return GlobalFrictionResult(tuple(u), tuple(reactions), tuple(residual), state, iteration, converged)


def solve_tet4_with_rigid_plane_coulomb(nodes, elements, young, poisson,
                                         constraints, loads, contact, **kwargs):
    """Assemble verified TET4 stiffness then solve rigid-plane Coulomb contact."""
    return solve_rigid_plane_coulomb_from_stiffness(
        nodes, assemble_stiffness(nodes, elements, young, poisson), constraints, loads,
        contact, **kwargs
    )
