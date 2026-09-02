from types import SimpleNamespace
import numpy as np
import pytest

from astermax.fast_contour_viewport import build_cached_contour_data, project_cached_contour
from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet4 import IsotropicMaterial


def _summary():
    nodes = np.array([
        [0.,0.,0.], [10.,0.,0.], [0.,10.,0.], [0.,0.,10.],
        [5.,0.,0.], [5.,5.,0.], [0.,5.,0.], [0.,0.,5.], [0.,5.,5.], [5.,0.,5.],
    ])
    elements = np.array([[0,1,2,3,4,5,6,7,8,9]], dtype=int)
    loads = np.zeros((len(nodes), 3), dtype=float)
    loads[3, 2] = -100.0
    fixed_nodes = (0, 1, 2, 4, 5, 6)
    fixed_dofs = [3*n + d for n in fixed_nodes for d in range(3)]
    result = solve_linear_static_tet10(
        nodes,
        elements,
        IsotropicMaterial(young_modulus_mpa=200000.0, poisson_ratio=0.30),
        loads,
        fixed_dofs,
    )
    workspace_sha = "workspace-sha-c71"
    solve_sha = "solve-sha-c71"
    return {
        "production_results": {"workspace_sha256": workspace_sha, "solve_evidence_sha256": solve_sha},
        "solve_evidence": {"solve_evidence_sha256": solve_sha},
        "_runtime_results": {
            "workspace": SimpleNamespace(workspace_sha256=workspace_sha),
            "nodes_mm": nodes,
            "elements": elements,
            "result": result,
        },
    }


def test_cached_contour_builds_verified_scene_once_and_projection_preserves_surface_scalars():
    data = build_cached_contour_data(_summary(), deformation_scale=2.0)
    assert data.scene.surface_triangles.shape == (16, 3)
    assert len(data.triangle_scalar_by_key) == 16
    xy_a, tri_a, scalars_a = project_cached_contour(data, yaw_deg=35.0, pitch_deg=25.0)
    xy_b, tri_b, scalars_b = project_cached_contour(data, yaw_deg=55.0, pitch_deg=25.0)
    assert xy_a.shape == xy_b.shape == (10, 2)
    assert tri_a.shape == tri_b.shape == (16, 3)
    assert scalars_a.shape == scalars_b.shape == (16,)
    # Orbit changes only display projection; evidence-bound physical scene remains immutable.
    assert not np.allclose(xy_a, xy_b)
    assert data.scene.workspace_sha256 == "workspace-sha-c71"
    assert data.scene.solve_evidence_sha256 == "solve-sha-c71"
    for tri, scalar in zip(tri_a, scalars_a):
        assert scalar == pytest.approx(data.triangle_scalar_by_key[tuple(int(v) for v in tri)])


def test_cached_contour_still_fails_closed_on_stale_solver_evidence():
    summary = _summary()
    summary["production_results"] = dict(summary["production_results"], solve_evidence_sha256="stale")
    with pytest.raises(ValueError, match="SOLVER_RESULTS_DESKTOP_SOLVE_STALE"):
        build_cached_contour_data(summary)
