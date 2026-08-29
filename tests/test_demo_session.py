from __future__ import annotations

from copy import deepcopy

import pytest

from astermax.fea.demo_session import build_end_to_end_demo_session


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
SHA_F = "f" * 64


def _summary() -> dict:
    return {
        "source_step_sha256": SHA_A,
        "units": {"length": "mm", "force": "N", "stress": "MPa"},
        "scope_contract": {
            "support_binding_sha256": SHA_B,
            "load_binding_sha256": SHA_C,
            "route_sha256": SHA_D,
        },
        "preparation": {"schema": "controlled-preparation", "evidence_sha256": SHA_B},
        "mesh": {"family": "TET10", "target_size_mm": 5.0, "nodes": 10, "elements": 1},
        "solve_evidence": {"solve_evidence_sha256": SHA_E},
        "checks": {"force_residual_n": 1.0e-10, "moment_residual_nmm": 2.0e-9},
        "production_results": {"workspace_sha256": SHA_F, "solve_evidence_sha256": SHA_E},
        "claims": {"converged": False, "industrial_validation": False, "ansys_equivalence": False},
        "artifacts": {"vtu_sha256": SHA_B, "viewer_sha256": SHA_C},
    }


def _section_ui() -> dict:
    return {
        "schema": "AsterMaxNativeSectionContourUiV1",
        "status": "READY",
        "workspace_sha256": SHA_F,
        "solve_evidence_sha256": SHA_E,
        "contour_sha256": SHA_D,
        "ui_sha256": SHA_C,
        "field_name": "U_MAG",
        "field_unit": "mm",
    }


def test_complete_demo_session_is_ready_and_deterministic() -> None:
    a = build_end_to_end_demo_session(_summary(), _section_ui())
    b = build_end_to_end_demo_session(_summary(), _section_ui())
    assert a.status == "READY"
    assert a.stage_count == 8
    assert a.ready_stage_count == 8
    assert not a.blockers
    assert a.session_sha256 == b.session_sha256
    assert tuple(stage.name for stage in a.stages) == (
        "CAD_STEP_MM", "MODEL_PREPARATION", "BC_LOAD_BINDING", "MESH_TET10",
        "SPARSE_FEA_SOLVE", "PRODUCTION_RESULTS", "SECTION_CONTOUR_PROBE", "EVIDENCE_EXPORT",
    )


def test_stale_section_solve_fails_closed() -> None:
    ui = _section_ui(); ui["solve_evidence_sha256"] = SHA_A
    session = build_end_to_end_demo_session(_summary(), ui)
    assert session.status == "BLOCKED"
    assert session.ready_stage_count == 7
    assert "SECTION_CONTOUR_PROBE:SECTION_SOLVE_STALE" in session.blockers


def test_results_solve_mismatch_fails_closed() -> None:
    summary = _summary(); summary["production_results"]["solve_evidence_sha256"] = SHA_A
    session = build_end_to_end_demo_session(summary, _section_ui())
    assert session.status == "BLOCKED"
    assert "PRODUCTION_RESULTS:RESULTS_SOLVE_PROVENANCE_STALE" in session.blockers


def test_empty_mesh_is_blocked() -> None:
    summary = _summary(); summary["mesh"]["elements"] = 0
    session = build_end_to_end_demo_session(summary, _section_ui())
    assert session.status == "BLOCKED"
    assert "MESH_TET10:MESH_NONEMPTY_REQUIRED" in session.blockers


def test_nonfinite_residual_is_blocked() -> None:
    summary = _summary(); summary["checks"]["force_residual_n"] = float("inf")
    session = build_end_to_end_demo_session(summary, _section_ui())
    assert session.status == "BLOCKED"
    assert "SPARSE_FEA_SOLVE:FORCE_RESIDUAL_N_FINITE_REQUIRED" in session.blockers


def test_unit_contract_rejects_metre_drift() -> None:
    summary = _summary(); summary["units"]["length"] = "m"
    with pytest.raises(ValueError, match="DEMO_SESSION_UNIT_CONTRACT"):
        build_end_to_end_demo_session(summary, _section_ui())


def test_claim_boundary_rejects_ansys_equivalence() -> None:
    summary = _summary(); summary["claims"]["ansys_equivalence"] = True
    with pytest.raises(ValueError, match="DEMO_SESSION_CLAIM_BOUNDARY"):
        build_end_to_end_demo_session(summary, _section_ui())


def test_session_identity_changes_when_solve_changes() -> None:
    summary = _summary(); ui = _section_ui()
    a = build_end_to_end_demo_session(summary, ui)
    changed = deepcopy(summary)
    changed["solve_evidence"]["solve_evidence_sha256"] = SHA_A
    changed["production_results"]["solve_evidence_sha256"] = SHA_A
    changed_ui = deepcopy(ui); changed_ui["solve_evidence_sha256"] = SHA_A
    b = build_end_to_end_demo_session(changed, changed_ui)
    assert a.session_sha256 != b.session_sha256


def test_contract_is_readiness_evidence_not_physics_claim() -> None:
    session = build_end_to_end_demo_session(_summary(), _section_ui())
    text = (session.schema + " " + session.semantics).lower()
    assert "physics_revalidation" in text
    assert session.claims == {"converged": False, "industrial_validation": False, "ansys_equivalence": False}
