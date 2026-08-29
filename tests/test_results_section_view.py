from __future__ import annotations

import numpy as np
import pytest

from astermax.fea.results_section_view import (
    build_native_section_view_payload,
    section_axis_plane,
)


def _fixture():
    nodes = np.asarray([
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
    ], dtype=float)
    elements = np.arange(10, dtype=np.int64).reshape((1, 10))
    projected = np.column_stack((nodes[:, 0] + 0.36 * nodes[:, 2], -nodes[:, 1] + 0.22 * nodes[:, 2]))
    return nodes, elements, projected


def test_axis_plane_is_absolute_global_mm_and_fail_closed():
    assert section_axis_plane("X", 0.25) == ((0.25, 0.0, 0.0), (1.0, 0.0, 0.0))
    assert section_axis_plane("y", -2.0) == ((0.0, -2.0, 0.0), (0.0, 1.0, 0.0))
    assert section_axis_plane("Z", 3.0) == ((0.0, 0.0, 3.0), (0.0, 0.0, 1.0))
    with pytest.raises(ValueError, match="SECTION_VIEW_AXIS"):
        section_axis_plane("Q", 0.0)
    with pytest.raises(ValueError, match="SECTION_VIEW_OFFSET"):
        section_axis_plane("X", float("nan"))


def test_native_section_view_is_deterministic_provenance_bound_and_canvas_ready():
    nodes, elements, projected = _fixture()
    kwargs = dict(
        workspace_sha256="a" * 64,
        solve_evidence_sha256="b" * 64,
        axis="X",
        offset_mm=0.25,
        projected_view_xy=projected,
        canvas_width=800.0,
        canvas_height=600.0,
    )
    first = build_native_section_view_payload(nodes, elements, **kwargs)
    second = build_native_section_view_payload(nodes, elements, **kwargs)
    assert first == second
    assert first.schema == "AsterMaxNativeSectionViewPayloadV1"
    assert first.workspace_sha256 == "a" * 64
    assert first.solve_evidence_sha256 == "b" * 64
    assert first.polyline_count == 1
    assert len(first.polylines[0].canvas_xy) == 3
    assert first.section_sha256
    assert first.overlay_sha256
    assert first.view_sha256


def test_plane_movement_changes_section_and_view_identity_without_field_claims():
    nodes, elements, projected = _fixture()
    common = dict(
        workspace_sha256="c" * 64,
        solve_evidence_sha256="d" * 64,
        axis="X",
        projected_view_xy=projected,
        canvas_width=640.0,
        canvas_height=480.0,
    )
    a = build_native_section_view_payload(nodes, elements, offset_mm=0.25, **common)
    b = build_native_section_view_payload(nodes, elements, offset_mm=0.5, **common)
    assert a.section_sha256 != b.section_sha256
    assert a.view_sha256 != b.view_sha256
    text = repr(a).lower()
    for forbidden in ("von_mises", "stress_mpa", "section_force", "resultant", "ansys_equivalence"):
        assert forbidden not in text


def test_canvas_geometry_changes_only_view_identity_not_section_identity():
    nodes, elements, projected = _fixture()
    base = dict(
        workspace_sha256="e" * 64,
        solve_evidence_sha256="f" * 64,
        axis="X",
        offset_mm=0.25,
        projected_view_xy=projected,
        canvas_height=500.0,
    )
    small = build_native_section_view_payload(nodes, elements, canvas_width=600.0, **base)
    wide = build_native_section_view_payload(nodes, elements, canvas_width=1000.0, **base)
    assert small.section_sha256 == wide.section_sha256
    assert small.overlay_sha256 == wide.overlay_sha256
    assert small.view_sha256 != wide.view_sha256


def test_invalid_canvas_and_reference_fail_closed():
    nodes, elements, projected = _fixture()
    common = dict(
        workspace_sha256="1" * 64,
        solve_evidence_sha256="2" * 64,
        axis="X",
        offset_mm=0.25,
        canvas_width=800.0,
        canvas_height=600.0,
    )
    with pytest.raises(ValueError, match="SECTION_VIEW_REFERENCE_EMPTY"):
        build_native_section_view_payload(nodes, elements, projected_view_xy=np.empty((0, 2)), **common)
    with pytest.raises(ValueError, match="SECTION_VIEW_CANVAS"):
        build_native_section_view_payload(
            nodes,
            elements,
            projected_view_xy=projected,
            canvas_width=-1.0,
            canvas_height=600.0,
            workspace_sha256="1" * 64,
            solve_evidence_sha256="2" * 64,
            axis="X",
            offset_mm=0.25,
        )
