from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path

import numpy as np

from astermax.credibility import canonical_sha256
from astermax.fea.analytical_witness import build_linear_normal_stress_witness
from astermax.fea.axisymmetric_shoulder import recognize_x_axis_shaft_shoulder
from astermax.fea.curved_far_field_kinematics import fit_curved_tet10_far_field_axial_kinematics
from astermax.fea.curved_tet10_solver import audit_curved_tet10_mesh_jacobians, solve_linear_static_curved_tet10
from astermax.fea.feature_adaptivity import mesh_step_tet10_around_shoulder
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.section_evidence import planar_section_properties
from astermax.fea.shaft_end_faces import capture_x_axis_shaft_end_faces
from astermax.fea.tet4 import IsotropicMaterial
from astermax.fea.tri6_isoparametric import consistent_tri6_resultant_load_isoparametric
from astermax.fea.tri6_traction import fixed_dofs_from_tri6


STEP = Path("curved_far_field_kinematic_corroboration.step")
OUT = Path("curved_far_field_kinematic_corroboration.json")
GLOBAL_SIZE_MM = 8.0
LOCAL_SIZE_MM = 1.4
HIGH_ORDER_OPTIMIZE = 2
PADDING_MM = 5.0
TOTAL_FORCE_N = np.asarray((1000.0, 0.0, 0.0), dtype=float)
YOUNG_MODULUS_MPA = 200000.0
POISSON_RATIO = 0.3
FAR_FIELD_X_MIN_MM = 15.0
FAR_FIELD_X_MAX_MM = 23.0
MIN_END_AND_FILLET_DISTANCE_OVER_DIAMETER = 0.75
MAX_AXIAL_GRADIENT_RELATIVE_ERROR = 0.02
MIN_WEIGHTED_R_SQUARED = 0.99
MAX_RESIDUAL_RMS_OVER_EXPECTED_SPAN = 0.05
MAX_SLAB_VOLUME_RELATIVE_ERROR = 0.15
MAX_TRACTION_RESULTANT_RELATIVE_ERROR = 1.0e-12
MAX_FORCE_RESIDUAL_N = 1.0e-5
MAX_MOMENT_RESIDUAL_NMM = 1.0e-3

C13_BENCHMARK_SHA256 = "d20322ba3518060071df18d940d12890f4f1b7fffaea6198d9812fda0e418e43"


def _write_fixture() -> None:
    gmsh = _gmsh()
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("curved_far_field_kinematic_corroboration")
        small = gmsh.model.occ.addCylinder(0.0, 0.0, 0.0, 40.0, 0.0, 0.0, 10.0)
        large = gmsh.model.occ.addCylinder(40.0, 0.0, 0.0, 40.0, 0.0, 0.0, 15.0)
        gmsh.model.occ.fuse([(3, small)], [(3, large)])
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        candidates: list[int] = []
        for _, tag in gmsh.model.getEntities(1):
            box = tuple(float(v) for v in gmsh.model.getBoundingBox(1, int(tag)))
            x_mid = 0.5 * (box[0] + box[3])
            if (
                abs(x_mid - 40.0) <= 1.0e-4
                and box[3] - box[0] <= 1.0e-4
                and abs(0.5 * (box[4] - box[1]) - 10.0) <= 1.0e-4
                and abs(0.5 * (box[5] - box[2]) - 10.0) <= 1.0e-4
            ):
                candidates.append(int(tag))
        if len(volumes) != 1 or len(candidates) != 1:
            raise RuntimeError(f"fixture topology unexpected: volumes={volumes}, fillet_edges={candidates}")
        gmsh.model.occ.fillet([int(volumes[0][1])], [candidates[0]], [2.0], removeVolume=True)
        gmsh.model.occ.synchronize()
        gmsh.write(str(STEP))
    finally:
        gmsh.finalize()


def _relative(a: float, b: float) -> float:
    return abs(float(a) - float(b)) / max(abs(float(a)), abs(float(b)), 1.0e-30)


def main() -> int:
    _write_fixture()
    feature = recognize_x_axis_shaft_shoulder(STEP, feature_id="C14_FAR_FIELD_KINEMATIC_CORROBORATION")
    ends = capture_x_axis_shaft_end_faces(STEP)
    section = planar_section_properties(STEP, ends.x_min)
    analytical = build_linear_normal_stress_witness(
        section,
        axial_force_n=float(TOTAL_FORCE_N[0]),
        moment_u_nmm=0.0,
        moment_v_nmm=0.0,
    )
    expected_gradient = float(analytical.sigma0_mpa / YOUNG_MODULUS_MPA)
    if expected_gradient <= 0.0:
        raise RuntimeError("C14 expected a positive tensile axial displacement gradient")

    diameter = 2.0 * float(feature.small_radius_mm)
    small_tangency_x = float(feature.transition_x_mm - feature.fillet_radius_mm)
    distance_from_support = FAR_FIELD_X_MIN_MM
    distance_from_fillet = small_tangency_x - FAR_FIELD_X_MAX_MM
    applicability_checks = {
        "slab_inside_small_diameter_segment": bool(
            FAR_FIELD_X_MIN_MM > 0.0 and FAR_FIELD_X_MAX_MM < small_tangency_x
        ),
        "support_distance_over_diameter": bool(
            distance_from_support / diameter >= MIN_END_AND_FILLET_DISTANCE_OVER_DIAMETER
        ),
        "fillet_distance_over_diameter": bool(
            distance_from_fillet / diameter >= MIN_END_AND_FILLET_DISTANCE_OVER_DIAMETER
        ),
    }

    material = IsotropicMaterial(young_modulus_mpa=YOUNG_MODULUS_MPA, poisson_ratio=POISSON_RATIO)
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
    jac = audit_curved_tet10_mesh_jacobians(mesh.nodes_mm, mesh.elements, quadrature_order=5)
    support_tri6 = mesh.surface_tri6_by_selection[ends.x_min.selection_id]
    load_tri6 = mesh.surface_tri6_by_selection[ends.x_max.selection_id]
    applied = consistent_tri6_resultant_load_isoparametric(
        mesh.nodes_mm,
        load_tri6,
        total_force_n=TOTAL_FORCE_N,
        quadrature_order=4,
    )
    result = solve_linear_static_curved_tet10(
        mesh.nodes_mm,
        mesh.elements,
        material,
        applied.loads_n,
        fixed_dofs_from_tri6(support_tri6),
    )

    reaction_force = np.sum(result.reactions_n, axis=0)
    force_residual = float(np.linalg.norm(reaction_force + np.asarray(applied.integrated_resultant_n)))
    load_moment = np.sum(np.cross(mesh.nodes_mm, applied.loads_n), axis=0)
    reaction_moment = np.sum(np.cross(mesh.nodes_mm, result.reactions_n), axis=0)
    moment_residual = float(np.linalg.norm(reaction_moment + load_moment))

    kinematics = fit_curved_tet10_far_field_axial_kinematics(
        nodes_mm=mesh.nodes_mm,
        elements=mesh.elements,
        mesh_sha256=mesh.mesh_sha256,
        displacement_mm=result.displacement_mm,
        integration_point_natural_coordinates=result.integration_point_natural_coordinates,
        integration_point_weights=result.integration_point_weights,
        x_min_mm=FAR_FIELD_X_MIN_MM,
        x_max_mm=FAR_FIELD_X_MAX_MM,
    )

    analytical_volume = section.area_mm2 * (FAR_FIELD_X_MAX_MM - FAR_FIELD_X_MIN_MM)
    slab_volume_relative_error = _relative(kinematics.sampled_physical_volume_mm3, analytical_volume)
    gradient_relative_error = _relative(kinematics.axial_displacement_gradient, expected_gradient)
    expected_span_extension = expected_gradient * (FAR_FIELD_X_MAX_MM - FAR_FIELD_X_MIN_MM)
    residual_ratio = kinematics.weighted_residual_rms_mm / max(abs(expected_span_extension), 1.0e-30)

    checks = {
        "applicability": all(applicability_checks.values()),
        "selected_meshing_contract": bool(
            mesh.global_size_mm == GLOBAL_SIZE_MM
            and mesh.local_size_mm == LOCAL_SIZE_MM
            and mesh.second_order_linear is False
            and mesh.high_order_optimize == HIGH_ORDER_OPTIMIZE
        ),
        "all_gl5_jacobians_positive": bool(jac.all_positive),
        "traction_resultant_within_limit": bool(applied.relative_resultant_error <= MAX_TRACTION_RESULTANT_RELATIVE_ERROR),
        "force_balance": bool(force_residual <= MAX_FORCE_RESIDUAL_N),
        "moment_balance": bool(moment_residual <= MAX_MOMENT_RESIDUAL_NMM),
        "slab_volume_within_limit": bool(slab_volume_relative_error <= MAX_SLAB_VOLUME_RELATIVE_ERROR),
        "axial_gradient_matches_F_over_AE": bool(gradient_relative_error <= MAX_AXIAL_GRADIENT_RELATIVE_ERROR),
        "weighted_fit_r_squared": bool(kinematics.weighted_r_squared >= MIN_WEIGHTED_R_SQUARED),
        "weighted_fit_residual_small": bool(residual_ratio <= MAX_RESIDUAL_RMS_OVER_EXPECTED_SPAN),
    }
    permitted = all(checks.values())

    payload = {
        "schema": "AsterMaxCurvedFarFieldKinematicCorroborationBenchmarkV1",
        "classification": "KINEMATIC_ANALYTICAL_CORROBORATION_VERIFICATION_FIXTURE_NOT_INDUSTRIAL_RESULT",
        "upstream_c13_reference": {
            "benchmark_sha256": C13_BENCHMARK_SHA256,
            "analytical_stress_corroboration_claim": True,
            "note": "Reference only; C14 independently reruns the final curved mesh and solve and does not treat the C13 result as runtime proof.",
        },
        "source_sha256": feature.source_sha256,
        "feature_sha256": feature.feature_sha256,
        "mesh_sha256": mesh.mesh_sha256,
        "mesh": {
            "global_size_mm": GLOBAL_SIZE_MM,
            "local_size_mm": LOCAL_SIZE_MM,
            "nodes": int(mesh.nodes_mm.shape[0]),
            "tet10": int(mesh.elements.shape[0]),
            "high_order_optimize": mesh.high_order_optimize,
            "second_order_linear": mesh.second_order_linear,
        },
        "far_field_contract": {
            "x_min_mm": FAR_FIELD_X_MIN_MM,
            "x_max_mm": FAR_FIELD_X_MAX_MM,
            "small_diameter_mm": diameter,
            "small_diameter_tangency_x_mm": small_tangency_x,
            "distance_from_support_mm": distance_from_support,
            "distance_from_fillet_mm": distance_from_fillet,
            "minimum_distance_over_diameter": MIN_END_AND_FILLET_DISTANCE_OVER_DIAMETER,
            "applicability_checks": applicability_checks,
        },
        "analytical_section": asdict(section),
        "nominal_axial_stress_mpa": float(analytical.sigma0_mpa),
        "young_modulus_mpa": YOUNG_MODULUS_MPA,
        "expected_axial_gradient_F_over_AE": expected_gradient,
        "expected_extension_over_declared_span_mm": expected_span_extension,
        "kinematics": asdict(kinematics),
        "comparison": {
            "gradient_relative_error": gradient_relative_error,
            "max_gradient_relative_error": MAX_AXIAL_GRADIENT_RELATIVE_ERROR,
            "weighted_r_squared": kinematics.weighted_r_squared,
            "minimum_weighted_r_squared": MIN_WEIGHTED_R_SQUARED,
            "weighted_residual_rms_mm": kinematics.weighted_residual_rms_mm,
            "residual_rms_over_expected_span_extension": residual_ratio,
            "max_residual_rms_over_expected_span_extension": MAX_RESIDUAL_RMS_OVER_EXPECTED_SPAN,
        },
        "slab_volume": {
            "analytical_volume_mm3": analytical_volume,
            "sampled_volume_mm3": kinematics.sampled_physical_volume_mm3,
            "relative_error": slab_volume_relative_error,
            "max_relative_error": MAX_SLAB_VOLUME_RELATIVE_ERROR,
        },
        "equilibrium": {
            "force_residual_n": force_residual,
            "moment_residual_nmm": moment_residual,
        },
        "gl5_jacobian_audit": {
            "minimum_det_jacobian": jac.minimum_det_jacobian,
            "invalid_element_count": jac.invalid_element_count,
            "nonpositive_point_count": jac.nonpositive_point_count,
        },
        "checks": checks,
        "kinematic_corroboration_claim": permitted,
        "stress_corroboration_claim_inherited_as_runtime_claim": False,
        "local_stress_convergence_claim_inherited_as_runtime_claim": False,
        "empirical_kt_validation_claim": False,
        "experimental_validation_claim": False,
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
        "interpretation_boundary": (
            "C14 corroborates only the far-field axial displacement gradient against the exact prismatic-bar witness du_x/dx=F/(AE) for this generated verification fixture. "
            "The observation is derived from TET10-interpolated displacement at actual volume integration points and does not use recovered stress. It is numerical solution verification, not physical or industrial validation."
        ),
    }
    payload["benchmark_sha256"] = canonical_sha256(payload)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "kinematic_corroboration_claim": permitted,
        "expected_axial_gradient_F_over_AE": expected_gradient,
        "fea_axial_displacement_gradient": kinematics.axial_displacement_gradient,
        "gradient_relative_error": gradient_relative_error,
        "weighted_r_squared": kinematics.weighted_r_squared,
        "residual_rms_over_expected_span_extension": residual_ratio,
        "slab_volume_relative_error": slab_volume_relative_error,
        "force_residual_n": force_residual,
        "moment_residual_nmm": moment_residual,
        "benchmark_sha256": payload["benchmark_sha256"],
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
    }, indent=2, sort_keys=True))
    if not permitted:
        raise RuntimeError(f"C14 kinematic corroboration blocked: {checks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
