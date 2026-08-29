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
from astermax.fea.curved_shoulder_sector_probe import (
    curved_tet10_integration_point_coordinates,
    sample_curved_tet10_sectorized_small_diameter_fillet_ring,
)
from astermax.fea.curved_tet10_solver import (
    CURVED_TET10_VOLUME_QUADRATURE_ORDER,
    audit_curved_tet10_mesh_jacobians,
    solve_linear_static_curved_tet10,
)
from astermax.fea.feature_adaptivity import mesh_step_tet10_around_shoulder, shoulder_local_box
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.local_stress_convergence import (
    LocalStressConvergencePolicy,
    LocalStressRefinementSample,
    evaluate_local_stress_convergence,
)
from astermax.fea.persistent_geometry import capture_face_selection
from astermax.fea.shaft_end_faces import capture_x_axis_shaft_end_faces
from astermax.fea.singularity_diagnostic import RefinementFieldSample, diagnose_local_singularity
from astermax.fea.tet10_isoparametric import relative_matrix_difference, tet10_stiffness_isoparametric_reference
from astermax.fea.tet4 import IsotropicMaterial
from astermax.fea.tri6_isoparametric import compare_tri6_surface_quadrature, consistent_tri6_resultant_load_isoparametric
from astermax.fea.tri6_traction import fixed_dofs_from_tri6


STEP = Path("curved_tet10_local_stress_convergence.step")
OUT = Path("curved_tet10_local_stress_convergence.json")
GLOBAL_SIZE_MM = 8.0
LOCAL_TARGETS_MM = (2.0, 1.8, 1.6, 1.4)
PADDING_MM = 5.0
HIGH_ORDER_OPTIMIZE = 2
TOTAL_FORCE_N = np.asarray((1000.0, 0.0, 0.0), dtype=float)
SECTOR_COUNT = 12
PROBE_DISTANCE_LIMIT_MM = 2.0

# Frozen before C12 result observation. These are inherited from C10b/C11 or
# the already-established local-stress convergence policy.
MAX_ANALYTIC_FILLET_SURFACE_ERROR_MM = 0.02
MAX_ANALYTIC_FILLET_MIDSIDE_ERROR_MM = 2.0e-8
MAX_SURFACE_GL4_GL5_RELATIVE_AREA_DIFFERENCE = 1.0e-9
MAX_SURFACE_GL4_GL5_CENTROID_DELTA_MM = 1.0e-8
MAX_TRACTION_RESULTANT_RELATIVE_ERROR = 1.0e-12
MAX_VOLUME_GL4_GL5_RELATIVE_STIFFNESS_DIFFERENCE = 1.0e-4

# Exact analytical fixture geometry: R10 -> R15 shaft, 2 mm quarter-round at x=40.
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
        gmsh.model.add("curved_tet10_local_stress_convergence")
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
    theta = np.arctan2(dr, dx)
    theta = np.clip(theta, FIXTURE_THETA_MIN, FIXTURE_THETA_MAX)
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


def _blocked_report(base: dict[str, Any], reason: str) -> int:
    base["blocking_reason"] = reason
    base["passed"] = False
    base["local_stress_convergence_claim"] = False
    base["industrial_validation_claim"] = False
    base["ansys_equivalence_claim"] = False
    native = _json_native(base)
    native["benchmark_sha256"] = _canonical(native)
    OUT.write_text(json.dumps(native, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(native, indent=2, sort_keys=True, allow_nan=False))
    print(f"wrote BLOCKED C12 evidence {OUT.resolve()}")
    return 0


def main() -> int:
    _write_fixture()
    feature = recognize_x_axis_shaft_shoulder(STEP, feature_id="C12_CURVED_LOCAL_CONVERGENCE")
    ends = capture_x_axis_shaft_end_faces(STEP)
    transition = capture_face_selection(STEP, feature.transition_face_tag, "C12_TRANSITION_FILLET")
    material = IsotropicMaterial(young_modulus_mpa=200000.0, poisson_ratio=0.3)
    policy = LocalStressConvergencePolicy()

    report: dict[str, Any] = {
        "schema": "AsterMaxCurvedTet10LocalStressConvergenceBenchmarkV1",
        "classification": "CURVED_TET10_LOCAL_STRESS_CONVERGENCE_STUDY_NOT_INDUSTRIAL_RESULT",
        "source_sha256": feature.source_sha256,
        "feature_sha256": feature.feature_sha256,
        "c11_verified_solver_path": {
            "required": True,
            "curved_volume_quadrature": "DUFFY_GL4_64_IP_PER_TET10",
            "dense_jacobian_preflight": "DUFFY_GL5_125_POINTS_PER_TET10",
        },
        "predeclared_mesh_sequence": {
            "global_target_mm": GLOBAL_SIZE_MM,
            "local_targets_mm": list(LOCAL_TARGETS_MM),
            "high_order_optimize": HIGH_ORDER_OPTIMIZE,
            "second_order_linear": False,
            "declared_before_c12_result_observation": True,
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
                "theta_range_rad": [FIXTURE_THETA_MIN, FIXTURE_THETA_MAX],
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
            "require_gl5_positive_jacobians": True,
            "max_analytic_fillet_surface_error_mm": MAX_ANALYTIC_FILLET_SURFACE_ERROR_MM,
            "max_analytic_fillet_midside_error_mm": MAX_ANALYTIC_FILLET_MIDSIDE_ERROR_MM,
            "max_surface_gl4_gl5_relative_area_difference": MAX_SURFACE_GL4_GL5_RELATIVE_AREA_DIFFERENCE,
            "max_surface_gl4_gl5_centroid_delta_mm": MAX_SURFACE_GL4_GL5_CENTROID_DELTA_MM,
            "max_traction_resultant_relative_error": MAX_TRACTION_RESULTANT_RELATIVE_ERROR,
            "max_volume_gl4_gl5_relative_stiffness_difference": MAX_VOLUME_GL4_GL5_RELATIVE_STIFFNESS_DIFFERENCE,
        },
        "local_stress_policy": asdict(policy),
        "probe_policy": {
            "sector_count": SECTOR_COUNT,
            "maximum_allowed_distance_mm": PROBE_DISTANCE_LIMIT_MM,
            "measurement": "ONE_ACTUAL_DUFFY_GL4_INTEGRATION_POINT_PER_EQUAL_AZIMUTH_SECTOR",
            "nodal_smoothing": False,
            "surface_extrapolation": False,
        },
        "samples": [],
        "local_stress_convergence_claim": False,
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
        "empirical_kt_validation_claim": False,
    }

    refinement_samples: list[LocalStressRefinementSample] = []
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

        preflight = {
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
            "support_tri6": int(support_tri6.shape[0]),
            "load_tri6": int(load_tri6.shape[0]),
            "transition_tri6": int(transition_tri6.shape[0]),
            "local_mean_max_corner_edge_mm": mesh.local_mean_max_corner_edge_mm,
            "maximum_element_midside_offset_from_chord_midpoint_mm": float(np.max(offsets)),
            "preflight": {
                "checks": preflight,
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
                    "sample_count": int(sampled_surface_error.size),
                    "midside_node_count": int(midside_error.size),
                },
                "load_surface_gl4_vs_gl5": {
                    "area_gl4_mm2": surface_quad.area_a_mm2,
                    "area_gl5_mm2": surface_quad.area_b_mm2,
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
        if not all(preflight.values()):
            return _blocked_report(report, f"C12_MESH_PREFLIGHT_FAILED_AT_LOCAL_{local_size:g}_MM")

        applied = consistent_tri6_resultant_load_isoparametric(
            mesh.nodes_mm,
            load_tri6,
            total_force_n=TOTAL_FORCE_N,
            quadrature_order=4,
        )
        traction_ok = bool(applied.relative_resultant_error <= MAX_TRACTION_RESULTANT_RELATIVE_ERROR)
        sample_report["preflight"]["checks"]["traction_resultant_error_within_limit"] = traction_ok
        sample_report["traction"] = {
            "integrated_resultant_n": list(applied.integrated_resultant_n),
            "relative_resultant_error": applied.relative_resultant_error,
            "surface_area_mm2": applied.surface_area_mm2,
            "quadrature_order": applied.quadrature_order,
        }
        if not traction_ok:
            return _blocked_report(report, f"C12_TRACTION_PREFLIGHT_FAILED_AT_LOCAL_{local_size:g}_MM")

        fixed_dofs = fixed_dofs_from_tri6(support_tri6)
        result = solve_linear_static_curved_tet10(
            mesh.nodes_mm,
            mesh.elements,
            material,
            applied.loads_n,
            fixed_dofs,
        )
        sample_report["solver_executed"] = True

        ip_coords = curved_tet10_integration_point_coordinates(
            mesh.nodes_mm,
            mesh.elements,
            result.integration_point_natural_coordinates,
        )
        box = np.asarray(shoulder_local_box(feature, padding_mm=2.0), dtype=float)
        local_mask = np.all((ip_coords >= box[:3]) & (ip_coords <= box[3:]), axis=2)
        if not np.any(local_mask):
            raise RuntimeError(f"no curved integration points in shoulder neighborhood at local {local_size}")
        local_values = result.integration_point_von_mises_mpa[local_mask]
        if not np.all(np.isfinite(local_values)):
            raise RuntimeError("non-finite local curved stress samples")

        probe = sample_curved_tet10_sectorized_small_diameter_fillet_ring(
            mesh,
            feature,
            integration_point_natural_coordinates=result.integration_point_natural_coordinates,
            integration_point_von_mises_mpa=result.integration_point_von_mises_mpa,
            sector_count=SECTOR_COUNT,
            maximum_allowed_distance_mm=PROBE_DISTANCE_LIMIT_MM,
        )
        if probe.covered_sector_count != SECTOR_COUNT or probe.angular_coverage_fraction != 1.0:
            raise RuntimeError("curved sector probe did not achieve full angular coverage")

        reaction_force = np.sum(result.reactions_n, axis=0)
        force_balance = reaction_force + np.asarray(applied.integrated_resultant_n, dtype=float)
        load_moment = np.sum(np.cross(mesh.nodes_mm, applied.loads_n), axis=0)
        reaction_moment = np.sum(np.cross(mesh.nodes_mm, result.reactions_n), axis=0)
        force_residual = float(np.linalg.norm(force_balance))
        moment_residual = float(np.linalg.norm(reaction_moment + load_moment))
        max_displacement = float(np.max(np.linalg.norm(result.displacement_mm, axis=1)))

        refinement = LocalStressRefinementSample(
            local_target_size_mm=float(local_size),
            local_mean_max_corner_edge_mm=float(mesh.local_mean_max_corner_edge_mm),
            node_count=int(mesh.nodes_mm.shape[0]),
            tet10_count=int(mesh.elements.shape[0]),
            local_ip_peak_mpa=float(np.max(local_values)),
            probe_ring_mean_mpa=probe.mean_von_mises_mpa,
            probe_ring_max_mpa=probe.max_von_mises_mpa,
            probe_ring_max_distance_mm=probe.maximum_sample_distance_mm,
            max_displacement_mm=max_displacement,
            force_residual_n=force_residual,
            moment_residual_nmm=moment_residual,
        )
        refinement_samples.append(refinement)
        sample_report["solution"] = {
            "volume_quadrature_order": result.volume_quadrature_order,
            "integration_points_per_element": int(result.integration_point_natural_coordinates.shape[0]),
            "minimum_production_det_jacobian": result.minimum_production_det_jacobian,
            "stiffness_nnz": result.stiffness_nnz,
            "max_displacement_mm": max_displacement,
            "local_ip_sample_count": int(local_values.size),
            "local_ip_peak_mpa": refinement.local_ip_peak_mpa,
            "probe_ring_mean_mpa": probe.mean_von_mises_mpa,
            "probe_ring_max_mpa": probe.max_von_mises_mpa,
            "probe_ring_max_distance_mm": probe.maximum_sample_distance_mm,
            "probe_ring_mean_distance_mm": probe.mean_sample_distance_mm,
            "probe_covered_sector_count": probe.covered_sector_count,
            "force_residual_n": force_residual,
            "moment_residual_nmm": moment_residual,
            "probe_sha256": probe.probe_sha256,
            "quadrature_natural_coordinates_sha256": probe.quadrature_natural_coordinates_sha256,
            "displacement_sha256": _sha_array(result.displacement_mm),
            "reaction_sha256": _sha_array(result.reactions_n),
            "ip_von_mises_sha256": _sha_array(result.integration_point_von_mises_mpa),
        }

    decision = evaluate_local_stress_convergence(refinement_samples, policy=policy)
    singularity = diagnose_local_singularity(
        diagnostic_id="C12_CURVED_FINITE_FILLET_SECTOR_PROBE_REFINEMENT",
        samples=tuple(
            RefinementFieldSample(
                mesh_size_mm=sample.local_target_size_mm,
                local_peak_mpa=sample.local_ip_peak_mpa,
                neighborhood_value_mpa=sample.probe_ring_mean_mpa,
            )
            for sample in refinement_samples
        ),
        peak_stability_tolerance=policy.max_last_peak_relative_change,
        neighborhood_stability_tolerance=policy.max_last_probe_mean_relative_change,
        minimum_peak_growth_factor_for_singularity=1.20,
    )
    convergence_claim = bool(decision.passed and singularity.classification == "LOCALLY_CONVERGED_FIELD")

    report["decision"] = {
        "passed": bool(decision.passed),
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
    report["local_stress_convergence_claim"] = convergence_claim
    report["passed"] = True
    report["interpretation_boundary"] = (
        "C12 measures numerical local-stress convergence only on the declared curved R10-to-R15, R2-fillet STEP verification fixture, "
        "using four predeclared HO2 meshes and one actual Duffy-GL4 integration point per equal azimuth sector. "
        "Workflow PASS means the study executed and emitted evidence; local_stress_convergence_claim is enabled only if the unchanged convergence policy passes and the singularity diagnostic classifies the field as LOCALLY_CONVERGED_FIELD. "
        "No empirical Kt, physical validation, industrial validation or ANSYS equivalence is established by this study."
    )
    native = _json_native(report)
    native["benchmark_sha256"] = _canonical(native)
    OUT.write_text(json.dumps(native, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(native, indent=2, sort_keys=True, allow_nan=False))
    print(f"wrote {OUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
