from __future__ import annotations

import json
import math
from pathlib import Path
import sys

from astermax.desktop import main as desktop_main
from astermax.face_picker import build_project_from_face_fingerprints, write_face_picker_html
from astermax.fea.selections import inspect_step_surfaces
from astermax.project_runner import run_project


def _write_fixture_step(path: Path) -> None:
    import gmsh

    initialized = False
    try:
        gmsh.initialize()
        initialized = True
        gmsh.model.add("astermax_exe_self_test")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, 100.0, 20.0, 10.0)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        if initialized:
            gmsh.finalize()


def _self_test(root: Path) -> int:
    root.mkdir(parents=True, exist_ok=True)
    step = root / "exe_self_test.step"
    picker_html = root / "exe_face_picker.html"
    project_file = root / "exe_self_test.astermax"
    results = root / "results"
    _write_fixture_step(step)

    picker = write_face_picker_html(step, picker_html, display_mesh_size_mm=20.0)
    surfaces = inspect_step_surfaces(step)
    end_faces = [sig for _, sig in surfaces if abs(sig.area_mm2 - 200.0) <= 1.0e-6]
    if len(end_faces) != 2:
        raise RuntimeError(f"EXE self-test expected two 200 mm2 end faces, found {len(end_faces)}")
    end_faces.sort(key=lambda sig: sig.centroid_mm)
    build_project_from_face_fingerprints(
        step,
        project_file,
        end_faces[0].fingerprint_sha256,
        end_faces[1].fingerprint_sha256,
        mesh_size_mm=20.0,
        resultant_n=(0.0, -1000.0, 0.0),
    )
    summary = run_project(project_file, results)

    force_residual = float(summary["checks"]["force_residual_n"])
    moment_residual = float(summary["checks"]["moment_residual_nmm"])
    sampled_jacobian = summary["tet10_sampled_jacobian"]
    reference_jacobian = summary["tet10_reference_jacobian"]
    adaptive_jacobian = summary["tet10_adaptive_jacobian"]
    geometry_scope = summary["tet10_geometry_scope"]
    mesh_quality = summary["mesh_quality"]
    quality_policy = mesh_quality["policy"]
    checks = {
        "finite_force_residual": math.isfinite(force_residual),
        "finite_moment_residual": math.isfinite(moment_residual),
        "force_balance": force_residual <= 1.0e-5,
        "moment_balance": moment_residual <= 1.0e-3,
        "picker_html_exists": picker_html.is_file(),
        "picker_faces_exposed": int(picker["faces"]) == 6,
        "project_exists": project_file.is_file(),
        "persistent_selection_mode": summary["selection_mode"] == "PERSISTENT_CAD_SURFACE_SIGNATURES",
        "named_support": summary["scope_contract"]["constraint"] == "SUPPORT",
        "named_load": summary["scope_contract"]["load"] == "LOAD",
        "support_tri6_present": summary["mesh"]["support_tri6"] > 0,
        "load_tri6_present": summary["mesh"]["load_tri6"] > 0,
        "tet10_sampled_jacobian_pass": sampled_jacobian["status"] == "PASS",
        "tet10_sampled_jacobian_zero_nonpositive": sampled_jacobian["nonpositive_sample_count"] == 0,
        "tet10_sampled_jacobian_all_nodes": sampled_jacobian["sample_count_per_element"] == 15,
        "tet10_sampled_jacobian_pre_reference": sampled_jacobian["gate_order"] == "BEFORE_DENSE_REFERENCE_ADAPTIVE_REFERENCE_STRAIGHT_SIDED_SCOPE_BC_LOAD_ASSEMBLY_AND_SOLVE",
        "tet10_sampled_jacobian_not_global_proof": sampled_jacobian["global_positivity_proof"] is False,
        "tet10_reference_jacobian_pass": reference_jacobian["status"] == "PASS",
        "tet10_reference_jacobian_zero_nonpositive": reference_jacobian["nonpositive_sample_count"] == 0,
        "tet10_reference_jacobian_dense": reference_jacobian["sample_count_per_element"] == 286,
        "tet10_reference_jacobian_pre_adaptive": reference_jacobian["gate_order"] == "AFTER_V1_BEFORE_ADAPTIVE_REFERENCE_STRAIGHT_SIDED_SCOPE_BC_LOAD_ASSEMBLY_AND_SOLVE",
        "tet10_reference_jacobian_not_global_proof": reference_jacobian["global_positivity_proof"] is False,
        "tet10_reference_known_v1_guard": reference_jacobian["known_v1_false_negative_guard"] is True,
        "tet10_reference_curved_solver_disabled": reference_jacobian["curved_tet10_solver_enabled"] is False,
        "tet10_adaptive_jacobian_pass": adaptive_jacobian["status"] == "PASS",
        "tet10_adaptive_jacobian_zero_nonpositive": adaptive_jacobian["nonpositive_sample_count"] == 0,
        "tet10_adaptive_jacobian_points_evaluated": adaptive_jacobian["evaluated_points"] > 0,
        "tet10_adaptive_jacobian_pre_scope": adaptive_jacobian["gate_order"] == "AFTER_V1_AND_DENSE_REFERENCE_BEFORE_STRAIGHT_SIDED_SCOPE_BC_LOAD_ASSEMBLY_AND_SOLVE",
        "tet10_adaptive_jacobian_not_global_proof": adaptive_jacobian["global_positivity_proof"] is False,
        "tet10_adaptive_validated_fixture_count": adaptive_jacobian["validated_against_dense_reference_fixture_count"] == 500,
        "tet10_adaptive_no_declared_v2_misses": adaptive_jacobian["dense_reference_fail_adaptive_pass_count"] == 0,
        "tet10_adaptive_curved_solver_disabled": adaptive_jacobian["curved_tet10_solver_enabled"] is False,
        "tet10_geometry_scope_pass": geometry_scope["status"] == "PASS",
        "tet10_geometry_scope_zero_outside": geometry_scope["non_straight_sided_elements"] == 0,
        "tet10_geometry_scope_preassembly": geometry_scope["gate_order"] == "AFTER_V1_DENSE_REFERENCE_AND_ADAPTIVE_REFERENCE_BEFORE_BC_LOAD_ASSEMBLY_AND_SOLVE",
        "curved_tet10_disabled": geometry_scope["curved_tet10_solver_enabled"] is False,
        "mesh_quality_not_fail": mesh_quality["status"] != "FAIL",
        "mesh_quality_policy_serialized": isinstance(quality_policy, dict) and len(quality_policy) >= 7,
        "mesh_inspector_policy_matches_gate": mesh_quality["inspector_policy_matches_gate"] is True,
        "mesh_inspector_policy_exact": mesh_quality["inspector_policy"] == quality_policy,
        "mesh_inspector_shared_classifier": mesh_quality["inspector_status_uses_shared_classifier"] is True,
        "mesh_inspector_exists": Path(summary["artifacts"]["mesh_inspector"]).is_file(),
        "converged_claim_false": summary["claims"]["converged"] is False,
        "industrial_validation_false": summary["claims"]["industrial_validation"] is False,
        "ansys_equivalence_false": summary["claims"]["ansys_equivalence"] is False,
        "curved_tet10_claim_false": summary["claims"]["curved_tet10"] is False,
        "global_jacobian_proof_claim_false": summary["claims"]["global_jacobian_positivity_proved"] is False,
        "viewer_exists": Path(summary["artifacts"]["viewer"]).is_file(),
        "vtu_exists": Path(summary["artifacts"]["vtu"]).is_file(),
        "summary_exists": Path(summary["artifacts"]["summary"]).is_file(),
    }
    passed = all(checks.values())
    report = {
        "schema": "AsterMaxWindowsExeSelfTestV6",
        "passed": passed,
        "checks": checks,
        "picker": picker,
        "mesh": summary["mesh"],
        "tet10_sampled_jacobian": sampled_jacobian,
        "tet10_reference_jacobian": reference_jacobian,
        "tet10_adaptive_jacobian": adaptive_jacobian,
        "tet10_geometry_scope": geometry_scope,
        "mesh_quality": mesh_quality,
        "force_residual_n": force_residual,
        "moment_residual_nmm": moment_residual,
        "result_class": "ASTERMAX_PROJECT_UNCONVERGED_NOT_INDUSTRIAL_RESULT",
        "desktop_entry": "PROJECT_CENTRIC_CAD_FACE_PICKER",
    }
    (root / "exe_self_test.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if passed else 2


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--self-test":
        target = Path(sys.argv[2] if len(sys.argv) >= 3 else "astermax_exe_self_test")
        return _self_test(target.resolve())
    return desktop_main()


if __name__ == "__main__":
    raise SystemExit(main())
