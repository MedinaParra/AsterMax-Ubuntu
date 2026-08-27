from __future__ import annotations

import numpy as np
import pytest

from astermax.fea.tet10_geometry import (
    Tet10GeometryScopeError,
    require_tet10_geometry_scope,
    tet10_geometry_scope,
)


def _straight_tet10() -> tuple[np.ndarray, np.ndarray]:
    corners = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [0.0, 10.0, 0.0],
            [0.0, 0.0, 10.0],
        ]
    )
    mids = np.asarray(
        [
            0.5 * (corners[0] + corners[1]),
            0.5 * (corners[1] + corners[2]),
            0.5 * (corners[2] + corners[0]),
            0.5 * (corners[0] + corners[3]),
            0.5 * (corners[2] + corners[3]),
            0.5 * (corners[1] + corners[3]),
        ]
    )
    nodes = np.vstack([corners, mids])
    return nodes, np.arange(10, dtype=np.int64).reshape(1, 10)


def test_straight_tet10_scope_passes_with_auditable_zero_deviation() -> None:
    nodes, elements = _straight_tet10()
    report = tet10_geometry_scope(nodes, elements)
    assert report.status == "PASS"
    assert report.non_straight_sided_elements == 0
    assert report.max_midpoint_deviation_mm == pytest.approx(0.0)
    assert report.max_relative_midpoint_deviation == pytest.approx(0.0)
    assert report.solver_scope == "STRAIGHT_SIDED_TET10_FOUR_POINT_VERIFICATION"
    assert report.policy["relative_midpoint_tolerance"] > 0.0
    require_tet10_geometry_scope(report)


def test_curved_midside_node_fails_before_solver_scope_is_claimed() -> None:
    nodes, elements = _straight_tet10()
    nodes[4, 2] += 0.01
    report = tet10_geometry_scope(nodes, elements)
    assert report.status == "FAIL"
    assert report.non_straight_sided_elements == 1
    assert report.max_midpoint_deviation_mm == pytest.approx(0.01)
    assert report.max_relative_midpoint_deviation > 0.0
    assert report.worst_element_index == 0
    with pytest.raises(Tet10GeometryScopeError, match="failed before assembly"):
        require_tet10_geometry_scope(report)


def test_tiny_roundoff_within_declared_tolerance_remains_in_scope() -> None:
    nodes, elements = _straight_tet10()
    nodes[4, 0] += 1.0e-12
    report = tet10_geometry_scope(nodes, elements)
    assert report.status == "PASS"
    assert report.non_straight_sided_elements == 0
