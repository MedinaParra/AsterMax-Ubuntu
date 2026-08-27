from __future__ import annotations

import numpy as np
import pytest

from astermax.fea.tet10_jacobian import (
    TET10_JACOBIAN_SAMPLE_POINTS_V1,
    require_tet10_sampled_jacobian,
    tet10_jacobian_matrix,
    tet10_sampled_jacobian_report,
    tet10_shape_function_gradients,
)


EDGES = ((0, 1), (1, 2), (2, 0), (0, 3), (2, 3), (1, 3))


def _straight_tet10() -> np.ndarray:
    corners = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=float,
    )
    mids = np.asarray([0.5 * (corners[i] + corners[j]) for i, j in EDGES], dtype=float)
    return np.vstack([corners, mids])


def test_shape_gradient_partition_of_unity() -> None:
    for point in TET10_JACOBIAN_SAMPLE_POINTS_V1:
        gradients = tet10_shape_function_gradients(point)
        assert gradients.shape == (10, 3)
        assert np.allclose(np.sum(gradients, axis=0), 0.0, atol=1.0e-14, rtol=0.0)


def test_straight_sided_reference_has_constant_positive_jacobian() -> None:
    nodes = _straight_tet10()
    elements = np.arange(10, dtype=np.int64).reshape(1, 10)
    determinants = [float(np.linalg.det(tet10_jacobian_matrix(nodes, p))) for p in TET10_JACOBIAN_SAMPLE_POINTS_V1]
    assert np.allclose(determinants, 1.0, atol=1.0e-14, rtol=0.0)
    report = tet10_sampled_jacobian_report(nodes, elements)
    assert report.status == "PASS"
    assert report.nonpositive_sample_count == 0
    assert report.minimum_determinant == pytest.approx(1.0, abs=1.0e-14)
    require_tet10_sampled_jacobian(report)


def test_curved_warped_positive_control_passes_sampled_gate() -> None:
    nodes = _straight_tet10()
    nodes[4:] = np.asarray(
        [
            [0.44062756, 0.03823434, -0.00612707],
            [0.39966507, 0.42919467, 0.14134235],
            [0.02834805, 0.53331092, -0.02212414],
            [-0.05517757, 0.07133247, 0.49162988],
            [-0.06072865, 0.48926972, 0.42755152],
            [0.51520367, 0.09033821, 0.43311319],
        ],
        dtype=float,
    )
    report = tet10_sampled_jacobian_report(nodes, np.arange(10, dtype=np.int64).reshape(1, 10))
    assert report.status == "PASS"
    assert report.nonpositive_sample_count == 0
    assert report.minimum_determinant > 0.30
    assert "DOES_NOT_ENABLE_CURVED_TET10_SOLVER" in report.evidence_boundary


def test_corner_positive_but_locally_inverted_control_fails_closed() -> None:
    nodes = _straight_tet10()
    # The four corner nodes retain the positively oriented unit tetrahedron.
    nodes[4:] = np.asarray(
        [
            [0.48155359, -0.03198238, 0.10408551],
            [0.46169509, 0.60675111, 0.09134530],
            [-0.08365321, 0.58283948, -0.05203025],
            [0.21891670, -0.03086643, 0.42472590],
            [-0.15288610, 0.39655639, 0.45354809],
            [0.42015778, -0.09829495, 0.44437282],
        ],
        dtype=float,
    )
    corner_det = float(np.linalg.det((nodes[1:4] - nodes[0]).T))
    assert corner_det == pytest.approx(1.0)

    report = tet10_sampled_jacobian_report(nodes, np.arange(10, dtype=np.int64).reshape(1, 10))
    assert report.status == "FAIL"
    assert report.nonpositive_sample_count > 0
    assert report.minimum_determinant < -0.60
    assert report.worst_element_index == 0
    assert report.worst_sample_index is not None
    with pytest.raises(ValueError, match="sampled isoparametric Jacobian gate failed"):
        require_tet10_sampled_jacobian(report)
