from dataclasses import replace

import pytest

from astermax.fea.local_adaptive_one_click import (
    LocalAdaptiveOneClickError,
    approve_local_adaptive_proposal,
    execute_approved_local_adaptive_cutover,
    prepare_local_adaptive_proposal,
)
from astermax.fea.named_selections import capture_named_selection
from astermax.fea.one_click_adaptive_loop import approve_one_click_adaptive_run, prepare_one_click_adaptive_run
from astermax.fea.persistent_geometry import list_face_signatures


def _write_box_step(tmp_path):
    gmsh = pytest.importorskip("gmsh")
    path = tmp_path / "local_adaptive_witness_20mm.step"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c55l_step")
        gmsh.model.occ.addBox(0, 0, 0, 20, 20, 20)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()
    return path


def _setup(tmp_path):
    step = _write_box_step(tmp_path)
    faces = list(list_face_signatures(step))
    ordered = sorted(faces, key=lambda item: item[1].center_mm[0])
    support = capture_named_selection(step, [ordered[0][0]], "Fixed X-", "SUPPORT")
    load = capture_named_selection(step, [ordered[-1][0]], "Load X+", "LOAD")
    run = prepare_one_click_adaptive_run(
        step,
        support,
        load,
        baseline_target_size_mm=10.0,
        refined_target_size_mm=5.0,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(1000.0, 0.0, 0.0),
        maximum_relative_qoi_change=10.0,
    )
    run_approval = approve_one_click_adaptive_run(run, approver="Harness Run Reviewer", approved=True)
    proposal, plan, baseline = prepare_local_adaptive_proposal(
        step,
        support,
        load,
        run,
        run_approval,
        maximum_candidates=4,
        influence_radius_factor=2.0,
    )
    local_approval = approve_local_adaptive_proposal(
        proposal,
        plan,
        approver="Harness Mesh Reviewer",
        approved=True,
    )
    return step, support, load, run, run_approval, proposal, plan, baseline, local_approval


def test_real_local_remesh_is_exactly_reimported_rebound_resolved_and_presented(tmp_path):
    step, support, load, run, run_approval, proposal, plan, baseline, local_approval = _setup(tmp_path)
    output = tmp_path / "approved_local_adaptive_tet10.msh"
    execution, session, dashboard, remesh_ev, import_ev, refined = execute_approved_local_adaptive_cutover(
        step,
        support,
        load,
        run,
        run_approval,
        proposal,
        plan,
        local_approval,
        baseline,
        output_msh_path=output,
    )
    assert output.is_file() and output.stat().st_size > 0
    assert remesh_ev.output_mesh_sha256 == import_ev.source_mesh_sha256
    assert import_ev.exact_mesh_artifact_consumed is True
    assert import_ev.ready_for_rebinding is True
    assert refined.ownership_sha256 != baseline.ownership_sha256
    assert refined.elements.shape[1] == 10
    assert execution.refinement_driver == "CROSSCHECKED_TET10_MEAN_RATIO_WORST_ELEMENT_LOCALIZATION"
    assert execution.refined_mesh_sha256 == refined.ownership_sha256
    assert execution.session_sha256 == session.session_sha256
    assert execution.dashboard_sha256 == dashboard.dashboard_sha256
    assert session.status == "READY"
    assert dashboard.status == "READY"
    assert execution.global_analysis_converged is False
    assert execution.industrial_validation is False
    assert execution.ansys_equivalence is False


def test_proposal_requires_second_human_approval_after_candidates_exist(tmp_path):
    step, support, load, run, run_approval, proposal, plan, baseline, _ = _setup(tmp_path)
    denied = approve_local_adaptive_proposal(proposal, plan, approver="Reviewer", approved=False)
    with pytest.raises(LocalAdaptiveOneClickError, match="REFINEMENT_APPROVAL_REQUIRED"):
        execute_approved_local_adaptive_cutover(
            step, support, load, run, run_approval, proposal, plan, denied, baseline,
            output_msh_path=tmp_path / "must_not_execute.msh",
        )


def test_stale_or_tampered_proposal_fails_closed(tmp_path):
    step, support, load, run, run_approval, proposal, plan, baseline, local_approval = _setup(tmp_path)
    tampered = replace(proposal, radius_mm=proposal.radius_mm * 1.1)
    with pytest.raises(LocalAdaptiveOneClickError, match="PROPOSAL_TAMPERED"):
        execute_approved_local_adaptive_cutover(
            step, support, load, run, run_approval, tampered, plan, local_approval, baseline,
            output_msh_path=tmp_path / "tampered.msh",
        )


def test_stale_baseline_identity_fails_closed(tmp_path):
    step, support, load, run, run_approval, proposal, plan, baseline, local_approval = _setup(tmp_path)
    stale = replace(baseline, ownership_sha256="f" * 64)
    with pytest.raises(LocalAdaptiveOneClickError, match="BASELINE_STALE"):
        execute_approved_local_adaptive_cutover(
            step, support, load, run, run_approval, proposal, plan, local_approval, stale,
            output_msh_path=tmp_path / "stale.msh",
        )
