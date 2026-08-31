"""Geometry-updated frictionless node-to-TRI3 contact verification solver.

Unlike ``global_surface_contact`` (small sliding), this solver re-searches the master
TRI3 on the deformed geometry every iteration and refreshes the contact normal and
barycentric coordinates. Each active contact uses a first-order gap linearization::

    g(u_new) ~= c + q^T u_new
    c = g(u_k) - q^T u_k
    q = [n, -N1*n, -N2*n, -N3*n]

with ``Kc = kp*q*q^T`` and ``f_contact = -kp*c*q``. This is an auditable
updated-geometry/Picard verification increment, not a production large-sliding Newton
contact algorithm. Missing master projections fail closed by default.
"""

from dataclasses import dataclass
import math
from typing import Mapping, Sequence

from .global_static import GlobalStaticError, _solve_dense, assemble_stiffness
from .surface_contact import SurfaceContactError, project_point_to_triangle, triangle_unit_normal


class UpdatedSurfaceContactError(ValueError):
    pass


@dataclass(frozen=True)
class UpdatedSurfaceContactState:
    slave_node: int
    master_nodes: tuple[int, int, int]
    signed_gap_mm: float
    penetration_mm: float
    normal_force_n: float
    active: bool
    barycentric: tuple[float, float, float]
    normal: tuple[float, float, float]
    slave_force_n: tuple[float, float, float]
    master_nodal_forces_n: tuple[tuple[float, float, float], ...]


@dataclass(frozen=True)
class UpdatedSurfaceContactResult:
    displacements: tuple[float, ...]
    reactions: tuple[float, ...]
    residual: tuple[float, ...]
    contact_states: tuple[UpdatedSurfaceContactState, ...]
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


def _unit(values: Sequence[float]) -> tuple[float, float, float]:
    if len(values) != 3:
        raise UpdatedSurfaceContactError("master normal hint must contain three components")
    v = tuple(float(x) for x in values)
    if not all(math.isfinite(x) for x in v):
        raise UpdatedSurfaceContactError("master normal hint must be finite")
    mag = math.sqrt(sum(x*x for x in v))
    if mag <= 0.0:
        raise UpdatedSurfaceContactError("master normal hint must be non-zero")
    return tuple(x/mag for x in v)


def _dot(a, b):
    return sum(a[i]*b[i] for i in range(3))


def _deformed(nodes, u):
    return tuple(tuple(float(nodes[i][j]) + float(u[3*i+j]) for j in range(3)) for i in range(len(nodes)))


def _oriented_triangle(points, tri, hint):
    tri = tuple(int(i) for i in tri)
    try:
        n = triangle_unit_normal(*(points[i] for i in tri))
    except (SurfaceContactError, IndexError) as exc:
        raise UpdatedSurfaceContactError(str(exc)) from exc
    if _dot(n, hint) < 0.0:
        tri = (tri[0], tri[2], tri[1])
    return tri


def _search(points, slave_nodes, master_triangles, hint, search_distance, activation_tol):
    found, unmatched = [], []
    oriented = tuple(sorted(_oriented_triangle(points, tri, hint) for tri in master_triangles))
    for slave in sorted(set(int(i) for i in slave_nodes)):
        candidates = []
        for tri in oriented:
            if slave in tri:
                continue
            try:
                p = project_point_to_triangle(points[slave], *(points[i] for i in tri))
            except (SurfaceContactError, IndexError) as exc:
                raise UpdatedSurfaceContactError(str(exc)) from exc
            distance = abs(p.signed_gap_mm)
            if p.inside_triangle and distance <= search_distance:
                candidates.append((distance, tri, p))
        if not candidates:
            unmatched.append(slave)
            continue
        _, tri, p = min(candidates, key=lambda item: (item[0], item[1]))
        found.append(_Candidate(slave, tri, p.signed_gap_mm, p.barycentric, p.normal,
                                p.signed_gap_mm < -activation_tol))
    return tuple(found), tuple(unmatched)


def _require_matches(unmatched, allow_unmatched):
    if unmatched and not allow_unmatched:
        raise UpdatedSurfaceContactError(
            "updated contact search lost master projection for slave nodes: " +
            ", ".join(str(i) for i in unmatched)
        )


def _q(candidate: _Candidate, ndof: int) -> tuple[float, ...]:
    q = [0.0]*ndof
    for c in range(3):
        q[3*candidate.slave+c] = candidate.normal[c]
    for weight, master in zip(candidate.barycentric, candidate.master):
        for c in range(3):
            q[3*master+c] -= weight*candidate.normal[c]
    return tuple(q)


def _solve_linear(k, f, fixed):
    ndof = len(k)
    free = [i for i in range(ndof) if i not in fixed]
    if not free:
        raise UpdatedSurfaceContactError("model has no free DOFs to solve")
    kr = [[k[i][j] for j in free] for i in free]
    fr = [f[i] - sum(k[i][j]*value for j, value in fixed.items()) for i in free]
    try:
        ur = _solve_dense(kr, fr)
    except GlobalStaticError as exc:
        raise UpdatedSurfaceContactError(str(exc)) from exc
    u = [0.0]*ndof
    for dof, value in fixed.items():
        u[dof] = value
    for dof, value in zip(free, ur):
        u[dof] = value
    return u


def solve_updated_surface_contact_from_stiffness(
    nodes: Sequence[Sequence[float]], stiffness: Sequence[Sequence[float]],
    constraints: Mapping[int, float], loads: Mapping[int, float], *,
    slave_nodes: Sequence[int], master_triangles: Sequence[Sequence[int]],
    master_normal_hint: Sequence[float], penalty_stiffness_n_per_mm: float,
    search_distance_mm: float, max_iterations: int = 30,
    activation_tolerance_mm: float = 1e-10, geometry_tolerance_mm: float = 1e-9,
    allow_unmatched: bool = False,
) -> UpdatedSurfaceContactResult:
    """Solve frictionless contact with deformed-geometry master re-search.

    ``allow_unmatched=False`` is the engineering-safe default. Set it True only for
    diagnostics where intentionally lost contact candidates must remain observable.
    """
    ndof = len(stiffness)
    if ndof == 0 or any(len(row) != ndof for row in stiffness) or ndof % 3:
        raise UpdatedSurfaceContactError("stiffness matrix must be square with 3 DOFs per node")
    if len(nodes)*3 != ndof or any(len(node) != 3 for node in nodes):
        raise UpdatedSurfaceContactError("nodes must match stiffness size and be 3D")
    if any(not math.isfinite(float(x)) for row in stiffness for x in row):
        raise UpdatedSurfaceContactError("stiffness entries must be finite")
    node_count = len(nodes)
    slaves = tuple(sorted(set(int(i) for i in slave_nodes)))
    masters = tuple(tuple(int(i) for i in tri) for tri in master_triangles)
    if not slaves or not masters:
        raise UpdatedSurfaceContactError("slave nodes and master TRI3 candidates are required")
    if any(i < 0 or i >= node_count for i in slaves):
        raise UpdatedSurfaceContactError("slave surface references an unknown node")
    if any(len(tri) != 3 or len(set(tri)) != 3 or any(i < 0 or i >= node_count for i in tri) for tri in masters):
        raise UpdatedSurfaceContactError("master surface contains invalid TRI3 connectivity")
    kp, search = float(penalty_stiffness_n_per_mm), float(search_distance_mm)
    if not math.isfinite(kp) or kp <= 0.0:
        raise UpdatedSurfaceContactError("contact penalty stiffness must be finite and positive")
    if not math.isfinite(search) or search < 0.0:
        raise UpdatedSurfaceContactError("contact search distance must be finite and non-negative")
    if max_iterations <= 0:
        raise UpdatedSurfaceContactError("max_iterations must be positive")
    if (not math.isfinite(activation_tolerance_mm) or activation_tolerance_mm < 0.0 or
            not math.isfinite(geometry_tolerance_mm) or geometry_tolerance_mm < 0.0):
        raise UpdatedSurfaceContactError("contact tolerances must be finite and non-negative")
    hint = _unit(master_normal_hint)

    fixed = {int(d): float(v) for d, v in constraints.items()}
    force = [0.0]*ndof
    for dof, value in loads.items():
        d, v = int(dof), float(value)
        if d < 0 or d >= ndof or not math.isfinite(v):
            raise UpdatedSurfaceContactError("load references an unknown DOF or is non-finite")
        force[d] += v
    for dof, value in fixed.items():
        if dof < 0 or dof >= ndof or not math.isfinite(value):
            raise UpdatedSurfaceContactError("constraint references an unknown DOF or is non-finite")

    base_k = [list(map(float, row)) for row in stiffness]
    u = _solve_linear(base_k, force, fixed)
    previous_master, switches = {}, 0

    for iteration in range(1, max_iterations+1):
        candidates, unmatched = _search(_deformed(nodes, u), slaves, masters, hint, search, activation_tolerance_mm)
        _require_matches(unmatched, allow_unmatched)
        current_master = {c.slave: c.master for c in candidates}
        for slave, tri in current_master.items():
            if slave in previous_master and previous_master[slave] != tri:
                switches += 1
        previous_master = current_master

        k_eff, f_eff = [row[:] for row in base_k], force[:]
        for candidate in candidates:
            if not candidate.active:
                continue
            q = _q(candidate, ndof)
            c0 = candidate.gap - sum(qi*ui for qi, ui in zip(q, u))
            for i, qi in enumerate(q):
                if qi == 0.0:
                    continue
                f_eff[i] -= kp*c0*qi
                for j, qj in enumerate(q):
                    if qj != 0.0:
                        k_eff[i][j] += kp*qi*qj
        u_new = _solve_linear(k_eff, f_eff, fixed)
        new_candidates, new_unmatched = _search(_deformed(nodes, u_new), slaves, masters, hint, search, activation_tolerance_mm)
        _require_matches(new_unmatched, allow_unmatched)
        sig = tuple((c.slave, c.master, c.active) for c in candidates)
        new_sig = tuple((c.slave, c.master, c.active) for c in new_candidates)
        delta = max(abs(a-b) for a, b in zip(u_new, u))
        u = u_new
        if new_sig == sig and delta <= geometry_tolerance_mm:
            break
    else:
        final_candidates, unmatched = _search(_deformed(nodes, u), slaves, masters, hint, search, activation_tolerance_mm)
        _require_matches(unmatched, allow_unmatched)
        return UpdatedSurfaceContactResult(tuple(u), tuple(0.0 for _ in range(ndof)),
            tuple(float("nan") for _ in range(ndof)), _states(final_candidates, kp), unmatched,
            max_iterations, False, switches)

    final_candidates, unmatched = _search(_deformed(nodes, u), slaves, masters, hint, search, activation_tolerance_mm)
    _require_matches(unmatched, allow_unmatched)
    states = _states(final_candidates, kp)
    contact_internal = [0.0]*ndof
    for candidate in final_candidates:
        if candidate.active:
            q = _q(candidate, ndof)
            for i, qi in enumerate(q):
                contact_internal[i] += kp*candidate.gap*qi
    ku = [sum(base_k[i][j]*u[j] for j in range(ndof)) for i in range(ndof)]
    residual = [ku[i] + contact_internal[i] - force[i] for i in range(ndof)]
    reactions = [residual[i] if i in fixed else 0.0 for i in range(ndof)]
    return UpdatedSurfaceContactResult(tuple(u), tuple(reactions), tuple(residual), states,
        unmatched, iteration, True, switches)


def _states(candidates, kp):
    result = []
    for c in candidates:
        penetration = max(0.0, -c.gap) if c.active else 0.0
        fn = kp*penetration
        sf = tuple(fn*x for x in c.normal)
        mf = tuple(tuple(-w*x for x in sf) for w in c.barycentric)
        result.append(UpdatedSurfaceContactState(c.slave, c.master, c.gap, penetration, fn,
            c.active, c.barycentric, c.normal, sf, mf))
    return tuple(result)


def solve_tet4_with_updated_surface_contact(nodes, elements, young, poisson,
                                             constraints, loads, **contact_kwargs):
    """Assemble verified TET4 stiffness then solve with updated-geometry contact."""
    return solve_updated_surface_contact_from_stiffness(
        nodes, assemble_stiffness(nodes, elements, young, poisson), constraints, loads,
        **contact_kwargs
    )
