from __future__ import annotations

import math

import numpy as np

from astermax.fea.axisymmetric_shoulder import XAxisShoulderFeature
from astermax.fea.curved_shoulder_sector_probe import (
    curved_tet10_integration_point_coordinates,
    sample_curved_tet10_sectorized_small_diameter_fillet_ring,
)
from astermax.fea.feature_adaptivity import FeatureRefinedTet10Mesh


def _feature() -> XAxisShoulderFeature:
    return XAxisShoulderFeature(
        feature_id="TEST_CURVED_PROBE",
        source_name="fixture.step",
        source_sha256="1" * 64,
        source_size_bytes=1,
        gmsh_version="test",
        recognition_scope="TEST",
        small_cylinder_tag=1,
        large_cylinder_tag=2,
        transition_face_tag=3,
        shoulder_plane_tag=4,
        small_radius_mm=10.0,
        large_radius_mm=15.0,
        fillet_radius_mm=2.0,
        transition_x_mm=40.0,
        small_side="X_MIN_SIDE",
        axis_center_yz_mm=(0.0, 0.0),
        transition_bbox_mm=(38.0, -12.0, -12.0, 40.0, 12.0, 12.0),
        feature_sha256="2" * 64,
    )


def _mesh_for_ring(sectors: int = 12) -> FeatureRefinedTet10Mesh:
    points = []
    elements = []
    for sector in range(sectors):
        theta = 2.0 * math.pi * (sector + 0.5) / sectors
        p = np.asarray((38.0, 10.0 * math.cos(theta), 10.0 * math.sin(theta)), dtype=float)
        start = len(points)
        points.extend([p.copy() for _ in range(10)])
        elements.append(np.arange(start, start + 10, dtype=np.int64))
    return FeatureRefinedTet10Mesh(
        nodes_mm=np.asarray(points, dtype=float),
        elements=np.asarray(elements, dtype=np.int64),
        feature_sha256="2" * 64,
        source_sha256="1" * 64,
        global_size_mm=8.0,
        local_size_mm=2.0,
        local_box_mm=(35.0, -20.0, -20.0, 45.0, 20.0, 20.0),
        second_order_linear=False,
        gmsh_version="test",
        local_element_count=sectors,
        outside_element_count=0,
        local_mean_max_corner_edge_mm=1.0,
        outside_mean_max_corner_edge_mm=None,
        mesh_sha256="3" * 64,
        high_order_optimize=2,
    )


def test_coordinate_mapping_is_not_hardcoded_to_four_points() -> None:
    mesh = _mesh_for_ring(4)
    natural = np.asarray(
        [
            (0.25, 0.25, 0.25),
            (0.10, 0.20, 0.30),
            (0.20, 0.10, 0.10),
            (0.05, 0.05, 0.05),
            (0.50, 0.10, 0.10),
            (0.10, 0.50, 0.10),
            (0.10, 0.10, 0.50),
        ],
        dtype=float,
    )
    mapped = curved_tet10_integration_point_coordinates(mesh.nodes_mm, mesh.elements, natural)
    assert mapped.shape == (4, 7, 3)
    for element_index in range(4):
        assert np.allclose(mapped[element_index], mesh.nodes_mm[mesh.elements[element_index, 0]])


def test_curved_sector_probe_uses_actual_quadrature_count_and_full_coverage() -> None:
    sectors = 12
    mesh = _mesh_for_ring(sectors)
    feature = _feature()
    natural = np.asarray(((0.25, 0.25, 0.25),), dtype=float)
    values = np.arange(1, sectors + 1, dtype=float).reshape((sectors, 1))
    result = sample_curved_tet10_sectorized_small_diameter_fillet_ring(
        mesh,
        feature,
        integration_point_natural_coordinates=natural,
        integration_point_von_mises_mpa=values,
        sector_count=sectors,
        maximum_allowed_distance_mm=0.01,
    )
    assert result.quadrature_point_count == 1
    assert result.covered_sector_count == sectors
    assert result.angular_coverage_fraction == 1.0
    assert result.maximum_sample_distance_mm < 1.0e-12
    assert {sample.integration_point_index for sample in result.samples} == {0}
    assert sorted(sample.von_mises_mpa for sample in result.samples) == list(range(1, sectors + 1))


def test_curved_sector_probe_rejects_stress_shape_not_matching_quadrature() -> None:
    mesh = _mesh_for_ring(12)
    feature = _feature()
    natural = np.asarray(((0.25, 0.25, 0.25), (0.10, 0.20, 0.30)), dtype=float)
    bad_values = np.zeros((12, 4), dtype=float)
    try:
        sample_curved_tet10_sectorized_small_diameter_fillet_ring(
            mesh,
            feature,
            integration_point_natural_coordinates=natural,
            integration_point_von_mises_mpa=bad_values,
        )
    except ValueError as exc:
        assert "shape (m,q)" in str(exc)
    else:
        raise AssertionError("mismatched stress/quadrature shape must fail closed")
