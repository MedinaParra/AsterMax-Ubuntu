from __future__ import annotations

import numpy as np
import pytest

from astermax.fea.tet10_jacobian_adaptive import (
    Tet10JacobianAdaptivePolicy,
    require_tet10_adaptive_jacobian,
    tet10_adaptive_jacobian_report,
)


def _straight_tet10() -> np.ndarray:
    return np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.5, 0.0, 0.0],
            [0.5, 0.5, 0.0],
            [0.0, 0.5, 0.0],
            [0.0, 0.0, 0.5],
            [0.0, 0.5, 0.5],
            [0.5, 0.0, 0.5],
        ],
        dtype=float,
    )


def _v1_false_negative_fixture() -> np.ndarray:
    return np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.4903915413553965, 0.02898905543321116, 0.03529071241949736],
            [0.3192629029223042, 0.6593659722236465, 0.00680903339979113],
            [0.2000264455615086, 0.5089956543253049, -0.07807891672433837],
            [0.08463231823459492, 0.011021041422047, 0.5908290733621199],
            [-0.04098543666108984, 0.4569471477238474, 0.43431095493686117],
            [0.4337065973435658, 0.04396390005843077, 0.37558366221097667],
        ],
        dtype=float,
    )


def test_straight_tet10_passes_adaptive_search() -> None:
    nodes = _straight_tet10()
    elements = np.arange(10, dtype=np.int64)[None, :]
    report = tet10_adaptive_jacobian_report(nodes, elements)
    assert report.status == "PASS"
    assert report.nonpositive_sample_count == 0
    assert report.minimum_determinant == pytest.approx(1.0, rel=0.0, abs=2.0e-14)
    assert report.evaluated_points > 15
    require_tet10_adaptive_jacobian(report)


def test_adaptive_search_catches_known_v1_false_negative() -> None:
    nodes = _v1_false_negative_fixture()
    elements = np.arange(10, dtype=np.int64)[None, :]
    report = tet10_adaptive_jacobian_report(
        nodes,
        elements,
        policy=Tet10JacobianAdaptivePolicy(max_depth=5),
    )
    assert report.status == "FAIL"
    assert report.minimum_determinant < 0.0
    assert report.nonpositive_sample_count > 0
    with pytest.raises(ValueError, match="adaptive Jacobian gate failed"):
        require_tet10_adaptive_jacobian(report)


def test_adaptive_report_is_reproducible() -> None:
    nodes = _v1_false_negative_fixture()
    elements = np.arange(10, dtype=np.int64)[None, :]
    a = tet10_adaptive_jacobian_report(nodes, elements)
    b = tet10_adaptive_jacobian_report(nodes, elements)
    assert a == b


def test_adaptive_search_does_not_claim_global_positivity_proof() -> None:
    nodes = _straight_tet10()
    elements = np.arange(10, dtype=np.int64)[None, :]
    report = tet10_adaptive_jacobian_report(nodes, elements)
    assert "NOT_GLOBAL_POSITIVITY_PROOF" in report.evidence_boundary
    assert "DOES_NOT_ENABLE_CURVED_TET10_SOLVER" in report.evidence_boundary
