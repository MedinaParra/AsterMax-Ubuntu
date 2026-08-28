import numpy as np
import pytest

from astermax.fea.tri6_traction import consistent_tri6_resultant_load, fixed_dofs_from_tri6


def _triangle():
    return np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.5, 0.0, 0.0],
            [0.5, 0.5, 0.0],
            [0.0, 0.5, 0.0],
        ]
    )


def test_consistent_tri6_load_recovers_area_resultant_and_moment():
    nodes = _triangle()
    tri6 = np.arange(6, dtype=np.int64).reshape(1, 6)
    result = consistent_tri6_resultant_load(nodes, tri6, total_force_n=(0.0, 0.0, 100.0))
    assert result.surface_area_mm2 == pytest.approx(0.5)
    assert result.integrated_resultant_n == pytest.approx((0.0, 0.0, 100.0))
    assert result.integrated_moment_about_origin_nmm == pytest.approx((100.0 / 3.0, -100.0 / 3.0, 0.0))
    assert result.relative_resultant_error <= 1.0e-12


def test_consistent_loading_is_not_equal_load_per_node():
    nodes = _triangle()
    tri6 = np.arange(6, dtype=np.int64).reshape(1, 6)
    result = consistent_tri6_resultant_load(nodes, tri6, total_force_n=(100.0, 0.0, 0.0))
    nodal_x = result.loads_n[:, 0]
    # Quadratic consistent traction has distinct corner/midside weights.
    assert np.ptp(nodal_x) > 0.0
    assert nodal_x.sum() == pytest.approx(100.0)


def test_fixed_dofs_cover_all_three_components_of_unique_surface_nodes():
    tri6 = np.asarray([[0, 1, 2, 3, 4, 5], [1, 6, 2, 7, 8, 4]], dtype=np.int64)
    dofs = fixed_dofs_from_tri6(tri6)
    assert len(dofs) == 9 * 3
    assert set(dofs.tolist()) == set(range(27))
