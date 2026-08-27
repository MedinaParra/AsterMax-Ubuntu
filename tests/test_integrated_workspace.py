from __future__ import annotations

import copy

import pytest

from astermax.integrated_workspace import (
    WORKSPACE_ORDER,
    WorkspacePanel,
    assert_workspace_does_not_upgrade_claims,
    build_integrated_workspace,
)


def _summary() -> dict:
    return {
        "mesh": {"nodes": 231, "elements": 96, "support_tri6": 4, "load_tri6": 4},
        "mesh_quality": {"status": "PASS"},
        "tet10_geometry_scope": {"status": "PASS"},
        "checks": {"force_residual_n": 1.0e-9, "moment_residual_nmm": 1.0e-8},
        "claims": {
            "converged": False,
            "industrial_validation": False,
            "ansys_equivalence": False,
            "curved_tet10": False,
        },
        "analysis_passport": {"highest_demonstrated_stage": "EQUILIBRIUM_VERIFIED"},
        "artifacts": {
            "viewer": "viewer.html",
            "mesh_inspector": "mesh.html",
            "analysis_passport": "passport.html",
            "results_evidence_workspace": "workspace.html",
        },
    }


def test_workspace_has_stable_professional_order() -> None:
    panels = build_integrated_workspace()
    assert tuple(panel.key for panel in panels) == WORKSPACE_ORDER


def test_solved_workspace_derives_state_from_evidence() -> None:
    summary = _summary()
    panels = build_integrated_workspace(summary)
    by_key = {panel.key: panel for panel in panels}
    assert by_key["geometry"].state == "VERIFIED"
    assert by_key["mesh"].state == "VERIFIED"
    assert by_key["boundary_conditions"].state == "VERIFIED"
    assert by_key["solution"].state == "EQUILIBRIUM_VERIFIED"
    assert by_key["results"].state == "AVAILABLE"
    assert by_key["evidence"].state == "EQUILIBRIUM_VERIFIED"
    assert_workspace_does_not_upgrade_claims(summary, panels)


def test_failed_equilibrium_downgrades_solution_without_changing_claims() -> None:
    summary = _summary()
    summary["checks"]["force_residual_n"] = 1.0
    panels = build_integrated_workspace(summary)
    solution = next(panel for panel in panels if panel.key == "solution")
    assert solution.state == "COMPUTED"
    assert "converged=False" in solution.detail
    assert_workspace_does_not_upgrade_claims(summary, panels)


def test_workspace_rejects_presentation_claim_upgrade() -> None:
    summary = _summary()
    panels = list(build_integrated_workspace(summary))
    panels[0] = WorkspacePanel("overview", "Overview", "READY", "ansys_equivalence=true")
    with pytest.raises(ValueError, match="ansys_equivalence"):
        assert_workspace_does_not_upgrade_claims(summary, tuple(panels))


def test_missing_result_artifact_is_visible_not_silently_available() -> None:
    summary = copy.deepcopy(_summary())
    summary["artifacts"].pop("viewer")
    panels = build_integrated_workspace(summary)
    results = next(panel for panel in panels if panel.key == "results")
    assert results.state == "MISSING"
    assert results.artifact is None
