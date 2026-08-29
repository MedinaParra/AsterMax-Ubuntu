from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from astermax.credibility import canonical_sha256
from astermax.fea.axisymmetric_shoulder import recognize_x_axis_shaft_shoulder
from astermax.fea.curved_feature_geometry import interpolated_tri6_points
from astermax.fea.curved_neighborhood_integral import integrate_curved_tet10_fixed_tangency_neighborhood
from astermax.fea.curved_shoulder_sector_probe import curved_tet10_integration_point_coordinates
from astermax.fea.curved_tet10_solver import audit_curved_tet10_mesh_jacobians, solve_linear_static_curved_tet10
from astermax.fea.feature_adaptivity import mesh_step_tet10_around_shoulder, shoulder_local_box
from astermax.fea.fixed_neighborhood_convergence import (
    FixedNeighborhoodConvergencePolicy,
    FixedNeighborhoodRefinementSample,
    evaluate_fixed_neighborhood_convergence,
)
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.persistent_geometry import capture_face_selection
from astermax.fea.shaft_end_faces import capture_x_axis_shaft_end_faces
from astermax.fea.singularity_diagnostic import RefinementFieldSample, diagnose_local_singularity
from astermax.fea.tet10_isoparametric import relative_matrix_difference, tet10_stiffness_isoparametric_reference
from astermax.fea.tet4 import IsotropicMaterial
from astermax.fea.tri6_isoparametric import compare_tri6_surface_quadrature, consistent_tri6_resultant_load_isoparametric
from astermax.fea.tri6_traction import fixed_dofs_from_tri6


STEP = Path("curved_fixed_neighborhood_convergence.step")
OUT = Path("curved_fixed_neighborhood_convergence.json")
GLOBAL_SIZE_MM = 8.0
LOCAL_TARGETS_MM = (2.0, 1.8, 1.6, 1.4)
PADDING_MM = 5.0
LOCAL_PEAK_BOX_PADDING_MM = 2.0
HIGH_ORDER_OPTIMIZE = 2
TOTAL_FORCE_N = np.asarray((1000.0, 0.0, 0.0), dtype=float)
FIXED_NEIGHBORHOOD_RADIUS_MM = 0.5  # R/4; frozen in C12a before its result.

# Inherited unchanged preflight gates from C12/C11.
MAX_ANALYTIC_FILLET_SURFACE_ERROR_MM = 0.02
MAX_ANALYTIC_FILLET_MIDSIDE_ERROR_MM = 2.0e-8
MAX_SURFACE_GL4_GL5_RELATIVE_AREA_DIFFERENCE = 1.0e-9
MAX_SURFACE_GL4_GL5_CENTROID_DELTA_MM = 1.0e-8
MAX_TRACTION_RESULTANT_RELATIVE_ERROR = 1.0e-12
MAX_VOLUME_GL4_GL5_RELATIVE_STIFFNESS_DIFFERENCE = 1.0e-4

# Exact analytical fixture geometry: R10 -> R15 shaft, R2 quarter-round at x=40.
FIXTURE_FILLET_CENTER_X_MM = 38.0
FIXTURE_FILLET_CENTER_RHO_MM = 12.0
FIXTURE_FILLET_RADIUS_MM = 2.0
FIXTURE_THETA_MIN = -0.5 * math.pi
FIXTURE_THETA_MAX = 0.0


def _json_native(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _json_native(value.item())
    if isinstance(value, dict):
        return {str(key): _json_native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_native(item) for item in value]
    return value


def _canonical(value: Any) -> str:
    return canonical_sha256(_json_native(value))


def _sha_array(values: np.ndarray, dtype: str = "<f8") -> str:
    return hashlib.sha256(np.asarray(values, dtype=dtype).tobytes(order="C")).hexdigest()


def _write_fixture() -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("curved_fixed_neighborhood_convergence")
        small = gmsh.model.occ.addCylinder(0.0, 0.0, 0.0, 40.0, 0.0, 0.0, 10.0)
        large = gmsh.model.occ.addCylinder(40.0, 0.0, 0.0, 40.0, 0.0, 0.0, 15.0)
        gmsh.model.occ.fuse([(3, small)], [(3, large)])
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        candidates: list[int] = []
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
        if len(gmsh.model.getEntities(3)) != 1:
            raise RuntimeError("fillet operation did not preserve one shaft solid")
        gmsh.write(str(STEP))
    finally:
        gmsh.finalize()


def _analytic_quarter_torus_distances(points_mm: np.ndarray) -> np.ndarray:
    points = np.asarray(points_mm, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not np.all(np.isfinite(points)):
        raise ValueError("points_mm must be finite with shape (n,3)")
    rho = np.sqrt(points[:, 1] ** 2 + points[:, 2] ** 2)
    dx = points[:, 0] - FIXTURE_FILLET_CENTER_X_MM
    dr = rho - FIXTURE_FILLET_CENTER_RHO_MM
    theta = np.clip(np.arctan2(dr, dx), FIXTURE_THETA_MIN, FIXTURE_THETA_MAX)
    nearest_x = FIXTURE_FILLET_CENTER_X_MM + FIXTURE_FILLET_RADIUS_MM * np.cos(theta)
    nearest_rho = FIXTURE_FILLET_CENTER_RHO_MM + FIXTURE_FILLET_RADIUS_MM * np.sin(theta)
    return np.sqrt((points[:, 0] - nearest_x) ** 2 + (rho - nearest_rho) ** 2)


def _midside_offset(coords: np.ndarray) -> float:
    expected = np.asarray(
        [
            0.5 * (coords[0] + coords[1]),
            0.5 * (coords[1] + coords[2]),
            0.5 * (coords[2] + coords[0]),
            0.5 * (coords[0] + coords[3]),
            0.5 * (coords[2] + coords[3]),
            0.5 * (coords[1] + coords[3]),
        ]
    )
    return float(np.max(np.linalg.norm(coords[4:] - expected, axis=1)))


def _write_report(report: dict[str, Any]) -> None:
    native = _json_native(report)
    native["benchmark_sha256"] = _canonical(native)
    OUT.write_text(json.dumps(native, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(native, indent=2, sort_keys=True, allow_nan=False))
    print(f"wrote {OUT.resolve()}")


def _blocked_report(report: dict[str, Any], reason: str) -> int:
    report["blocking_reason"] = reason
    report["study_executed"] = False
    report["local_stress_convergence_claim"] = False
    report["industrial_validation_claim"] = False
    report["ansys_equivalence_claim"] = False
    _write_report(report)
    return 0


def main() -> int:
    _write_fixture()
    feature = recognize_x_axis_shaft_shoulder(STEP, feature_id="C12B_FIXED_NEIGHBORHOOD_CONVERGENCE")
    ends = capture_x_axis_shaft_end_faces(STEP)
    transition = capture_face_selection(STEP, feature.transition_face_tag, "C12B_TRANSITION_FILLET")
    material = IsotropicMaterial(young_modulus_mpa=200000.0, poisson_ratio=0.3)
    policy = FixedNeighborhoodConvergencePolicy()

    report: dict[str, Any] = {
        "schema": "AsterMaxCurvedFixedNeighborhoodConvergenceBenchmarkV1",
        "classification": "CURVED_TET10_FIXED_PHYSICAL_NEIGHBORHOOD_CONVERGENCE_STUDY_NOT_INDUSTRIAL_RESULT",
        "source_sha256": feature.source_sha256,
        "feature_sha256": feature.feature_sha256,
        "c12_preserved_result": "LOCAL_STRESS_NOT_CONVERGED",
        "c12a_measurement_audit_sha256": "cae382f12baaf8dc4e40720a7a8981de9a3af67d9f1951c9e7c5fcf448a1fe70",
        "c12a_classification": "NEAREST_IP_PROBE_UNSTABLE_FIXED_PHYSICAL_INTEGRAL_STABLE",
        "predeclared_mesh_sequence": {
            "global_target_mm": GLOBAL_SIZE_MM,
            "local_targets_mm": list(LOCAL_TARGETS_MM),
            "second_order_linear": False,
            "high_order_optimize": HIGH_ORDER_OPTIMIZE,
            "declared_before_c12b_result_observation": True,
            "no_post_result_mesh_insertion": True,
        },
        "measurement_contract": {
            "local_peak": "MAX_ACTUAL_DUFFY_GL4_IP_INSIDE_FIXED_SHOULDER_BOX",
            "neighborhood": "R_OVER_4_FIXED_PHYSICAL_TANGENCY_NEIGHBORHOOD_VOLUME_INTEGRAL",
            "fixed_neighborhood_radius_mm": FIXED_NEIGHBORHOOD_RADIUS_MM,
            "integration_weight": "DUFFY_WEIGHT_TIMES_DETJ",
            "mean_gate": policy.max_last_fixed_mean_relative_change,
            "rms_gate": policy.max_last_fixed_rms_relative_change,
            "sampled_volume_gate": policy.max_last_sampled_volume_relative_change,
            "nodal_recovery": False,
            "stress_smoothing": False,
            "surface_extrapolation": False,
        },
        "geometry": {
            "small_diameter_mm": 2.0 * feature.small_radius_mm,
            "large_diameter_mm": 2.0 * feature.large_radius_mm,
            "fillet_radius_mm": feature.fillet_radius_mm,
            "transition_x_mm": feature.transition_x_mm,
            "transition_selection_sha256": transition.selection_sha256,
            "analytic_fixture_witness": {
                "type": "QUARTER_TORUS_MERIDIONAL_ARC",
                "center_x_mm": FIXTURE_FILLET_CENTER_X_MM,
                "center_rho_mm": FIXTURE_FILLET_CENTER_RHO_MM,
                "radius_mm": FIXTURE_FILLET_RADIUS_MM,
            },
        },
        "boundary_identity": {
            "support_selection_sha256": ends.x_min.selection_sha256,
            "load_selection_sha256": ends.x_max.selection_sha256,
            "requested_force_n": [float(v) for v in TOTAL_FORCE_N],
        },
        "material": {
            "young_modulus_mpa": material.young_modulus_mpa,
            "poisson_ratio": material.poisson_ratio,
        },
        "preflight_policy": {
            "max_analytic_fillet_surface_error_mm": MAX_ANALYTIC_FILLET_SURFACE_ERROR_MM,
            "max_analytic_fillet_midside_error_mm": MAX_ANALYTIC_FILLET_MIDSIDE_ERROR_MM,
            "max_surface_gl4_gl5_relative_area_difference": MAX_SURFACE_GL4_GL5_RELATIVE_AREA_DIFFERENCE,
            "max_surface_gl4_gl5_centroid_delta_mm": MAX_SURFACE_GL4_GL5_CENTROID_DELTA_MM,
            "max_traction_resultant_relative_error": MAX_TRACTION_RESULTANT_RELATIVE_ERROR,
            "max_volume_gl4_gl5_relative_stiffness_difference": MAX_VOLUME_GL4_GL5_RELATIVE_STIFFNESS_DIFFERENCE,
        },
        "convergence_policy": asdict(policy),
        "samples": [],
        "study_executed": False,
        "local_stress_convergence_claim": False,
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
        "empirical_kt_validation_claim": False,
    }

    refinement_samples: list[FixedNeighborhoodRefinementSample] = []
    for local_size in LOCAL_TARGETS_MM:
        mesh = mesh_step_tet10_around_shoulder(
            STEP,
            feature,
            global_size_mm=GLOBAL_SIZE_MM,
            local_size_mm=local_size,
            padding_mm=PADDING_MM,
            face_selections=(ends.x_min, ends.x_max, transition),
            second_order_linear=False,
            high_order_optimize=HIGH_ORDER_OPTIMIZE,
        )
        support_tri6 = mesh.surface_tri6_by_selection[ends.x_min.selection_id]
        load_tri6 = mesh.surface_tri6_by_selection[ends.x_max.selection_id]
        transition_tri6 = mesh.surface_tri6_by_selection[transition.selection_id]

        jac = audit_curved_tet10_mesh_jacobians(mesh.nodes_mm, mesh.elements, quadrature_order=5)
        sampled_surface = interpolated_tri6_points(mesh.nodes_mm, transition_tri6)
        sampled_surface_error = _analytic_quarter_torus_distances(sampled_surface)
        transition_midside = np.unique(transition_tri6[:, 3:].reshape(-1))
        midside_error = _analytic_quarter_torus_distances(mesh.nodes_mm[transition_midside])
        surface_quad = compare_tri6_surface_quadrature(mesh.nodes_mm, load_tri6, order_a=4, order_b=5)

        offsets = np.asarray([_midside_offset(mesh.nodes_mm[conn]) for conn in mesh.elements], dtype=float)
        worst_index = int(np.argmax(offsets))
        worst_coords = mesh.nodes_mm[mesh.elements[worst_index]]
        k4 = tet10_stiffness_isoparametric_reference(worst_coords, material, quadrature_order=4)
        k5 = tet10_stiffness_isoparametric_reference(worst_coords, material, quadrature_order=5)
        volume_diff = float(relative_matrix_difference(k4, k5))

        preflight_checks = {
            "selected_meshing_contract": bool(
                mesh.second_order_linear is False
                and mesh.high_order_optimize == HIGH_ORDER_OPTIMIZE
                and mesh.local_size_mm == float(local_size)
                and mesh.global_size_mm == GLOBAL_SIZE_MM
            ),
            "all_tet10_jacobians_positive_at_gl5_125_points": bool(jac.all_positive),
            "analytic_fillet_surface_error_within_limit": bool(
                float(np.max(sampled_surface_error)) <= MAX_ANALYTIC_FILLET_SURFACE_ERROR_MM
            ),
            "analytic_fillet_midside_error_within_limit": bool(
                float(np.max(midside_error)) <= MAX_ANALYTIC_FILLET_MIDSIDE_ERROR_MM
            ),
            "load_surface_gl4_gl5_area_within_limit": bool(
                surface_quad.relative_area_difference <= MAX_SURFACE_GL4_GL5_RELATIVE_AREA_DIFFERENCE
            ),
            "load_surface_gl4_gl5_centroid_within_limit": bool(
                surface_quad.centroid_delta_mm <= MAX_SURFACE_GL4_GL5_CENTROID_DELTA_MM
            ),
            "volume_gl4_gl5_reference_stiffness_within_limit": bool(
                volume_diff <= MAX_VOLUME_GL4_GL5_RELATIVE_STIFFNESS_DIFFERENCE
            ),
        }

        sample_report: dict[str, Any] = {
            "local_target_size_mm": float(local_size),
            "mesh_sha256": mesh.mesh_sha256,
            "nodes": int(mesh.nodes_mm.shape[0]),
            "tet10": int(mesh.elements.shape[0]),
            "local_mean_max_corner_edge_mm": mesh.local_mean_max_corner_edge_mm,
            "support_tri6": int(support_tri6.shape[0]),
            "load_tri6": int(load_tri6.shape[0]),
            "transition_tri6": int(transition_tri6.shape[0]),
            "preflight": {
                "checks": preflight_checks,
                "jacobian_gl5": {
                    "points_per_element": jac.point_count_per_element,
                    "minimum_det_jacobian": jac.minimum_det_jacobian,
                    "maximum_det_jacobian": jac.maximum_det_jacobian,
                    "minimum_element_det_over_maximum_ratio": jac.minimum_element_det_over_maximum_ratio,
                    "invalid_element_count": jac.invalid_element_count,
                    "nonpositive_point_count": jac.nonpositive_point_count,
                },
                "analytic_fillet_geometry": {
                    "sampled_surface_max_error_mm": float(np.max(sampled_surface_error)),
                    "sampled_surface_mean_error_mm": float(np.mean(sampled_surface_error)),
                    "midside_max_error_mm": float(np.max(midside_error)),
                },
                "load_surface_gl4_vs_gl5": {
                    "relative_area_difference": surface_quad.relative_area_difference,
                    "centroid_delta_mm": surface_quad.centroid_delta_mm,
                },
                "worst_geometric_element_volume_gl4_vs_gl5": {
                    "element_index_runtime_only": worst_index,
                    "midside_offset_mm": float(offsets[worst_index]),
                    "relative_stiffness_difference": volume_diff,
                },
            },
            "solver_executed": False,
        }
        report["samples"].append(sample_report)
        if not all(preflight_checks.values()):
            return _blocked_report(report, f"C12B_PREFLIGHT_FAILED_AT_LOCAL_{local_size}")

        applied = consistent_tri6_resultant_load_isoparametric(
            mesh.nodes_mm,
            load_tri6,
            total_force_n=TOTAL_FORCE_N,
            quadrature_order=4,
        )
        traction_ok = bool(applied.relative_resultant_error <= MAX_TRACTION_RESULTANT_RELATIVE_ERROR)
        sample_report["preflight"]["checks"]["traction_resultant_error_within_limit"] = traction_ok
        sample_report["traction"] = {
            "surface_area_mm2": applied.surface_area_mm2,
            "relative_resultant_error": applied.relative_resultant_error,
            "integrated_resultant_n": list(applied.integrated_resultant_n),
        }
        if not traction_ok:
            return _blocked_report(report, f"C12B_TRACTION_GATE_FAILED_AT_LOCAL_{local_size}")

        result = solve_linear_static_curved_tet10(
            mesh.nodes_mm,
            mesh.elements,
            material,
            applied.loads_n,
            fixed_dofs_from_tri6(support_tri6),
        )
        sample_report["solver_executed"] = True

        reaction_force = np.sum(result.reactions_n, axis=0)
        applied_force = np.asarray(applied.integrated_resultant_n, dtype=float)
        force_residual = float(np.linalg.norm(reaction_force + applied_force))
        load_moment = np.sum(np.cross(mesh.nodes_mm, applied.loads_n), axis=0)
        reaction_moment = np.sum(np.cross(mesh.nodes_mm, result.reactions_n), axis=0)
        moment_residual = float(np.linalg.norm(reaction_moment + load_moment))
        max_displacement = float(np.max(np.linalg.norm(result.displacement_mm, axis=1)))

        ip_coords = curved_tet10_integration_point_coordinates(
            mesh.nodes_mm,
            mesh.elements,
            result.integration_point_natural_coordinates,
        )
        local_box = np.asarray(shoulder_local_box(feature, padding_mm=LOCAL_PEAK_BOX_PADDING_MM), dtype=float)
        inside = np.all((ip_coords >= local_box[:3]) & (ip_coords <= local_box[3:]), axis=2)
        local_values = result.integration_point_von_mises_mpa[inside]
        if local_values.size == 0 or not np.all(np.isfinite(local_values)):
            raise RuntimeError(f"C12b fixed shoulder box has no finite IP values at local {local_size}")
        local_peak = float(np.max(local_values))

        integral = integrate_curved_tet10_fixed_tangency_neighborhood(
            mesh,
            feature,
            integration_point_natural_coordinates=result.integration_point_natural_coordinates,
            integration_point_weights=result.integration_point_weights,
            integration_point_von_mises_mpa=result.integration_point_von_mises_mpa,
            maximum_meridional_distance_mm=FIXED_NEIGHBORHOOD_RADIUS_MM,
        )

        refinement = FixedNeighborhoodRefinementSample(
            local_target_size_mm=float(local_size),
            local_mean_max_corner_edge_mm=mesh.local_mean_max_corner_edge_mm,
            node_count=int(mesh.nodes_mm.shape[0]),
            tet10_count=int(mesh.elements.shape[0]),
            local_ip_peak_mpa=local_peak,
            fixed_neighborhood_mean_mpa=integral.weighted_mean_von_mises_mpa,
            fixed_neighborhood_rms_mpa=integral.weighted_rms_von_mises_mpa,
            sampled_physical_volume_mm3=integral.sampled_physical_volume_mm3,
            max_displacement_mm=max_displacement,
            force_residual_n=force_residual,
            moment_residual_nmm=moment_residual,
        )
        refinement_samples.append(refinement)

        sample_report["solution"] = {
            "integration_points_per_element": int(result.integration_point_natural_coordinates.shape[0]),
            "minimum_production_det_jacobian": result.minimum_production_det_jacobian,
            "stiffness_nnz": result.stiffness_nnz,
            "force_residual_n": force_residual,
            "moment_residual_nmm": moment_residual,
            "max_displacement_mm": max_displacement,
            "local_ip_sample_count": int(local_values.size),
            "local_ip_peak_mpa": local_peak,
            "displacement_sha256": _sha_array(result.displacement_mm),
            "reaction_sha256": _sha_array(result.reactions_n),
            "ip_von_mises_sha256": _sha_array(result.integration_point_von_mises_mpa),
        }
        sample_report["fixed_physical_neighborhood_integral"] = {
            "integral_sha256": integral.integral_sha256,
            "quadrature_sha256": integral.quadrature_sha256,
            "maximum_meridional_distance_mm": integral.maximum_meridional_distance_mm,
            "selected_integration_point_count": integral.selected_integration_point_count,
            "sampled_physical_volume_mm3": integral.sampled_physical_volume_mm3,
            "weighted_mean_von_mises_mpa": integral.weighted_mean_von_mises_mpa,
            "weighted_rms_von_mises_mpa": integral.weighted_rms_von_mises_mpa,
            "weighted_std_von_mises_mpa": integral.weighted_std_von_mises_mpa,
            "minimum_von_mises_mpa": integral.minimum_von_mises_mpa,
            "maximum_von_mises_mpa": integral.maximum_von_mises_mpa,
            "maximum_selected_distance_mm": integral.maximum_selected_distance_mm,
        }

    decision = evaluate_fixed_neighborhood_convergence(refinement_samples, policy=policy)
    singularity = diagnose_local_singularity(
        diagnostic_id="C12B_FIXED_PHYSICAL_NEIGHBORHOOD_REFINEMENT",
        samples=tuple(
            RefinementFieldSample(
                mesh_size_mm=sample.local_target_size_mm,
                local_peak_mpa=sample.local_ip_peak_mpa,
                neighborhood_value_mpa=sample.fixed_neighborhood_mean_mpa,
            )
            for sample in refinement_samples
        ),
        peak_stability_tolerance=policy.max_last_peak_relative_change,
        neighborhood_stability_tolerance=policy.max_last_fixed_mean_relative_change,
        minimum_peak_growth_factor_for_singularity=1.20,
    )
    claim = bool(decision.passed and singularity.classification == "LOCALLY_CONVERGED_FIELD")

    report["study_executed"] = True
    report["decision"] = {
        "passed": decision.passed,
        "classification": decision.classification,
        "checks": decision.checks,
        "metrics": decision.metrics,
        "decision_sha256": decision.decision_sha256,
    }
    report["singularity_diagnostic"] = {
        "classification": singularity.classification,
        "peak_last_change": singularity.peak_last_change,
        "neighborhood_last_change": singularity.neighborhood_last_change,
        "peak_growth_factor": singularity.peak_growth_factor,
        "peak_monotonic_non_decreasing": singularity.peak_monotonic_non_decreasing,
        "diagnostic_sha256": singularity.diagnostic_sha256,
    }
    report["local_stress_convergence_claim"] = claim
    report["interpretation_boundary"] = (
        "C12b is a new four-mesh numerical convergence study using the fixed physical R/4 neighborhood integral "
        "that was predeclared before C12a results and diagnosed there as more stable than nearest-IP sampling. "
        "C12 remains failed under its original operator. C12b can establish only numerical local-field convergence "
        "for this generated R10-to-R15, R2-fillet linear-elastic verification fixture. It does not establish empirical Kt, "
        "physical validation, industrial validation or ANSYS equivalence."
    )
    _write_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
