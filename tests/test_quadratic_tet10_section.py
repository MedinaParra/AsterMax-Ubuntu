from __future__ import annotations

import math

import numpy as np
import pytest

from astermax.fea.quadratic_tet10_section import build_quadratic_tet10_plane_edge_intersection


def _nodes(curved_edge: bool) -> np.ndarray:
    nodes = np.asarray(
        [
            [0.0, 0.0, 1.0],
            [1.0, 0.0, 1.0],
            [0.0, 1.0, 1.0],
            [0.0, 0.0, 2.0],
            [0.5, 0.0, -1.0 if curved_edge else 1.0],
            [0.5, 0.5, 1.0],
            [0.0, 0.5, 1.0],
            [0.0, 0.0, 1.5],
            [0.0, 0.5, 1.5],
            [0.5, 0.0, 1.5],
        ],
        dtype=float,
    )
    return nodes


def _element() -> np.ndarray:
    return np.arange(10, dtype=np.int64).reshape((1, 10))


def _build(nodes: np.ndarray, *, origin=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0)):
    return build_quadratic_tet10_plane_edge_intersection(
        nodes,
        _element(),
        plane_origin_mm=origin,
        plane_normal=normal,
        workspace_sha256="a" * 64,
        solve_evidence_sha256="b" * 64,
    )


def test_curved_edge_has_two_analytic_plane_roots() -> None:
    result = _build(_nodes(curved_edge=True))
    edge_hits = [hit for hit in result.hits if hit.edge_id == 0]
    assert len(edge_hits) == 2
    expected = ((1.0 - math.sqrt(0.5)) / 2.0, (1.0 + math.sqrt(0.5)) / 2.0)
    assert [hit.parameter_t for hit in edge_hits] == pytest.approx(expected, abs=1.0e-12)
    assert [hit.point_mm[0] for hit in edge_hits] == pytest.approx(expected, abs=1.0e-12)
    assert [hit.point_mm[2] for hit in edge_hits] == pytest.approx((0.0, 0.0), abs=1.0e-12)
    assert result.length_unit == "mm"
    assert result.semantics == "quadratic_tet10_edge_plane_roots_geometry_only"


def test_straight_quadratic_edge_reduces_to_expected_linear_root() -> None:
    nodes = _nodes(curved_edge=False)
    result = _build(nodes, origin=(0.25, 0.0, 0.0), normal=(1.0, 0.0, 0.0))
    edge_hits = [hit for hit in result.hits if hit.edge_id == 0]
    assert len(edge_hits) == 1
    assert edge_hits[0].parameter_t == pytest.approx(0.25, abs=1.0e-12)
    assert edge_hits[0].point_mm == pytest.approx((0.25, 0.0, 1.0), abs=1.0e-12)


def test_identity_is_deterministic_and_sensitive_to_geometry_plane_and_provenance() -> None:
    nodes = _nodes(curved_edge=True)
    a = _build(nodes)
    b = _build(nodes.copy())
    moved = _build(nodes, origin=(0.0, 0.0, 0.1))
    changed_nodes = nodes.copy()
    changed_nodes[4, 2] = -0.8
    changed = _build(changed_nodes)
    other_solve = build_quadratic_tet10_plane_edge_intersection(
        nodes,
        _element(),
        plane_origin_mm=(0.0, 0.0, 0.0),
        plane_normal=(0.0, 0.0, 1.0),
        workspace_sha256="a" * 64,
        solve_evidence_sha256="c" * 64,
    )
    assert a == b
    assert len(a.geometry_sha256) == 64
    assert len(a.plane_sha256) == 64
    assert len(a.intersection_sha256) == 64
    assert a.intersection_sha256 != moved.intersection_sha256
    assert a.intersection_sha256 != changed.intersection_sha256
    assert a.intersection_sha256 != other_solve.intersection_sha256


def test_coincident_quadratic_edge_is_explicit_not_fabricated_into_point_hits() -> None:
    nodes = _nodes(curved_edge=False)
    nodes[0, 2] = 0.0
    nodes[1, 2] = 0.0
    nodes[4, 2] = 0.0
    result = _build(nodes)
    assert any(edge.edge_id == 0 for edge in result.coincident_edges)
    assert not any(hit.edge_id == 0 for hit in result.hits)


def test_fail_closed_validation() -> None:
    nodes = _nodes(curved_edge=True)
    with pytest.raises(ValueError, match="QUADRATIC_SECTION_NORMAL"):
        build_quadratic_tet10_plane_edge_intersection(
            nodes, _element(), plane_origin_mm=(0, 0, 0), plane_normal=(0, 0, 0),
            workspace_sha256="a" * 64, solve_evidence_sha256="b" * 64,
        )
    with pytest.raises(ValueError, match="QUADRATIC_SECTION_TOLERANCE"):
        build_quadratic_tet10_plane_edge_intersection(
            nodes, _element(), plane_origin_mm=(0, 0, 0), plane_normal=(0, 0, 1),
            workspace_sha256="a" * 64, solve_evidence_sha256="b" * 64, tolerance_mm=0.0,
        )
    bad = _element().copy()
    bad[0, 9] = 999
    with pytest.raises(ValueError, match="QUADRATIC_SECTION_CONNECTIVITY"):
        build_quadratic_tet10_plane_edge_intersection(
            nodes, bad, plane_origin_mm=(0, 0, 0), plane_normal=(0, 0, 1),
            workspace_sha256="a" * 64, solve_evidence_sha256="b" * 64,
        )


def test_contract_does_not_claim_unimplemented_cut_physics_or_ansys_equivalence() -> None:
    result = _build(_nodes(curved_edge=True))
    text = repr(result).lower()
    for forbidden in (
        "von_mises",
        "stress_interpolation",
        "section_resultant",
        "industrial_validation",
        "ansys_equivalence",
    ):
        assert forbidden not in text
