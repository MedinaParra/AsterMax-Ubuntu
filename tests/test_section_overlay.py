import numpy as np
import pytest

from astermax.fea.section_intersection import build_linearized_tet10_section_intersection
from astermax.fea.section_overlay import build_section_overlay_payload


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


def _section(workspace="w" * 64, solve="s" * 64, offset=0.25):
    nodes, elements = _unit_tet10()
    return build_linearized_tet10_section_intersection(
        nodes,
        elements,
        plane_origin_mm=(offset, 0.0, 0.0),
        plane_normal=(1.0, 0.0, 0.0),
        workspace_sha256=workspace,
        solve_evidence_sha256=solve,
    )


def test_overlay_projects_exact_analytic_section_with_native_oblique_projection():
    section = _section()
    overlay = build_section_overlay_payload(
        section,
        expected_workspace_sha256="w" * 64,
        expected_solve_evidence_sha256="s" * 64,
    )
    assert overlay.schema == "AsterMaxSectionOverlayPayloadV1"
    assert overlay.polyline_count == 1
    projected = np.asarray(overlay.polylines[0].projected_xy)
    original = np.asarray(section.polygons[0].points_mm)
    expected = np.column_stack((original[:, 0] + 0.36 * original[:, 2], -original[:, 1] + 0.22 * original[:, 2]))
    assert projected == pytest.approx(expected)


def test_overlay_is_deterministic_and_bound_to_section_identity():
    first = build_section_overlay_payload(
        _section(),
        expected_workspace_sha256="w" * 64,
        expected_solve_evidence_sha256="s" * 64,
    )
    second = build_section_overlay_payload(
        _section(),
        expected_workspace_sha256="w" * 64,
        expected_solve_evidence_sha256="s" * 64,
    )
    moved = build_section_overlay_payload(
        _section(offset=0.5),
        expected_workspace_sha256="w" * 64,
        expected_solve_evidence_sha256="s" * 64,
    )
    assert first.overlay_sha256 == second.overlay_sha256
    assert first.section_sha256 == second.section_sha256
    assert moved.section_sha256 != first.section_sha256
    assert moved.overlay_sha256 != first.overlay_sha256


def test_overlay_fails_closed_on_stale_workspace_or_solve():
    section = _section()
    with pytest.raises(ValueError, match="SECTION_OVERLAY_WORKSPACE_STALE"):
        build_section_overlay_payload(
            section,
            expected_workspace_sha256="x" * 64,
            expected_solve_evidence_sha256="s" * 64,
        )
    with pytest.raises(ValueError, match="SECTION_OVERLAY_SOLVE_STALE"):
        build_section_overlay_payload(
            section,
            expected_workspace_sha256="w" * 64,
            expected_solve_evidence_sha256="x" * 64,
        )


def test_overlay_contains_no_cut_field_or_resultant_claims():
    overlay = build_section_overlay_payload(
        _section(),
        expected_workspace_sha256="w" * 64,
        expected_solve_evidence_sha256="s" * 64,
    )
    assert "visualization_only" in overlay.semantics
    assert not hasattr(overlay, "stress")
    assert not hasattr(overlay, "von_mises")
    assert not hasattr(overlay, "displacement")
    assert not hasattr(overlay, "resultant")
