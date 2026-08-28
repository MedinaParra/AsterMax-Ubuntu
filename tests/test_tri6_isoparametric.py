from __future__ import annotations

import numpy as np
import pytest

from astermax.fea.tri6_isoparametric import (
    compare_tri6_surface_quadrature,
    consistent_tri6_resultant_load_isoparametric,
    duffy_triangle_gauss_rule,
    triangle_monomial_integral,
)


def _planar_tri6() -> tuple[np.ndarray, np.ndarray]:
    nodes = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [0.0, 3.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.5, 0.0],
            [0.0, 1.5, 0.0],
        ]
    )
    return nodes, np.asarray([[0, 1, 2, 3, 4, 5]], dtype=np.int64)


def test_triangle_duffy_order4_integrates_monomials_through_total_degree5():
    rule = duffy_triangle_gauss_rule(4)
    assert rule.points.shape == (16, 2)
    assert np.sum(rule.weights) == pytest.approx(0.5, abs=5.0e-15)
    for total in range(6):
        for i in range(total + 1):
            j = total - i
            numerical = float(np.sum(rule.weights * rule.points[:, 0] ** i * rule.points[:, 1] ** j))
            assert numerical == pytest.approx(triangle_monomial_integral(i, j), rel=2.0e-13, abs=2.0e-14)


def test_planar_tri6_gl4_gl5_area_centroid_and_resultant_are_exact():
    nodes, tri6 = _planar_tri6()
    comparison = compare_tri6_surface_quadrature(nodes, tri6, order_a=4, order_b=5)
    assert comparison.area_a_mm2 == pytest.approx(3.0, rel=1.0e-13, abs=1.0e-13)
    assert comparison.area_b_mm2 == pytest.approx(3.0, rel=1.0e-13, abs=1.0e-13)
    assert comparison.relative_area_difference < 1.0e-13
    assert comparison.centroid_delta_mm < 1.0e-13
    assert comparison.centroid_a_mm == pytest.approx((2.0 / 3.0, 1.0, 0.0), abs=1.0e-13)

    load = consistent_tri6_resultant_load_isoparametric(
        nodes, tri6, total_force_n=(7.0, -11.0, 13.0), quadrature_order=4
    )
    assert load.integrated_resultant_n == pytest.approx((7.0, -11.0, 13.0), abs=2.0e-12)
    assert load.relative_resultant_error <= 1.0e-12
    assert np.all(np.isfinite(load.loads_n))


def test_mild_curved_tri6_reference_sequence_stabilizes_and_preserves_resultant():
    nodes, tri6 = _planar_tri6()
    nodes = nodes.copy()
    nodes[3, 2] = 0.03
    nodes[4, 2] = -0.02
    nodes[5, 2] = 0.01
    c34 = compare_tri6_surface_quadrature(nodes, tri6, order_a=3, order_b=4)
    c45 = compare_tri6_surface_quadrature(nodes, tri6, order_a=4, order_b=5)
    assert c45.relative_area_difference < c34.relative_area_difference
    assert c45.centroid_delta_mm < c34.centroid_delta_mm

    load = consistent_tri6_resultant_load_isoparametric(
        nodes, tri6, total_force_n=(100.0, 25.0, -10.0), quadrature_order=4
    )
    assert load.relative_resultant_error <= 1.0e-12
    assert load.integrated_resultant_n == pytest.approx((100.0, 25.0, -10.0), abs=2.0e-11)
