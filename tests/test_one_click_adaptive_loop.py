from dataclasses import replace

import pytest

from astermax.fea.named_selections import capture_named_selection
from astermax.fea.one_click_adaptive_loop import (
    OneClickAdaptiveLoopError,
    approve_one_click_adaptive_run,
    execute_approved_one_click_adaptive_run,
    prepare_one_click_adaptive_run,
)
from astermax.fea.face_ownership import mesh_step_tet10_with_face_ownership


def _write_box_step(tmp_path):
    gmsh = pytest.importorskip("gmsh")
    path = tmp_path / "one_click_20mm.step"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c55k_one_click")
        gmsh.model.occ.addBox(0, 0, 0, 20, 20, 20)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()
    return path


def _selection_pair(step):
    inventory = mesh_step_tet10_with_face_ownership(step, 10.0)
    ordered = sorted(inventory.faces, key=lambda face: face.center_mm[0])
    support = capture_named_selection(step, [ordered[0].face_tag], "Fixed X-", "SUPPORT")
    load = capture_named_selection(step, [ordered[-1].face_tag], "Load X+", "LOAD")
    return support, load


def _run(step, support, load):
    return prepare_one_click_adaptive_run(
        step,
        support,
        load,
        baseline_target_size_mm=10.0,
        refined_target_size_mm=6.0,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(1000.0, 0.0, 0.0),
        maximum_relative_qoi_change=10.0,
    )


def test_approved_one_click_run_executes_real_two_solve_dashboard_chain(tmp_path):
    step = _write_box_step(tmp_path)
    support, load = _selection_pair(step)
    run = _run(step, support, load)
    approval = approve_one_click_adaptive_run(run, approver="Harness Engineer", approved=True)
    execution, session, dashboard, baseline, refined = execute_approved_one_click_adaptive_run(
        step, support, load, run, approval
    )
    assert run.requires_human_approval is True and run.changes_physics is False
    assert refined.elements.shape[0] > baseline.elements.shape[0]
    assert execution.baseline_mesh_sha256 != execution.refined_mesh_sha256
    assert execution.session_sha256 == session.session_sha256
    assert execution.dashboard_sha256 == dashboard.dashboard_sha256
    assert dashboard.status == "READY"
    assert len(dashboard.stages) == 9
    assert execution.qoi_status in {"PASS", "FAIL"}
    assert execution.qoi_relative_change >= 0.0
    assert execution.global_analysis_converged is False
    assert execution.industrial_validation is False
    assert execution.ansys_equivalence is False


def test_one_click_run_cannot_execute_without_human_approval(tmp_path):
    step = _write_box_step(tmp_path)
    support, load = _selection_pair(step)
    run = _run(step, support, load)
    denied = approve_one_click_adaptive_run(run, approver="Harness Engineer", approved=False)
    with pytest.raises(OneClickAdaptiveLoopError, match="HUMAN_APPROVAL_REQUIRED"):
        execute_approved_one_click_adaptive_run(step, support, load, run, denied)


def test_one_click_run_fails_closed_on_tampered_plan_or_stale_approval(tmp_path):
    step = _write_box_step(tmp_path)
    support, load = _selection_pair(step)
    run = _run(step, support, load)
    approval = approve_one_click_adaptive_run(run, approver="Harness Engineer", approved=True)
    tampered = replace(run, refined_target_size_mm=5.0)
    with pytest.raises(OneClickAdaptiveLoopError, match="RUN_TAMPERED"):
        execute_approved_one_click_adaptive_run(step, support, load, tampered, approval)
    stale = replace(approval, run_sha256="a" * 64)
    with pytest.raises(OneClickAdaptiveLoopError, match="APPROVAL_STALE"):
        execute_approved_one_click_adaptive_run(step, support, load, run, stale)


def test_prepare_rejects_non_refining_mesh_order(tmp_path):
    step = _write_box_step(tmp_path)
    support, load = _selection_pair(step)
    with pytest.raises(OneClickAdaptiveLoopError, match="REFINEMENT_ORDER"):
        prepare_one_click_adaptive_run(
            step, support, load,
            baseline_target_size_mm=6.0,
            refined_target_size_mm=10.0,
            young_modulus_mpa=200000.0,
            poisson_ratio=0.30,
            resultant_n=(1000.0, 0.0, 0.0),
            maximum_relative_qoi_change=0.05,
        )
