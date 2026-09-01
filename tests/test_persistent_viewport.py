from types import SimpleNamespace
import numpy as np
import pytest
from astermax.persistent_viewport import (ViewportSnapshot, extract_tet10_surface, project_surface, projected_box_segments, snapshot_from_inventory, snapshot_with_assignment, snapshot_with_results, stage_caption, validate_snapshot)


def _inventory():
    # One valid quadratic tetrahedron with all six midside nodes.
    return SimpleNamespace(nodes_mm=np.array([
        [0.,0.,0.],[100.,0.,0.],[0.,20.,0.],[0.,0.,10.],
        [50.,0.,0.],[50.,10.,0.],[0.,10.,0.],[0.,0.,5.],[50.,0.,5.],[0.,10.,5.]
    ]), elements=np.array([[0,1,2,3,4,5,6,7,8,9]], dtype=int))


def test_inventory_snapshot_is_real_mm_tet10_surface_evidence():
    inv=_inventory(); nodes,triangles=extract_tet10_surface(inv)
    assert nodes.shape==(10,3)
    assert triangles.shape==(16,3)  # four quadratic faces, four display triangles each
    snap=snapshot_from_inventory(inv)
    assert snap.stage=="MESH_READY" and snap.units==("mm","N","MPa")
    assert snap.bbox_min_mm==(0.0,0.0,0.0) and snap.bbox_max_mm==(100.0,20.0,10.0)
    assert snap.node_count==10 and snap.element_count==1 and snap.scene_triangle_count==16
    validate_snapshot(snap); assert len(projected_box_segments(snap))==12
    assert "16 surface triangles" in stage_caption(snap)


def test_surface_projection_is_deterministic_and_depth_sorted():
    nodes,triangles=extract_tet10_surface(_inventory())
    xy1,t1=project_surface(nodes,triangles,yaw_deg=35,pitch_deg=25)
    xy2,t2=project_surface(nodes,triangles,yaw_deg=35,pitch_deg=25)
    assert xy1.shape==(10,2) and t1.shape==(16,3)
    np.testing.assert_allclose(xy1,xy2); np.testing.assert_array_equal(t1,t2)


def test_internal_tet10_face_is_removed_from_display_surface():
    # Two TET10s share corner face (0,1,2) and its midsides (5,6,7).
    nodes=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1],[0,0,-1],
                    [.5,0,0],[.5,.5,0],[0,.5,0],[0,0,.5],[.5,0,.5],[0,.5,.5],
                    [0,0,-.5],[.5,0,-.5],[0,.5,-.5]],float)
    e1=[0,1,2,3,5,6,7,8,9,10]
    e2=[0,1,2,4,5,6,7,11,12,13]
    _,tri=extract_tet10_surface(SimpleNamespace(nodes_mm=nodes,elements=np.array([e1,e2])))
    assert tri.shape==(24,3)  # 6 external quadratic faces x 4 triangles; shared face excluded


def test_assignment_and_results_keep_geometry_and_require_provenance():
    base=snapshot_from_inventory(_inventory())
    assignment=SimpleNamespace(support_selection=SimpleNamespace(face_ids=("face-1",)),load_selection=SimpleNamespace(face_ids=("face-7","face-8")))
    bc=snapshot_with_assignment(base,assignment); validate_snapshot(bc)
    assert bc.scene_triangle_count==16 and bc.support_face_ids==("face-1",)
    summary={"production_results":{"workspace_sha256":"abc123"},"solve_evidence":{"solve_evidence_sha256":"def456"}}
    solved=snapshot_with_results(bc,summary); validate_snapshot(solved)
    assert solved.workspace_sha256=="abc123" and stage_caption(solved).endswith("results provenance verified")


def test_viewport_fails_closed_on_fake_results_units_or_non_tet10():
    with pytest.raises(ValueError,match="VIEWPORT_UNIT_CONTRACT_CHANGED"):
        validate_snapshot(ViewportSnapshot(stage="EMPTY",units=("m","N","Pa")))
    fake=ViewportSnapshot(stage="RESULTS_READY",units=("mm","N","MPa"),bbox_min_mm=(0,0,0),bbox_max_mm=(1,1,1),node_count=4,element_count=1,scene_triangle_count=4)
    with pytest.raises(ValueError,match="VIEWPORT_RESULTS_PROVENANCE_REQUIRED"): validate_snapshot(fake)
    with pytest.raises(ValueError,match="VIEWPORT_TET10_REQUIRED"):
        extract_tet10_surface(SimpleNamespace(nodes_mm=np.zeros((4,3)),elements=np.zeros((1,4),dtype=int)))
