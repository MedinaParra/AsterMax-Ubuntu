from __future__ import annotations

from pathlib import Path

import pytest

from astermax.fea.credibility_visualization import (
    CredibilityVisualizationError,
    render_credibility_html,
)


def _payload() -> dict:
    source = "a" * 64
    section = "b" * 64
    witness = "c" * 64
    return {
        "schema": "AsterMaxC3_2CadDerivedAxialBenchmarkV1",
        "provenance": {
            "same_step_drives_meshing_and_analytical_reference": True,
            "source_sha256": source,
            "section_sha256": section,
        },
        "cad_analytical_witness": {
            "source_sha256": source,
            "section_sha256": section,
            "witness_sha256": witness,
            "area_mm2": 400.0,
            "analytical_sigma_mpa": 100.0,
        },
        "levels": [
            {"level": {"mesh_size_mm": 20.0, "rms_error_mpa": 0.20, "maximum_relative_error": 0.012}},
            {"level": {"mesh_size_mm": 14.0, "rms_error_mpa": 0.15, "maximum_relative_error": 0.010}},
            {"level": {"mesh_size_mm": 10.0, "rms_error_mpa": 0.10, "maximum_relative_error": 0.008}},
        ],
        "claims": {
            "cad_derived_reference": True,
            "stress_convergence_for_this_axial_fixture": True,
            "arbitrary_model_convergence": False,
            "industrial_validation": False,
            "ansys_equivalence": False,
        },
    }


def test_c4_renders_exact_provenance_and_claim_boundary(tmp_path: Path) -> None:
    output = tmp_path / "credibility.html"
    manifest = render_credibility_html(_payload(), output)
    text = output.read_text(encoding="utf-8")
    assert manifest.mesh_sizes_mm == (20.0, 14.0, 10.0)
    assert manifest.fixture_convergence_claim is True
    assert manifest.arbitrary_model_convergence is False
    assert manifest.industrial_validation is False
    assert manifest.ansys_equivalence is False
    assert "100 MPa" in text
    assert "Arbitrary-model convergence: false" in text
    assert "ANSYS equivalence: false" in text
    assert len(manifest.html_sha256) == 64


def test_c4_refuses_section_provenance_mismatch(tmp_path: Path) -> None:
    payload = _payload()
    payload["cad_analytical_witness"]["section_sha256"] = "d" * 64
    with pytest.raises(CredibilityVisualizationError, match="section SHA mismatch"):
        render_credibility_html(payload, tmp_path / "bad.html")


def test_c4_refuses_claim_upgrade(tmp_path: Path) -> None:
    payload = _payload()
    payload["claims"]["ansys_equivalence"] = True
    with pytest.raises(CredibilityVisualizationError, match="ANSYS-equivalence"):
        render_credibility_html(payload, tmp_path / "bad.html")


def test_c4_refuses_non_monotonic_refinement_order(tmp_path: Path) -> None:
    payload = _payload()
    payload["levels"][1]["level"]["mesh_size_mm"] = 25.0
    with pytest.raises(CredibilityVisualizationError, match="coarse to fine"):
        render_credibility_html(payload, tmp_path / "bad.html")


def test_c4_is_deterministic(tmp_path: Path) -> None:
    a = render_credibility_html(_payload(), tmp_path / "a.html")
    b = render_credibility_html(_payload(), tmp_path / "b.html")
    assert a.html_sha256 == b.html_sha256
