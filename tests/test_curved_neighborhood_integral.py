from __future__ import annotations

import math

import numpy as np

from astermax.fea.axisymmetric_shoulder import XAxisShoulderFeature
from astermax.fea.curved_neighborhood_integral import integrate_curved_tet10_fixed_tangency_neighborhood
from astermax.fea.feature_adaptivity import FeatureRefinedTet10Mesh
from astermax.fea.tet10_isoparametric import duffy_tetra_gauss_rule


def _straight_unit_tet10_mesh() -> FeatureRefinedTet10Mesh:
    nodes = np.asarray(
        [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (0.5, 0.0, 0.0),
            (0.5, 0.5, 0.0),
            (0.0, 0.5, 0.0),
            (0.0, 0.0, 0.5),
            (0.0, 0.5, 0.5),
            (0.5, 0.0, 0.5),
        ],
        dtype=float,
    )
    return FeatureRefinedTet10Mesh(
        nodes_mm=nodes,
        elements=np.asarray([np.arange(10)], dtype=np.int64),
        feature_sha256="a" * 64,
        source_sha256="b" * 64,
        global_size_mm=1.0,
        local_size_mm=1.0,
        local_box_mm=(-1.0, -1.0, -1.0, 2.0, 2.0, 2.0),
        second_order_linear=True,
        gmsh_version="test",
        local_element_count=1,
        outside_element_count=0,
        local_mean_max_corner_edge_mm=math.sqrt(2.0),
        outside_mean_max_corner_edge_mm=None,
        mesh_sha256="c" * 64,
        high_order_optimize=0,
    )


def _feature() -> XAxisShoulderFeature:
    return XAxisShoulderFeature(
        feature_id="UNIT_TET_NEIGHBORHOOD",
        source_name="unit.step",
        source_sha256="b" * 64,
        source_size_bytes=1,
        gmsh_version="test",
        recognition_scope="TEST",
        small_cylinder_tag=1,
        large_cylinder_tag=2,
        transition_face_tag=3,
        shoulder_plane_tag=4,
        small_radius_mm=1.0,
        large_radius_mm=2.0,
        fillet_radius_mm=1.0,
        transition_x_mm=2.0,
        small_side="X_MIN_SIDE",
        axis_center_yz_mm=(0.0, 0.0),
        transition_bbox_mm=(1.0, -2.0, -2.0, 2.0, 2.0, 2.0),
        feature_sha256="a" * 64,
    )


def test_fixed_neighborhood_integral_recovers_unit_tetra_volume_and_constant_stress() -> None:
    mesh = _straight_unit_tet10_mesh()
    feature = _feature()
    rule = duffy_tetra_gauss_rule(4)
    values = np.full((1, rule.points.shape[0]), 7.0, dtype=float)
    result = integrate_curved_tet10_fixed_tangency_neighborhood(
        mesh,
        feature,
        integration_point_natural_coordinates=rule.points,
        integration_point_weights=rule.weights,
        integration_point_von_mises_mpa=values,
        maximum_meridional_distance_mm=2.0,
    )
    assert result.quadrature_point_count == 64
    assert result.selected_integration_point_count == 64
    assert abs(result.sampled_physical_volume_mm3 - 1.0 / 6.0) < 1.0e-12
    assert abs(result.weighted_mean_von_mises_mpa - 7.0) < 1.0e-12
    assert abs(result.weighted_rms_von_mises_mpa - 7.0) < 1.0e-12
    assert result.weighted_std_von_mises_mpa < 1.0e-12


def test_fixed_neighborhood_integral_fails_if_region_contains_no_ip() -> None:
    mesh = _straight_unit_tet10_mesh()
    feature = _feature()
    rule = duffy_tetra_gauss_rule(4)
    values = np.ones((1, rule.points.shape[0]), dtype=float)
    try:
        integrate_curved_tet10_fixed_tangency_neighborhood(
            mesh,
            feature,
            integration_point_natural_coordinates=rule.points,
            integration_point_weights=rule.weights,
            integration_point_von_mises_mpa=values,
            maximum_meridional_distance_mm=1.0e-9,
        )
    except RuntimeError as exc:
        assert "CONTAINS_NO_INTEGRATION_POINTS" in str(exc)
    else:
        raise AssertionError("empty physical neighborhood must fail closed")
