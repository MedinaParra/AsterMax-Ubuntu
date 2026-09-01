"""Geometry-updated frictionless node-to-TRI3 contact verification solver.

Re-searches the master TRI3 on deformed geometry every iteration.  Search supports
legacy strict plane projection and a finite-TRI3 ``closest_feature`` policy that can
remain associated at edges/vertices.  This is an auditable updated-geometry/Picard
verification increment, not a production large-sliding Newton contact algorithm.
"""
from dataclasses import dataclass
import math
from typing import Mapping, Sequence
from .global_static import GlobalStaticError, _solve_dense, assemble_stiffness
from .surface_contact import SurfaceContactError, project_point_to_triangle, closest_point_to_triangle, triangle_unit_normal

class UpdatedSurfaceContactError(ValueError): pass

@dataclass(frozen=True)
class UpdatedSurfaceContactState:
    slave_node:int; master_nodes:tuple[int,int,int]; signed_gap_mm:float; penetration_mm:float
    normal_force_n:float; active:bool; barycentric:tuple[float,float,float]; normal:tuple[float,float,float]
    slave_force_n:tuple[float,float,float]; master_nodal_forces_n:tuple[tuple[float,float,float],...]
@dataclass(frozen=True)
class UpdatedSurfaceContactResult:
    displacements:tuple[float,...]; reactions:tuple[float,...]; residual:tuple[float,...]
    contact_states:tuple[UpdatedSurfaceContactState,...]; unmatched_slave_nodes:tuple[int,...]
    iterations:int; converged:bool; master_switch_count:int
@dataclass(frozen=True)
class _Candidate:
    slave:int; master:tuple[int,int,int]; gap:float; barycentric:tuple[float,float,float]
    normal:tuple[float,float,float]; active:bool

def _unit(v):
    if len(v)!=3: raise UpdatedSurfaceContactError("master normal hint must contain three components")
    x=tuple(float(a) for a in v); m=math.sqrt(sum(a*a for a in x))
    if not all(math.isfinite(a) for a in x) or m<=0: raise UpdatedSurfaceContactError("master normal hint must be finite and non-zero")
    return tuple(a/m for a in x)
def _dot(a,b): return sum(a[i]*b[i] for i in range(3))
def _sub(a,b): return tuple(a[i]-b[i] for i in range(3))
def _norm(a): return math.sqrt(_dot(a,a))
def _deformed(nodes,u): return tuple(tuple(float(nodes[i][j])+float(u[3*i+j]) for j in range(3)) for i in range(len(nodes)))
def _oriented_triangle(points,tri,hint):
    tri=tuple(int(i) for i in tri)
    try: n=triangle_unit_normal(*(points[i] for i in tri))
    except (SurfaceContactError,IndexError) as exc: raise UpdatedSurfaceContactError(str(exc)) from exc
    return (tri[0],tri[2],tri[1]) if _dot(n,hint)<0 else tri

def _search(points,slave_nodes,master_triangles,hint,search_distance,activation_tol,projection_mode):
    found,unmatched=[],[]; oriented=tuple(sorted(_oriented_triangle(points,t,hint) for t in master_triangles))
    for slave in sorted(set(int(i) for i in slave_nodes)):
        candidates=[]
        for tri in oriented:
            if slave in tri: continue
            try:
                if projection_mode=="strict":
                    p=project_point_to_triangle(points[slave],*(points[i] for i in tri)); distance=abs(p.signed_gap_mm)
                    if not p.inside_triangle: continue
                    normal=p.normal; gap=p.signed_gap_mm
                else:
                    p=closest_point_to_triangle(points[slave],*(points[i] for i in tri)); delta=_sub(points[slave],p.projected_point_mm); distance=_norm(delta)
                    # Keep the master orientation as the sign oracle, but use the closest-point line
                    # of action so edge/vertex force transfer does not create a spurious moment.
                    side=1.0 if _dot(p.normal,delta)>=0.0 else -1.0
                    normal=p.normal if distance<=1e-15 else tuple(side*x/distance for x in delta)
                    gap=side*distance
            except (SurfaceContactError,IndexError) as exc: raise UpdatedSurfaceContactError(str(exc)) from exc
            if distance<=search_distance: candidates.append((distance,tri,p,normal,gap))
        if not candidates: unmatched.append(slave); continue
        _,tri,p,normal,gap=min(candidates,key=lambda item:(item[0],item[1]))
        found.append(_Candidate(slave,tri,gap,p.barycentric,normal,gap < -activation_tol))
    return tuple(found),tuple(unmatched)
def _require_matches(unmatched,allow):
    if unmatched and not allow: raise UpdatedSurfaceContactError("updated contact search lost master projection for slave nodes: "+", ".join(str(i) for i in unmatched))
def _q(c,ndof):
    q=[0.0]*ndof
    for j in range(3): q[3*c.slave+j]=c.normal[j]
    for w,m in zip(c.barycentric,c.master):
        for j in range(3): q[3*m+j]-=w*c.normal[j]
    return tuple(q)
def _solve_linear(k,f,fixed):
    free=[i for i in range(len(k)) if i not in fixed]
    if not free: raise UpdatedSurfaceContactError("model has no free DOFs to solve")
    kr=[[k[i][j] for j in free] for i in free]; fr=[f[i]-sum(k[i][j]*v for j,v in fixed.items()) for i in free]
    try: ur=_solve_dense(kr,fr)
    except GlobalStaticError as exc: raise UpdatedSurfaceContactError(str(exc)) from exc
    u=[0.0]*len(k)
    for d,v in fixed.items(): u[d]=v
    for d,v in zip(free,ur): u[d]=v
    return u

def solve_updated_surface_contact_from_stiffness(nodes,stiffness,constraints:Mapping[int,float],loads:Mapping[int,float],*,slave_nodes,master_triangles,master_normal_hint,penalty_stiffness_n_per_mm,search_distance_mm,max_iterations=30,activation_tolerance_mm=1e-10,geometry_tolerance_mm=1e-9,allow_unmatched=False,projection_mode="strict"):
    ndof=len(stiffness)
    if ndof==0 or any(len(r)!=ndof for r in stiffness) or ndof%3: raise UpdatedSurfaceContactError("stiffness matrix must be square with 3 DOFs per node")
    if len(nodes)*3!=ndof or any(len(n)!=3 for n in nodes): raise UpdatedSurfaceContactError("nodes must match stiffness size and be 3D")
    if any(not math.isfinite(float(x)) for r in stiffness for x in r): raise UpdatedSurfaceContactError("stiffness entries must be finite")
    if projection_mode not in ("strict","closest_feature"): raise UpdatedSurfaceContactError("projection_mode must be 'strict' or 'closest_feature'")
    nc=len(nodes); slaves=tuple(sorted(set(int(i) for i in slave_nodes))); masters=tuple(tuple(int(i) for i in t) for t in master_triangles)
    if not slaves or not masters: raise UpdatedSurfaceContactError("slave nodes and master TRI3 candidates are required")
    if any(i<0 or i>=nc for i in slaves): raise UpdatedSurfaceContactError("slave surface references an unknown node")
    if any(len(t)!=3 or len(set(t))!=3 or any(i<0 or i>=nc for i in t) for t in masters): raise UpdatedSurfaceContactError("master surface contains invalid TRI3 connectivity")
    kp,search=float(penalty_stiffness_n_per_mm),float(search_distance_mm)
    if not math.isfinite(kp) or kp<=0: raise UpdatedSurfaceContactError("contact penalty stiffness must be finite and positive")
    if not math.isfinite(search) or search<0: raise UpdatedSurfaceContactError("contact search distance must be finite and non-negative")
    if max_iterations<=0: raise UpdatedSurfaceContactError("max_iterations must be positive")
    if not math.isfinite(activation_tolerance_mm) or activation_tolerance_mm<0 or not math.isfinite(geometry_tolerance_mm) or geometry_tolerance_mm<0: raise UpdatedSurfaceContactError("contact tolerances must be finite and non-negative")
    hint=_unit(master_normal_hint); fixed={int(d):float(v) for d,v in constraints.items()}; force=[0.0]*ndof
    for dof,value in loads.items():
        d,v=int(dof),float(value)
        if d<0 or d>=ndof or not math.isfinite(v): raise UpdatedSurfaceContactError("load references an unknown DOF or is non-finite")
        force[d]+=v
    for d,v in fixed.items():
        if d<0 or d>=ndof or not math.isfinite(v): raise UpdatedSurfaceContactError("constraint references an unknown DOF or is non-finite")
    base=[list(map(float,r)) for r in stiffness]; u=_solve_linear(base,force,fixed); previous={},; switches=0
    for iteration in range(1,max_iterations+1):
        cand,unmatched=_search(_deformed(nodes,u),slaves,masters,hint,search,activation_tolerance_mm,projection_mode); _require_matches(unmatched,allow_unmatched)
        current={c.slave:c.master for c in cand}
        for s,t in current.items():
            if s in previous and previous[s]!=t: switches+=1
        previous=current; ke=[r[:] for r in base]; fe=force[:]
        for c in cand:
            if not c.active: continue
            q=_q(c,ndof); c0=c.gap-sum(qi*ui for qi,ui in zip(q,u))
            for i,qi in enumerate(q):
                if qi==0: continue
                fe[i]-=kp*c0*qi
                for j,qj in enumerate(q):
                    if qj!=0: ke[i][j]+=kp*qi*qj
        un=_solve_linear(ke,fe,fixed); ncand,nun=_search(_deformed(nodes,un),slaves,masters,hint,search,activation_tolerance_mm,projection_mode); _require_matches(nun,allow_unmatched)
        sig=tuple((c.slave,c.master,c.active) for c in cand); nsig=tuple((c.slave,c.master,c.active) for c in ncand); delta=max(abs(a-b) for a,b in zip(un,u)); u=un
        if nsig==sig and delta<=geometry_tolerance_mm: break
    else:
        fc,um=_search(_deformed(nodes,u),slaves,masters,hint,search,activation_tolerance_mm,projection_mode); _require_matches(um,allow_unmatched)
        return UpdatedSurfaceContactResult(tuple(u),tuple(0.0 for _ in range(ndof)),tuple(float('nan') for _ in range(ndof)),_states(fc,kp),um,max_iterations,False,switches)
    fc,um=_search(_deformed(nodes,u),slaves,masters,hint,search,activation_tolerance_mm,projection_mode); _require_matches(um,allow_unmatched); states=_states(fc,kp); ci=[0.0]*ndof
    for c in fc:
        if c.active:
            q=_q(c,ndof)
            for i,qi in enumerate(q): ci[i]+=kp*c.gap*qi
    ku=[sum(base[i][j]*u[j] for j in range(ndof)) for i in range(ndof)]; res=[ku[i]+ci[i]-force[i] for i in range(ndof)]; reactions=[res[i] if i in fixed else 0.0 for i in range(ndof)]
    return UpdatedSurfaceContactResult(tuple(u),tuple(reactions),tuple(res),states,um,iteration,True,switches)
def _states(candidates,kp):
    out=[]
    for c in candidates:
        pen=max(0.0,-c.gap) if c.active else 0.0; fn=kp*pen; sf=tuple(fn*x for x in c.normal); mf=tuple(tuple(-w*x for x in sf) for w in c.barycentric)
        out.append(UpdatedSurfaceContactState(c.slave,c.master,c.gap,pen,fn,c.active,c.barycentric,c.normal,sf,mf))
    return tuple(out)
def solve_tet4_with_updated_surface_contact(nodes,elements,young,poisson,constraints,loads,**contact_kwargs):
    return solve_updated_surface_contact_from_stiffness(nodes,assemble_stiffness(nodes,elements,young,poisson),constraints,loads,**contact_kwargs)
