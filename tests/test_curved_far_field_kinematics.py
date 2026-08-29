from __future__ import annotations

import numpy as np
import pytest

from astermax.fea.curved_far_field_kinematics import (
    CurvedFarFieldKinematicsError,
    curved_far_field_kinematics_evidence,
    fit_curved_tet10_far_field_axial_kinematics,
)
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet10_isoparametric import duffy_tetra_gauss_rule


def _fixture(epsilon: float = 2.5e-4):
    nodes = straight_sided_tet10_from_vertices(
        np.asarray(
            [
                [0.0, 0.0, 0.0],
                [10.0, 0.0, 0.0],
                [0.0, 2.0, 0.0],
                [0.0, 0.0, 2.0],
            ],
            dtype=float,
        )
    )
    elements = np.arange(10, dtype=np.int64).reshape(1, 10)
    displacement = np.zeros_like(nodes)
    displacement[:, 0] = 0.125 + epsilon * nodes[:, 0]
    rule = duffy_tetra_gauss_rule(4)
    return nodes, elements, displacement, rule


def test_exact_linear_axial_field_recovers_gradient_and_fit():
    epsilon = 2.5e-4
    nodes, elements, displacement, rule = _fixture(epsilon)
    result = fit_curved_tet10_far_field_axial_kinematics(
        nodes_mm=nodes,
        elements=elements,
        mesh_sha256="1" * 64,
        displacement_mm=displacement,
        integration_point_natural_coordinates=rule.points,
        integration_point_weights=rule.weights,
        x_min_mm=0.0,
        x_max_mm=10.0,
    )
    assert result.axial_displacement_gradient == pytest.approx(epsilon, rel=0.0, abs=1e-14)
    assert result.axial_displacement_intercept_mm == pytest.approx(0.125, rel=0.0, abs=1e-13)
    assert result.weighted_residual_rms_mm <= 1e-13
    assert result.weighted_r_squared == pytest.approx(1.0, rel=0.0, abs=1e-12)
    assert result.fitted_extension_over_declared_span_mm == pytest.approx(10.0 * epsilon)
    assert result.selected_integration_point_count == rule.points.shape[0]


def test_evidence_is_deterministic_and_mesh_bound():
    nodes, elements, displacement, rule = _fixture()
    kwargs = dict(
        nodes_mm=nodes,
        elements=elements,
        mesh_sha256="a" * 64,
        displacement_mm=displacement,
        integration_point_natural_coordinates=rule.points,
        integration_point_weights=rule.weights,
        x_min_mm=0.0,
        x_max_mm=10.0,
    )
    a = fit_curved_tet10_far_field_axial_kinematics(**kwargs)
    b = fit_curved_tet10_far_field_axial_kinematics(**kwargs)
    assert a.evidence_sha256 == b.evidence_sha256
    record = curved_far_field_kinematics_evidence(a)
    assert record.payload_sha256 == a.evidence_sha256
    assert record.metadata["mesh_sha256"] == "a" * 64


def test_changed_displacement_changes_evidence():
    nodes, elements, displacement, rule = _fixture()
    a = fit_curved_tet10_far_field_axial_kinematics(
        nodes_mm=nodes,
        elements=elements,
        mesh_sha256="b" * 64,
        displacement_mm=displacement,
        integration_point_natural_coordinates=rule.points,
        integration_point_weights=rule.weights,
        x_min_mm=0.0,
        x_max_mm=10.0,
    )
    changed = displacement.copy()
    changed[:, 0] += 1.0e-5 * nodes[:, 0]
    b = fit_curved_tet10_far_field_axial_kinematics(
        nodes_mm=nodes,
        elements=elements,
        mesh_sha256="b" * 64,
        displacement_mm=changed,
        integration_point_natural_coordinates=rule.points,
        integration_point_weights=rule.weights,
        x_min_mm=0.0,
        x_max_mm=10.0,
    )
    assert a.evidence_sha256 != b.evidence_sha256
    assert a.axial_displacement_gradient != b.axial_displacement_gradient


def test_fail_closed_for_invalid_mesh_sha_and_displacement_shape():
    nodes, elements, displacement, rule = _fixture()
    with pytest.raises(ValueError, match="mesh_sha256"):
        fit_curved_tet10_far_field_axial_kinematics(
            nodes_mm=nodes,
            elements=elements,
            mesh_sha256="bad",
            displacement_mm=displacement,
            integration_point_natural_coordinates=rule.points,
            integration_point_weights=rule.weights,
            x_min_mm=0.0,
            x_max_mm=10.0,
        )
    with pytest.raises(ValueError, match="displacement_mm"):
        fit_curved_tet10_far_field_axial_kinematics(
            nodes_mm=nodes,
            elements=elements,
            mesh_sha256="c" * 64,
            displacement_mm=displacement[:-1],
            integration_point_natural_coordinates=rule.points,
            integration_point_weights=rule.weights,
            x_min_mm=0.0,
            x_max_mm=10.0,
        )


def test_fail_closed_when_slab_has_no_points():
    nodes, elements, displacement, rule = _fixture()
    with pytest.raises(CurvedFarFieldKinematicsError, match="AT_LEAST_TWO"):
        fit_curved_tet10_far_field_axial_kinematics(
            nodes_mm=nodes,
            elements=elements,
            mesh_sha256="d" * 64,
            displacement_mm=displacement,
            integration_point_natural_coordinates=rule.points,
            integration_point_weights=rule.weights,
            x_min_mm=20.0,
            x_max_mm=21.0,
        )
