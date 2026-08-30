from dataclasses import dataclass

import numpy as np
import pytest

from astermax.fea.robust_surface_association import (
    SurfaceAssociationError,
    build_mesh_surface_descriptor,
    choose_unique_cad_face,
)


@dataclass(frozen=True)
class Sig:
    sha256: str
    surface_type: str
    area_mm2: float
    center_mm: tuple[float, float, float]
    bbox_mm: tuple[float, float, float, float, float, float]


def _square_tri6():
    nodes = np.array([
        [0.,0.,0.], [10.,0.,0.], [10.,10.,0.], [0.,10.,0.],
        [5.,0.,0.], [10.,5.,0.], [5.,5.,0.], [5.,10.,0.], [0.,5.,0.]
    ])
    tris = np.array([[0,1,2,4,5,6],[0,2,3,6,7,8]], dtype=np.int64)
    return nodes, tris


def test_descriptor_recovers_planar_geometry():
    nodes, tris = _square_tri6()
    d = build_mesh_surface_descriptor(nodes, tris)
    assert d.area_mm2 == pytest.approx(100.0)
    assert d.bbox_mm == pytest.approx((0,0,0,10,10,0))
    assert d.normal_abs == pytest.approx((0,0,1))


def test_unique_match_uses_bbox_centroid_area_and_plane_normal():
    nodes, tris = _square_tri6()
    d = build_mesh_surface_descriptor(nodes, tris)
    good = Sig('a'*64, 'Plane', 100.0, (5,5,0), (0,0,0,10,10,0))
    wrong = Sig('b'*64, 'Plane', 100.0, (5,5,20), (0,0,20,10,10,20))
    match, metrics = choose_unique_cad_face(d, [(1, wrong),(2, good)], 30.0)
    assert match.sha256 == good.sha256
    assert metrics['area_error_rel'] == pytest.approx(0.0)


def test_ambiguous_match_fails_closed():
    nodes, tris = _square_tri6()
    d = build_mesh_surface_descriptor(nodes, tris)
    a = Sig('a'*64, 'Plane', 100.0, (5,5,0), (0,0,0,10,10,0))
    b = Sig('b'*64, 'Plane', 100.0, (5,5,0), (0,0,0,10,10,0))
    with pytest.raises(SurfaceAssociationError, match='SURFACE_ASSOC_AMBIGUOUS'):
        choose_unique_cad_face(d, [(1,a),(2,b)], 30.0)


def test_area_mismatch_fails_closed():
    nodes, tris = _square_tri6()
    d = build_mesh_surface_descriptor(nodes, tris)
    wrong = Sig('b'*64, 'Plane', 120.0, (5,5,0), (0,0,0,10,10,0))
    with pytest.raises(SurfaceAssociationError, match='SURFACE_ASSOC_NO_MATCH'):
        choose_unique_cad_face(d, [(1,wrong)], 30.0)


def test_nonfinite_nodes_are_rejected():
    nodes, tris = _square_tri6(); nodes[0,0] = np.nan
    with pytest.raises(SurfaceAssociationError, match='SURFACE_ASSOC_NODES'):
        build_mesh_surface_descriptor(nodes, tris)
