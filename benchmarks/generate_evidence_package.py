from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path

import numpy as np
import scipy

from astermax.fea.benchmark import ConvergencePolicy, evaluate_convergence, run_cantilever_convergence
from astermax.fea.evidence import (
    sha256_file,
    stage_source_file,
    verify_analysis_evidence_manifest,
    write_analysis_evidence_manifest,
)
from astermax.fea.gmsh_bridge import (
    distribute_resultant_on_triangles,
    fixed_dofs_for_nodes,
    force_and_moment,
    mesh_step_tet4,
    unique_surface_nodes,
)
from astermax.fea.postprocess import write_linear_static_vtu
from astermax.fea.solver import solve_linear_static
from astermax.fea.tet4 import IsotropicMaterial
from astermax.fea.viewer import write_offline_viewer_html


def _write_proof_step(path: Path) -> None:
    """Create a real STEP file used only as a deterministic verification fixture."""
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_step_provenance_fixture")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, 100.0, 20.0, 10.0)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


if __name__ == "__main__":
    package = Path("astermax_evidence_package")
    package.mkdir(exist_ok=True)

    external_step = Path("astermax_proof_fixture.step")
    _write_proof_step(external_step)
    source_step = stage_source_file(package, external_step, target_name="source.step")

    mesh_size_mm = 15.0
    mesh = mesh_step_tet4(source_step, mesh_size_mm)
    material = IsotropicMaterial(200000.0, 0.30)
    fixed_nodes = unique_surface_nodes(mesh.surface_triangles["X_MIN"])
    fixed_dofs = fixed_dofs_for_nodes(fixed_nodes)
    loads = distribute_resultant_on_triangles(
        mesh.nodes_mm,
        mesh.surface_triangles["X_MAX"],
        [0.0, -1000.0, 0.0],
    )
    result = solve_linear_static(mesh.nodes_mm, mesh.elements, material, loads, fixed_dofs)

    policy = ConvergencePolicy(
        min_samples=3,
        max_final_tip_error_percent=10.0,
        max_last_refinement_change_percent=5.0,
        max_force_balance_norm_n=1.0e-5,
        max_moment_balance_norm_nmm=1.0e-3,
        require_nonincreasing_tip_error=True,
    )
    reference, samples = run_cantilever_convergence(source_step, (25.0, 20.0, 15.0))
    convergence = evaluate_convergence(samples, policy)

    vtu_path = package / "result.vtu"
    html_path = package / "viewer.html"
    vtu_manifest = write_linear_static_vtu(
        vtu_path,
        mesh.nodes_mm,
        mesh.elements,
        result,
        converged_claim=convergence.converged,
        industrial_validation_claim=False,
    )
    viewer_manifest = write_offline_viewer_html(
        html_path,
        mesh.nodes_mm,
        mesh.elements,
        result,
        converged_claim=convergence.converged,
        industrial_validation_claim=False,
    )

    applied_force, applied_moment = force_and_moment(mesh.nodes_mm, loads)
    reaction_force, reaction_moment = force_and_moment(mesh.nodes_mm, result.reactions_n)
    force_residual = float(np.linalg.norm(applied_force + reaction_force))
    moment_residual = float(np.linalg.norm(applied_moment + reaction_moment))

    convergence_evidence = {
        "classification": "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT",
        "analytical_reference": asdict(reference),
        "samples": [asdict(sample) for sample in samples],
        "decision": asdict(convergence),
    }
    (package / "convergence_evidence.json").write_text(
        json.dumps(convergence_evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
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
            "element": "TET4_FIRST_ORDER",
            "target_size_mm": mesh_size_mm,
            "node_count": int(mesh.nodes_mm.shape[0]),
            "tet4_count": int(mesh.elements.shape[0]),
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
            {"type": "UNIFORM_SURFACE_TRACTION_RESULTANT", "scope": "X_MAX", "vector_N": [0.0, -1000.0, 0.0]}
        ],
        "acceptance_evidence": {
            "force_residual_N": force_residual,
            "moment_residual_Nmm": moment_residual,
            "convergence": asdict(convergence),
            "industrial_validation_claim": False,
        },
    }
    solver_identity = {
        "product": "AsterMax PMV",
        "analysis": "LINEAR_STATIC_3D_TET4",
        "assembly": "COO_TO_CSR_ELIMINATE_EXPLICIT_ZEROS",
        "linear_solver": "scipy.sparse.linalg.spsolve",
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
        "gmsh_version": mesh.gmsh_version,
        "git_sha": os.getenv("GITHUB_SHA"),
        "github_run_id": os.getenv("GITHUB_RUN_ID"),
    }

    (package / "analysis_definition.json").write_text(
        json.dumps(analysis_definition, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (package / "solver_identity.json").write_text(
        json.dumps(solver_identity, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    manifest = write_analysis_evidence_manifest(
        package,
        nodes_mm=mesh.nodes_mm,
        elements=mesh.elements,
        analysis_definition=analysis_definition,
        solver_identity=solver_identity,
        artifacts=[
            ("result.vtu", "FEA_RESULT_VTU"),
            ("result.vtu.manifest.json", "VTU_EVIDENCE_MANIFEST"),
            ("viewer.html", "OFFLINE_RESULT_VIEWER"),
            ("viewer.html.manifest.json", "VIEWER_EVIDENCE_MANIFEST"),
            ("analysis_definition.json", "ANALYSIS_DEFINITION"),
            ("solver_identity.json", "SOLVER_IDENTITY"),
            ("convergence_evidence.json", "CONVERGENCE_EVIDENCE"),
        ],
        source_path=source_step,
        source_kind="STEP_CAD_VERIFICATION_FIXTURE",
        converged_claim=convergence.converged,
        industrial_validation_claim=False,
    )
    verification = verify_analysis_evidence_manifest(package)
    if not verification["valid"]:
        raise RuntimeError(f"evidence package verification failed: {verification}")
    if manifest.claims["converged"] != convergence.converged:
        raise RuntimeError("manifest convergence claim diverged from convergence gate")

    print(f"package: {package.resolve()}")
    print(f"step_sha256: {manifest.source['sha256']}")
    print(f"mesh_nodes: {manifest.mesh['nodes']}")
    print(f"mesh_tet4: {manifest.mesh['tet4']}")
    print(f"chain_sha256: {manifest.chain_sha256}")
    print(f"vtu_sha256: {vtu_manifest.vtu_sha256}")
    print(f"viewer_sha256: {viewer_manifest.html_sha256}")
    print(f"force_residual_N: {force_residual:.17g}")
    print(f"moment_residual_Nmm: {moment_residual:.17g}")
    print(f"converged_claim: {str(convergence.converged).lower()}")
    print(f"convergence_checks: {json.dumps(convergence.checks, sort_keys=True)}")
    print(f"convergence_metrics: {json.dumps(convergence.metrics, sort_keys=True)}")
    print("verification: VALID")
