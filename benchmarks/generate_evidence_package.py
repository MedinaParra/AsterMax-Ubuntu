from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import scipy

from astermax.fea.connected_scaling import build_structured_bar
from astermax.fea.evidence import verify_analysis_evidence_manifest, write_analysis_evidence_manifest
from astermax.fea.postprocess import write_linear_static_vtu
from astermax.fea.solver import solve_linear_static
from astermax.fea.tet4 import IsotropicMaterial
from astermax.fea.viewer import write_offline_viewer_html


if __name__ == "__main__":
    package = Path("astermax_evidence_package")
    package.mkdir(exist_ok=True)

    nx, ny, nz = 8, 2, 1
    nodes, elements, loads, fixed = build_structured_bar(nx, ny=ny, nz=nz)
    material = IsotropicMaterial(210000.0, 0.3)
    result = solve_linear_static(nodes, elements, material, loads, fixed)

    vtu_path = package / "result.vtu"
    html_path = package / "viewer.html"
    vtu_manifest = write_linear_static_vtu(vtu_path, nodes, elements, result)
    viewer_manifest = write_offline_viewer_html(html_path, nodes, elements, result)

    applied_force = loads.sum(axis=0)
    reaction_force = result.reactions_n.sum(axis=0)
    applied_moment = np.cross(nodes, loads).sum(axis=0)
    reaction_moment = np.cross(nodes, result.reactions_n).sum(axis=0)

    analysis_definition = {
        "fixture": {
            "kind": "CONNECTED_STRUCTURED_TET4_BAR",
            "dimensions_mm": [100.0, 20.0, 10.0],
            "mesh_divisions": [nx, ny, nz],
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
            {"type": "NODAL_DISTRIBUTED_TOTAL", "scope": "X_MAX", "vector_N": [0.0, -1000.0, 0.0]}
        ],
        "acceptance_evidence": {
            "force_residual_N": float(np.linalg.norm(applied_force + reaction_force)),
            "moment_residual_Nmm": float(np.linalg.norm(applied_moment + reaction_moment)),
            "converged_claim": False,
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
        nodes_mm=nodes,
        elements=elements,
        analysis_definition=analysis_definition,
        solver_identity=solver_identity,
        artifacts=[
            ("result.vtu", "FEA_RESULT_VTU"),
            ("result.vtu.manifest.json", "VTU_EVIDENCE_MANIFEST"),
            ("viewer.html", "OFFLINE_RESULT_VIEWER"),
            ("viewer.html.manifest.json", "VIEWER_EVIDENCE_MANIFEST"),
            ("analysis_definition.json", "ANALYSIS_DEFINITION"),
            ("solver_identity.json", "SOLVER_IDENTITY"),
        ],
    )
    verification = verify_analysis_evidence_manifest(package)
    if not verification["valid"]:
        raise RuntimeError(f"evidence package verification failed: {verification}")

    print(f"package: {package.resolve()}")
    print(f"chain_sha256: {manifest.chain_sha256}")
    print(f"vtu_sha256: {vtu_manifest.vtu_sha256}")
    print(f"viewer_sha256: {viewer_manifest.html_sha256}")
    print(f"force_residual_N: {analysis_definition['acceptance_evidence']['force_residual_N']:.17g}")
    print(f"moment_residual_Nmm: {analysis_definition['acceptance_evidence']['moment_residual_Nmm']:.17g}")
    print("verification: VALID")
