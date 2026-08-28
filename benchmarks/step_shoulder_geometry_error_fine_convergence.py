from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import numpy as np

from astermax.credibility import canonical_sha256
from astermax.fea.axisymmetric_shoulder import recognize_x_axis_shaft_shoulder
from astermax.fea.feature_adaptivity import mesh_step_tet10_around_shoulder
from astermax.fea.feature_geometry_error import measure_straight_sided_shoulder_geometry_error
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.local_stress_convergence import (
    LocalStressConvergencePolicy,
    LocalStressRefinementSample,
    evaluate_local_stress_convergence,
)
from astermax.fea.shaft_end_faces import capture_x_axis_shaft_end_faces
from astermax.fea.shoulder_sector_probe import sample_tet10_sectorized_small_diameter_fillet_ring
from astermax.fea.singularity_diagnostic import RefinementFieldSample, diagnose_local_singularity
from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet4 import IsotropicMaterial
from astermax.fea.tet10_feature_sampling import sample_tet10_shoulder_neighborhood
from astermax.fea.tri6_traction import consistent_tri6_resultant_load, fixed_dofs_from_tri6


STEP = Path("step_shoulder_geometry_error_fine_convergence.step")
OUT = Path("step_shoulder_geometry_error_fine_convergence.json")
LOCAL_TARGETS_MM = (2.5, 2.0, 1.75, 1.5)
GLOBAL_TARGET_MM = 8.0
PADDING_MM = 5.0
TOTAL_FORCE_N = (1000.0, 0.0, 0.0)
SECTOR_COUNT = 12
PROBE_DISTANCE_LIMIT_MM = 4.0
MAX_GEOMETRY_ERROR_OVER_FILLET_RADIUS = 0.01


def _write_fixture() -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("step_shoulder_geometry_error_fine_convergence")
        small = gmsh.model.occ.addCylinder(0.0, 0.0, 0.0, 40.0, 0.0, 0.0, 10.0)
        large = gmsh.model.occ.addCylinder(40.0, 0.0, 0.0, 40.0, 0.0, 0.0, 15.0)
        gmsh.model.occ.fuse([(3, small)], [(3, large)])
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
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
        if len(volumes) != 1 or len(candidates) != 1:
            raise RuntimeError(f"fixture topology unexpected: volumes={volumes}, fillet_edges={candidates}")
        gmsh.model.occ.fillet([int(volumes[0][1])], [candidates[0]], [2.0], removeVolume=True)
        gmsh.model.occ.synchronize()
        gmsh.write(str(STEP))
    finally:
        gmsh.finalize()


def main() -> int:
    _write_fixture()
    feature = recognize_x_axis_shaft_shoulder(STEP, feature_id="REAL_FINE_GEOMETRY_SHOULDER")
    ends = capture_x_axis_shaft_end_faces(STEP)
    material = IsotropicMaterial(young_modulus_mpa=200000.0, poisson_ratio=0.3)
    samples = []
    per_mesh = []

    for local_size in LOCAL_TARGETS_MM:
        mesh = mesh_step_tet10_around_shoulder(
            STEP,
            feature,
            global_size_mm=GLOBAL_TARGET_MM,
            local_size_mm=local_size,
            padding_mm=PADDING_MM,
            face_selections=(ends.x_min, ends.x_max),
        )
        geometry = measure_straight_sided_shoulder_geometry_error(
            STEP,
            feature,
            global_size_mm=GLOBAL_TARGET_MM,
            local_size_mm=local_size,
            padding_mm=PADDING_MM,
        )
        if geometry.mesh_sha256 != mesh.mesh_sha256:
            raise RuntimeError(
                f"GEOMETRY_AUDIT_MESH_IDENTITY_MISMATCH:{local_size}:"
                f"{geometry.mesh_sha256}!={mesh.mesh_sha256}"
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
        probe = sample_tet10_sectorized_small_diameter_fillet_ring(
            mesh,
            feature,
            integration_point_von_mises_mpa=result.integration_point_von_mises_mpa,
            sector_count=SECTOR_COUNT,
            maximum_allowed_distance_mm=PROBE_DISTANCE_LIMIT_MM,
        )
        local_vm = np.asarray([s.von_mises_mpa for s in neighborhood.samples], dtype=float)
        reaction_force = np.sum(result.reactions_n, axis=0)
        force_balance = reaction_force + np.asarray(applied.integrated_resultant_n)
        load_moment = np.sum(np.cross(mesh.nodes_mm, applied.loads_n), axis=0)
        reaction_moment = np.sum(np.cross(mesh.nodes_mm, result.reactions_n), axis=0)
        force_residual = float(np.linalg.norm(force_balance))
        moment_residual = float(np.linalg.norm(reaction_moment + load_moment))
        max_displacement = float(np.max(np.linalg.norm(result.displacement_mm, axis=1)))

        sample = LocalStressRefinementSample(
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
        samples.append(sample)
        per_mesh.append(
            {
                "local_target_size_mm": local_size,
                "mesh_sha256": mesh.mesh_sha256,
                "nodes": int(mesh.nodes_mm.shape[0]),
                "tet10": int(mesh.elements.shape[0]),
                "local_mean_max_corner_edge_mm": mesh.local_mean_max_corner_edge_mm,
                "shoulder_ip_peak_mpa": sample.local_ip_peak_mpa,
                "probe_ring_mean_mpa": probe.mean_von_mises_mpa,
                "probe_ring_max_mpa": probe.max_von_mises_mpa,
                "probe_ring_max_distance_mm": probe.maximum_sample_distance_mm,
                "max_displacement_mm": max_displacement,
                "force_residual_n": force_residual,
                "moment_residual_nmm": moment_residual,
                "geometry_evidence_sha256": geometry.evidence_sha256,
                "transition_tri6_count": geometry.tri6_count,
                "corner_cad_deviation_max_mm": geometry.corner_nodes.maximum_mm,
                "midside_cad_deviation_max_mm": geometry.midside_nodes.maximum_mm,
                "midside_cad_deviation_mean_mm": geometry.midside_nodes.mean_mm,
                "midside_cad_deviation_rms_mm": geometry.midside_nodes.rms_mm,
                "max_midside_deviation_over_fillet_radius": geometry.max_midside_deviation_over_fillet_radius,
            }
        )

    policy = LocalStressConvergencePolicy()
    decision = evaluate_local_stress_convergence(samples, policy=policy)
    singularity = diagnose_local_singularity(
        diagnostic_id="REAL_FINITE_FILLET_FINE_REFINEMENT",
        samples=tuple(
            RefinementFieldSample(
                mesh_size_mm=s.local_target_size_mm,
                local_peak_mpa=s.local_ip_peak_mpa,
                neighborhood_value_mpa=s.probe_ring_mean_mpa,
            )
            for s in samples
        ),
        peak_stability_tolerance=policy.max_last_peak_relative_change,
        neighborhood_stability_tolerance=policy.max_last_probe_mean_relative_change,
        minimum_peak_growth_factor_for_singularity=1.20,
    )

    geometry_ratios = [float(row["max_midside_deviation_over_fillet_radius"]) for row in per_mesh]
    geometry_error_strictly_decreasing = all(b < a for a, b in zip(geometry_ratios, geometry_ratios[1:]))
    final_geometry_target_pass = geometry_ratios[-1] <= MAX_GEOMETRY_ERROR_OVER_FILLET_RADIUS
    geometry_claim = bool(geometry_error_strictly_decreasing and final_geometry_target_pass)
    local_stress_claim = bool(
        decision.passed
        and singularity.classification == "LOCALLY_CONVERGED_FIELD"
        and geometry_claim
    )

    report = {
        "schema": "AsterMaxStepShoulderGeometryErrorFineConvergenceBenchmarkV1",
        "classification": "REAL_TET10_FINE_STRESS_AND_GEOMETRY_VERIFICATION_STUDY_NOT_INDUSTRIAL_RESULT",
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
        "empirical_kt_validation_claim": False,
        "local_stress_convergence_claim": local_stress_claim,
        "straight_sided_geometry_claim": geometry_claim,
        "predeclared_mesh_sequence": {
            "global_target_mm": GLOBAL_TARGET_MM,
            "local_targets_mm": list(LOCAL_TARGETS_MM),
            "declared_before_result_evaluation": True,
        },
        "geometry_policy": {
            "name": "ASTERMAX_INTERNAL_VERIFICATION_TARGET_NOT_EXTERNAL_STANDARD",
            "max_final_midside_deviation_over_fillet_radius": MAX_GEOMETRY_ERROR_OVER_FILLET_RADIUS,
            "require_strictly_decreasing_error": True,
            "final_absolute_target_mm": MAX_GEOMETRY_ERROR_OVER_FILLET_RADIUS * feature.fillet_radius_mm,
        },
        "geometry_decision": {
            "passed": geometry_claim,
            "strictly_decreasing": geometry_error_strictly_decreasing,
            "final_target_pass": final_geometry_target_pass,
            "ratios": geometry_ratios,
            "final_ratio": geometry_ratios[-1],
            "final_max_midside_deviation_mm": per_mesh[-1]["midside_cad_deviation_max_mm"],
        },
        "stress_policy": asdict(policy),
        "stress_decision": {
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
        "geometry": {
            "source_sha256": feature.source_sha256,
            "feature_sha256": feature.feature_sha256,
            "small_diameter_mm": 2.0 * feature.small_radius_mm,
            "large_diameter_mm": 2.0 * feature.large_radius_mm,
            "fillet_radius_mm": feature.fillet_radius_mm,
        },
        "samples": per_mesh,
        "interpretation_boundary": (
            "C9 separately measures exact OCC CAD-to-straight-sided TRI6/TET10 boundary deviation and local stress convergence. "
            "The 1%-of-fillet-radius geometry target is an AsterMax internal verification target, not an external engineering standard. "
            "A local-stress claim requires both numerical convergence and this geometry target. No curved TET10, Shigley data, industrial validation or ANSYS equivalence is claimed."
        ),
    }
    report["benchmark_sha256"] = canonical_sha256(report)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    print(f"wrote {OUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
