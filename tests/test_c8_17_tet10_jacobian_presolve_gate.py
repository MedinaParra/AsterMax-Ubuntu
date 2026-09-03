import numpy as np
import pytest

from astermax.code_aster_mesh_quality_gate import (
    CodeAsterMeshQualityError,
    Tet10PreSolveQualityThresholds,
    build_tet10_presolve_quality_report,
    require_tet10_presolve_quality,
)
from astermax.fea.tet10 import straight_sided_tet10_from_vertices


def _valid_mesh():
    vertices = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [0.0, 10.0, 0.0],
            [0.0, 0.0, 10.0],
        ]
    )
    nodes = straight_sided_tet10_from_vertices(vertices)
    return nodes, np.arange(10, dtype=int).reshape((1, 10))


def test_straight_tet10_passes_sampled_jacobian_gate_without_solver_claims():
    nodes, elements = _valid_mesh()
    report = build_tet10_presolve_quality_report(nodes, elements)

    assert report.solver_gate_passed is True
    assert report.all_sampled_jacobians_positive is True
    assert report.minimum_sampled_jacobian_ratio == pytest.approx(1.0)
    assert report.minimum_corner_mean_ratio > 0.0
    assert report.length_unit == "mm"
    assert report.ansys_metric_equivalence is False
    assert report.fea_solve_executed is False
    assert report.numerical_verification is False
    assert report.results_verified is False
    assert len(report.report_sha256) == 64
    require_tet10_presolve_quality(report)


def test_valid_corner_tetra_is_blocked_when_midside_node_inverts_quadratic_mapping():
    nodes, elements = _valid_mesh()
    # Keep all four corner nodes intact while moving the 1-2 midside node far
    # inside/outside the nominal edge. Corner-only quality remains positive,
    # but the quadratic isoparametric Jacobian becomes non-positive at samples.
    nodes[4] += np.asarray([10.0, 10.0, 10.0])

    report = build_tet10_presolve_quality_report(nodes, elements)

    assert report.minimum_corner_mean_ratio > 0.0
    assert report.all_sampled_jacobians_positive is False
    assert report.solver_gate_passed is False
    assert any(item.startswith("TET10_JACOBIAN_NONPOSITIVE") for item in report.blockers)
    with pytest.raises(CodeAsterMeshQualityError, match="CODE_ASTER_PRESOLVE_MESH_QUALITY_BLOCKED"):
        require_tet10_presolve_quality(report)


def test_positive_but_highly_distorted_mapping_can_be_blocked_by_ratio_threshold():
    nodes, elements = _valid_mesh()
    nodes[4] += np.asarray([0.25, 0.25, 0.25])
    limits = Tet10PreSolveQualityThresholds(minimum_jacobian_ratio=0.95)

    report = build_tet10_presolve_quality_report(nodes, elements, thresholds=limits)

    assert report.solver_gate_passed is False
    assert any(item.startswith("TET10_JACOBIAN_RATIO_BELOW_THRESHOLD") for item in report.blockers)


def test_duplicate_tet10_node_fails_closed():
    nodes, elements = _valid_mesh()
    elements[0, 9] = elements[0, 8]
    with pytest.raises(CodeAsterMeshQualityError, match="MESH_QUALITY_DUPLICATE_TET10_NODE"):
        build_tet10_presolve_quality_report(nodes, elements)


def test_out_of_range_connectivity_fails_closed():
    nodes, elements = _valid_mesh()
    elements[0, 9] = 99
    with pytest.raises(CodeAsterMeshQualityError, match="MESH_QUALITY_NODE_INDEX_OUT_OF_RANGE"):
        build_tet10_presolve_quality_report(nodes, elements)


def test_empty_tet10_set_fails_closed():
    nodes, _ = _valid_mesh()
    with pytest.raises(CodeAsterMeshQualityError, match="MESH_QUALITY_TET10_CONNECTIVITY_INVALID"):
        build_tet10_presolve_quality_report(nodes, np.empty((0, 10), dtype=int))


def test_invalid_thresholds_fail_closed():
    nodes, elements = _valid_mesh()
    with pytest.raises(CodeAsterMeshQualityError, match="MESH_QUALITY_JACOBIAN_RATIO_THRESHOLD_INVALID"):
        build_tet10_presolve_quality_report(
            nodes,
            elements,
            thresholds=Tet10PreSolveQualityThresholds(minimum_jacobian_ratio=0.0),
        )
