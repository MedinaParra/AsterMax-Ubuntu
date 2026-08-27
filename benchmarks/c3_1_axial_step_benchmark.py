from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import tempfile

import numpy as np

from astermax.fea.axial_step_verification import AxialRefinementLevel, assess_axial_refinement
from astermax.fea.gmsh_bridge import (
    distribute_resultant_on_tri6,
    fixed_dofs_for_nodes,
    mesh_step_tet10,
    unique_surface_nodes,
)
from astermax.fea.neighborhood_verification import NeighborhoodVerificationPolicy, tet10_integration_point_positions, verify_scalar_stress_neighborhood
from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet4 import IsotropicMaterial


LENGTH_MM = 100.0
WIDTH_MM = 20.0
HEIGHT_MM = 20.0
AREA_MM2 = WIDTH_MM * HEIGHT_MM
TARGET_SIGMA_MPA = 100.0
RESULTANT_N = TARGET_SIGMA_MPA * AREA_MM2
MESH_SIZES_MM = (20.0, 14.0, 10.0)


def _write_box_step(path: Path) -> str:
    import gmsh  # type: ignore

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_c3_1_axial_step")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, LENGTH_MM, WIDTH_MM, HEIGHT_MM)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
        return str(getattr(gmsh, "__version__", "unknown"))
    finally:
        gmsh.finalize()


def _run_level(step_path: Path, mesh_size_mm: float) -> dict:
    mesh = mesh_step_tet10(step_path, mesh_size_mm)
    material = IsotropicMaterial(young_modulus_mpa=200000.0, poisson_ratio=0.3)
    support_nodes = unique_surface_nodes(mesh.surface_triangles["X_MIN"])
    fixed_dofs = fixed_dofs_for_nodes(support_nodes)
    loads = distribute_resultant_on_tri6(
        mesh.nodes_mm,
        mesh.surface_triangles["X_MAX"],
        (RESULTANT_N, 0.0, 0.0),
    )
    result = solve_linear_static_tet10(
        mesh.nodes_mm,
        mesh.elements,
        material,
        loads,
        fixed_dofs,
    )
    positions = tet10_integration_point_positions(mesh.nodes_mm, mesh.elements)
    report = verify_scalar_stress_neighborhood(
        positions,
        result.integration_point_stress_mpa[:, :, 0],
        TARGET_SIGMA_MPA,
        policy=NeighborhoodVerificationPolicy(
            axis=0,
            lower_fraction=0.20,
            upper_fraction=0.80,
            relative_error_limit=0.20,
        ),
    )
    level = AxialRefinementLevel(
        mesh_size_mm=float(mesh_size_mm),
        node_count=int(mesh.nodes_mm.shape[0]),
        tet10_count=int(mesh.elements.shape[0]),
        interior_sample_count=int(report.sample_count_in_neighborhood),
        mean_sigma_xx_mpa=float(report.mean_fea_mpa),
        rms_error_mpa=float(report.rms_error_mpa),
        maximum_relative_error=float(report.maximum_relative_error),
    )
    return {
        "level": asdict(level),
        "neighborhood_report": asdict(report),
        "support_node_count": int(support_nodes.size),
        "load_resultant_n": [float(v) for v in loads.sum(axis=0)],
        "dimensions_mm": [float(v) for v in mesh.dimensions_mm],
        "gmsh_version": mesh.gmsh_version,
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="astermax_c3_1_") as tmp:
        step_path = Path(tmp) / "axial_bar.step"
        step_writer_gmsh_version = _write_box_step(step_path)
        rows = [_run_level(step_path, size) for size in MESH_SIZES_MM]

    levels = [AxialRefinementLevel(**row["level"]) for row in rows]
    assessment = assess_axial_refinement(levels, TARGET_SIGMA_MPA)
    payload = {
        "schema": "AsterMaxC3_1AxialStepBenchmarkV1",
        "geometry": {
            "source": "GENERATED_STEP_BOX_REIMPORTED_THROUGH_PRODUCTION_GMSH_BRIDGE",
            "length_mm": LENGTH_MM,
            "width_mm": WIDTH_MM,
            "height_mm": HEIGHT_MM,
            "area_mm2": AREA_MM2,
            "units": "mm",
            "step_writer_gmsh_version": step_writer_gmsh_version,
        },
        "loading": {
            "support": "FULLY_FIXED_X_MIN",
            "load": "UNIFORM_TRI6_TRACTION_RESULTANT_ON_X_MAX",
            "resultant_n": RESULTANT_N,
            "analytical_sigma_xx_mpa": TARGET_SIGMA_MPA,
        },
        "comparison": {
            "quantity": "SIGMA_XX_AT_TET10_INTEGRATION_POINTS",
            "region": "20_TO_80_PERCENT_OF_INTEGRATION_POINT_X_SPAN",
            "nodal_stress_smoothing": False,
            "singular_peak_used": False,
        },
        "levels": rows,
        "assessment": asdict(assessment),
        "claims": {
            "stress_convergence_for_this_axial_fixture": assessment.stress_convergence_claim,
            "arbitrary_model_convergence": False,
            "industrial_validation": False,
            "ansys_equivalence": False,
        },
    }
    out = Path("c3_1_axial_step_benchmark.json")
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))

    if len(rows) != 3:
        raise RuntimeError("C3.1 requires exactly three measured refinement levels")
    if any(row["neighborhood_report"]["sample_count_in_neighborhood"] <= 0 for row in rows):
        raise RuntimeError("C3.1 interior neighborhood must contain integration-point samples at every level")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
