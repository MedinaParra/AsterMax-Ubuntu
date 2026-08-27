from __future__ import annotations

from pathlib import Path

from astermax.analysis_passport import build_analysis_passport, write_analysis_passport


def _summary() -> dict:
    return {
        "result_class": "ASTERMAX_PROJECT_UNCONVERGED_NOT_INDUSTRIAL_RESULT",
        "selection_mode": "PERSISTENT_CAD_SURFACE_SIGNATURES",
        "tet10_sampled_jacobian": {"status": "PASS"},
        "tet10_reference_jacobian": {"status": "PASS"},
        "tet10_adaptive_jacobian": {"status": "PASS"},
        "tet10_geometry_scope": {"status": "PASS"},
        "mesh_quality": {"status": "PASS"},
        "checks": {"force_residual_n": 1.0e-8, "moment_residual_nmm": 1.0e-6},
        "claims": {
            "converged": False,
            "industrial_validation": False,
            "ansys_equivalence": False,
            "curved_tet10": False,
            "global_jacobian_positivity_proved": False,
        },
        "provenance": {
            "geometry_sha256": "a" * 64,
            "support_surface_sha256": "b" * 64,
            "load_surface_sha256": "c" * 64,
        },
        "artifacts": {"vtu": "result.vtu", "viewer": "viewer.html"},
    }


def test_passport_reaches_equilibrium_without_upgrading_false_claims() -> None:
    passport = build_analysis_passport(_summary())
    assert passport["schema"] == "AsterMaxAnalysisPassportV1"
    assert passport["highest_demonstrated_stage"] == "EQUILIBRIUM_VERIFIED"
    assert passport["evidence_vector"]["solution_convergence"]["status"] == "NOT_DEMONSTRATED"
    assert passport["evidence_vector"]["industrial_validation"]["status"] == "NOT_DEMONSTRATED"
    assert passport["evidence_vector"]["ansys_equivalence"]["status"] == "NOT_CLAIMED"
    assert passport["claim_guards"]["converged"] is False
    assert passport["claim_guards"]["industrial_validation"] is False
    assert "NO_TRUST_SCORE" in passport["evidence_boundary"]


def test_passport_does_not_hide_failed_equilibrium() -> None:
    summary = _summary()
    summary["checks"]["force_residual_n"] = 2.0e-5
    passport = build_analysis_passport(summary)
    assert passport["highest_demonstrated_stage"] == "GEOMETRY_AND_MESH_VERIFIED"
    assert passport["evidence_vector"]["force_balance"]["status"] == "FAIL"


def test_passport_does_not_hide_missing_provenance() -> None:
    summary = _summary()
    summary["provenance"]["geometry_sha256"] = None
    passport = build_analysis_passport(summary)
    assert passport["highest_demonstrated_stage"] == "COMPUTED"
    assert passport["evidence_vector"]["geometry_provenance"]["status"] == "MISSING"


def test_write_passport_is_offline_and_machine_readable(tmp_path: Path) -> None:
    target = tmp_path / "passport.html"
    manifest = write_analysis_passport(target, _summary())
    text = target.read_text(encoding="utf-8")
    assert target.is_file()
    assert "ASTERMAX ANALYSIS PASSPORT" in text
    assert "EQUILIBRIUM_VERIFIED" in text
    assert "Machine-readable passport" in text
    assert len(manifest["html_sha256"]) == 64
