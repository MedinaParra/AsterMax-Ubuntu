import numpy as np
import pytest

from astermax.fea.axisymmetric_shoulder import XAxisShoulderFeature
from astermax.fea.feature_adaptivity import FeatureRefinedTet10Mesh
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet10_feature_sampling import (
    Tet10FeatureSamplingError,
    sample_tet10_shoulder_neighborhood,
    tet10_integration_point_coordinates,
)


def _feature(feature_sha="f" * 64):
    return XAxisShoulderFeature(
        feature_id="S1",
        source_name="fixture.step",
        source_sha256="a" * 64,
        source_size_bytes=1,
        gmsh_version="verification",
        recognition_scope="test",
        small_cylinder_tag=1,
        large_cylinder_tag=2,
        transition_face_tag=3,
        shoulder_plane_tag=4,
        small_radius_mm=1.0,
        large_radius_mm=2.0,
        fillet_radius_mm=0.25,
        transition_x_mm=0.5,
        small_side="X_MIN_SIDE",
        axis_center_yz_mm=(0.0, 0.0),
        transition_bbox_mm=(-0.1, -0.1, -0.1, 1.1, 1.1, 1.1),
        feature_sha256=feature_sha,
    )


def _mesh(feature_sha="f" * 64):
    vertices = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    nodes = straight_sided_tet10_from_vertices(vertices)
    return FeatureRefinedTet10Mesh(
        nodes_mm=nodes,
        elements=np.arange(10, dtype=np.int64).reshape(1, 10),
        feature_sha256=feature_sha,
        source_sha256="a" * 64,
        global_size_mm=1.0,
        local_size_mm=0.5,
        local_box_mm=(-1, -1, -1, 2, 2, 2),
        second_order_linear=True,
        gmsh_version="verification",
        local_element_count=1,
        outside_element_count=0,
        local_mean_max_corner_edge_mm=1.0,
        outside_mean_max_corner_edge_mm=None,
        mesh_sha256="b" * 64,
    )


def test_physical_ip_coordinates_are_inside_the_straight_tetrahedron():
    mesh = _mesh()
    coords = tet10_integration_point_coordinates(mesh.nodes_mm, mesh.elements)
    assert coords.shape == (1, 4, 3)
    assert np.all(coords >= 0.0)
    assert np.all(coords.sum(axis=2) <= 1.0 + 1.0e-12)


def test_ip_stress_values_are_preserved_without_nodal_smoothing():
    feature = _feature()
    mesh = _mesh()
    vm = np.asarray([[101.0, 202.0, 303.0, 404.0]])
    neighborhood = sample_tet10_shoulder_neighborhood(
        mesh,
        feature,
        padding_mm=0.1,
        integration_point_von_mises_mpa=vm,
    )
    assert neighborhood.sample_count == 4
    assert neighborhood.stress_representation == "FOUR_TET10_INTEGRATION_POINTS_NO_NODAL_SMOOTHING"
    assert [sample.von_mises_mpa for sample in neighborhood.samples] == [101.0, 202.0, 303.0, 404.0]
    assert len(neighborhood.neighborhood_sha256) == 64


def test_geometry_only_sampling_never_invents_stress_values():
    neighborhood = sample_tet10_shoulder_neighborhood(_mesh(), _feature(), padding_mm=0.1)
    assert neighborhood.stress_representation == "GEOMETRY_ONLY_NO_STRESS_VALUES"
    assert all(sample.von_mises_mpa is None for sample in neighborhood.samples)


def test_feature_mesh_hash_mismatch_fails_closed():
    with pytest.raises(Tet10FeatureSamplingError, match="FEATURE_MESH_BINDING_MISMATCH"):
        sample_tet10_shoulder_neighborhood(_mesh("1" * 64), _feature("2" * 64), padding_mm=0.1)
