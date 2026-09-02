import numpy as np
import pytest

from astermax.cad_mesh_face_consistency import (
    CadMeshFaceConsistencyError,
    verify_cad_face_mesh_surface,
)


def rectangle_surface():
    nodes = np.array([
        [0.0, 0.0, 0.0],
        [20.0, 0.0, 0.0],
        [20.0, 10.0, 0.0],
        [0.0, 10.0, 0.0],
    ])
    triangles = np.array([[0, 1, 2], [0, 2, 3]])
    return nodes, triangles


def test_exact_cad_area_matches_mesh_surface():
    nodes, triangles = rectangle_surface()
    result = verify_cad_face_mesh_surface(
        cad_face_id="FACE:12",
        cad_area_mm2=200.0,
        mesh_group="LOAD_FACE_12",
        mesh_nodes_mm=nodes,
        mesh_triangles=triangles,
    )
    assert result.verified is True
    assert result.cad_area_mm2 == 200.0
    assert result.mesh_area_mm2 == pytest.approx(200.0)
    assert result.relative_area_error == pytest.approx(0.0)
    assert result.triangle_count == 2


def test_small_mesh_area_error_within_gate_is_accepted():
    nodes, triangles = rectangle_surface()
    result = verify_cad_face_mesh_surface(
        cad_face_id="FACE:12",
        cad_area_mm2=200.5,
        mesh_group="LOAD_FACE_12",
        mesh_nodes_mm=nodes,
        mesh_triangles=triangles,
        relative_area_tolerance=0.005,
    )
    assert result.relative_area_error < 0.005


def test_area_mismatch_fails_closed():
    nodes, triangles = rectangle_surface()
    with pytest.raises(CadMeshFaceConsistencyError, match="CAD_MESH_AREA_MISMATCH"):
        verify_cad_face_mesh_surface(
            cad_face_id="FACE:12",
            cad_area_mm2=250.0,
            mesh_group="LOAD_FACE_12",
            mesh_nodes_mm=nodes,
            mesh_triangles=triangles,
        )


def test_duplicate_surface_triangle_fails_closed():
    nodes, triangles = rectangle_surface()
    duplicated = np.vstack([triangles, triangles[0]])
    with pytest.raises(CadMeshFaceConsistencyError, match="CAD_MESH_DUPLICATE_TRIANGLE"):
        verify_cad_face_mesh_surface(
            cad_face_id="FACE:12",
            cad_area_mm2=300.0,
            mesh_group="LOAD_FACE_12",
            mesh_nodes_mm=nodes,
            mesh_triangles=duplicated,
        )


def test_missing_persistent_face_identity_fails_closed():
    nodes, triangles = rectangle_surface()
    with pytest.raises(CadMeshFaceConsistencyError, match="CAD_FACE_ID_MISSING"):
        verify_cad_face_mesh_surface(
            cad_face_id="",
            cad_area_mm2=200.0,
            mesh_group="LOAD_FACE_12",
            mesh_nodes_mm=nodes,
            mesh_triangles=triangles,
        )
