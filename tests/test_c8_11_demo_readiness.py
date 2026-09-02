from astermax.demo_readiness import build_professional_demo_readiness, demo_readiness_evidence
from astermax.windows_capability_outline import selection_contract


def test_static_structural_is_visible_but_not_a_verified_solver_claim():
    readiness = build_professional_demo_readiness()
    assert readiness.gui_available is True
    assert readiness.solver_claim_allowed is False
    assert readiness.result_workspace_available is False
    assert readiness.complete_verified_chain is False


def test_runtime_and_solve_remain_the_blocking_demo_stages():
    readiness = build_professional_demo_readiness()
    states = {stage.id: stage.ready for stage in readiness.stages}
    assert states == {
        "cad": True,
        "mesh": True,
        "bc": True,
        "runtime": False,
        "solve": False,
        "results": False,
    }


def test_gui_only_progress_cannot_unlock_results_or_solver_claims():
    readiness = build_professional_demo_readiness(
        cad_step_mm_ready=True,
        tet10_mesh_ready=True,
        boundary_conditions_ready=True,
        runtime_qualified=True,
        genuine_solve_verified=False,
    )
    assert readiness.solver_claim_allowed is False
    assert readiness.result_workspace_available is False
    assert readiness.complete_verified_chain is False


def test_schema_only_capability_stays_blocked_after_integration():
    modal = selection_contract("structural.modal")
    assert modal.enabled is False
    assert modal.action == "BLOCKED"


def test_evidence_never_invents_fea_or_ansys_equivalence():
    evidence = demo_readiness_evidence()
    assert evidence["fea_solve_executed"] is False
    assert evidence["numerical_verification"] is False
    assert evidence["results_verified"] is False
    assert evidence["industrial_validation"] is False
    assert evidence["ansys_equivalence"] is False
