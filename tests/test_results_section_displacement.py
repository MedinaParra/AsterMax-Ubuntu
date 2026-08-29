from __future__ import annotations

import numpy as np
import pytest

from astermax.fea.adaptive_tet10_section import build_adaptive_tet10_section
from astermax.fea.section_polyline_assembly import assemble_section_polylines
from astermax.fea.section_displacement_field import build_section_displacement_field
from astermax.fea.results_quadratic_section import build_production_quadratic_section_view
from astermax.fea.results_section_displacement import (
    build_production_section_displacement_contour,
    probe_section_displacement_contour,
)


def _linear_tet10() -> tuple[np.ndarray, np.ndarray]:
    corners = np.asarray(((0.0,0.0,0.0),(1.0,0.0,0.0),(0.0,1.0,0.0),(0.0,0.0,1.0)), dtype=float)
    nodes = np.vstack((
        corners,
        0.5*(corners[0]+corners[1]),
        0.5*(corners[1]+corners[2]),
        0.5*(corners[2]+corners[0]),
        0.5*(corners[0]+corners[3]),
        0.5*(corners[2]+corners[3]),
        0.5*(corners[1]+corners[3]),
    ))
    return nodes, np.arange(10, dtype=np.int64).reshape(1,10)


def _affine(points: np.ndarray) -> np.ndarray:
    x,y,z = points[:,0], points[:,1], points[:,2]
    return np.column_stack((1+2*x-3*y+0.5*z, -2+x+4*y-z, 0.25-0.5*x+2*z))


def _fixture():
    nodes, elements = _linear_tet10()
    workspace = "workspace-c5-4t"
    solve = "solve-c5-4t"
    section = build_adaptive_tet10_section(
        nodes, elements,
        plane_origin_mm=(0.0,0.0,0.3), plane_normal=(0.0,0.0,1.0),
        workspace_sha256=workspace, solve_evidence_sha256=solve,
        target_error_mm=1.0e-10, topology_tolerance_mm=1.0e-8,
        initial_sampling_divisions=4, max_sampling_divisions=8,
    )
    assembly = assemble_section_polylines(section, endpoint_tolerance_mm=1.0e-8)
    field = build_section_displacement_field(
        nodes, elements, _affine(nodes), assembly,
        workspace_sha256=workspace, solve_evidence_sha256=solve,
        geometry_tolerance_mm=1.0e-10, cross_element_tolerance_mm=1.0e-10,
    )
    projected = np.column_stack((nodes[:,0] + 0.36*nodes[:,2], -nodes[:,1] + 0.22*nodes[:,2]))
    view = build_production_quadratic_section_view(
        nodes, elements,
        workspace_sha256=workspace, solve_evidence_sha256=solve,
        axis="Z", offset_mm=0.3, projected_view_xy=projected,
        canvas_width=800, canvas_height=600,
        target_error_mm=1.0e-10, topology_tolerance_mm=1.0e-8,
        initial_sampling_divisions=4, max_sampling_divisions=8,
    )
    assert view.status == "READY"
    assert field.status == "READY"
    return nodes, elements, view, field


def test_verified_u_mag_contour_binds_one_to_one_with_section_view() -> None:
    _, _, view, field = _fixture()
    contour = build_production_section_displacement_contour(view, field)
    assert contour.status == "READY"
    assert contour.scalar_name == "U_MAG"
    assert contour.scalar_unit == "mm"
    assert contour.sample_count == field.sample_count
    assert contour.sample_count == sum(len(p.canvas_xy) for p in view.polylines)
    by_key = {(s.polyline_index,s.point_index): s for s in field.samples}
    for sample in contour.samples:
        source = by_key[(sample.polyline_index, sample.point_index)]
        assert sample.displacement_magnitude_mm == pytest.approx(source.displacement_magnitude_mm)
        assert 0.0 <= sample.normalized_scalar <= 1.0


def test_probe_returns_exact_verified_sample_without_interpolation() -> None:
    _, _, view, field = _fixture()
    contour = build_production_section_displacement_contour(view, field)
    target = contour.samples[len(contour.samples)//2]
    probe = probe_section_displacement_contour(contour, *target.canvas_xy, max_distance_px=1.0e-9)
    assert probe.canvas_distance_px == pytest.approx(0.0)
    assert probe.point_mm == target.point_mm
    assert probe.displacement_mm == target.displacement_mm
    assert probe.displacement_magnitude_mm == target.displacement_magnitude_mm
    assert probe.element_id == target.element_id


def test_probe_distance_limit_fails_closed() -> None:
    _, _, view, field = _fixture()
    contour = build_production_section_displacement_contour(view, field)
    with pytest.raises(ValueError, match="SECTION_PROBE_NO_SAMPLE_WITHIN_LIMIT"):
        probe_section_displacement_contour(contour, -1.0e6, -1.0e6, max_distance_px=2.0)


def test_contour_identity_is_deterministic_and_canvas_sensitive_only_at_view_layer() -> None:
    nodes, elements, view, field = _fixture()
    a = build_production_section_displacement_contour(view, field)
    b = build_production_section_displacement_contour(view, field)
    assert a.contour_sha256 == b.contour_sha256
    projected = np.column_stack((nodes[:,0] + 0.36*nodes[:,2], -nodes[:,1] + 0.22*nodes[:,2]))
    resized_view = build_production_quadratic_section_view(
        nodes, elements,
        workspace_sha256=view.workspace_sha256, solve_evidence_sha256=view.solve_evidence_sha256,
        axis="Z", offset_mm=0.3, projected_view_xy=projected,
        canvas_width=1200, canvas_height=700,
        target_error_mm=1.0e-10, topology_tolerance_mm=1.0e-8,
        initial_sampling_divisions=4, max_sampling_divisions=8,
    )
    c = build_production_section_displacement_contour(resized_view, field)
    assert resized_view.assembly_sha256 == view.assembly_sha256
    assert c.field_sha256 == a.field_sha256
    assert c.contour_sha256 != a.contour_sha256


def test_stale_field_is_blocked_and_renders_no_samples() -> None:
    nodes, elements, view, _ = _fixture()
    section = build_adaptive_tet10_section(
        nodes, elements,
        plane_origin_mm=(0.0,0.0,0.3), plane_normal=(0.0,0.0,1.0),
        workspace_sha256="workspace-c5-4t", solve_evidence_sha256="other-solve",
        target_error_mm=1.0e-10, topology_tolerance_mm=1.0e-8,
        initial_sampling_divisions=4, max_sampling_divisions=8,
    )
    assembly = assemble_section_polylines(section, endpoint_tolerance_mm=1.0e-8)
    stale = build_section_displacement_field(
        nodes, elements, _affine(nodes), assembly,
        workspace_sha256="workspace-c5-4t", solve_evidence_sha256="other-solve",
    )
    contour = build_production_section_displacement_contour(view, stale)
    assert contour.status == "BLOCKED"
    assert "SOLVE_PROVENANCE_MISMATCH" in contour.blockers
    assert contour.sample_count == 0


def test_contract_does_not_claim_stress_or_smoothed_section_results() -> None:
    _, _, view, field = _fixture()
    contour = build_production_section_displacement_contour(view, field)
    text = (contour.schema + " " + contour.semantics).lower()
    forbidden = ("von_mises", "stress_recovery", "section_resultant", "ansys_equivalence")
    assert not any(token in text for token in forbidden)
