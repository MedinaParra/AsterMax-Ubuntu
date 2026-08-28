import numpy as np
import pytest

from astermax.fea.tet10 import (
    straight_sided_tet10_from_vertices,
    tet10_B_matrix,
    tet10_shape_derivatives,
    tet10_stiffness,
)
from astermax.fea.tet10_isoparametric import (
    duffy_tetra_gauss_rule,
    relative_matrix_difference,
    simplex_monomial_integral,
    tet10_isoparametric_jacobian_audit,
    tet10_stiffness_isoparametric_reference,
)
from astermax.fea.tet4 import IsotropicMaterial


MATERIAL = IsotropicMaterial(young_modulus_mpa=200000.0, poisson_ratio=0.3)


def _straight_coords():
    vertices = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    return straight_sided_tet10_from_vertices(vertices)


def _mild_curved_coords():
    coords = _straight_coords().copy()
    coords[4] += np.asarray([0.0, 0.07, 0.03])
    coords[5] += np.asarray([0.02, 0.0, 0.04])
    coords[7] += np.asarray([0.03, 0.02, 0.0])
    return coords


def test_duffy_order4_integrates_reference_monomials_through_total_degree5():
    rule = duffy_tetra_gauss_rule(4)
    assert rule.points.shape == (64, 3)
    assert np.sum(rule.weights) == pytest.approx(1.0 / 6.0, abs=5.0e-15)
    for total in range(6):
        for i in range(total + 1):
            for j in range(total - i + 1):
                k = total - i - j
                numerical = float(np.sum(rule.weights * (rule.points[:, 0] ** i) * (rule.points[:, 1] ** j) * (rule.points[:, 2] ** k)))
                exact = simplex_monomial_integral(i, j, k)
                assert numerical == pytest.approx(exact, rel=2.0e-13, abs=2.0e-14)


def test_straight_tet10_four_point_stiffness_matches_independent_reference():
    coords = _straight_coords()
    baseline = tet10_stiffness(coords, MATERIAL)
    independent = tet10_stiffness_isoparametric_reference(coords, MATERIAL, quadrature_order=4)
    assert relative_matrix_difference(baseline, independent) < 2.0e-12


def test_curved_mapping_reproduces_any_affine_physical_displacement_field():
    coords = _mild_curved_coords()
    gradient = np.asarray(
        [
            [0.010, 0.020, -0.030],
            [0.005, -0.020, 0.010],
            [0.004, 0.002, 0.015],
        ]
    )
    offset = np.asarray([1.2, -0.7, 0.4])
    nodal_displacement = coords @ gradient.T + offset
    ue = nodal_displacement.reshape(30)
    expected_engineering_strain = np.asarray(
        [
            gradient[0, 0],
            gradient[1, 1],
            gradient[2, 2],
            gradient[0, 1] + gradient[1, 0],
            gradient[1, 2] + gradient[2, 1],
            gradient[0, 2] + gradient[2, 0],
        ]
    )
    rule = duffy_tetra_gauss_rule(5)
    for point in rule.points:
        b, det_j = tet10_B_matrix(coords, point)
        assert det_j > 0.0
        assert b @ ue == pytest.approx(expected_engineering_strain, rel=2.0e-12, abs=2.0e-12)


def test_curved_reference_quadrature_converges_and_jacobians_stay_positive():
    coords = _mild_curved_coords()
    k3 = tet10_stiffness_isoparametric_reference(coords, MATERIAL, quadrature_order=3)
    k4 = tet10_stiffness_isoparametric_reference(coords, MATERIAL, quadrature_order=4)
    k5 = tet10_stiffness_isoparametric_reference(coords, MATERIAL, quadrature_order=5)
    diff34 = relative_matrix_difference(k3, k4)
    diff45 = relative_matrix_difference(k4, k5)
    assert diff45 < diff34
    assert diff45 < 1.0e-4
    audit = tet10_isoparametric_jacobian_audit(coords, quadrature_order=5)
    assert audit.all_positive is True
    assert audit.nonpositive_point_count == 0
    assert audit.minimum_det_jacobian > 0.0
    assert audit.minimum_over_maximum_ratio is not None
    assert 0.0 < audit.minimum_over_maximum_ratio <= 1.0


def test_four_point_rule_is_not_silently_relabelled_as_curved_reference():
    coords = _mild_curved_coords()
    four_point = tet10_stiffness(coords, MATERIAL)
    reference = tet10_stiffness_isoparametric_reference(coords, MATERIAL, quadrature_order=5)
    assert relative_matrix_difference(four_point, reference) > 1.0e-5


def test_inverted_curved_mapping_is_measured_without_weakening_solver_guard():
    coords = _mild_curved_coords()
    coords[[0, 1]] = coords[[1, 0]]
    rule = duffy_tetra_gauss_rule(4)
    raw_dets = np.asarray([
        np.linalg.det(coords.T @ tet10_shape_derivatives(point)) for point in rule.points
    ])
    bad_point = rule.points[int(np.argmin(raw_dets))]

    audit = tet10_isoparametric_jacobian_audit(coords, quadrature_order=4)
    assert audit.all_positive is False
    assert audit.nonpositive_point_count > 0
    assert audit.minimum_det_jacobian <= 0.0
    with pytest.raises(ValueError, match="Degenerate or inverted TET10 Jacobian"):
        tet10_B_matrix(coords, bad_point)
