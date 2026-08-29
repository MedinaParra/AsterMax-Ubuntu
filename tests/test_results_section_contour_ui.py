from __future__ import annotations

from dataclasses import replace

import pytest

from astermax.fea.results_section_contour_ui import build_native_section_contour_ui, probe_native_section_contour_ui
from astermax.fea.results_section_displacement import (
    ProductionSectionDisplacementContourV1,
    SectionDisplacementContourSampleV1,
)


def _contour() -> ProductionSectionDisplacementContourV1:
    samples = (
        SectionDisplacementContourSampleV1(0, 0, (10.0, 20.0), (0.0, 0.0, 0.3), (0.1, 0.0, 0.0), 0.1, 0.0, 0),
        SectionDisplacementContourSampleV1(0, 1, (30.0, 40.0), (0.5, 0.0, 0.3), (0.2, 0.0, 0.0), 0.2, 0.5, 0),
        SectionDisplacementContourSampleV1(0, 2, (50.0, 20.0), (0.0, 0.5, 0.3), (0.3, 0.0, 0.0), 0.3, 1.0, 0),
    )
    return ProductionSectionDisplacementContourV1(
        schema="AsterMaxProductionSectionDisplacementContourV1",
        semantics="verified_tet10_section_u_mag_results_contour_no_smoothing",
        length_unit="mm",
        workspace_sha256="workspace",
        solve_evidence_sha256="solve",
        section_view_sha256="view",
        assembly_sha256="assembly",
        field_sha256="field",
        contour_sha256="contour-c5-4u",
        status="READY",
        blockers=(),
        scalar_name="U_MAG",
        scalar_unit="mm",
        min_value_mm=0.1,
        max_value_mm=0.3,
        sample_count=3,
        samples=samples,
    )


def test_native_ui_preserves_verified_samples_and_builds_mm_legend() -> None:
    contour = _contour()
    ui = build_native_section_contour_ui(contour, legend_tick_count=5)
    assert ui.status == "READY"
    assert ui.scalar_name == "U_MAG" and ui.scalar_unit == "mm"
    assert ui.sample_count == contour.sample_count
    assert len(ui.legend_ticks) == 5
    assert ui.legend_ticks[0].value_mm == pytest.approx(0.1)
    assert ui.legend_ticks[-1].value_mm == pytest.approx(0.3)
    flattened = [point for line in ui.polylines for point in line.points]
    assert [p.displacement_magnitude_mm for p in flattened] == [s.displacement_magnitude_mm for s in contour.samples]
    assert [p.normalized_scalar for p in flattened] == [s.normalized_scalar for s in contour.samples]


def test_native_probe_returns_exact_verified_sample() -> None:
    contour = _contour()
    ui = build_native_section_contour_ui(contour)
    probe = probe_native_section_contour_ui(ui, contour, 30.0, 40.0, max_distance_px=0.0)
    assert probe.canvas_distance_px == 0.0
    assert probe.point_mm == contour.samples[1].point_mm
    assert probe.displacement_mm == contour.samples[1].displacement_mm
    assert probe.displacement_magnitude_mm == contour.samples[1].displacement_magnitude_mm


def test_blocked_contour_renders_no_samples_or_legend() -> None:
    contour = replace(_contour(), status="BLOCKED", blockers=("TEST",), samples=(), sample_count=0)
    ui = build_native_section_contour_ui(contour)
    assert ui.status == "BLOCKED"
    assert ui.sample_count == 0
    assert not ui.polylines
    assert not ui.legend_ticks


def test_stale_ui_cannot_probe_different_contour() -> None:
    contour = _contour()
    ui = build_native_section_contour_ui(contour)
    other = replace(contour, contour_sha256="other-contour")
    with pytest.raises(ValueError, match="SECTION_CONTOUR_UI_STALE"):
        probe_native_section_contour_ui(ui, other, 10.0, 20.0)


def test_ui_identity_is_deterministic_and_legend_sensitive() -> None:
    contour = _contour()
    a = build_native_section_contour_ui(contour, legend_tick_count=5)
    b = build_native_section_contour_ui(contour, legend_tick_count=5)
    c = build_native_section_contour_ui(contour, legend_tick_count=3)
    assert a.ui_sha256 == b.ui_sha256
    assert a.ui_sha256 != c.ui_sha256
    assert a.contour_sha256 == c.contour_sha256


def test_contract_does_not_claim_stress_or_equivalence() -> None:
    ui = build_native_section_contour_ui(_contour())
    text = (ui.schema + " " + ui.semantics).lower()
    forbidden = ("von_mises", "stress_recovery", "section_resultant", "ansys_equivalence")
    assert not any(token in text for token in forbidden)
