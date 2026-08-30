from dataclasses import replace

import pytest

from astermax.fea.adaptive_execution_bundle import build_adaptive_execution_artifact_bundle
from astermax.fea.face_ownership import mesh_step_tet10_with_face_ownership
from astermax.fea.named_selections import capture_named_selection
from astermax.fea.one_click_adaptive_loop import approve_one_click_adaptive_run, prepare_one_click_adaptive_run
from astermax.fea.portable_adaptive_results import (
    PortableAdaptiveResultsError,
    bind_portable_adaptive_results,
    open_portable_adaptive_results_package,
    verify_portable_adaptive_results_package,
    write_portable_adaptive_results_package,
)
from astermax.fea.solution_driven_local_loop import (
    approve_solution_driven_local_proposal,
    execute_solution_driven_local_loop,
    prepare_solution_driven_local_proposal,
)


def _write_box_step(tmp_path):
    gmsh = pytest.importorskip("gmsh")
    path = tmp_path / "portable_results_20mm.step"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c55r_portable_results")
        gmsh.model.occ.addBox(0, 0, 0, 20, 20, 20)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()
    return path


def _real_bundle(tmp_path):
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
    loop, refined, refined_solved, refined_indicator, coarse_qoi, fine_qoi, qoi = execute_solution_driven_local_loop(
        step, support, load, run, run_approval, proposal, plan, approval, baseline, baseline_solved, baseline_indicator,
        output_msh_path=tmp_path / "portable_refined.msh", maximum_indicator_candidates=3, return_artifacts=True,
    )
    assert coarse_qoi.solve_evidence_sha256 == loop.baseline_solve_evidence_sha256
    assert fine_qoi.solve_evidence_sha256 == loop.refined_solve_evidence_sha256
    assert qoi.assessment_sha256 == loop.qoi_assessment_sha256
    return build_adaptive_execution_artifact_bundle(
        loop_evidence=loop, proposal=proposal, plan=plan,
        baseline_mesh=baseline, refined_mesh=refined,
        baseline_solved=baseline_solved, refined_solved=refined_solved,
        baseline_indicator=baseline_indicator, refined_indicator=refined_indicator,
        displacement_scale=1.0,
    )


def test_real_adaptive_package_reopens_and_binds_without_solver_or_gmsh(tmp_path, monkeypatch):
    bundle = _real_bundle(tmp_path)
    path = write_portable_adaptive_results_package(bundle, tmp_path / "adaptive_demo.astermaxr")

    def forbidden(*args, **kwargs):
        raise AssertionError("reopen must not invoke solver or gmsh")

    import astermax.fea.gmsh_bridge as gmsh_bridge
    import astermax.fea.solver as solver
    monkeypatch.setattr(gmsh_bridge, "_gmsh", forbidden)
    monkeypatch.setattr(solver, "solve_linear_static_tet10", forbidden)

    package = open_portable_adaptive_results_package(path)
    assert package.source_bundle_sha256 == bundle.bundle_sha256
    assert package.claims["reopened_without_solver"] is True
    assert package.claims["reopened_without_gmsh"] is True
    assert package.payload_arrays["baseline_displacement_mm"].flags.writeable is False
    assert package.payload_arrays["refined_ip_von_mises_mpa"].flags.writeable is False
    assert package.hotspot_view.visualization_sha256 == bundle.hotspot_visualization_sha256
    assert package.stress_view.comparison_sha256 == bundle.stress_comparison_sha256

    seen = []
    receipt = bind_portable_adaptive_results(
        package,
        hotspot_binder=lambda view: seen.append(view.visualization_sha256),
        stress_binder=lambda view: seen.append(view.comparison_sha256),
    )
    assert receipt.bound_tabs == ("Adaptive Hotspots", "Stress Compare")
    assert seen == [bundle.hotspot_visualization_sha256, bundle.stress_comparison_sha256]


def test_portable_package_detects_file_mutation(tmp_path):
    bundle = _real_bundle(tmp_path)
    path = write_portable_adaptive_results_package(bundle, tmp_path / "mutation.astermaxr")
    package = open_portable_adaptive_results_package(path)
    with path.open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(PortableAdaptiveResultsError, match="PACKAGE_FILE_CHANGED"):
        verify_portable_adaptive_results_package(package)


def test_portable_package_rejects_validation_overclaim(tmp_path):
    bundle = _real_bundle(tmp_path)
    package = open_portable_adaptive_results_package(
        write_portable_adaptive_results_package(bundle, tmp_path / "overclaim.astermaxr")
    )
    claims = dict(package.claims); claims["ansys_equivalence"] = True
    with pytest.raises(PortableAdaptiveResultsError, match="VALIDATION_OVERCLAIM"):
        verify_portable_adaptive_results_package(replace(package, claims=claims))
