from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import tempfile

import gmsh  # type: ignore

from astermax.fea.axial_step_verification import AxialRefinementLevel, assess_axial_refinement
from astermax.fea.cad_axial_witness import derive_cad_axial_stress_witness
from astermax.fea.gmsh_bridge import distribute_resultant_on_tri6, fixed_dofs_for_nodes, mesh_step_tet10, unique_surface_nodes
from astermax.fea.neighborhood_verification import NeighborhoodVerificationPolicy, tet10_integration_point_positions, verify_scalar_stress_neighborhood
from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet4 import IsotropicMaterial


LENGTH_MM = 100.0
WIDTH_MM = 20.0
HEIGHT_MM = 20.0
RESULTANT_N = 40000.0
MESH_SIZES_MM = (20.0, 14.0, 10.0)


def _write_step(path: Path) -> str:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_c3_2_axial")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, LENGTH_MM, WIDTH_MM, HEIGHT_MM)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
        return str(getattr(gmsh, "__version__", "unknown"))
    finally:
        gmsh.finalize()


def _level(step: Path, mesh_size_mm: float, analytical_sigma_mpa: float) -> dict:
    mesh = mesh_step_tet10(step, mesh_size_mm)
    support_nodes = unique_surface_nodes(mesh.surface_triangles["X_MIN"])
    loads = distribute_resultant_on_tri6(mesh.nodes_mm, mesh.surface_triangles["X_MAX"], (RESULTANT_N, 0.0, 0.0))
    result = solve_linear_static_tet10(
        mesh.nodes_mm,
        mesh.elements,
        IsotropicMaterial(young_modulus_mpa=200000.0, poisson_ratio=0.3),
        loads,
        fixed_dofs_for_nodes(support_nodes),
    )
    positions = tet10_integration_point_positions(mesh.nodes_mm, mesh.elements)
    report = verify_scalar_stress_neighborhood(
        positions,
        result.integration_point_stress_mpa[:, :, 0],
        analytical_sigma_mpa,
        policy=NeighborhoodVerificationPolicy(axis=0, lower_fraction=0.20, upper_fraction=0.80, relative_error_limit=0.20),
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
        "load_resultant_n": [float(v) for v in loads.sum(axis=0)],
        "support_node_count": int(support_nodes.size),
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="astermax_c3_2_") as tmp:
        step = Path(tmp) / "axial_bar.step"
        gmsh_version = _write_step(step)
        witness, section = derive_cad_axial_stress_witness(step, RESULTANT_N, axis=0, end="MAX")
        rows = [_level(step, size, witness.analytical_sigma_mpa) for size in MESH_SIZES_MM]

    levels = [AxialRefinementLevel(**row["level"]) for row in rows]
    assessment = assess_axial_refinement(levels, witness.analytical_sigma_mpa)
    payload = {
        "schema": "AsterMaxC3_2CadDerivedAxialBenchmarkV1",
        "provenance": {
            "same_step_drives_meshing_and_analytical_reference": True,
            "source_sha256": witness.source_sha256,
            "selection_id": witness.selection_id,
            "selection_sha256": witness.selection_sha256,
            "section_sha256": witness.section_sha256,
            "section_method": section.method,
            "step_writer_gmsh_version": gmsh_version,
            "units": {"length": "mm", "force": "N", "stress": "MPa"},
        },
        "cad_analytical_witness": asdict(witness),
        "levels": rows,
        "assessment": asdict(assessment),
        "claims": {
            "cad_derived_reference": True,
            "stress_convergence_for_this_axial_fixture": assessment.stress_convergence_claim,
            "arbitrary_model_convergence": False,
            "industrial_validation": False,
            "ansys_equivalence": False,
        },
    }
    Path("c3_2_cad_derived_axial_benchmark.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))

    if abs(witness.area_mm2 - 400.0) > 1.0e-8:
        raise RuntimeError("C3.2 exact STEP section area witness is not 400 mm^2")
    if abs(witness.analytical_sigma_mpa - 100.0) > 1.0e-9:
        raise RuntimeError("C3.2 CAD-derived analytical stress is not 100 MPa")
    if not assessment.stress_convergence_claim:
        raise RuntimeError("C3.2 did not preserve the already demonstrated axial-fixture refinement claim")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
