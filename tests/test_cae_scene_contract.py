from types import SimpleNamespace
import numpy as np
import pytest

from astermax.cae_scene_contract import (
    build_cae_scene_contract,
    renderer_capabilities,
    validate_cae_scene_contract,
)
from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet4 import IsotropicMaterial


def _fixture_summary():
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
    workspace_sha = "workspace-sha-c70"
    solve_sha = "solve-sha-c70"
    return {
        "production_results": {
            "workspace_sha256": workspace_sha,
            "solve_evidence_sha256": solve_sha,
        },
        "solve_evidence": {"solve_evidence_sha256": solve_sha},
        "_runtime_results": {
            "workspace": SimpleNamespace(workspace_sha256=workspace_sha),
            "nodes_mm": nodes,
            "elements": elements,
            "result": result,
        },
    }, nodes, result


def test_real_solver_builds_backend_neutral_scene_without_synthetic_fields():
    summary, nodes, result = _fixture_summary()
    scene = build_cae_scene_contract(summary, deformation_scale=2.0)
    assert scene.surface_triangles.shape == (16, 3)
    np.testing.assert_allclose(scene.undeformed_nodes_mm, nodes)
    np.testing.assert_allclose(scene.deformed_nodes_mm, nodes + 2.0 * result.displacement_mm)
    np.testing.assert_allclose(scene.displacement_magnitude_mm, np.linalg.norm(result.displacement_mm, axis=1))
    assert scene.length_unit == "mm"
    assert scene.stress_unit == "MPa"
    assert scene.workspace_sha256 == "workspace-sha-c70"
    assert scene.solve_evidence_sha256 == "solve-sha-c70"
    assert np.isfinite(scene.nodal_von_mises_mpa).all()
    assert np.isfinite(scene.triangle_von_mises_mpa).all()
    assert np.all((scene.triangle_scalar_normalized >= 0.0) & (scene.triangle_scalar_normalized <= 1.0))


def test_scene_contract_fails_closed_on_stale_provenance():
    summary, _, _ = _fixture_summary()
    summary["production_results"] = dict(summary["production_results"], workspace_sha256="stale")
    with pytest.raises(ValueError, match="SOLVER_RESULTS_DESKTOP_WORKSPACE_STALE"):
        build_cae_scene_contract(summary)


def test_renderer_contract_has_no_screen_projection_dependency():
    summary, _, _ = _fixture_summary()
    scene = build_cae_scene_contract(summary)
    validate_cae_scene_contract(scene)
    capabilities = renderer_capabilities()
    assert "deformed_geometry" in capabilities
    assert "von_mises_display_scalar" in capabilities
    assert "workspace_provenance" in capabilities
    assert not hasattr(scene, "xy")
    assert not hasattr(scene, "yaw_deg")
    assert not hasattr(scene, "zoom")
