from __future__ import annotations

import numpy as np
import pytest

from astermax.fea.curved_far_field_stress import (
    CurvedFarFieldStressError,
    integrate_curved_tet10_far_field_stress,
)


def _unit_tet10_nodes() -> np.ndarray:
    corners = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=float,
    )
    midsides = np.asarray(
        [
            0.5 * (corners[0] + corners[1]),
            0.5 * (corners[1] + corners[2]),
            0.5 * (corners[2] + corners[0]),
            0.5 * (corners[0] + corners[3]),
            0.5 * (corners[2] + corners[3]),
            0.5 * (corners[1] + corners[3]),
        ]
    )
    return np.vstack((corners, midsides))


def test_constant_uniaxial_stress_integrates_exactly_on_straight_tet10():
    nodes = _unit_tet10_nodes()
    elements = np.arange(10, dtype=np.int64).reshape((1, 10))
    natural = np.asarray([[0.25, 0.25, 0.25]], dtype=float)
    weights = np.asarray([1.0 / 6.0], dtype=float)
    stress = np.asarray([[[10.0, 0.0, 0.0, 0.0, 0.0, 0.0]]], dtype=float)
    mises = np.asarray([[10.0]], dtype=float)
    result = integrate_curved_tet10_far_field_stress(
        nodes_mm=nodes,
        elements=elements,
        mesh_sha256="1" * 64,
        integration_point_natural_coordinates=natural,
        integration_point_weights=weights,
        integration_point_stress_mpa=stress,
        integration_point_von_mises_mpa=mises,
        x_min_mm=-1.0,
        x_max_mm=2.0,
    )
    assert result.selected_integration_point_count == 1
    assert result.sampled_physical_volume_mm3 == pytest.approx(1.0 / 6.0, rel=1e-12, abs=1e-12)
    assert result.weighted_mean_stress_mpa == pytest.approx((10.0, 0.0, 0.0, 0.0, 0.0, 0.0))
    assert result.weighted_std_stress_mpa == pytest.approx((0.0, 0.0, 0.0, 0.0, 0.0, 0.0))
    assert result.weighted_mean_von_mises_mpa == pytest.approx(10.0)


def test_far_field_region_fails_closed_when_no_ip_is_inside():
    nodes = _unit_tet10_nodes()
    elements = np.arange(10, dtype=np.int64).reshape((1, 10))
    natural = np.asarray([[0.25, 0.25, 0.25]], dtype=float)
    with pytest.raises(CurvedFarFieldStressError, match="CONTAINS_NO_INTEGRATION_POINTS"):
        integrate_curved_tet10_far_field_stress(
            nodes_mm=nodes,
            elements=elements,
            mesh_sha256="2" * 64,
            integration_point_natural_coordinates=natural,
            integration_point_weights=np.asarray([1.0 / 6.0]),
            integration_point_stress_mpa=np.asarray([[[1.0, 0, 0, 0, 0, 0]]], dtype=float),
            integration_point_von_mises_mpa=np.asarray([[1.0]], dtype=float),
            x_min_mm=2.0,
            x_max_mm=3.0,
        )


def test_hash_changes_when_stress_payload_changes():
    nodes = _unit_tet10_nodes(); elements = np.arange(10, dtype=np.int64).reshape((1, 10))
    natural = np.asarray([[0.25, 0.25, 0.25]], dtype=float); weights = np.asarray([1.0 / 6.0])
    a = integrate_curved_tet10_far_field_stress(
        nodes_mm=nodes, elements=elements, mesh_sha256="3" * 64,
        integration_point_natural_coordinates=natural, integration_point_weights=weights,
        integration_point_stress_mpa=np.asarray([[[10.0,0,0,0,0,0]]]),
        integration_point_von_mises_mpa=np.asarray([[10.0]]), x_min_mm=-1.0, x_max_mm=2.0,
    )
    b = integrate_curved_tet10_far_field_stress(
        nodes_mm=nodes, elements=elements, mesh_sha256="3" * 64,
        integration_point_natural_coordinates=natural, integration_point_weights=weights,
        integration_point_stress_mpa=np.asarray([[[11.0,0,0,0,0,0]]]),
        integration_point_von_mises_mpa=np.asarray([[11.0]]), x_min_mm=-1.0, x_max_mm=2.0,
    )
    assert a.evidence_sha256 != b.evidence_sha256


def test_invalid_stress_shape_is_rejected():
    nodes = _unit_tet10_nodes(); elements = np.arange(10, dtype=np.int64).reshape((1, 10))
    with pytest.raises(ValueError, match=r"shape \(m,q,6\)"):
        integrate_curved_tet10_far_field_stress(
            nodes_mm=nodes,
            elements=elements,
            mesh_sha256="4" * 64,
            integration_point_natural_coordinates=np.asarray([[0.25,0.25,0.25]]),
            integration_point_weights=np.asarray([1.0 / 6.0]),
            integration_point_stress_mpa=np.zeros((1,1,5)),
            integration_point_von_mises_mpa=np.zeros((1,1)),
            x_min_mm=-1.0,
            x_max_mm=2.0,
        )
