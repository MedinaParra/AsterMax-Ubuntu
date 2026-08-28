from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

from astermax.credibility import canonical_sha256
from astermax.fea.axisymmetric_shoulder import recognize_x_axis_shaft_shoulder
from astermax.fea.feature_adaptivity import mesh_step_tet10_around_shoulder
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.shaft_end_faces import capture_x_axis_shaft_end_faces
from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet4 import IsotropicMaterial
from astermax.fea.tet10_feature_sampling import sample_tet10_shoulder_neighborhood
from astermax.fea.tri6_traction import consistent_tri6_resultant_load, fixed_dofs_from_tri6


STEP = Path("step_shoulder_real_tet10_solve.step")
OUT = Path("step_shoulder_real_tet10_solve.json")


def _sha_array(values: np.ndarray, dtype: str) -> str:
    return hashlib.sha256(np.asarray(values, dtype=dtype).tobytes(order="C")).hexdigest()


def _write_fixture() -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("step_shoulder_real_tet10_solve")
        small = gmsh.model.occ.addCylinder(0.0, 0.0, 0.0, 40.0, 0.0, 0.0, 10.0)
        large = gmsh.model.occ.addCylinder(40.0, 0.0, 0.0, 40.0, 0.0, 0.0, 15.0)
        gmsh.model.occ.fuse([(3, small)], [(3, large)])
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        if len(volumes) != 1:
            raise RuntimeError(f"expected one fused shaft volume, got {volumes}")
        candidates = []
        for _, tag in gmsh.model.getEntities(1):
            box = tuple(float(v) for v in gmsh.model.getBoundingBox(1, int(tag)))
            x_mid = 0.5 * (box[0] + box[3])
            x_span = box[3] - box[0]
            radius_y = 0.5 * (box[4] - box[1])
            radius_z = 0.5 * (box[5] - box[2])
            if (
                abs(x_mid - 40.0) <= 1.0e-4
                and x_span <= 1.0e-4
                and abs(radius_y - 10.0) <= 1.0e-4
                and abs(radius_z - 10.0) <= 1.0e-4
            ):
                candidates.append(int(tag))
        if len(candidates) != 1:
            raise RuntimeError(f"expected one shoulder fillet edge, got {candidates}")
        gmsh.model.occ.fillet([int(volumes[0][1])], [candidates[0]], [2.0], removeVolume=True)
        gmsh.model.occ.synchronize()
        if len(gmsh.model.getEntities(3)) != 1:
            raise RuntimeError("fillet operation did not preserve one shaft solid")
        gmsh.write(str(STEP))
    finally:
        gmsh.finalize()


def main() -> int:
    _write_fixture()
    feature = recognize_x_axis_shaft_shoulder(STEP, feature_id="REAL_FEA_SHOULDER")
    ends = capture_x_axis_shaft_end_faces(STEP)
    mesh = mesh_step_tet10_around_shoulder(
        STEP,
        feature,
        global_size_mm=8.0,
        local_size_mm=4.0,
        padding_mm=5.0,
        face_selections=(ends.x_min, ends.x_max),
    )
    support_tri6 = mesh.surface_tri6_by_selection[ends.x_min.selection_id]
    load_tri6 = mesh.surface_tri6_by_selection[ends.x_max.selection_id]
    fixed_dofs = fixed_dofs_from_tri6(support_tri6)

    applied = consistent_tri6_resultant_load(
        mesh.nodes_mm,
        load_tri6,
        total_force_n=(1000.0, 0.0, 0.0),
    )
    material = IsotropicMaterial(young_modulus_mpa=200000.0, poisson_ratio=0.3)
    result = solve_linear_static_tet10(
        mesh.nodes_mm,
        mesh.elements,
        material,
        applied.loads_n,
        fixed_dofs,
    )

    neighborhood = sample_tet10_shoulder_neighborhood(
        mesh,
        feature,
        padding_mm=2.0,
        integration_point_von_mises_mpa=result.integration_point_von_mises_mpa,
    )
    vm = np.asarray([sample.von_mises_mpa for sample in neighborhood.samples], dtype=float)
    if vm.size == 0 or not np.all(np.isfinite(vm)):
        raise RuntimeError("real FEA shoulder neighborhood contains no finite stress values")

    reaction_force = np.sum(result.reactions_n, axis=0)
    force_balance = reaction_force + np.asarray(applied.integrated_resultant_n)
    load_moment = np.sum(np.cross(mesh.nodes_mm, applied.loads_n), axis=0)
    reaction_moment = np.sum(np.cross(mesh.nodes_mm, result.reactions_n), axis=0)
    moment_balance = reaction_moment + load_moment
    force_residual = float(np.linalg.norm(force_balance))
    moment_residual = float(np.linalg.norm(moment_balance))
    if force_residual > 1.0e-5:
        raise RuntimeError(f"global force equilibrium failed: {force_residual} N")
    if moment_residual > 1.0e-3:
        raise RuntimeError(f"global moment equilibrium failed: {moment_residual} Nmm")

    support_nodes = np.unique(support_tri6.reshape(-1))
    load_nodes = np.unique(load_tri6.reshape(-1))
    nominal_small = 1000.0 / (math.pi * feature.small_radius_mm**2)
    local_max = float(np.max(vm))
    max_displacement = float(np.max(np.linalg.norm(result.displacement_mm, axis=1)))
    result_identity = {
        "schema": "AsterMaxRealStepShoulderTet10ResultIdentityV1",
        "source_sha256": feature.source_sha256,
        "feature_sha256": feature.feature_sha256,
        "mesh_sha256": mesh.mesh_sha256,
        "support_selection_sha256": ends.x_min.selection_sha256,
        "load_selection_sha256": ends.x_max.selection_sha256,
        "displacement_sha256": _sha_array(result.displacement_mm, "<f8"),
        "reaction_sha256": _sha_array(result.reactions_n, "<f8"),
        "ip_stress_sha256": _sha_array(result.integration_point_stress_mpa, "<f8"),
        "ip_von_mises_sha256": _sha_array(result.integration_point_von_mises_mpa, "<f8"),
        "neighborhood_sha256": neighborhood.neighborhood_sha256,
    }
    result_sha = canonical_sha256(result_identity)

    report = {
        "schema": "AsterMaxStepShoulderRealTet10SolveBenchmarkV1",
        "classification": "REAL_TET10_FEA_VERIFICATION_FIXTURE_NOT_INDUSTRIAL_RESULT",
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
        "convergence_claim": False,
        "empirical_kt_validation_claim": False,
        "geometry": {
            "source_sha256": feature.source_sha256,
            "feature_sha256": feature.feature_sha256,
            "small_diameter_mm": 2.0 * feature.small_radius_mm,
            "large_diameter_mm": 2.0 * feature.large_radius_mm,
            "fillet_radius_mm": feature.fillet_radius_mm,
            "transition_x_mm": feature.transition_x_mm,
        },
        "mesh": {
            "mesh_sha256": mesh.mesh_sha256,
            "nodes": int(mesh.nodes_mm.shape[0]),
            "tet10": int(mesh.elements.shape[0]),
            "global_size_mm": mesh.global_size_mm,
            "local_size_mm": mesh.local_size_mm,
            "second_order_linear": mesh.second_order_linear,
            "support_tri6": int(support_tri6.shape[0]),
            "support_nodes": int(support_nodes.size),
            "load_tri6": int(load_tri6.shape[0]),
            "load_nodes": int(load_nodes.size),
        },
        "boundary_conditions": {
            "support_selection_sha256": ends.x_min.selection_sha256,
            "load_selection_sha256": ends.x_max.selection_sha256,
            "fixed_dof_count": int(fixed_dofs.size),
            "requested_force_n": list(applied.requested_resultant_n),
            "integrated_force_n": list(applied.integrated_resultant_n),
            "load_surface_mesh_area_mm2": applied.surface_area_mm2,
            "traction_resultant_relative_error": applied.relative_resultant_error,
        },
        "material": {
            "young_modulus_mpa": material.young_modulus_mpa,
            "poisson_ratio": material.poisson_ratio,
        },
        "equilibrium": {
            "reaction_force_n": [float(v) for v in reaction_force],
            "force_balance_vector_n": [float(v) for v in force_balance],
            "force_residual_norm_n": force_residual,
            "load_moment_about_origin_nmm": [float(v) for v in load_moment],
            "reaction_moment_about_origin_nmm": [float(v) for v in reaction_moment],
            "moment_balance_vector_nmm": [float(v) for v in moment_balance],
            "moment_residual_norm_nmm": moment_residual,
        },
        "result": {
            "result_sha256": result_sha,
            "max_displacement_mm": max_displacement,
            "global_ip_von_mises_max_mpa": float(np.max(result.integration_point_von_mises_mpa)),
            "shoulder_ip_sample_count": int(vm.size),
            "shoulder_ip_von_mises_max_mpa": local_max,
            "shoulder_ip_von_mises_mean_mpa": float(np.mean(vm)),
            "shoulder_ip_von_mises_p95_mpa": float(np.quantile(vm, 0.95)),
            "nominal_small_section_axial_stress_mpa": nominal_small,
            "local_ip_max_over_nominal_measurement_only": local_max / nominal_small,
            "stress_representation": neighborhood.stress_representation,
            "neighborhood_sha256": neighborhood.neighborhood_sha256,
            "array_hashes": result_identity,
        },
        "interpretation_boundary": (
            "This is a real AsterMax TET10 solve on a generated STEP verification fixture. The local/nominal stress ratio is a numerical measurement only, not a validated Kt. "
            "No Shigley values are used, no convergence claim is made from one mesh, and no industrial or ANSYS-equivalence claim is permitted."
        ),
    }
    report["benchmark_sha256"] = canonical_sha256(report)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    print(f"wrote {OUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
