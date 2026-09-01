"""Auditable frictionless node-to-TRI3 contact geometry for AsterMax PMV.

The legacy orthogonal plane projection remains unchanged.  A separate closest-point
operator adds explicit edge/vertex support for robust finite-TRI3 pairing without
silently changing existing contact models. Units: mm and N.
"""

from dataclasses import dataclass
import math
from typing import Sequence


class SurfaceContactError(ValueError):
    """Raised for invalid TRI3 contact geometry or contact parameters."""


@dataclass(frozen=True)
class TriangleProjection:
    projected_point_mm: tuple[float, float, float]
    barycentric: tuple[float, float, float]
    normal: tuple[float, float, float]
    signed_gap_mm: float
    inside_triangle: bool


@dataclass(frozen=True)
class NodeTriangleContactState:
    signed_gap_mm: float
    penetration_mm: float
    normal_force_n: float
    active: bool
    barycentric: tuple[float, float, float]
    slave_force_n: tuple[float, float, float]
    master_nodal_forces_n: tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]


def _vec3(values: Sequence[float], name: str) -> tuple[float, float, float]:
    if len(values) != 3:
        raise SurfaceContactError(f"{name} must contain three components")
    result = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in result):
        raise SurfaceContactError(f"{name} components must be finite")
    return result


def _sub(a, b): return tuple(a[i] - b[i] for i in range(3))
def _add(a, b): return tuple(a[i] + b[i] for i in range(3))
def _scale(a, factor): return tuple(factor * a[i] for i in range(3))
def _dot(a, b): return sum(a[i] * b[i] for i in range(3))
def _cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def _norm(a): return math.sqrt(_dot(a, a))


def triangle_unit_normal(a_mm, b_mm, c_mm) -> tuple[float, float, float]:
    a, b, c = _vec3(a_mm, "triangle node a"), _vec3(b_mm, "triangle node b"), _vec3(c_mm, "triangle node c")
    raw = _cross(_sub(b, a), _sub(c, a)); magnitude = _norm(raw)
    if magnitude <= 0.0:
        raise SurfaceContactError("master triangle is degenerate")
    return _scale(raw, 1.0 / magnitude)


def project_point_to_triangle(point_mm, a_mm, b_mm, c_mm, *, barycentric_tolerance: float = 1e-10) -> TriangleProjection:
    """Orthogonally project a point to the TRI3 plane (legacy strict-facet route)."""
    if not math.isfinite(barycentric_tolerance) or barycentric_tolerance < 0.0:
        raise SurfaceContactError("barycentric tolerance must be finite and non-negative")
    p, a, b, c = _vec3(point_mm,"slave point"), _vec3(a_mm,"triangle node a"), _vec3(b_mm,"triangle node b"), _vec3(c_mm,"triangle node c")
    normal = triangle_unit_normal(a,b,c); gap = _dot(normal,_sub(p,a)); projected = _sub(p,_scale(normal,gap))
    v0,v1,v2=_sub(b,a),_sub(c,a),_sub(projected,a)
    d00,d01,d11,d20,d21=_dot(v0,v0),_dot(v0,v1),_dot(v1,v1),_dot(v2,v0),_dot(v2,v1)
    denominator=d00*d11-d01*d01; scale=max(d00*d11,1.0)
    if abs(denominator) <= 1e-14*scale:
        raise SurfaceContactError("master triangle is numerically degenerate")
    beta=(d11*d20-d01*d21)/denominator; gamma=(d00*d21-d01*d20)/denominator; alpha=1.0-beta-gamma
    bary=(alpha,beta,gamma)
    inside=all(v>=-barycentric_tolerance for v in bary) and all(v<=1.0+barycentric_tolerance for v in bary)
    return TriangleProjection(projected,bary,normal,gap,inside)


def closest_point_to_triangle(point_mm, a_mm, b_mm, c_mm) -> TriangleProjection:
    """Return the exact closest point on a finite TRI3, including edges/vertices.

    Implements the region tests from Real-Time Collision Detection (Ericson).  The
    returned barycentric weights are always convex and therefore suitable for
    conservative master-force distribution.  ``signed_gap_mm`` remains the oriented
    normal gap; callers should use Euclidean point-to-closest distance for search
    acceptance when the closest feature is an edge or vertex.
    """
    p,a,b,c=_vec3(point_mm,"slave point"),_vec3(a_mm,"triangle node a"),_vec3(b_mm,"triangle node b"),_vec3(c_mm,"triangle node c")
    normal=triangle_unit_normal(a,b,c); ab=_sub(b,a); ac=_sub(c,a); ap=_sub(p,a)
    d1,d2=_dot(ab,ap),_dot(ac,ap)
    if d1<=0.0 and d2<=0.0: bary=(1.0,0.0,0.0); q=a
    else:
        bp=_sub(p,b); d3,d4=_dot(ab,bp),_dot(ac,bp)
        if d3>=0.0 and d4<=d3: bary=(0.0,1.0,0.0); q=b
        else:
            vc=d1*d4-d3*d2
            if vc<=0.0 and d1>=0.0 and d3<=0.0:
                v=d1/(d1-d3); bary=(1.0-v,v,0.0); q=_add(a,_scale(ab,v))
            else:
                cp=_sub(p,c); d5,d6=_dot(ab,cp),_dot(ac,cp)
                if d6>=0.0 and d5<=d6: bary=(0.0,0.0,1.0); q=c
                else:
                    vb=d5*d2-d1*d6
                    if vb<=0.0 and d2>=0.0 and d6<=0.0:
                        w=d2/(d2-d6); bary=(1.0-w,0.0,w); q=_add(a,_scale(ac,w))
                    else:
                        va=d3*d6-d5*d4
                        if va<=0.0 and (d4-d3)>=0.0 and (d5-d6)>=0.0:
                            bc=_sub(c,b); w=(d4-d3)/((d4-d3)+(d5-d6)); bary=(0.0,1.0-w,w); q=_add(b,_scale(bc,w))
                        else:
                            denom=va+vb+vc
                            if abs(denom)<=1e-30: raise SurfaceContactError("master triangle is numerically degenerate")
                            v=vb/denom; w=vc/denom; bary=(1.0-v-w,v,w); q=_add(a,_add(_scale(ab,v),_scale(ac,w)))
    gap=_dot(normal,_sub(p,q))
    return TriangleProjection(q,bary,normal,gap,True)


def evaluate_node_triangle_penalty_contact(slave_point_mm,a_mm,b_mm,c_mm,*,penalty_stiffness_n_per_mm:float,activation_tolerance_mm:float=1e-10) -> NodeTriangleContactState:
    penalty=float(penalty_stiffness_n_per_mm)
    if not math.isfinite(penalty) or penalty<=0.0: raise SurfaceContactError("contact penalty stiffness must be finite and positive")
    if not math.isfinite(activation_tolerance_mm) or activation_tolerance_mm<0.0: raise SurfaceContactError("activation tolerance must be finite and non-negative")
    projection=project_point_to_triangle(slave_point_mm,a_mm,b_mm,c_mm)
    active=projection.inside_triangle and projection.signed_gap_mm < -activation_tolerance_mm
    penetration=max(0.0,-projection.signed_gap_mm) if active else 0.0; normal_force=penalty*penetration
    slave_force=_scale(projection.normal,normal_force); master_total=_scale(slave_force,-1.0)
    master_forces=tuple(_scale(master_total,w) for w in projection.barycentric)
    return NodeTriangleContactState(projection.signed_gap_mm,penetration,normal_force,active,projection.barycentric,slave_force,master_forces)


def resultant_and_moment_about_origin(slave_point_mm,slave_force_n,master_points_mm,master_forces_n):
    if len(master_points_mm)!=3 or len(master_forces_n)!=3: raise SurfaceContactError("TRI3 force recovery requires three master nodes/forces")
    points=[_vec3(slave_point_mm,"slave point")]+[_vec3(p,"master point") for p in master_points_mm]
    forces=[_vec3(slave_force_n,"slave force")]+[_vec3(f,"master force") for f in master_forces_n]
    resultant=[0.0]*3; moment=[0.0]*3
    for point,force in zip(points,forces):
        cross=_cross(point,force)
        for i in range(3): resultant[i]+=force[i]; moment[i]+=cross[i]
    return tuple(resultant),tuple(moment)
