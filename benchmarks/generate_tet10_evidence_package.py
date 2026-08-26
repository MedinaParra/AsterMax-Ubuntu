from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path

import numpy as np
import scipy

from astermax.fea.benchmark import ConvergencePolicy, evaluate_convergence, run_cantilever_convergence_tet10
from astermax.fea.evidence import sha256_file, stage_source_file, verify_analysis_evidence_manifest
from astermax.fea.gmsh_bridge import (
    distribute_resultant_on_tri6,
    fixed_dofs_for_nodes,
    force_and_moment,
    mesh_step_tet10,
    unique_surface_nodes,
)
from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet10_evidence import write_tet10_analysis_evidence_manifest
from astermax.fea.tet10_postprocess import tet10_hotspot, write_tet10_linear_static_vtu
from astermax.fea.tet10_viewer import write_tet10_offline_viewer_html
from astermax.fea.tet4 import IsotropicMaterial


def _write_proof_step(path: Path) -> None:
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_tet10_evidence_fixture")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, 100.0, 20.0, 10.0)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def main() -> int:
    package = Path("astermax_tet10_evidence_package")
    package.mkdir(exist_ok=True)

    external_step = Path("astermax_tet10_proof_fixture.step")
    _write_proof_step(external_step)
    source_step = stage_source_file(package, external_step, target_name="source.step")

    mesh_size_mm = 10.0
    mesh = mesh_step_tet10(source_step, mesh_size_mm)
    material = IsotropicMaterial(200000.0, 0.30)
    fixed_nodes = unique_surface_nodes(mesh.surface_triangles["X_MIN"])
    fixed_dofs = fixed_dofs_for_nodes(fixed_nodes)
    loads = distribute_resultant_on_tri6(
        mesh.nodes_mm,
        mesh.surface_triangles["X_MAX"],
        [0.0, -1000.0, 0.0],
    )
    result = solve_linear_static_tet10(mesh.nodes_mm, mesh.elements, material, loads, fixed_dofs)

    policy = ConvergencePolicy(
        min_samples=3,
        max_final_tip_error_percent=10.0,
        max_last_refinement_change_percent=5.0,
        max_force_balance_norm_n=1.0e-5,
        max_moment_balance_norm_nmm=1.0e-3,
        require_nonincreasing_tip_error=True,
    )
    reference, samples = run_cantilever_convergence_tet10(source_step, (20.0, 15.0, 10.0, 8.0, 6.0))
    convergence = evaluate_convergence(samples, policy)
    if not convergence.converged:
        raise RuntimeError(f"TET10 evidence package requires a converged verification gate: {convergence}")

    vtu_path = package / "result_tet10.vtu"
    html_path = package / "viewer_tet10.html"
    vtu_manifest = write_tet10_linear_static_vtu(
        vtu_path,
        mesh.nodes_mm,
        mesh.elements,
        result,
        converged_claim=True,
        industrial_validation_claim=False,
    )
    viewer_manifest = write_tet10_offline_viewer_html(
        html_path,
        mesh.nodes_mm,
        mesh.elements,
        result,
        converged_claim=True,
        industrial_validation_claim=False,
    )

    applied_force, applied_moment = force_and_moment(mesh.nodes_mm, loads)
    reaction_force, reaction_moment = force_and_moment(mesh.nodes_mm, result.reactions_n)
    force_residual = float(np.linalg.norm(applied_force + reaction_force))
    moment_residual = float(np.linalg.norm(applied_moment + reaction_moment))
    hotspot = tet10_hotspot(mesh.nodes_mm, mesh.elements, result)
    if hotspot is None:
        raise RuntimeError("TET10 evidence package requires a finite stress hotspot")

    convergence_evidence = {
        "classification": "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT",
        "analytical_reference": asdict(reference),
        "analytical_reference_model": {
            "theory": "TIMOSHENKO_BEAM_BENDING_PLUS_SHEAR",
            "poisson_ratio": 0.30,
            "shear_correction_factor": 5.0 / 6.0,
            "euler_bernoulli_bending_tip_mm": -0.25,
            "timoshenko_shear_tip_mm": -0.0078,
            "total_tip_mm": -0.2578,
            "acceptance_thresholds_relaxed": False,
        },
        "samples": [asdict(sample) for sample in samples],
        "decision": asdict(convergence),
    }
    (package / "convergence_evidence.json").write_text(
        json.dumps(convergence_evidence, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (package / "hotspot.json").write_text(
        json.dumps(
            {
                "classification": "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT",
                "stress_location": "INTEGRATION_POINT",
                "nodal_stress_smoothing": False,
                "hotspot": hotspot,
            },
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )

    analysis_definition = {
        "source": {
            "kind": "STEP_CAD_VERIFICATION_FIXTURE",
            "units_contract": "MILLIMETRE",
            "expected_dimensions_mm": [100.0, 20.0, 10.0],
            "observed_dimensions_mm": list(mesh.dimensions_mm),
            "step_sha256": sha256_file(source_step),
        },
        "mesh": {
            "generator": "GMSH_OCC",
            "gmsh_version": mesh.gmsh_version,
            "element": "TET10_QUADRATIC_STRAIGHT_SIDED",
            "gmsh_volume_element_type": 11,
            "gmsh_surface_element_type": 9,
            "vtk_cell_type": 24,
            "node_order": "GMSH_TETRAHEDRON10",
            "target_size_mm": mesh_size_mm,
            "node_count": int(mesh.nodes_mm.shape[0]),
            "tet10_count": int(mesh.elements.shape[0]),
        },
        "material": {
            "model": "LINEAR_ISOTROPIC_ELASTIC",
            "young_modulus_MPa": material.young_modulus_mpa,
            "poisson_ratio": material.poisson_ratio,
        },
        "boundary_conditions": [
            {"type": "FIXED_SUPPORT", "scope": "X_MIN", "components": ["UX", "UY", "UZ"]}
        ],
        "loads": [
            {
                "type": "CONSISTENT_UNIFORM_TRI6_TRACTION_RESULTANT",
                "scope": "X_MAX",
                "vector_N": [0.0, -1000.0, 0.0],
            }
        ],
        "integration": {
            "volume_rule": "SYMMETRIC_TETRAHEDRON_4_POINT",
            "integration_points_per_element": 4,
            "geometry_scope": "STRAIGHT_SIDED_TET10_ONLY",
        },
        "result_fields": {
            "displacement_location": "NODE",
            "stress_location": "INTEGRATION_POINT",
            "von_mises_location": "INTEGRATION_POINT",
            "nodal_stress_smoothing": False,
            "viewer_cell_scalar": "MAX_RAW_INTEGRATION_POINT_VON_MISES",
        },
        "acceptance_evidence": {
            "force_residual_N": force_residual,
            "moment_residual_Nmm": moment_residual,
            "convergence": asdict(convergence),
            "industrial_validation_claim": False,
            "ansys_equivalence_claim": False,
        },
    }
    solver_identity = {
        "product": "AsterMax PMV",
        "analysis": "LINEAR_STATIC_3D_TET10",
        "assembly": "COO_TO_CSR_ELIMINATE_EXPLICIT_ZEROS",
        "linear_solver": "scipy.sparse.linalg.spsolve",
        "stress_recovery": "FOUR_RAW_INTEGRATION_POINTS_NO_NODAL_SMOOTHING",
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
        "gmsh_version": mesh.gmsh_version,
        "git_sha": os.getenv("GITHUB_SHA"),
        "github_run_id": os.getenv("GITHUB_RUN_ID"),
    }
    (package / "analysis_definition.json").write_text(
        json.dumps(analysis_definition, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (package / "solver_identity.json").write_text(
        json.dumps(solver_identity, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    manifest = write_tet10_analysis_evidence_manifest(
        package,
        nodes_mm=mesh.nodes_mm,
        elements=mesh.elements,
        analysis_definition=analysis_definition,
        solver_identity=solver_identity,
        artifacts=[
            ("result_tet10.vtu", "TET10_FEA_RESULT_VTU"),
            ("result_tet10.vtu.manifest.json", "TET10_VTU_EVIDENCE_MANIFEST"),
            ("viewer_tet10.html", "TET10_OFFLINE_RESULT_VIEWER"),
            ("viewer_tet10.html.manifest.json", "TET10_VIEWER_EVIDENCE_MANIFEST"),
            ("analysis_definition.json", "ANALYSIS_DEFINITION"),
            ("solver_identity.json", "SOLVER_IDENTITY"),
            ("convergence_evidence.json", "TET10_CONVERGENCE_EVIDENCE"),
            ("hotspot.json", "RAW_INTEGRATION_POINT_HOTSPOT"),
        ],
        source_path=source_step,
        source_kind="STEP_CAD_VERIFICATION_FIXTURE",
        converged_claim=True,
        industrial_validation_claim=False,
    )
    verification = verify_analysis_evidence_manifest(package)
    if not verification["valid"]:
        raise RuntimeError(f"TET10 evidence package verification failed: {verification}")
    if manifest.analysis_type != "LINEAR_STATIC_3D_TET10":
        raise RuntimeError("TET10 evidence manifest analysis type is inconsistent")
    if manifest.mesh["tet10"] != int(mesh.elements.shape[0]):
        raise RuntimeError("TET10 evidence manifest cell count is inconsistent")
    if manifest.claims["converged"] is not True:
        raise RuntimeError("TET10 evidence manifest must carry the passed convergence claim")
    if vtu_manifest.vtk_cell_type != 24 or vtu_manifest.nodal_stress_smoothing:
        raise RuntimeError("TET10 VTU provenance boundary is inconsistent")
    if viewer_manifest.nodal_stress_smoothing:
        raise RuntimeError("TET10 viewer must not claim nodal stress smoothing")

    print(f"package: {package.resolve()}")
    print(f"step_sha256: {manifest.source['sha256']}")
    print(f"mesh_nodes: {manifest.mesh['nodes']}")
    print(f"mesh_tet10: {manifest.mesh['tet10']}")
    print(f"chain_sha256: {manifest.chain_sha256}")
    print(f"vtu_sha256: {vtu_manifest.vtu_sha256}")
    print(f"viewer_sha256: {viewer_manifest.html_sha256}")
    print(f"hotspot_von_mises_MPa: {hotspot['von_mises_mpa']:.17g}")
    print(f"hotspot_element: {hotspot['element_index']}")
    print(f"hotspot_ip: {hotspot['integration_point_index']}")
    print(f"force_residual_N: {force_residual:.17g}")
    print(f"moment_residual_Nmm: {moment_residual:.17g}")
    print(f"converged_claim: {str(convergence.converged).lower()}")
    print("verification: VALID_TET10_EVIDENCE_CHAIN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
