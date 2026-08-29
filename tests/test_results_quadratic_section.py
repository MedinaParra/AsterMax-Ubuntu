from __future__ import annotations

import numpy as np

from astermax.fea.results_quadratic_section import build_production_quadratic_section_view


def _linear_tet10_fixture():
    p0 = np.array([0.0, 0.0, 0.0])
    p1 = np.array([1.0, 0.0, 0.0])
    p2 = np.array([0.0, 1.0, 0.0])
    p3 = np.array([0.0, 0.0, 1.0])
    p4 = 0.5 * (p0 + p1)
    p5 = 0.5 * (p1 + p2)
    p6 = 0.5 * (p2 + p0)
    p7 = 0.5 * (p0 + p3)
    p8 = 0.5 * (p2 + p3)
    p9 = 0.5 * (p1 + p3)
    nodes = np.vstack((p0, p1, p2, p3, p4, p5, p6, p7, p8, p9))
    return nodes, np.arange(10, dtype=np.int64).reshape(1, 10)


def _curved_tet10_fixture():
    f = lambda r: r * r - r + 0.2
    p0 = np.array([0.0, 0.0, f(0.0)])
    p1 = np.array([1.0, 0.0, f(1.0)])
    p2 = np.array([0.0, 1.0, f(0.0)])
    p3 = np.array([0.0, 0.0, 1.0])
    p4 = np.array([0.5, 0.0, f(0.5)])
    p5 = np.array([0.5, 0.5, f(0.5)])
    p6 = np.array([0.0, 0.5, f(0.0)])
    p7 = 0.5 * (p0 + p3)
    p8 = 0.5 * (p2 + p3)
    p9 = 0.5 * (p1 + p3)
    return np.vstack((p0, p1, p2, p3, p4, p5, p6, p7, p8, p9)), np.arange(10, dtype=np.int64).reshape(1, 10)


def _reference(nodes):
    return np.column_stack((nodes[:, 0] + 0.36 * nodes[:, 2], -nodes[:, 1] + 0.22 * nodes[:, 2]))


def test_verified_quadratic_section_is_results_ready_and_canvas_bound():
    nodes, elements = _linear_tet10_fixture()
    view = build_production_quadratic_section_view(
        nodes,
        elements,
        workspace_sha256="w" * 64,
        solve_evidence_sha256="s" * 64,
        axis="Z",
        offset_mm=0.3,
        projected_view_xy=_reference(nodes),
        canvas_width=900.0,
        canvas_height=600.0,
        target_error_mm=1.0e-10,
        topology_tolerance_mm=1.0e-8,
        initial_sampling_divisions=8,
        max_sampling_divisions=16,
    )
    assert view.status == "READY"
    assert view.ready_for_results
    assert view.topology_valid
    assert view.length_unit == "mm"
    assert view.polyline_count == 1
    assert view.closed_polyline_count == 1
    assert view.open_polyline_count == 0
    assert view.max_plane_residual_mm <= view.target_error_mm
    assert view.max_chord_error_mm <= view.target_error_mm
    assert len(view.polylines[0].canvas_xy) >= 4
    assert len(view.adaptive_section_sha256) == 64
    assert len(view.assembly_sha256) == 64
    assert len(view.view_sha256) == 64


def test_nonconverged_quadratic_section_is_blocked_and_not_rendered():
    nodes, elements = _curved_tet10_fixture()
    view = build_production_quadratic_section_view(
        nodes,
        elements,
        workspace_sha256="w" * 64,
        solve_evidence_sha256="s" * 64,
        axis="Z",
        offset_mm=0.0,
        projected_view_xy=_reference(nodes),
        canvas_width=900.0,
        canvas_height=600.0,
        target_error_mm=1.0e-12,
        initial_sampling_divisions=4,
        max_sampling_divisions=4,
    )
    assert view.status == "BLOCKED"
    assert not view.ready_for_results
    assert "SECTION_GEOMETRY_NOT_CONVERGED" in view.blockers
    assert "SECTION_NOT_READY_FOR_RESULTS" in view.blockers
    assert view.polyline_count == 0
    assert view.polylines == ()


def test_view_identity_is_deterministic_and_sensitive_to_plane_and_canvas():
    nodes, elements = _linear_tet10_fixture()
    kwargs = dict(
        workspace_sha256="w" * 64,
        solve_evidence_sha256="s" * 64,
        axis="Z",
        offset_mm=0.3,
        projected_view_xy=_reference(nodes),
        canvas_width=900.0,
        canvas_height=600.0,
        target_error_mm=1.0e-10,
        topology_tolerance_mm=1.0e-8,
        initial_sampling_divisions=8,
        max_sampling_divisions=16,
    )
    first = build_production_quadratic_section_view(nodes, elements, **kwargs)
    second = build_production_quadratic_section_view(nodes, elements, **kwargs)
    moved = build_production_quadratic_section_view(nodes, elements, **{**kwargs, "offset_mm": 0.4})
    resized = build_production_quadratic_section_view(nodes, elements, **{**kwargs, "canvas_width": 1000.0})
    assert first == second
    assert first.view_sha256 == second.view_sha256
    assert moved.adaptive_section_sha256 != first.adaptive_section_sha256
    assert moved.view_sha256 != first.view_sha256
    assert resized.adaptive_section_sha256 == first.adaptive_section_sha256
    assert resized.assembly_sha256 == first.assembly_sha256
    assert resized.view_sha256 != first.view_sha256


def test_production_section_does_not_claim_unvalidated_cut_fields():
    nodes, elements = _linear_tet10_fixture()
    view = build_production_quadratic_section_view(
        nodes,
        elements,
        workspace_sha256="w" * 64,
        solve_evidence_sha256="s" * 64,
        axis="Z",
        offset_mm=0.3,
        projected_view_xy=_reference(nodes),
        canvas_width=900.0,
        canvas_height=600.0,
        target_error_mm=1.0e-10,
        topology_tolerance_mm=1.0e-8,
        initial_sampling_divisions=8,
        max_sampling_divisions=16,
    )
    text = repr(view).lower()
    assert "geometry_only_fail_closed" in view.semantics
    for forbidden in ("stress_interpolation", "von_mises_field", "section_resultant", "ansys_equivalence", "industrial_validation"):
        assert forbidden not in text
