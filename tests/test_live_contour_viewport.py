from types import SimpleNamespace
import numpy as np
import pytest

from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet4 import IsotropicMaterial
from astermax.live_contour_viewport import build_contour_frame, fit_xy, scalar_hex


def _summary():
    nodes=np.array([
        [0.,0.,0.],[10.,0.,0.],[0.,10.,0.],[0.,0.,10.],
        [5.,0.,0.],[5.,5.,0.],[0.,5.,0.],[0.,0.,5.],[0.,5.,5.],[5.,0.,5.],
    ])
    elements=np.array([[0,1,2,3,4,5,6,7,8,9]],dtype=int)
    loads=np.zeros((10,3)); loads[3,2]=-100.0
    fixed_nodes=(0,1,2,4,5,6)
    fixed=[3*n+d for n in fixed_nodes for d in range(3)]
    result=solve_linear_static_tet10(nodes,elements,IsotropicMaterial(young_modulus_mpa=200000.,poisson_ratio=.30),loads,fixed)
    workspace_sha="workspace-sha-c69"; solve_sha="solve-sha-c69"
    return {
        "production_results":{"workspace_sha256":workspace_sha,"solve_evidence_sha256":solve_sha},
        "solve_evidence":{"solve_evidence_sha256":solve_sha},
        "_runtime_results":{"workspace":SimpleNamespace(workspace_sha256=workspace_sha),"nodes_mm":nodes,"elements":elements,"result":result},
    }, nodes, result


def test_live_contour_uses_actual_solver_deformation_and_surface():
    summary,nodes,result=_summary()
    frame=build_contour_frame(summary,deformation_scale=3.0)
    assert frame.triangles.shape==(16,3)
    assert frame.xy.shape==(10,2)
    assert frame.triangle_scalar.shape==(16,)
    assert np.all((frame.triangle_scalar>=0)&(frame.triangle_scalar<=1))
    assert frame.workspace_sha256=="workspace-sha-c69"
    assert frame.solve_evidence_sha256=="solve-sha-c69"
    assert "NO_SMOOTHING" in frame.stress_representation
    # Changing deformation scale must change projected geometry when displacement is non-zero.
    frame0=build_contour_frame(summary,deformation_scale=0.0)
    assert not np.allclose(frame.xy,frame0.xy)
    assert np.linalg.norm(result.displacement_mm)>0


def test_live_contour_fails_closed_on_stale_evidence():
    summary,_,_=_summary()
    summary["production_results"]["workspace_sha256"]="stale-workspace"
    with pytest.raises(ValueError,match="SOLVER_RESULTS_DESKTOP_WORKSPACE_STALE"):
        build_contour_frame(summary)


def test_fit_zoom_pan_and_palette_are_deterministic():
    xy=np.array([[-1.,-1.],[1.,1.],[1.,-1.]])
    a=fit_xy(xy,800,600,zoom=1.0,pan=(0,0))
    b=fit_xy(xy,800,600,zoom=2.0,pan=(20,-10))
    assert a.shape==(3,2) and b.shape==(3,2)
    assert np.ptp(b[:,0])>np.ptp(a[:,0])
    assert scalar_hex(0.0)=="#0000ff"
    assert scalar_hex(1.0)=="#ff0000"
    with pytest.raises(ValueError,match="LIVE_CONTOUR_VIEW_INVALID"):
        fit_xy(xy,20,20)
