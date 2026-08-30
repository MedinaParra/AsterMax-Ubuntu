from dataclasses import replace
from pathlib import Path

import pytest

from astermax.fea.native_adaptive_analysis import (
    NativeAdaptiveAnalysisError,
    execute_native_adaptive_analysis,
    prepare_native_adaptive_analysis,
    verify_native_adaptive_analysis_receipt,
    verify_native_adaptive_proposal_context,
)
from astermax.fea.portable_adaptive_results import open_portable_adaptive_results_package, verify_portable_adaptive_results_package
from astermax.fea.pre_solve_review import accept_model_preparation, prepare_model_for_review


def _write_box_step(tmp_path: Path) -> Path:
    gmsh = pytest.importorskip("gmsh")
    path = tmp_path / "native_adaptive_20mm.step"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c55x_native_adaptive")
        gmsh.model.occ.addBox(0, 0, 0, 20, 20, 20)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()
    return path


def _prepared(tmp_path: Path):
    step = _write_box_step(tmp_path)
    prepared = prepare_model_for_review(
        step,
        mesh_size_mm=8.0,
        young_modulus_mpa=200000.0,
        poisson_ratio=0.30,
        resultant_n=(1000.0, 250.0, 0.0),
        support_surface_keys=("X_MIN",),
        load_surface_keys=("X_MAX",),
    )
    return prepared, accept_model_preparation(prepared["review"])


def test_native_adaptive_desktop_pipeline_produces_verified_portable_results(tmp_path):
    prepared, acceptance = _prepared(tmp_path)
    context = prepare_native_adaptive_analysis(
        prepared,
        acceptance,
        approver="Harness Engineer",
        approved=True,
        refined_size_factor=0.5,
        maximum_relative_qoi_change=0.05,
        maximum_candidates=3,
        influence_radius_factor=1.5,
    )
    verify_native_adaptive_proposal_context(context)
    assert context.requires_refinement_approval is True
    assert context.candidate_count >= 1
    assert context.baseline_target_size_mm == 8.0
    assert context.refined_target_size_mm == 4.0

    bound = []
    receipt = execute_native_adaptive_analysis(
        prepared,
        acceptance,
        context,
        refinement_approver="Harness Engineer",
        refinement_approved=True,
        output_dir=tmp_path / "results",
        hotspot_binder=lambda view: bound.append(("hotspot", view.visualization_sha256)),
        stress_binder=lambda view: bound.append(("stress", view.comparison_sha256)),
    )
    verify_native_adaptive_analysis_receipt(receipt)
    assert receipt.status == "VERIFIED_ADAPTIVE_RESULTS_READY"
    assert receipt.baseline_mesh_sha256 != receipt.refined_mesh_sha256
    assert receipt.baseline_solve_evidence_sha256 != receipt.refined_solve_evidence_sha256
    assert receipt.qoi_status in {"PASS", "FAIL"}
    assert receipt.indicator_status in {"REDUCED", "NOT_REDUCED"}
    assert receipt.global_analysis_converged is False
    assert receipt.industrial_validation is False
    assert receipt.ansys_equivalence is False
    assert receipt.captured_to_active_project is False
    assert [name for name, _sha in bound] == ["hotspot", "stress"]

    package_path = Path(receipt.result_package_path)
    assert package_path.suffix == ".astermaxr"
    package = open_portable_adaptive_results_package(package_path)
    verify_portable_adaptive_results_package(package)
    assert package.package_sha256 == receipt.result_package_sha256
    assert package.source_step_sha256 == receipt.source_step_sha256


def test_native_adaptive_gates_and_context_tamper_fail_closed(tmp_path):
    prepared, acceptance = _prepared(tmp_path)
    with pytest.raises(NativeAdaptiveAnalysisError, match="NATIVE_ADAPTIVE_RUN_APPROVAL_REQUIRED"):
        prepare_native_adaptive_analysis(prepared, acceptance, approver="Harness Engineer", approved=False)

    context = prepare_native_adaptive_analysis(
        prepared,
        acceptance,
        approver="Harness Engineer",
        approved=True,
        maximum_candidates=2,
    )
    tampered = replace(context, candidate_count=context.candidate_count + 1)
    with pytest.raises(NativeAdaptiveAnalysisError, match="NATIVE_ADAPTIVE_CONTEXT_TAMPERED"):
        verify_native_adaptive_proposal_context(tampered)

    with pytest.raises(NativeAdaptiveAnalysisError, match="NATIVE_ADAPTIVE_REFINEMENT_APPROVAL_REQUIRED"):
        execute_native_adaptive_analysis(
            prepared,
            acceptance,
            context,
            refinement_approver="Harness Engineer",
            refinement_approved=False,
            output_dir=tmp_path / "denied",
            hotspot_binder=lambda _view: None,
            stress_binder=lambda _view: None,
        )


def test_shipping_app_exposes_adaptive_route_without_removing_single_solve():
    source = (Path(__file__).parents[1] / "src" / "astermax" / "app.py").read_text(encoding="utf-8")
    assert "2A · Accept exact preparation & Solve once" in source
    assert "2B · Adaptive Solve" in source
    assert "prepare_native_adaptive_analysis" in source
    assert "execute_native_adaptive_analysis" in source
    assert "_astermax_live_project_capture" in source
    assert "Gate 1" in source and "Gate 2" in source
    assert "maximum_relative_qoi_change=0.05" in source
    assert "ansys_equivalence" in source
