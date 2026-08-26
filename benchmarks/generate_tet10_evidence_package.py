from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import shutil

import numpy as np
import scipy

from astermax.fea.evidence import stage_source_file, verify_analysis_evidence_manifest
from astermax.fea.evidence_tet10 import write_tet10_analysis_evidence_manifest
from astermax.fea.gmsh_bridge import (
    distribute_resultant_on_tri6,
    fixed_dofs_for_nodes,
    force_and_moment,
    mesh_step_tet10,
    unique_surface_nodes,
)
from astermax.fea.postprocess_tet10 import write_tet10_linear_static_vtu
from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet4 import IsotropicMaterial
from astermax.fea.viewer_tet10 import write_tet10_offline_viewer


def main() -> int:
    source_step = Path("tet10_cantilever.step")
    convergence_path = Path("tet10_convergence.json")
    if not source_step.is_file() or not convergence_path.is_file():
        raise RuntimeError("run benchmarks/tet10_convergence.py before generating the T10-C package")

    convergence = json.loads(convergence_path.read_text(encoding="utf-8"))
    decision = convergence.get("convergence_decision", {})
    if not bool(decision.get("converged", False)):
        raise RuntimeError("T10-C refuses to publish a converged package when the convergence gate is false")
    samples = convergence.get("samples", [])
    if not samples:
        raise RuntimeError("convergence evidence contains no mesh samples")
    final_mesh_size = float(samples[-1]["mesh_size_mm"])

    package = Path("astermax_tet10_evidence_package")
    if package.exists():
        shutil.rmtree(package)
    package.mkdir(parents=True)
    staged_step = stage_source_file(package, source_step, target_name="source_cantilever.step")
    staged_convergence = package / "tet10_convergence.json"
    shutil.copyfile(convergence_path, staged_convergence)

    mesh = mesh_step_tet10(staged_step, final_mesh_size)
    material = IsotropicMaterial(200000.0, 0.30)
    fixed_nodes = unique_surface_nodes(mesh.surface_triangles["X_MIN"])
    fixed_dofs = fixed_dofs_for_nodes(fixed_nodes)
    loads = distribute_resultant_on_tri6(
        mesh.nodes_mm,
        mesh.surface_triangles["X_MAX"],
        [0.0, -1000.0, 0.0],
    )
    applied_force, applied_moment = force_and_moment(mesh.nodes_mm, loads)
    result = solve_linear_static_tet10(
        mesh.nodes_mm,
        mesh.elements,
        material,
        loads,
        fixed_dofs,
    )
    reaction_force, reaction_moment = force_and_moment(mesh.nodes_mm, result.reactions_n)
    force_residual = float(np.linalg.norm(reaction_force + applied_force))
    moment_residual = float(np.linalg.norm(reaction_moment + applied_moment))

    vtu = package / "tet10_result.vtu"
    vtu_manifest = write_tet10_linear_static_vtu(
        vtu,
        mesh.nodes_mm,
        mesh.elements,
        result,
        converged_claim=True,
        industrial_validation_claim=False,
    )
    viewer = package / "tet10_viewer.html"
    viewer_manifest = write_tet10_offline_viewer(
        viewer,
        mesh.nodes_mm,
        mesh.elements,
        result,
        converged_claim=True,
        industrial_validation_claim=False,
    )

    analysis_definition = {
        "schema": "AsterMaxTet10AnalysisDefinitionV1",
        "analysis": "LINEAR_STATIC_3D",
        "units": {"length": "mm", "force": "N", "stress": "MPa"},
        "source_geometry": "STAGED_STEP",
        "dimensions_mm": list(mesh.dimensions_mm),
        "mesh": {
            "family": "TET10",
            "gmsh_volume_type": 11,
            "gmsh_surface_type": 9,
            "target_size_mm": final_mesh_size,
            "straight_sided_certification_boundary": True,
        },
        "material": {
            "model": "LINEAR_ISOTROPIC_ELASTIC",
            "young_modulus_mpa": 200000.0,
            "poisson_ratio": 0.30,
        },
        "boundary_conditions": [
            {"scope": "X_MIN", "type": "FIXED_ALL_TRANSLATIONS"},
        ],
        "loads": [
            {"scope": "X_MAX", "type": "UNIFORM_TRACTION_RESULTANT", "resultant_n": [0.0, -1000.0, 0.0]},
        ],
        "stress_policy": {
            "integration_points_per_tet10": 4,
            "nodal_smoothing": False,
            "viewer_cell_summaries": ["MAX_IP_VON_MISES", "MEAN_IP_VON_MISES"],
        },
        "convergence_policy": decision.get("policy", {}),
        "convergence_checks": decision.get("checks", {}),
        "force_residual_n": force_residual,
        "moment_residual_nmm": moment_residual,
    }
    analysis_file = package / "analysis_definition.json"
    analysis_file.write_text(json.dumps(analysis_definition, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    solver_identity = {
        "schema": "AsterMaxTet10SolverIdentityV1",
        "solver": "ASTERMAX_INTERNAL_LINEAR_STATIC_TET10_SPARSE",
        "assembly": "COO_TO_CSR",
        "linear_solver": "SCIPY_SPSOLVE",
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "gmsh": mesh.gmsh_version,
        "github_sha": os.environ.get("GITHUB_SHA"),
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
    }
    solver_file = package / "solver_identity.json"
    solver_file.write_text(json.dumps(solver_identity, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    evidence = write_tet10_analysis_evidence_manifest(
        package,
        nodes_mm=mesh.nodes_mm,
        elements=mesh.elements,
        analysis_definition=analysis_definition,
        solver_identity=solver_identity,
        convergence_evidence=convergence,
        artifacts=[
            (vtu.name, "TET10_VTU_RESULT"),
            (vtu.name + ".manifest.json", "TET10_VTU_MANIFEST"),
            (viewer.name, "TET10_OFFLINE_VIEWER"),
            (viewer.name + ".manifest.json", "TET10_VIEWER_MANIFEST"),
            (staged_convergence.name, "TET10_CONVERGENCE_EVIDENCE"),
            (analysis_file.name, "ANALYSIS_DEFINITION"),
            (solver_file.name, "SOLVER_IDENTITY"),
        ],
        source_path=staged_step,
        converged_claim=True,
        industrial_validation_claim=False,
        ansys_equivalence_claim=False,
    )
    verification = verify_analysis_evidence_manifest(package)
    if not verification["valid"]:
        raise RuntimeError(f"TET10 evidence self-verification failed: {verification}")

    print(f"package: {package.resolve()}")
    print(f"chain_sha256: {evidence.chain_sha256}")
    print(f"vtu_sha256: {vtu_manifest.vtu_sha256}")
    print(f"viewer_sha256: {viewer_manifest.html_sha256}")
    print(f"nodes: {mesh.nodes_mm.shape[0]}")
    print(f"tet10: {mesh.elements.shape[0]}")
    print(f"force_residual_N: {force_residual:.17g}")
    print(f"moment_residual_Nmm: {moment_residual:.17g}")
    print("converged_claim: true")
    print("industrial_validation_claim: false")
    print("ansys_equivalence_claim: false")
    print("stress_location: FOUR_TET10_INTEGRATION_POINTS_NO_NODAL_SMOOTHING")
    print("verification: VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
