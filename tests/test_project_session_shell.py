from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from astermax.fea.adaptive_execution_bundle import build_adaptive_execution_artifact_bundle
from astermax.fea.face_ownership import mesh_step_tet10_with_face_ownership
from astermax.fea.named_selections import capture_named_selection
from astermax.fea.one_click_adaptive_loop import approve_one_click_adaptive_run, prepare_one_click_adaptive_run
from astermax.fea.portable_adaptive_results import write_portable_adaptive_results_package
from astermax.fea.project_session_shell import (
    inspect_analysis_path,
    inspect_recent_analyses,
    load_recent_analyses,
    open_verified_project_session,
)
from astermax.fea.solution_driven_local_loop import (
    approve_solution_driven_local_proposal,
    execute_solution_driven_local_loop,
    prepare_solution_driven_local_proposal,
)


def _write_box_step(tmp_path):
    gmsh = pytest.importorskip("gmsh")
    path = tmp_path / "project_session_20mm.step"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c55s_project_session")
        gmsh.model.occ.addBox(0, 0, 0, 20, 20, 20)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()
    return path


def _real_package(tmp_path):
    step = _write_box_step(tmp_path)
    witness = mesh_step_tet10_with_face_ownership(step, 8.0)
    ordered = sorted(witness.faces, key=lambda face: face.center_mm[0])
    support = capture_named_selection(step, [ordered[0].face_tag], "Fixed X-", "SUPPORT")
    load = capture_named_selection(step, [ordered[-1].face_tag], "Load X+", "LOAD")
    run = prepare_one_click_adaptive_run(
        step, support, load, baseline_target_size_mm=8.0, refined_target_size_mm=4.0,
        young_modulus_mpa=200000.0, poisson_ratio=0.30,
        resultant_n=(1000.0, 250.0, 0.0), maximum_relative_qoi_change=10.0,
    )
    run_approval = approve_one_click_adaptive_run(run, approver="Harness Reviewer", approved=True)
    proposal, plan, baseline, baseline_solved, baseline_indicator = prepare_solution_driven_local_proposal(
        step, support, load, run, run_approval, maximum_candidates=3, influence_radius_factor=1.5,
    )
    approval = approve_solution_driven_local_proposal(proposal, plan, approver="Harness Reviewer", approved=True)
    loop, refined, refined_solved, refined_indicator, _coarse_qoi, _fine_qoi, _qoi = execute_solution_driven_local_loop(
        step, support, load, run, run_approval, proposal, plan, approval, baseline, baseline_solved, baseline_indicator,
        output_msh_path=tmp_path / "session_refined.msh", maximum_indicator_candidates=3, return_artifacts=True,
    )
    bundle = build_adaptive_execution_artifact_bundle(
        loop_evidence=loop, proposal=proposal, plan=plan,
        baseline_mesh=baseline, refined_mesh=refined,
        baseline_solved=baseline_solved, refined_solved=refined_solved,
        baseline_indicator=baseline_indicator, refined_indicator=refined_indicator,
        displacement_scale=1.0,
    )
    return write_portable_adaptive_results_package(bundle, tmp_path / "professional_demo.astermaxr")


def test_verified_project_session_restores_native_views_without_solver_or_gmsh(tmp_path, monkeypatch):
    path = _real_package(tmp_path)
    recent = tmp_path / "recent_analyses.json"

    def forbidden(*args, **kwargs):
        raise AssertionError("project-session reopen must not invoke solver or gmsh")

    import astermax.fea.gmsh_bridge as gmsh_bridge
    import astermax.fea.solver as solver
    monkeypatch.setattr(gmsh_bridge, "_gmsh", forbidden)
    monkeypatch.setattr(solver, "solve_linear_static_tet10", forbidden)

    bound = []
    session, package, receipt = open_verified_project_session(
        path,
        hotspot_binder=lambda view: bound.append(("hotspot", view.visualization_sha256)),
        stress_binder=lambda view: bound.append(("stress", view.comparison_sha256)),
        recent_store_path=recent,
        opened_at_utc="2026-08-30T17:30:00+00:00",
    )
    assert session.status == "VERIFIED"
    assert session.package_sha256 == package.package_sha256
    assert session.binding_receipt_sha256 == receipt.receipt_sha256
    assert session.bound_tabs == ("Adaptive Hotspots", "Stress Compare")
    assert session.claims["results_restored_without_solver"] is True
    assert session.claims["results_restored_without_gmsh"] is True
    assert session.claims["ansys_equivalence"] is False
    assert [name for name, _sha in bound] == ["hotspot", "stress"]

    entries = load_recent_analyses(recent)
    assert len(entries) == 1
    assert entries[0].package_sha256 == package.package_sha256
    inspections = inspect_recent_analyses(recent)
    assert inspections[0].status == "VERIFIED"


def test_recent_identity_reports_stale_for_different_valid_file_sha(tmp_path):
    path = _real_package(tmp_path)
    inspection = inspect_analysis_path(path, expected_file_sha256="0" * 64)
    assert inspection.status == "STALE"
    assert inspection.package_sha256 is not None


def test_project_shell_reports_tampered_and_missing_fail_closed(tmp_path):
    path = _real_package(tmp_path)
    with ZipFile(path, "r") as archive:
        manifest = archive.read("manifest.json")
        views = bytearray(archive.read("views.json"))
        payload = archive.read("results.npz")
    views[-1] = ord("!")
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", manifest)
        archive.writestr("views.json", bytes(views))
        archive.writestr("results.npz", payload)
    tampered = inspect_analysis_path(path)
    assert tampered.status == "TAMPERED"
    missing = inspect_analysis_path(tmp_path / "gone.astermaxr")
    assert missing.status == "MISSING"
