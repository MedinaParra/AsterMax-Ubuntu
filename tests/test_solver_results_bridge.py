import numpy as np
import pytest

from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet4 import IsotropicMaterial
from astermax.persistent_viewport import extract_tet10_surface
from astermax.results_scene import build_results_scene
from astermax.solver_results_bridge import (
    STRESS_REPRESENTATION,
    bind_verified_tet10_solver_results,
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


def test_gmsh_tet10_surface_uses_solver_midside_order():
    nodes, elements = _single_tet10()
    _, triangles = extract_tet10_surface(type("Inventory", (), {"nodes_mm": nodes, "elements": elements})())
    assert triangles.shape == (16, 3)
    # Face (0,1,3) must use edges 0-1=node4, 1-3=node9, 0-3=node7.
    face_nodes = {0,1,3,4,7,9}
    rendered = [set(map(int, tri)) for tri in triangles]
    assert any(9 in tri and tri.issubset(face_nodes) for tri in rendered)
    assert not any(8 in tri and tri.issubset(face_nodes | {8}) and tri.intersection({0,1,3}) for tri in rendered if tri.issubset({0,1,3,4,7,8,9}))


def test_actual_tet10_solver_binds_exact_displacement_and_traceable_stress_projection():
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


def test_incident_element_projection_uses_max_not_average_and_fails_closed():
    # Two artificial connectivity rows are enough to validate the projection rule.
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
