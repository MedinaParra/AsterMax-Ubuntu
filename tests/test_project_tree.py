from __future__ import annotations

import pytest

from astermax.project_tree import TREE_ORDER, assert_tree_does_not_upgrade_claims, build_project_tree


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
            "global_jacobian_positivity_proved": False,
        },
        "analysis_passport": {"highest_demonstrated_stage": "EQUILIBRIUM_VERIFIED"},
        "artifacts": {
            "viewer": "results.html",
            "mesh_inspector": "mesh.html",
            "analysis_passport": "passport.html",
            "results_evidence_workspace": "workspace.html",
        },
    }


def test_empty_project_tree_has_stable_professional_order() -> None:
    nodes = build_project_tree()
    assert tuple(node.key for node in nodes) == TREE_ORDER
    assert nodes[0].state == "READY"
    assert all(node.state == "PENDING" for node in nodes[1:])


def test_solved_tree_exposes_verified_workflow_without_claim_upgrade() -> None:
    summary = _summary()
    nodes = build_project_tree(summary)
    by_key = {node.key: node for node in nodes}
    assert tuple(node.key for node in nodes) == TREE_ORDER
    assert by_key["geometry"].state == "VERIFIED"
    assert by_key["mesh"].state == "VERIFIED"
    assert by_key["supports"].state == "VERIFIED"
    assert by_key["loads"].state == "VERIFIED"
    assert by_key["solution"].state == "EQUILIBRIUM_VERIFIED"
    assert "converged=False" in by_key["solution"].detail
    assert "industrial=False" in by_key["solution"].detail
    assert "ansys=False" in by_key["solution"].detail
    assert by_key["results"].artifact == "results.html"
    assert by_key["evidence"].artifact == "workspace.html"
    assert_tree_does_not_upgrade_claims(summary, nodes)


def test_failed_equilibrium_cannot_render_equilibrium_verified() -> None:
    summary = _summary()
    summary["checks"]["force_residual_n"] = 1.0
    nodes = build_project_tree(summary)
    solution = next(node for node in nodes if node.key == "solution")
    assert solution.state == "COMPUTED"


def test_claim_upgrade_guard_fails_closed() -> None:
    summary = _summary()
    nodes = list(build_project_tree(summary))
    solution = next(i for i, node in enumerate(nodes) if node.key == "solution")
    node = nodes[solution]
    nodes[solution] = type(node)(node.key, node.label, node.state, node.detail + " ansys=true", node.artifact)
    with pytest.raises(ValueError, match="upgrade ansys claim"):
        assert_tree_does_not_upgrade_claims(summary, tuple(nodes))
