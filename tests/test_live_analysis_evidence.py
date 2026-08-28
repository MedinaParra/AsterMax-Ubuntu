from __future__ import annotations

from pathlib import Path

import pytest

from astermax.fea.live_analysis_evidence import (
    LiveAnalysisEvidenceError,
    build_live_analysis_evidence,
    file_sha256,
)


def _summary(tmp_path: Path) -> dict:
    step = tmp_path / "model.step"
    vtu = tmp_path / "result.vtu"
    viewer = tmp_path / "viewer.html"
    step.write_text("ISO-10303-21;TEST;END-ISO-10303-21;", encoding="utf-8")
    vtu.write_text("<VTKFile>verified</VTKFile>", encoding="utf-8")
    viewer.write_text("<html>verified</html>", encoding="utf-8")
    step_sha = file_sha256(step)
    return {
        "schema": "AsterMaxDesktopPMVResultV1",
        "result_class": "PMV_UNCONVERGED_USER_MODEL_NOT_INDUSTRIAL_RESULT",
        "source_step": str(step),
        "source_step_sha256": step_sha,
        "scope_contract": {"constraint": "X_MIN_FIXED_ALL_TRANSLATIONS", "load": "X_MAX_CONSISTENT_TRI6_RESULTANT"},
        "model_preparation": {
            "schema": "AsterMaxModelPreparationEvidenceV1",
            "step_sha256": step_sha,
            "constraint_selection_sha256": "1" * 64,
            "load_selection_sha256": "2" * 64,
            "snapshot_sha256": "3" * 64,
            "mesh_gate": {
                "schema": "AsterMaxMeshPreparationGateV1",
                "gate_sha256": "4" * 64,
                "minimum_det_jacobian_mm3": 12.5,
                "maximum_det_jacobian_mm3": 25.0,
                "positive_jacobian_fraction": 1.0,
                "maximum_midside_deviation_mm": 0.0,
                "maximum_relative_midside_deviation": 0.0,
                "straight_sided_verified": True,
                "positive_jacobian_verified": True,
                "tet10_count": 96,
                "integration_point_count": 384,
            },
        },
        "mesh": {"family": "TET10", "target_size_mm": 10.0, "nodes": 231, "elements": 96},
        "checks": {"force_residual_n": 3.2e-10, "moment_residual_nmm": 6.1e-9},
        "claims": {"converged": False, "industrial_validation": False, "ansys_equivalence": False},
        "artifacts": {"vtu": str(vtu), "viewer": str(viewer), "vtu_sha256": file_sha256(vtu), "viewer_sha256": file_sha256(viewer)},
    }


def test_live_evidence_binds_preparation_step_mesh_bc_equilibrium_and_artifacts(tmp_path: Path) -> None:
    summary = _summary(tmp_path)
    snap = build_live_analysis_evidence(summary)
    assert snap.step_sha256 == summary["source_step_sha256"]
    assert snap.constraint_selection_sha256 == "1" * 64
    assert snap.load_selection_sha256 == "2" * 64
    assert snap.mesh_gate_sha256 == "4" * 64
    assert snap.minimum_det_jacobian_mm3 == pytest.approx(12.5)
    assert snap.positive_jacobian_fraction == 1.0
    assert snap.maximum_relative_midside_deviation == 0.0
    assert snap.mesh_family == "TET10"
    assert snap.node_count == 231 and snap.element_count == 96
    assert snap.constraint_scope == "X_MIN_FIXED_ALL_TRANSLATIONS"
    assert snap.load_scope == "X_MAX_CONSISTENT_TRI6_RESULTANT"
    assert snap.vtu_sha256 == summary["artifacts"]["vtu_sha256"]
    assert snap.viewer_sha256 == summary["artifacts"]["viewer_sha256"]
    assert snap.converged is False
    assert snap.industrial_validation is False
    assert snap.ansys_equivalence is False


def test_live_evidence_hash_is_deterministic(tmp_path: Path) -> None:
    summary = _summary(tmp_path)
    assert build_live_analysis_evidence(summary).snapshot_sha256 == build_live_analysis_evidence(summary).snapshot_sha256


def test_tampered_step_fails_closed(tmp_path: Path) -> None:
    summary = _summary(tmp_path)
    Path(summary["source_step"]).write_text("tampered", encoding="utf-8")
    with pytest.raises(LiveAnalysisEvidenceError, match="STEP hash mismatch"):
        build_live_analysis_evidence(summary)


def test_tampered_vtu_fails_closed(tmp_path: Path) -> None:
    summary = _summary(tmp_path)
    Path(summary["artifacts"]["vtu"]).write_text("tampered", encoding="utf-8")
    with pytest.raises(LiveAnalysisEvidenceError, match="VTU hash mismatch"):
        build_live_analysis_evidence(summary)


def test_tampered_viewer_fails_closed(tmp_path: Path) -> None:
    summary = _summary(tmp_path)
    Path(summary["artifacts"]["viewer"]).write_text("tampered", encoding="utf-8")
    with pytest.raises(LiveAnalysisEvidenceError, match="viewer hash mismatch"):
        build_live_analysis_evidence(summary)


def test_preparation_step_mismatch_is_rejected(tmp_path: Path) -> None:
    summary = _summary(tmp_path)
    summary["model_preparation"]["step_sha256"] = "f" * 64
    with pytest.raises(LiveAnalysisEvidenceError, match="preparation STEP hash mismatch"):
        build_live_analysis_evidence(summary, verify_files=False)


def test_unverified_jacobian_gate_is_rejected(tmp_path: Path) -> None:
    summary = _summary(tmp_path)
    summary["model_preparation"]["mesh_gate"]["positive_jacobian_verified"] = False
    with pytest.raises(LiveAnalysisEvidenceError, match="Jacobian gate is not verified"):
        build_live_analysis_evidence(summary, verify_files=False)


def test_identical_support_and_load_selection_is_rejected(tmp_path: Path) -> None:
    summary = _summary(tmp_path)
    summary["model_preparation"]["load_selection_sha256"] = summary["model_preparation"]["constraint_selection_sha256"]
    with pytest.raises(LiveAnalysisEvidenceError, match="must be distinct"):
        build_live_analysis_evidence(summary, verify_files=False)


@pytest.mark.parametrize("claim", ["converged", "industrial_validation", "ansys_equivalence"])
def test_user_model_claim_upgrade_is_rejected(tmp_path: Path, claim: str) -> None:
    summary = _summary(tmp_path)
    summary["claims"][claim] = True
    with pytest.raises(LiveAnalysisEvidenceError, match="refuses upgraded user-model claims"):
        build_live_analysis_evidence(summary)


def test_missing_step_hash_is_rejected_even_without_file_verification(tmp_path: Path) -> None:
    summary = _summary(tmp_path)
    summary.pop("source_step_sha256")
    with pytest.raises(LiveAnalysisEvidenceError, match="STEP SHA-256 is missing"):
        build_live_analysis_evidence(summary, verify_files=False)
