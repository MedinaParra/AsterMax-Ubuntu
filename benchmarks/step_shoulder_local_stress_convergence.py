from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import numpy as np

from astermax.credibility import canonical_sha256
from astermax.fea.axisymmetric_shoulder import recognize_x_axis_shaft_shoulder
from astermax.fea.feature_adaptivity import mesh_step_tet10_around_shoulder
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.local_stress_convergence import (
    LocalStressConvergencePolicy,
    LocalStressRefinementSample,
    evaluate_local_stress_convergence,
)
from astermax.fea.shaft_end_faces import capture_x_axis_shaft_end_faces
from astermax.fea.shoulder_probe import sample_tet10_nearest_to_small_diameter_fillet_ring
from astermax.fea.singularity_diagnostic import RefinementFieldSample, diagnose_local_singularity
from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet4 import IsotropicMaterial
from astermax.fea.tet10_feature_sampling import sample_tet10_shoulder_neighborhood
from astermax.fea.tri6_traction import consistent_tri6_resultant_load, fixed_dofs_from_tri6


STEP = Path("step_shoulder_local_stress_convergence.step")
OUT = Path("step_shoulder_local_stress_convergence.json")
LOCAL_TARGETS_MM = (6.0, 5.0, 4.0, 3.0, 2.5)
GLOBAL_TARGET_MM = 8.0
TOTAL_FORCE_N = (1000.0, 0.0, 0.0)


def _write_fixture() -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("step_shoulder_local_stress_convergence")
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
        gmsh.write(str(STEP))
    finally:
        gmsh.finalize()


def _solve_sample(feature, ends, material, local_size: float):
    mesh = mesh_step_tet10_around_shoulder(
        STEP,
        feature,
        global_size_mm=GLOBAL_TARGET_MM,
        local_size_mm=local_size,
        padding_mm=5.0,
        face_selections=(ends.x_min, ends.x_max),
    )
    support_tri6 = mesh.surface_tri6_by_selection[ends.x_min.selection_id]
    load_tri6 = mesh.surface_tri6_by_selection[ends.x_max.selection_id]
    fixed_dofs = fixed_dofs_from_tri6(support_tri6)
    applied = consistent_tri6_resultant_load(mesh.nodes_mm, load_tri6, total_force_n=TOTAL_FORCE_N)
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
    probe = sample_tet10_nearest_to_small_diameter_fillet_ring(
        mesh,
        feature,
        integration_point_von_mises_mpa=result.integration_point_von_mises_mpa,
        sample_count=12,
        maximum_allowed_distance_mm=4.0,
    )
    local_vm = np.asarray([sample.von_mises_mpa for sample in neighborhood.samples], dtype=float)
    reaction_force = np.sum(result.reactions_n, axis=0)
    force_balance = reaction_force + np.asarray(applied.integrated_resultant_n)
    load_moment = np.sum(np.cross(mesh.nodes_mm, applied.loads_n), axis=0)
    reaction_moment = np.sum(np.cross(mesh.nodes_mm, result.reactions_n), axis=0)
    force_residual = float(np.linalg.norm(force_balance))
    moment_residual = float(np.linalg.norm(reaction_moment + load_moment))
    max_displacement = float(np.max(np.linalg.norm(result.displacement_mm, axis=1)))
    return mesh, applied, result, neighborhood, probe, LocalStressRefinementSample(
        local_target_size_mm=float(local_size),
        local_mean_max_corner_edge_mm=mesh.local_mean_max_corner_edge_mm,
        node_count=int(mesh.nodes_mm.shape[0]),
        tet10_count=int(mesh.elements.shape[0]),
        local_ip_peak_mpa=float(np.max(local_vm)),
        probe_ring_mean_mpa=probe.mean_von_mises_mpa,
        probe_ring_max_mpa=probe.max_von_mises_mpa,
        probe_ring_max_distance_mm=probe.maximum_sample_distance_mm,
        max_displacement_mm=max_displacement,
        force_residual_n=force_residual,
        moment_residual_nmm=moment_residual,
    )


def main() -> int:
    _write_fixture()
    feature = recognize_x_axis_shaft_shoulder(STEP, feature_id="REAL_CONVERGENCE_SHOULDER")
    ends = capture_x_axis_shaft_end_faces(STEP)
    material = IsotropicMaterial(young_modulus_mpa=200000.0, poisson_ratio=0.3)
    samples = []
    per_mesh = []
    for local_size in LOCAL_TARGETS_MM:
        mesh, applied, result, neighborhood, probe, sample = _solve_sample(feature, ends, material, local_size)
        if sample.force_residual_n > 1.0e-5 or sample.moment_residual_nmm > 1.0e-3:
            raise RuntimeError(
                f"equilibrium failed at local_size={local_size}: "
                f"force={sample.force_residual_n}, moment={sample.moment_residual_nmm}"
            )
        samples.append(sample)
        per_mesh.append(
            {
                "local_target_size_mm": local_size,
                "mesh_sha256": mesh.mesh_sha256,
                "nodes": int(mesh.nodes_mm.shape[0]),
                "tet10": int(mesh.elements.shape[0]),
                "local_mean_max_corner_edge_mm": mesh.local_mean_max_corner_edge_mm,
                "support_tri6": int(mesh.surface_tri6_by_selection[ends.x_min.selection_id].shape[0]),
                "load_tri6": int(mesh.surface_tri6_by_selection[ends.x_max.selection_id].shape[0]),
                "load_surface_mesh_area_mm2": applied.surface_area_mm2,
                "traction_resultant_relative_error": applied.relative_resultant_error,
                "force_residual_n": sample.force_residual_n,
                "moment_residual_nmm": sample.moment_residual_nmm,
                "max_displacement_mm": sample.max_displacement_mm,
                "shoulder_ip_count": neighborhood.sample_count,
                "shoulder_ip_peak_mpa": sample.local_ip_peak_mpa,
                "probe_ring_mean_mpa": probe.mean_von_mises_mpa,
                "probe_ring_max_mpa": probe.max_von_mises_mpa,
                "probe_ring_max_distance_mm": probe.maximum_sample_distance_mm,
                "probe_ring_mean_distance_mm": probe.mean_sample_distance_mm,
                "probe_sha256": probe.probe_sha256,
                "neighborhood_sha256": neighborhood.neighborhood_sha256,
            }
        )

    policy = LocalStressConvergencePolicy()
    decision = evaluate_local_stress_convergence(samples, policy=policy)
    singularity = diagnose_local_singularity(
        diagnostic_id="REAL_FINITE_FILLET_REFINEMENT",
        samples=tuple(
            RefinementFieldSample(
                mesh_size_mm=sample.local_target_size_mm,
                local_peak_mpa=sample.local_ip_peak_mpa,
                neighborhood_value_mpa=sample.probe_ring_mean_mpa,
            )
            for sample in samples
        ),
        peak_stability_tolerance=policy.max_last_peak_relative_change,
        neighborhood_stability_tolerance=policy.max_last_probe_mean_relative_change,
        minimum_peak_growth_factor_for_singularity=1.20,
    )
    convergence_claim = bool(decision.passed and singularity.classification == "LOCALLY_CONVERGED_FIELD")

    report = {
        "schema": "AsterMaxStepShoulderLocalStressConvergenceBenchmarkV1",
        "classification": "REAL_TET10_LOCAL_STRESS_REFINEMENT_STUDY_NOT_INDUSTRIAL_RESULT",
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
        "empirical_kt_validation_claim": False,
        "local_stress_convergence_claim": convergence_claim,
        "predeclared_mesh_sequence": {
            "global_target_mm": GLOBAL_TARGET_MM,
            "local_targets_mm": list(LOCAL_TARGETS_MM),
            "declared_before_result_evaluation": True,
        },
        "geometry": {
            "source_sha256": feature.source_sha256,
            "feature_sha256": feature.feature_sha256,
            "small_diameter_mm": 2.0 * feature.small_radius_mm,
            "large_diameter_mm": 2.0 * feature.large_radius_mm,
            "fillet_radius_mm": feature.fillet_radius_mm,
            "probe_ring_x_mm": probe.probe_ring_x_mm,
            "probe_ring_radius_mm": probe.probe_ring_radius_mm,
        },
        "boundary_identity": {
            "support_selection_sha256": ends.x_min.selection_sha256,
            "load_selection_sha256": ends.x_max.selection_sha256,
            "requested_force_n": list(TOTAL_FORCE_N),
        },
        "material": {
            "young_modulus_mpa": material.young_modulus_mpa,
            "poisson_ratio": material.poisson_ratio,
        },
        "policy": asdict(policy),
        "samples": per_mesh,
        "decision": {
            "passed": decision.passed,
            "classification": decision.classification,
            "checks": decision.checks,
            "metrics": decision.metrics,
            "decision_sha256": decision.decision_sha256,
        },
        "singularity_diagnostic": {
            "classification": singularity.classification,
            "peak_last_change": singularity.peak_last_change,
            "neighborhood_last_change": singularity.neighborhood_last_change,
            "peak_growth_factor": singularity.peak_growth_factor,
            "diagnostic_sha256": singularity.diagnostic_sha256,
        },
        "interpretation_boundary": (
            "This study measures local TET10 stress refinement on one generated finite-radius STEP shoulder with fixed physical geometry, persistent scopes and consistent resultant loading. "
            "A convergence claim is permitted only if the predeclared numerical policy passes and the independent peak-vs-probe diagnostic classifies the field as locally converged. "
            "No Shigley data, industrial validation or ANSYS equivalence is claimed."
        ),
    }
    report["benchmark_sha256"] = canonical_sha256(report)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    print(f"wrote {OUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
