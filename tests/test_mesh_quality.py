import numpy as np
import pytest

from astermax.fea.mesh_quality import MeshQualityError, require_mesh_quality, tetra_mesh_quality


def test_regular_tetrahedron_passes_quality_gate():
    nodes = np.array([[0.,0.,0.],[1.,0.,0.],[0.5,np.sqrt(3)/2,0.],[0.5,np.sqrt(3)/6,np.sqrt(2/3)]])
    report = tetra_mesh_quality(nodes, np.array([[0,1,2,3]]))
    assert report.status == "PASS"
    assert report.inverted_elements == 0
    assert report.degenerate_elements == 0
    assert report.min_mean_ratio == pytest.approx(1.0)
    require_mesh_quality(report)


def test_inverted_tetrahedron_fails_closed():
    nodes = np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
    report = tetra_mesh_quality(nodes, np.array([[0,2,1,3]]))
    assert report.status == "FAIL"
    assert report.inverted_elements == 1
    with pytest.raises(MeshQualityError):
        require_mesh_quality(report)


def test_sliver_tetrahedron_fails_quality_gate():
    nodes = np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[1e-6,1e-6,1e-8]])
    report = tetra_mesh_quality(nodes, np.array([[0,1,2,3]]))
    assert report.status == "FAIL"
    assert report.fail_elements == 1


def test_tet10_uses_corner_geometry_for_current_straight_sided_scope():
    corners = np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
    mids = np.array([(corners[0]+corners[1])/2,(corners[1]+corners[2])/2,(corners[2]+corners[0])/2,(corners[0]+corners[3])/2,(corners[1]+corners[3])/2,(corners[2]+corners[3])/2])
    nodes = np.vstack([corners,mids])
    report = tetra_mesh_quality(nodes, np.arange(10).reshape(1,10))
    assert report.status in {"PASS", "WARN"}
    assert report.fail_elements == 0
