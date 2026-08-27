from __future__ import annotations

import numpy as np
import pytest

from astermax.fea.tet10_jacobian import tet10_sampled_jacobian_report
from astermax.fea.tet10_jacobian_reference import (
    barycentric_lattice_points,
    require_tet10_reference_jacobian,
    tet10_reference_jacobian_report,
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
    # Deterministic counterexample discovered by seeded midside-node perturbation.
    # The 15-point V1 gate remains positive, while a denser barycentric scan finds
    # a local negative determinant on the r=0 face. Keep this fixture permanently
    # so future sample-set changes cannot silently reintroduce the blind spot.
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


def test_reference_lattice_has_declared_size() -> None:
    points = barycentric_lattice_points(10)
    assert points.shape == (286, 3)
    bary4 = 1.0 - points.sum(axis=1)
    assert np.min(points) >= 0.0
    assert np.min(bary4) >= -1.0e-15


def test_straight_tet10_passes_dense_reference() -> None:
    nodes = _straight_tet10()
    report = tet10_reference_jacobian_report(nodes, np.arange(10, dtype=np.int64)[None, :])
    assert report.status == "PASS"
    assert report.sample_count_per_element == 286
    assert report.nonpositive_sample_count == 0
    assert report.minimum_determinant == pytest.approx(1.0, rel=0.0, abs=2.0e-14)
    require_tet10_reference_jacobian(report)


def test_dense_reference_catches_known_v1_false_negative() -> None:
    nodes = _v1_false_negative_fixture()
    elements = np.arange(10, dtype=np.int64)[None, :]
    sampled = tet10_sampled_jacobian_report(nodes, elements)
    reference = tet10_reference_jacobian_report(nodes, elements)

    assert sampled.status == "PASS"
    assert sampled.minimum_determinant == pytest.approx(0.009391186546530516, rel=1.0e-12)
    assert reference.status == "FAIL"
    assert reference.minimum_determinant < -0.007
    assert reference.worst_natural_coordinates == pytest.approx((0.0, 0.2, 0.8))
    with pytest.raises(ValueError, match="dense Jacobian reference gate failed"):
        require_tet10_reference_jacobian(reference)


def test_reference_scan_evidence_does_not_claim_global_proof() -> None:
    nodes = _straight_tet10()
    report = tet10_reference_jacobian_report(nodes, np.arange(10, dtype=np.int64)[None, :])
    assert "NOT_GLOBAL_POSITIVITY_PROOF" in report.evidence_boundary
    assert "DOES_NOT_ENABLE_CURVED_TET10_SOLVER" in report.evidence_boundary
