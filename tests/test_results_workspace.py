from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from astermax.results_workspace import build_results_workspace_manifest, write_results_workspace


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _summary(tmp_path: Path) -> dict:
    viewer = tmp_path / "viewer.html"
    inspector = tmp_path / "inspector.html"
    passport = tmp_path / "passport.html"
    viewer.write_text("<html>RESULTS</html>", encoding="utf-8")
    inspector.write_text("<html>MESH</html>", encoding="utf-8")
    passport.write_text("<html>EVIDENCE</html>", encoding="utf-8")
    return {
        "result_class": "ASTERMAX_PROJECT_UNCONVERGED_NOT_INDUSTRIAL_RESULT",
        "claims": {
            "converged": False,
            "industrial_validation": False,
            "ansys_equivalence": False,
            "curved_tet10": False,
            "global_jacobian_positivity_proved": False,
        },
        "analysis_passport": {"highest_demonstrated_stage": "EQUILIBRIUM_VERIFIED"},
        "artifacts": {
            "viewer": str(viewer),
            "viewer_sha256": _sha(viewer),
            "mesh_inspector": str(inspector),
            "mesh_inspector_sha256": _sha(inspector),
            "analysis_passport": str(passport),
            "analysis_passport_sha256": _sha(passport),
        },
    }


def test_workspace_hash_verifies_original_artifacts_and_preserves_claims(tmp_path: Path) -> None:
    summary = _summary(tmp_path)
    target = tmp_path / "workspace.html"
    manifest = write_results_workspace(target, summary)

    assert manifest["schema"] == "AsterMaxResultsEvidenceWorkspaceV1"
    assert manifest["highest_demonstrated_stage"] == "EQUILIBRIUM_VERIFIED"
    assert manifest["workspace_contract"]["child_hashes_verified_before_render"] is True
    assert manifest["workspace_contract"]["workspace_does_not_upgrade_claims"] is True
    assert manifest["claims"] == summary["claims"]
    assert target.is_file()
    document = target.read_text(encoding="utf-8")
    assert "Results" in document
    assert "Mesh Inspector" in document
    assert "Analysis Passport" in document
    assert "http://" not in document and "https://" not in document


def test_workspace_fails_closed_when_child_artifact_is_tampered(tmp_path: Path) -> None:
    summary = _summary(tmp_path)
    Path(summary["artifacts"]["viewer"]).write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        build_results_workspace_manifest(summary, tmp_path / "workspace.html")


def test_workspace_fails_closed_when_required_artifact_is_missing(tmp_path: Path) -> None:
    summary = _summary(tmp_path)
    Path(summary["artifacts"]["analysis_passport"]).unlink()
    with pytest.raises(ValueError, match="missing required workspace artifact"):
        write_results_workspace(tmp_path / "workspace.html", summary)
