import numpy as np
import pytest

from astermax.code_aster_study import render_linear_static_comm
from astermax.face_resultant import (
    FaceResultantError,
    bind_force_resultant_to_uniform_traction,
    build_code_aster_study_from_face_resultant,
    triangulated_face_area_mm2,
)


def rectangle_face():
    nodes = np.array(
        [
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [10.0, 20.0, 0.0],
            [0.0, 20.0, 0.0],
        ]
    )
    triangles = np.array([[0, 1, 2], [0, 2, 3]], dtype=int)
    return nodes, triangles


def test_area_is_computed_from_actual_supplied_triangulation_mm2():
    nodes, triangles = rectangle_face()
    assert triangulated_face_area_mm2(nodes, triangles) == pytest.approx(200.0)


def test_total_force_is_preserved_when_converted_to_uniform_traction():
    nodes, triangles = rectangle_face()
    binding = bind_force_resultant_to_uniform_traction(nodes, triangles, (1000.0, -500.0, 250.0))
    assert binding.area_mm2 == pytest.approx(200.0)
    assert binding.traction_n_per_mm2 == pytest.approx((5.0, -2.5, 1.25))
    assert binding.recovered_force_n == pytest.approx((1000.0, -500.0, 250.0))
    assert binding.residual_norm_n <= 1.0e-10
    evidence = binding.as_evidence()
    assert evidence["fea_solve_executed"] is False
    assert evidence["results_verified"] is False


def test_bridge_feeds_verified_traction_into_code_aster_study():
    nodes, triangles = rectangle_face()
    study, binding = build_code_aster_study_from_face_resultant(
        mesh_filename="model.med",
        support_group="FIXED_FACE",
        load_group="LOAD_FACE",
        young_mpa=210000.0,
        poisson=0.3,
        face_nodes_mm=nodes,
        face_triangles=triangles,
        force_n=(0.0, -1000.0, 0.0),
    )
    assert binding.traction_n_per_mm2 == pytest.approx((0.0, -5.0, 0.0))
    comm = render_linear_static_comm(study)
    assert "FY=-5" in comm
    assert "FORCE_FACE" in comm


def test_area_is_orientation_independent():
    nodes, triangles = rectangle_face()
    reversed_triangles = triangles[:, ::-1]
    assert triangulated_face_area_mm2(nodes, reversed_triangles) == pytest.approx(200.0)


def test_degenerate_triangle_fails_closed():
    nodes = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
    with pytest.raises(FaceResultantError, match="DEGENERATE_TRIANGLE"):
        triangulated_face_area_mm2(nodes, np.array([[0, 1, 2]]))


def test_bad_connectivity_fails_closed():
    nodes, _ = rectangle_face()
    with pytest.raises(FaceResultantError, match="CONNECTIVITY_INVALID"):
        triangulated_face_area_mm2(nodes, np.array([[0, 1, 9]]))


def test_zero_force_fails_closed():
    nodes, triangles = rectangle_face()
    with pytest.raises(FaceResultantError, match="FORCE_ZERO"):
        bind_force_resultant_to_uniform_traction(nodes, triangles, (0.0, 0.0, 0.0))


def test_nonfinite_geometry_fails_closed():
    nodes, triangles = rectangle_face()
    nodes[0, 0] = np.nan
    with pytest.raises(FaceResultantError, match="NODES_NONFINITE"):
        triangulated_face_area_mm2(nodes, triangles)
