import numpy as np
import pytest

from astermax.fea.section_intersection import build_linearized_tet10_section_intersection


def _unit_tet10():
    nodes = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.5, 0.0, 0.0],
            [0.5, 0.5, 0.0],
            [0.0, 0.5, 0.0],
            [0.0, 0.0, 0.5],
            [0.5, 0.0, 0.5],
            [0.0, 0.5, 0.5],
        ],
        dtype=float,
    )
    elements = np.array([[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]], dtype=np.int64)
    return nodes, elements


def _build(nodes=None, elements=None, **kwargs):
    if nodes is None or elements is None:
        nodes, elements = _unit_tet10()
    return build_linearized_tet10_section_intersection(
        nodes,
        elements,
        plane_origin_mm=(0.25, 0.0, 0.0),
        plane_normal=(1.0, 0.0, 0.0),
        workspace_sha256="w" * 64,
        solve_evidence_sha256="s" * 64,
        **kwargs,
    )


def test_unit_tetra_x_quarter_section_is_expected_triangle():
    section = _build()
    assert section.schema == "AsterMaxSectionIntersectionContractV1"
    assert section.normal_unit == pytest.approx((1.0, 0.0, 0.0))
    assert len(section.polygons) == 1
    points = np.asarray(section.polygons[0].points_mm)
    assert points.shape == (3, 3)
    assert np.allclose(points[:, 0], 0.25)
    expected = np.array([[0.25, 0.0, 0.0], [0.25, 0.75, 0.0], [0.25, 0.0, 0.75]])
    for target in expected:
        assert np.min(np.linalg.norm(points - target, axis=1)) < 1.0e-12


def test_face_coincident_plane_deduplicates_to_three_vertices():
    nodes, elements = _unit_tet10()
    section = build_linearized_tet10_section_intersection(
        nodes,
        elements,
        plane_origin_mm=(0.0, 0.0, 0.0),
        plane_normal=(1.0, 0.0, 0.0),
        workspace_sha256="w" * 64,
        solve_evidence_sha256="s" * 64,
    )
    assert len(section.polygons) == 1
    points = np.asarray(section.polygons[0].points_mm)
    assert points.shape == (3, 3)
    assert np.allclose(points[:, 0], 0.0)


def test_contract_is_deterministic_and_provenance_sensitive():
    first = _build()
    second = _build()
    assert first.geometry_sha256 == second.geometry_sha256
    assert first.section_sha256 == second.section_sha256

    nodes, elements = _unit_tet10()
    changed = build_linearized_tet10_section_intersection(
        nodes,
        elements,
        plane_origin_mm=(0.25, 0.0, 0.0),
        plane_normal=(1.0, 0.0, 0.0),
        workspace_sha256="x" * 64,
        solve_evidence_sha256="s" * 64,
    )
    assert changed.geometry_sha256 == first.geometry_sha256
    assert changed.section_sha256 != first.section_sha256


def test_geometry_change_changes_geometry_and_section_identity():
    nodes, elements = _unit_tet10()
    baseline = _build(nodes, elements)
    changed_nodes = nodes.copy()
    changed_nodes[1, 0] = 1.1
    changed = _build(changed_nodes, elements)
    assert changed.geometry_sha256 != baseline.geometry_sha256
    assert changed.section_sha256 != baseline.section_sha256


def test_plane_change_changes_section_identity_and_geometry():
    baseline = _build()
    nodes, elements = _unit_tet10()
    moved = build_linearized_tet10_section_intersection(
        nodes,
        elements,
        plane_origin_mm=(0.5, 0.0, 0.0),
        plane_normal=(1.0, 0.0, 0.0),
        workspace_sha256="w" * 64,
        solve_evidence_sha256="s" * 64,
    )
    assert moved.section_sha256 != baseline.section_sha256
    assert np.asarray(moved.polygons[0].points_mm)[:, 0] == pytest.approx(0.5)


@pytest.mark.parametrize(
    "origin, normal, tolerance, expected",
    [
        ((0.0, 0.0), (1.0, 0.0, 0.0), 0.0, "SECTION_ORIGIN"),
        ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 0.0, "SECTION_NORMAL_ZERO"),
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), -1.0, "SECTION_TOLERANCE"),
    ],
)
def test_invalid_plane_fails_closed(origin, normal, tolerance, expected):
    nodes, elements = _unit_tet10()
    with pytest.raises(ValueError, match=expected):
        build_linearized_tet10_section_intersection(
            nodes,
            elements,
            plane_origin_mm=origin,
            plane_normal=normal,
            tolerance_mm=tolerance,
            workspace_sha256="w" * 64,
            solve_evidence_sha256="s" * 64,
        )


def test_no_solver_field_claims_are_present_in_section_contract():
    section = _build()
    assert not hasattr(section, "stress")
    assert not hasattr(section, "von_mises")
    assert not hasattr(section, "resultant")
    assert not hasattr(section, "displacement")
