from types import SimpleNamespace
import numpy as np
import pytest

from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet4 import IsotropicMaterial
from astermax.persistent_viewport import extract_tet10_surface
from astermax.results_scene import build_results_scene
from astermax.solver_results_bridge import (
    STRESS_REPRESENTATION,
    bind_verified_tet10_solver_results,
    build_results_scene_from_desktop_summary,
    incident_element_ipmax_to_nodes,
)


def _single_tet10():
    # Exact Gmsh Tetrahedron10 order used by fea.solver.
    nodes = np.array([
        [0.,0.,0.], [10.,0.,0.], [0.,10.,0.], [0.,0.,10.],
        [5.,0.,0.], [5.,5.,0.], [0.,5.,0.], [0.,0.,5.], [0.,5.,5.], [5.,0.,5.],
    ])
    elements = np.array([[0,1,2,3,4,5,6,7,8,9]], dtype=int)
    return nodes, elements


def _solve_fixture():
    nodes, elements = _single_tet10()
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
    return nodes, elements, result


def test_gmsh_tet10_surface_uses_solver_midside_order():
    nodes, elements = _single_tet10()
    _, triangles = extract_tet10_surface(SimpleNamespace(nodes_mm=nodes, elements=elements))
    assert triangles.shape == (16, 3)
    # Geometric face y=0 is corners (0,1,3) with midsides 4:(0,1), 7:(0,3), 9:(1,3).
    plane_triangles = [tri for tri in triangles if np.allclose(nodes[tri, 1], 0.0)]
    assert len(plane_triangles) == 4
    assert set(np.unique(np.asarray(plane_triangles))) == {0, 1, 3, 4, 7, 9}
    assert 8 not in set(np.unique(np.asarray(plane_triangles)))


def test_actual_tet10_solver_binds_exact_displacement_and_traceable_stress_projection():
    nodes, elements, result = _solve_fixture()
    assert np.isfinite(result.displacement_mm).all()
    assert result.integration_point_von_mises_mpa.shape == (1, 4)

    binding, evidence = bind_verified_tet10_solver_results(
        nodes,
        elements,
        result,
        workspace_sha256="workspace-sha-verified",
        solve_evidence_sha256="solve-sha-verified",
    )
    np.testing.assert_allclose(binding.displacement_mm, result.displacement_mm)
    expected = float(result.integration_point_von_mises_mpa.max())
    np.testing.assert_allclose(binding.von_mises_mpa, expected)
    assert binding.stress_representation == STRESS_REPRESENTATION
    assert evidence.stress_source == "Tet10LinearStaticResult.integration_point_von_mises_mpa"

    scene = build_results_scene(nodes, binding, deformation_scale=1.0)
    np.testing.assert_allclose(scene.deformed_nodes_mm, nodes + result.displacement_mm)
    assert scene.stress_representation == STRESS_REPRESENTATION
    assert scene.scalar_min == pytest.approx(expected)
    assert scene.scalar_max == pytest.approx(expected)


def test_existing_desktop_runtime_summary_cuts_over_without_field_synthesis():
    nodes, elements, result = _solve_fixture()
    workspace_sha = "workspace-sha-verified"
    solve_sha = "solve-sha-verified"
    summary = {
        "production_results": {"workspace_sha256": workspace_sha, "solve_evidence_sha256": solve_sha},
        "solve_evidence": {"solve_evidence_sha256": solve_sha},
        "_runtime_results": {
            "workspace": SimpleNamespace(workspace_sha256=workspace_sha),
            "nodes_mm": nodes,
            "elements": elements,
            "result": result,
        },
    }
    scene, evidence = build_results_scene_from_desktop_summary(summary, deformation_scale=2.0)
    np.testing.assert_allclose(scene.deformed_nodes_mm, nodes + 2.0 * result.displacement_mm)
    assert evidence.displacement_source == "Tet10LinearStaticResult.displacement_mm"
    assert evidence.stress_representation == STRESS_REPRESENTATION

    stale = dict(summary)
    stale["production_results"] = dict(summary["production_results"], workspace_sha256="different")
    with pytest.raises(ValueError, match="SOLVER_RESULTS_DESKTOP_WORKSPACE_STALE"):
        build_results_scene_from_desktop_summary(stale)


def test_incident_element_projection_uses_max_not_average_and_fails_closed():
    elements = np.array([
        [0,1,2,3,4,5,6,7,8,9],
        [0,1,2,10,4,5,6,11,12,13],
    ], dtype=int)
    ip = np.array([[1.,2.,3.,4.], [7.,5.,6.,2.]])
    nodal = incident_element_ipmax_to_nodes(elements, ip, 14)
    assert nodal[0] == 7.0 and nodal[1] == 7.0 and nodal[2] == 7.0
    assert nodal[3] == 4.0 and nodal[10] == 7.0
    with pytest.raises(ValueError, match="SOLVER_RESULTS_IP_VON_MISES_SHAPE_INVALID"):
        incident_element_ipmax_to_nodes(elements, np.zeros((2, 3)), 14)
    with pytest.raises(ValueError, match="SOLVER_RESULTS_ORPHAN_NODE_STRESS_UNDEFINED"):
        incident_element_ipmax_to_nodes(elements[:1], np.zeros((1, 4)), 14)
