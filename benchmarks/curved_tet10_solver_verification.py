from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

from astermax.credibility import canonical_sha256
from astermax.fea.axisymmetric_shoulder import recognize_x_axis_shaft_shoulder
from astermax.fea.curved_tet10_solver import (
    CURVED_TET10_VOLUME_QUADRATURE_ORDER,
    audit_curved_tet10_mesh_jacobians,
    solve_linear_static_curved_tet10,
)
from astermax.fea.feature_adaptivity import mesh_step_tet10_around_shoulder, shoulder_local_box
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.shaft_end_faces import capture_x_axis_shaft_end_faces
from astermax.fea.tet10 import tet10_shape_functions
from astermax.fea.tet10_isoparametric import (
    relative_matrix_difference,
    tet10_stiffness_isoparametric_reference,
)
from astermax.fea.tet4 import IsotropicMaterial
from astermax.fea.tri6_isoparametric import (
    compare_tri6_surface_quadrature,
    consistent_tri6_resultant_load_isoparametric,
)
from astermax.fea.tri6_traction import fixed_dofs_from_tri6


STEP = Path("curved_tet10_solver_verification.step")
OUT = Path("curved_tet10_solver_verification.json")
GLOBAL_SIZE_MM = 8.0
LOCAL_SIZE_MM = 2.0
PADDING_MM = 5.0
HIGH_ORDER_OPTIMIZE = 2
TOTAL_FORCE_N = np.asarray([1000.0, 0.0, 0.0])

# Frozen before C11 result observation.
MAX_SURFACE_GL4_GL5_RELATIVE_AREA_DIFFERENCE = 1.0e-9
MAX_SURFACE_GL4_GL5_CENTROID_DELTA_MM = 1.0e-8
MAX_TRACTION_RESULTANT_RELATIVE_ERROR = 1.0e-12
MAX_VOLUME_GL4_GL5_RELATIVE_STIFFNESS_DIFFERENCE = 1.0e-4
MAX_FORCE_RESIDUAL_N = 1.0e-5
MAX_MOMENT_RESIDUAL_NMM = 1.0e-3


def _sha_array(values: np.ndarray, dtype: str) -> str:
    return hashlib.sha256(np.asarray(values, dtype=dtype).tobytes(order="C")).hexdigest()


def _write_fixture() -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("curved_tet10_solver_verification")
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


def _write_blocked(report: dict) -> int:
    report["passed"] = False
    report["curved_tet10_solver_verification_claim"] = False
    report["local_stress_convergence_claim"] = False
    report["industrial_validation_claim"] = False
    report["ansys_equivalence_claim"] = False
    report["benchmark_sha256"] = canonical_sha256(report)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    print(f"wrote BLOCKED evidence {OUT.resolve()}")
    return 0


def main() -> int:
    _write_fixture()
    feature = recognize_x_axis_shaft_shoulder(STEP, feature_id="C11_CURVED_SOLVER_SHOULDER")
    ends = capture_x_axis_shaft_end_faces(STEP)
    mesh = mesh_step_tet10_around_shoulder(
        STEP,
        feature,
        global_size_mm=GLOBAL_SIZE_MM,
        local_size_mm=LOCAL_SIZE_MM,
        padding_mm=PADDING_MM,
        face_selections=(ends.x_min, ends.x_max),
        second_order_linear=False,
        high_order_optimize=HIGH_ORDER_OPTIMIZE,
    )
    support_tri6 = mesh.surface_tri6_by_selection[ends.x_min.selection_id]
    load_tri6 = mesh.surface_tri6_by_selection[ends.x_max.selection_id]

    material = IsotropicMaterial(young_modulus_mpa=200000.0, poisson_ratio=0.3)
    jacobian_gl5 = audit_curved_tet10_mesh_jacobians(
        mesh.nodes_mm, mesh.elements, quadrature_order=5
    )
    surface = compare_tri6_surface_quadrature(
        mesh.nodes_mm, load_tri6, order_a=4, order_b=5
    )

    offsets = np.asarray([_midside_offset(mesh.nodes_mm[conn]) for conn in mesh.elements], dtype=float)
    worst_index = int(np.argmax(offsets))
    worst_coords = mesh.nodes_mm[mesh.elements[worst_index]]
    k4 = tet10_stiffness_isoparametric_reference(worst_coords, material, quadrature_order=4)
    k5 = tet10_stiffness_isoparametric_reference(worst_coords, material, quadrature_order=5)
    volume_gl4_gl5 = relative_matrix_difference(k4, k5)

    preflight_checks = {
        "selected_meshing_contract": (
            mesh.second_order_linear is False
            and mesh.high_order_optimize == HIGH_ORDER_OPTIMIZE
            and mesh.local_size_mm == LOCAL_SIZE_MM
            and mesh.global_size_mm == GLOBAL_SIZE_MM
        ),
        "all_tet10_jacobians_positive_at_gl5_125_points": jacobian_gl5.all_positive,
        "surface_gl4_gl5_relative_area_within_limit": (
            surface.relative_area_difference <= MAX_SURFACE_GL4_GL5_RELATIVE_AREA_DIFFERENCE
        ),
        "surface_gl4_gl5_centroid_within_limit": (
            surface.centroid_delta_mm <= MAX_SURFACE_GL4_GL5_CENTROID_DELTA_MM
        ),
        "volume_gl4_gl5_reference_stiffness_within_limit": (
            volume_gl4_gl5 <= MAX_VOLUME_GL4_GL5_RELATIVE_STIFFNESS_DIFFERENCE
        ),
    }
    report: dict = {
        "schema": "AsterMaxCurvedTet10SolverVerificationBenchmarkV1",
        "classification": "CURVED_TET10_SOLVER_VERIFICATION_FIXTURE_NOT_INDUSTRIAL_RESULT",
        "source_sha256": feature.source_sha256,
        "feature_sha256": feature.feature_sha256,
        "mesh": {
            "mesh_sha256": mesh.mesh_sha256,
            "nodes": int(mesh.nodes_mm.shape[0]),
            "tet10": int(mesh.elements.shape[0]),
            "support_tri6": int(support_tri6.shape[0]),
            "load_tri6": int(load_tri6.shape[0]),
            "global_size_mm": mesh.global_size_mm,
            "local_size_mm": mesh.local_size_mm,
            "second_order_linear": mesh.second_order_linear,
            "high_order_optimize": mesh.high_order_optimize,
            "gmsh_version": mesh.gmsh_version,
            "maximum_element_midside_offset_from_chord_midpoint_mm": float(np.max(offsets)),
        },
        "preflight": {
            "jacobian_gl5": {
                "quadrature_order": jacobian_gl5.quadrature_order,
                "points_per_element": jacobian_gl5.point_count_per_element,
                "minimum_det_jacobian": jacobian_gl5.minimum_det_jacobian,
                "maximum_det_jacobian": jacobian_gl5.maximum_det_jacobian,
                "minimum_element_det_over_maximum_ratio": jacobian_gl5.minimum_element_det_over_maximum_ratio,
                "invalid_element_count": jacobian_gl5.invalid_element_count,
                "nonpositive_point_count": jacobian_gl5.nonpositive_point_count,
                "first_invalid_element_indices": list(jacobian_gl5.first_invalid_element_indices),
            },
            "load_surface_gl4_vs_gl5": {
                "area_gl4_mm2": surface.area_a_mm2,
                "area_gl5_mm2": surface.area_b_mm2,
                "relative_area_difference": surface.relative_area_difference,
                "centroid_gl4_mm": list(surface.centroid_a_mm),
                "centroid_gl5_mm": list(surface.centroid_b_mm),
                "centroid_delta_mm": surface.centroid_delta_mm,
                "relative_area_limit": MAX_SURFACE_GL4_GL5_RELATIVE_AREA_DIFFERENCE,
                "centroid_delta_limit_mm": MAX_SURFACE_GL4_GL5_CENTROID_DELTA_MM,
            },
            "worst_geometric_element_volume_gl4_vs_gl5": {
                "element_index_runtime_only": worst_index,
                "midside_offset_mm": float(offsets[worst_index]),
                "relative_stiffness_difference": volume_gl4_gl5,
                "acceptance_limit": MAX_VOLUME_GL4_GL5_RELATIVE_STIFFNESS_DIFFERENCE,
            },
            "checks": preflight_checks,
        },
        "solver_executed": False,
        "curved_tet10_solver_verification_claim": False,
        "local_stress_convergence_claim": False,
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
    }
    if not all(preflight_checks.values()):
        report["blocking_reason"] = "C11_PREFLIGHT_GATE_FAILED_NO_SOLVE_PERFORMED"
        return _write_blocked(report)

    applied = consistent_tri6_resultant_load_isoparametric(
        mesh.nodes_mm,
        load_tri6,
        total_force_n=TOTAL_FORCE_N,
        quadrature_order=4,
    )
    fixed_dofs = fixed_dofs_from_tri6(support_tri6)
    traction_gate = applied.relative_resultant_error <= MAX_TRACTION_RESULTANT_RELATIVE_ERROR
    if not traction_gate:
        report["preflight"]["checks"]["traction_resultant_error_within_limit"] = False
        report["blocking_reason"] = "C11_TRACTION_INTEGRATION_GATE_FAILED_NO_SOLVE_PERFORMED"
        report["traction"] = {
            "relative_resultant_error": applied.relative_resultant_error,
            "acceptance_limit": MAX_TRACTION_RESULTANT_RELATIVE_ERROR,
        }
        return _write_blocked(report)
    report["preflight"]["checks"]["traction_resultant_error_within_limit"] = True

    result = solve_linear_static_curved_tet10(
        mesh.nodes_mm,
        mesh.elements,
        material,
        applied.loads_n,
        fixed_dofs,
    )
    report["solver_executed"] = True

    reaction_force = np.sum(result.reactions_n, axis=0)
    applied_force = np.asarray(applied.integrated_resultant_n)
    force_balance = reaction_force + applied_force
    force_residual = float(np.linalg.norm(force_balance))
    load_moment = np.sum(np.cross(mesh.nodes_mm, applied.loads_n), axis=0)
    reaction_moment = np.sum(np.cross(mesh.nodes_mm, result.reactions_n), axis=0)
    moment_balance = reaction_moment + load_moment
    moment_residual = float(np.linalg.norm(moment_balance))

    shape = np.vstack([tet10_shape_functions(point) for point in result.integration_point_natural_coordinates])
    box = np.asarray(shoulder_local_box(feature, padding_mm=2.0), dtype=float)
    local_vm: list[float] = []
    local_sample_count = 0
    for element_index, conn in enumerate(mesh.elements):
        physical = shape @ mesh.nodes_mm[conn]
        inside = np.all((physical >= box[:3]) & (physical <= box[3:]), axis=1)
        if np.any(inside):
            values = result.integration_point_von_mises_mpa[element_index, inside]
            local_vm.extend(float(v) for v in values)
            local_sample_count += int(values.size)
    local = np.asarray(local_vm, dtype=float)
    if local.size == 0 or not np.all(np.isfinite(local)):
        raise RuntimeError("C11 shoulder neighborhood contains no finite Duffy integration-point stresses")

    result_checks = {
        "all_result_arrays_finite": (
            np.all(np.isfinite(result.displacement_mm))
            and np.all(np.isfinite(result.reactions_n))
            and np.all(np.isfinite(result.integration_point_stress_mpa))
            and np.all(np.isfinite(result.integration_point_von_mises_mpa))
        ),
        "production_quadrature_is_duffy_gl4": (
            result.volume_quadrature_order == CURVED_TET10_VOLUME_QUADRATURE_ORDER
            and result.integration_point_natural_coordinates.shape == (64, 3)
        ),
        "production_minimum_det_jacobian_positive": result.minimum_production_det_jacobian > 0.0,
        "global_force_equilibrium": force_residual <= MAX_FORCE_RESIDUAL_N,
        "global_moment_equilibrium": moment_residual <= MAX_MOMENT_RESIDUAL_NMM,
    }
    passed = all(preflight_checks.values()) and traction_gate and all(result_checks.values())

    nominal_small = float(np.linalg.norm(TOTAL_FORCE_N) / (math.pi * feature.small_radius_mm**2))
    result_identity = {
        "schema": "AsterMaxCurvedTet10SolverResultIdentityV1",
        "source_sha256": feature.source_sha256,
        "feature_sha256": feature.feature_sha256,
        "mesh_sha256": mesh.mesh_sha256,
        "support_selection_sha256": ends.x_min.selection_sha256,
        "load_selection_sha256": ends.x_max.selection_sha256,
        "displacement_sha256": _sha_array(result.displacement_mm, "<f8"),
        "reaction_sha256": _sha_array(result.reactions_n, "<f8"),
        "ip_coordinates_sha256": _sha_array(result.integration_point_natural_coordinates, "<f8"),
        "ip_weights_sha256": _sha_array(result.integration_point_weights, "<f8"),
        "ip_stress_sha256": _sha_array(result.integration_point_stress_mpa, "<f8"),
        "ip_von_mises_sha256": _sha_array(result.integration_point_von_mises_mpa, "<f8"),
    }
    result_sha = canonical_sha256(result_identity)

    report.update(
        {
            "traction": {
                "quadrature_method": applied.quadrature_method,
                "quadrature_order": applied.quadrature_order,
                "surface_area_mm2": applied.surface_area_mm2,
                "requested_resultant_n": list(applied.requested_resultant_n),
                "integrated_resultant_n": list(applied.integrated_resultant_n),
                "relative_resultant_error": applied.relative_resultant_error,
                "acceptance_limit": MAX_TRACTION_RESULTANT_RELATIVE_ERROR,
                "fixed_dof_count": int(fixed_dofs.size),
            },
            "solver": {
                "volume_quadrature_method": result.volume_quadrature_method,
                "volume_quadrature_order": result.volume_quadrature_order,
                "integration_points_per_element": int(result.integration_point_natural_coordinates.shape[0]),
                "minimum_production_det_jacobian": result.minimum_production_det_jacobian,
                "stiffness_nnz": result.stiffness_nnz,
            },
            "equilibrium": {
                "reaction_force_n": [float(v) for v in reaction_force],
                "force_balance_vector_n": [float(v) for v in force_balance],
                "force_residual_norm_n": force_residual,
                "force_residual_limit_n": MAX_FORCE_RESIDUAL_N,
                "load_moment_about_origin_nmm": [float(v) for v in load_moment],
                "reaction_moment_about_origin_nmm": [float(v) for v in reaction_moment],
                "moment_balance_vector_nmm": [float(v) for v in moment_balance],
                "moment_residual_norm_nmm": moment_residual,
                "moment_residual_limit_nmm": MAX_MOMENT_RESIDUAL_NMM,
            },
            "result": {
                "result_sha256": result_sha,
                "array_hashes": result_identity,
                "max_displacement_mm": float(np.max(np.linalg.norm(result.displacement_mm, axis=1))),
                "global_ip_von_mises_max_mpa": float(np.max(result.integration_point_von_mises_mpa)),
                "shoulder_duffy_ip_sample_count": local_sample_count,
                "shoulder_ip_von_mises_max_mpa": float(np.max(local)),
                "shoulder_ip_von_mises_mean_mpa": float(np.mean(local)),
                "shoulder_ip_von_mises_p95_mpa": float(np.quantile(local, 0.95)),
                "nominal_small_section_axial_stress_mpa": nominal_small,
                "local_ip_max_over_nominal_measurement_only": float(np.max(local) / nominal_small),
                "stress_representation": "DUFFY_GL4_64_TET10_INTEGRATION_POINTS_NO_NODAL_SMOOTHING",
            },
            "result_checks": result_checks,
            "curved_tet10_solver_verification_claim": passed,
            "local_stress_convergence_claim": False,
            "industrial_validation_claim": False,
            "ansys_equivalence_claim": False,
            "passed": passed,
            "interpretation_boundary": (
                "C11 is a single-mesh curved-isoparametric solver verification on a generated STEP fixture. "
                "It verifies the selected high-order meshing contract, dense Jacobian preflight, independently converged Duffy volume/surface integration, finite solution and global equilibrium. "
                "The local stress values are measurements only: one mesh cannot establish local-stress convergence, industrial validation, or ANSYS equivalence."
            ),
        }
    )
    report["benchmark_sha256"] = canonical_sha256(report)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    print(f"wrote {OUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
