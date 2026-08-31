"""Updated-geometry node-to-TRI3 Coulomb contact verification solver.

This module extends AsterMax's geometry-updated frictionless surface contact with an
auditable tangential penalty/Coulomb law. Master search, normal and barycentric weights
are refreshed on the deformed geometry. For each active slave/master pair, relative
motion is

    r = u_s - sum(N_i u_m)
    r_t = (I - n n^T) r

STICK contributes kt * B^T P B. SLIP applies a capped physical friction force
|Ft| = mu*Fn opposite r_t and distributes the equal/opposite master reaction by the
same barycentric weights. This is a Picard verification solver, not a production
consistent-tangent large-sliding algorithm.
"""

from dataclasses import dataclass
import math
from typing import Mapping, Sequence

from .friction import evaluate_coulomb_friction
from .global_static import GlobalStaticError, _solve_dense, assemble_stiffness
from .surface_contact import SurfaceContactError, project_point_to_triangle, triangle_unit_normal


class UpdatedSurfaceFrictionError(ValueError):
    pass


@dataclass(frozen=True)
class UpdatedSurfaceFrictionState:
    slave_node: int
    master_nodes: tuple[int, int, int]
    signed_gap_mm: float
    penetration_mm: float
    normal_force_n: float
    tangential_force_n: tuple[float, float, float]
    tangential_force_magnitude_n: float
    friction_limit_n: float
    regime: str
    active: bool
    barycentric: tuple[float, float, float]
    normal: tuple[float, float, float]
    master_nodal_tangential_forces_n: tuple[tuple[float, float, float], ...]


@dataclass(frozen=True)
class UpdatedSurfaceFrictionResult:
    displacements: tuple[float, ...]
    reactions: tuple[float, ...]
    residual: tuple[float, ...]
    contact_states: tuple[UpdatedSurfaceFrictionState, ...]
    unmatched_slave_nodes: tuple[int, ...]
    iterations: int
    converged: bool
    master_switch_count: int


@dataclass(frozen=True)
class _Candidate:
    slave: int
    master: tuple[int, int, int]
    gap: float
    barycentric: tuple[float, float, float]
    normal: tuple[float, float, float]
    active: bool


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _norm(a):
    return math.sqrt(_dot(a, a))


def _unit(v):
    if len(v) != 3:
        raise UpdatedSurfaceFrictionError("master normal hint must contain three components")
    x = tuple(float(a) for a in v)
    if not all(math.isfinite(a) for a in x) or _norm(x) <= 0.0:
        raise UpdatedSurfaceFrictionError("master normal hint must be finite and non-zero")
    m = _norm(x)
    return tuple(a / m for a in x)


def _deformed(nodes, u):
    return tuple(tuple(float(nodes[i][j]) + float(u[3*i+j]) for j in range(3)) for i in range(len(nodes)))


def _oriented(points, tri, hint):
    tri = tuple(int(i) for i in tri)
    try:
        n = triangle_unit_normal(*(points[i] for i in tri))
    except (SurfaceContactError, IndexError) as exc:
        raise UpdatedSurfaceFrictionError(str(exc)) from exc
    return (tri[0], tri[2], tri[1]) if _dot(n, hint) < 0.0 else tri


def _search(points, slaves, masters, hint, search_distance, activation_tol):
    oriented = tuple(sorted(_oriented(points, tri, hint) for tri in masters))
    found, unmatched = [], []
    for slave in sorted(set(int(i) for i in slaves)):
        candidates = []
        for tri in oriented:
            if slave in tri:
                continue
            try:
                p = project_point_to_triangle(points[slave], *(points[i] for i in tri))
            except (SurfaceContactError, IndexError) as exc:
                raise UpdatedSurfaceFrictionError(str(exc)) from exc
            if p.inside_triangle and abs(p.signed_gap_mm) <= search_distance:
                candidates.append((abs(p.signed_gap_mm), tri, p))
        if not candidates:
            unmatched.append(slave)
            continue
        _, tri, p = min(candidates, key=lambda item: (item[0], item[1]))
        found.append(_Candidate(slave, tri, p.signed_gap_mm, p.barycentric, p.normal,
                                p.signed_gap_mm < -activation_tol))
    return tuple(found), tuple(unmatched)


def _q_normal(c, ndof):
    q = [0.0] * ndof
    for j in range(3):
        q[3*c.slave+j] = c.normal[j]
    for w, m in zip(c.barycentric, c.master):
        for j in range(3):
            q[3*m+j] -= w*c.normal[j]
    return tuple(q)


def _B(c, ndof):
    B = [[0.0]*ndof for _ in range(3)]
    for j in range(3):
        B[j][3*c.slave+j] = 1.0
    for w, m in zip(c.barycentric, c.master):
        for j in range(3):
            B[j][3*m+j] -= w
    return B


def _relative_u(c, u):
    r = [u[3*c.slave+j] for j in range(3)]
    for w, m in zip(c.barycentric, c.master):
        for j in range(3):
            r[j] -= w*u[3*m+j]
    return tuple(r)


def _projector(n):
    return tuple(tuple((1.0 if i == j else 0.0) - n[i]*n[j] for j in range(3)) for i in range(3))


def _solve_linear(k, f, fixed):
    ndof = len(k)
    free = [i for i in range(ndof) if i not in fixed]
    if not free:
        raise UpdatedSurfaceFrictionError("model has no free DOFs to solve")
    kr = [[k[i][j] for j in free] for i in free]
    fr = [f[i] - sum(k[i][j]*v for j, v in fixed.items()) for i in free]
    try:
        ur = _solve_dense(kr, fr)
    except GlobalStaticError as exc:
        raise UpdatedSurfaceFrictionError(str(exc)) from exc
    u = [0.0]*ndof
    for d, v in fixed.items(): u[d] = v
    for d, v in zip(free, ur): u[d] = v
    return u


def _validate(nodes, stiffness, slaves, masters, kp, kt, mu, search):
    ndof = len(stiffness)
    if ndof == 0 or any(len(row) != ndof for row in stiffness) or ndof % 3:
        raise UpdatedSurfaceFrictionError("stiffness matrix must be square with 3 DOFs per node")
    if len(nodes)*3 != ndof or any(len(p) != 3 for p in nodes):
        raise UpdatedSurfaceFrictionError("nodes must match stiffness size and be 3D")
    if any(not math.isfinite(float(x)) for row in stiffness for x in row):
        raise UpdatedSurfaceFrictionError("stiffness entries must be finite")
    if not slaves or not masters:
        raise UpdatedSurfaceFrictionError("slave nodes and master TRI3 candidates are required")
    if any(i < 0 or i >= len(nodes) for i in slaves):
        raise UpdatedSurfaceFrictionError("slave surface references an unknown node")
    if any(len(t) != 3 or len(set(t)) != 3 or any(i < 0 or i >= len(nodes) for i in t) for t in masters):
        raise UpdatedSurfaceFrictionError("master surface contains invalid TRI3 connectivity")
    if not math.isfinite(kp) or kp <= 0.0 or not math.isfinite(kt) or kt <= 0.0:
        raise UpdatedSurfaceFrictionError("normal/tangential penalty must be finite and positive")
    if not math.isfinite(mu) or mu < 0.0:
        raise UpdatedSurfaceFrictionError("friction coefficient must be finite and non-negative")
    if not math.isfinite(search) or search < 0.0:
        raise UpdatedSurfaceFrictionError("contact search distance must be finite and non-negative")
    return ndof


def solve_updated_surface_coulomb_from_stiffness(
    nodes: Sequence[Sequence[float]], stiffness: Sequence[Sequence[float]],
    constraints: Mapping[int, float], loads: Mapping[int, float], *,
    slave_nodes: Sequence[int], master_triangles: Sequence[Sequence[int]],
    master_normal_hint: Sequence[float], normal_penalty_n_per_mm: float,
    tangential_penalty_n_per_mm: float, friction_coefficient: float,
    search_distance_mm: float, max_iterations: int = 60,
    activation_tolerance_mm: float = 1e-10, displacement_tolerance_mm: float = 1e-9,
    allow_unmatched: bool = False,
) -> UpdatedSurfaceFrictionResult:
    """Solve updated node-to-TRI3 contact with Coulomb STICK/SLIP."""
    slaves = tuple(sorted(set(int(i) for i in slave_nodes)))
    masters = tuple(tuple(int(i) for i in t) for t in master_triangles)
    kp, kt, mu, search = map(float, (normal_penalty_n_per_mm, tangential_penalty_n_per_mm,
                                      friction_coefficient, search_distance_mm))
    ndof = _validate(nodes, stiffness, slaves, masters, kp, kt, mu, search)
    if max_iterations <= 0 or displacement_tolerance_mm < 0.0 or activation_tolerance_mm < 0.0:
        raise UpdatedSurfaceFrictionError("iterations/tolerances are invalid")
    hint = _unit(master_normal_hint)
    fixed = {int(d): float(v) for d, v in constraints.items()}
    force = [0.0]*ndof
    for d, v in loads.items():
        d, v = int(d), float(v)
        if d < 0 or d >= ndof or not math.isfinite(v):
            raise UpdatedSurfaceFrictionError("load references an unknown DOF or is non-finite")
        force[d] += v
    for d, v in fixed.items():
        if d < 0 or d >= ndof or not math.isfinite(v):
            raise UpdatedSurfaceFrictionError("constraint references an unknown DOF or is non-finite")
    base_k = [list(map(float, row)) for row in stiffness]
    u = _solve_linear(base_k, force, fixed)
    previous_signature, previous_master, switches = None, {}, 0

    for iteration in range(1, max_iterations+1):
        candidates, unmatched = _search(_deformed(nodes, u), slaves, masters, hint, search, activation_tolerance_mm)
        if unmatched and not allow_unmatched:
            raise UpdatedSurfaceFrictionError("updated friction search lost master projection for slave nodes: " + ", ".join(map(str, unmatched)))
        current_master = {c.slave: c.master for c in candidates}
        for s, t in current_master.items():
            if s in previous_master and previous_master[s] != t: switches += 1
        previous_master = current_master
        k_eff, f_eff = [row[:] for row in base_k], force[:]
        signature = []
        for c in candidates:
            if not c.active:
                signature.append((c.slave, c.master, "OPEN")); continue
            q = _q_normal(c, ndof)
            c0 = c.gap - sum(qi*ui for qi, ui in zip(q, u))
            for i, qi in enumerate(q):
                if qi == 0.0: continue
                f_eff[i] -= kp*c0*qi
                for j, qj in enumerate(q):
                    if qj != 0.0: k_eff[i][j] += kp*qi*qj
            fn = kp*max(0.0, -c.gap)
            rel = _relative_u(c, u)
            fr = evaluate_coulomb_friction(rel, c.normal, normal_force_n=fn,
                friction_coefficient=mu, tangential_penalty_n_per_mm=kt)
            signature.append((c.slave, c.master, fr.regime))
            B, P = _B(c, ndof), _projector(c.normal)
            if fr.regime == "STICK":
                # Kt = kt * B^T P B
                for a in range(ndof):
                    for b in range(ndof):
                        value = sum(B[i][a]*P[i][j]*B[j][b] for i in range(3) for j in range(3))
                        if value: k_eff[a][b] += kt*value
            elif fr.regime == "SLIP":
                # Physical Ft acts on slave; master gets -N_i Ft. Add B^T Ft to RHS.
                for a in range(ndof):
                    value = sum(B[i][a]*fr.tangential_force_n[i] for i in range(3))
                    if value: f_eff[a] += value
        u_new = _solve_linear(k_eff, f_eff, fixed)
        delta = max(abs(a-b) for a, b in zip(u_new, u))
        u = u_new
        sig = tuple(signature)
        if sig == previous_signature and delta <= displacement_tolerance_mm:
            break
        previous_signature = sig
    else:
        return _finish(nodes, base_k, force, fixed, slaves, masters, hint, kp, kt, mu,
                       search, activation_tolerance_mm, u, max_iterations, False, switches, allow_unmatched)
    return _finish(nodes, base_k, force, fixed, slaves, masters, hint, kp, kt, mu,
                   search, activation_tolerance_mm, u, iteration, True, switches, allow_unmatched)


def _finish(nodes, base_k, force, fixed, slaves, masters, hint, kp, kt, mu, search,
            activation_tol, u, iteration, converged, switches, allow_unmatched):
    candidates, unmatched = _search(_deformed(nodes, u), slaves, masters, hint, search, activation_tol)
    if unmatched and not allow_unmatched:
        raise UpdatedSurfaceFrictionError("final friction search lost master projection")
    contact_internal = [0.0]*len(u)
    states = []
    for c in candidates:
        fn = kp*max(0.0, -c.gap) if c.active else 0.0
        rel = _relative_u(c, u)
        fr = evaluate_coulomb_friction(rel, c.normal, normal_force_n=fn,
            friction_coefficient=mu, tangential_penalty_n_per_mm=kt)
        regime = fr.regime if c.active else "OPEN"
        if c.active:
            q = _q_normal(c, len(u))
            B = _B(c, len(u))
            for a, qa in enumerate(q): contact_internal[a] += kp*c.gap*qa
            for a in range(len(u)):
                contact_internal[a] -= sum(B[i][a]*fr.tangential_force_n[i] for i in range(3))
        master_ft = tuple(tuple(-w*x for x in fr.tangential_force_n) for w in c.barycentric)
        states.append(UpdatedSurfaceFrictionState(c.slave, c.master, c.gap,
            max(0.0, -c.gap) if c.active else 0.0, fn, fr.tangential_force_n,
            fr.tangential_force_magnitude_n, mu*fn, regime, c.active,
            c.barycentric, c.normal, master_ft))
    ku = [sum(base_k[i][j]*u[j] for j in range(len(u))) for i in range(len(u))]
    residual = [ku[i] + contact_internal[i] - force[i] for i in range(len(u))]
    reactions = [residual[i] if i in fixed else 0.0 for i in range(len(u))]
    return UpdatedSurfaceFrictionResult(tuple(u), tuple(reactions), tuple(residual), tuple(states),
                                        unmatched, iteration, converged, switches)


def solve_tet4_with_updated_surface_coulomb(nodes, elements, young, poisson,
                                              constraints, loads, **contact_kwargs):
    """Assemble verified TET4 stiffness then solve updated surface Coulomb contact."""
    return solve_updated_surface_coulomb_from_stiffness(
        nodes, assemble_stiffness(nodes, elements, young, poisson), constraints, loads,
        **contact_kwargs
    )
