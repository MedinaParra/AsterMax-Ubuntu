import numpy as np
import pytest

from astermax.interactive_scene import CameraState, fit_camera, orbit, pan_by, project_scene, scene_modes, triangle_wire_edges, validate_camera, zoom_by


def _mesh():
    nodes=np.array([[0.,0.,0.],[100.,0.,0.],[0.,20.,0.],[0.,0.,10.]])
    tri=np.array([[0,1,2],[0,1,3],[0,2,3],[1,2,3]],dtype=int)
    return nodes,tri


def test_camera_orbit_zoom_pan_and_fit_are_deterministic():
    c=CameraState()
    c=orbit(c,45.0,20.0)
    assert c.yaw_deg==80.0 and c.pitch_deg==45.0
    c=zoom_by(c,2.0); assert c.zoom==2.0
    c=pan_by(c,12.5,-3.0); assert c.pan_x==12.5 and c.pan_y==-3.0
    assert fit_camera()==CameraState()


def test_pitch_and_zoom_are_safely_bounded():
    assert orbit(CameraState(),0,200).pitch_deg==89.0
    assert orbit(CameraState(),0,-200).pitch_deg==-89.0
    assert zoom_by(CameraState(),1e9).zoom==100.0
    assert zoom_by(CameraState(),1e-9).zoom==0.01
    with pytest.raises(ValueError,match="SCENE_ZOOM_FACTOR_INVALID"): zoom_by(CameraState(),0)


def test_projection_uses_real_mesh_and_preserves_connectivity():
    nodes,tri=_mesh(); camera=CameraState()
    xy,ordered,edges=project_scene(nodes,tri,camera)
    assert xy.shape==(4,2) and ordered.shape==(4,3)
    assert sorted(map(tuple,map(sorted,ordered.tolist())))==sorted(map(tuple,map(sorted,tri.tolist())))
    assert edges.shape==(6,2)
    xy2,ordered2,edges2=project_scene(nodes,tri,camera)
    np.testing.assert_allclose(xy,xy2); np.testing.assert_array_equal(ordered,ordered2); np.testing.assert_array_equal(edges,edges2)


def test_interaction_changes_view_not_model_geometry():
    nodes,tri=_mesh(); original=nodes.copy()
    a,_,_=project_scene(nodes,tri,CameraState())
    b,_,_=project_scene(nodes,tri,orbit(CameraState(),25,-10))
    assert not np.allclose(a,b)
    np.testing.assert_array_equal(nodes,original)


def test_scene_fails_closed_on_bad_connectivity_and_bad_camera():
    nodes,tri=_mesh()
    with pytest.raises(ValueError,match="SCENE_CONNECTIVITY_OUT_OF_RANGE"):
        project_scene(nodes,np.array([[0,1,99]]),CameraState())
    with pytest.raises(ValueError,match="SCENE_CAMERA_NONFINITE"):
        validate_camera(CameraState(yaw_deg=float('nan')))


def test_only_verified_scene_modes_are_advertised():
    assert scene_modes()==("surface","wireframe","surface+edges")
    assert "von_mises" not in scene_modes()
