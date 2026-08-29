from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path

import numpy as np

from astermax.credibility import canonical_sha256
from astermax.fea.axisymmetric_shoulder import recognize_x_axis_shaft_shoulder
from astermax.fea.curved_section_resultants import integrate_curved_tet10_section_resultant_slab
from astermax.fea.curved_tet10_solver import audit_curved_tet10_mesh_jacobians, solve_linear_static_curved_tet10
from astermax.fea.far_field_applicability import distance_ratio_requirement_satisfied
from astermax.fea.feature_adaptivity import mesh_step_tet10_around_shoulder
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.section_evidence import planar_section_properties
from astermax.fea.shaft_end_faces import capture_x_axis_shaft_end_faces
from astermax.fea.tet4 import IsotropicMaterial
from astermax.fea.tri6_isoparametric import consistent_tri6_resultant_load_isoparametric
from astermax.fea.tri6_traction import fixed_dofs_from_tri6


STEP = Path("curved_internal_section_resultant_corroboration.step")
OUT = Path("curved_internal_section_resultant_corroboration.json")
GLOBAL_SIZE_MM = 8.0
LOCAL_SIZE_MM = 1.4
HIGH_ORDER_OPTIMIZE = 2
PADDING_MM = 5.0
TOTAL_FORCE_N = np.asarray((1000.0, 0.0, 0.0), dtype=float)
YOUNG_MODULUS_MPA = 200000.0
POISSON_RATIO = 0.3
SECTION_NORMAL = np.asarray((1.0, 0.0, 0.0), dtype=float)
SLABS_MM = ((15.0, 19.0), (17.0, 21.0), (19.0, 23.0))
MIN_END_AND_FILLET_DISTANCE_OVER_DIAMETER = 0.75
APPLICABILITY_GEOMETRY_RELATIVE_TOLERANCE = 1.0e-8
MAX_AXIAL_FORCE_RELATIVE_ERROR = 0.02
MAX_SHEAR_OVER_APPLIED_FORCE = 0.01
MAX_MOMENT_OVER_FORCE_DIAMETER = 0.01
MAX_AXIAL_SPREAD_OVER_APPLIED_FORCE = 0.02
MAX_EFFECTIVE_THICKNESS_RELATIVE_ERROR = 0.15
MAX_TRACTION_RESULTANT_RELATIVE_ERROR = 1.0e-12
MAX_FORCE_RESIDUAL_N = 1.0e-5
MAX_MOMENT_RESIDUAL_NMM = 1.0e-3

C14_BENCHMARK_SHA256 = "184521235a0a8c6c73e468e4e341776046648c67ebb0fca5563176552669154d"


def _write_fixture() -> None:
    gmsh = _gmsh()
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("curved_internal_section_resultant_corroboration")
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
    feature = recognize_x_axis_shaft_shoulder(STEP, feature_id="C15_INTERNAL_SECTION_RESULTANT_CORROBORATION")
    ends = capture_x_axis_shaft_end_faces(STEP)
    section = planar_section_properties(STEP, ends.x_min)

    diameter = 2.0 * float(feature.small_radius_mm)
    small_tangency_x = float(feature.transition_x_mm - feature.fillet_radius_mm)
    envelope_min = min(v[0] for v in SLABS_MM)
    envelope_max = max(v[1] for v in SLABS_MM)
    distance_from_support = envelope_min
    distance_from_fillet = small_tangency_x - envelope_max
    applicability_checks = {
        "all_slabs_inside_small_diameter_segment": bool(
            envelope_min > 0.0 and envelope_max < small_tangency_x
        ),
        "support_distance_over_diameter": distance_ratio_requirement_satisfied(
            distance_mm=distance_from_support,
            diameter_mm=diameter,
            minimum_distance_over_diameter=MIN_END_AND_FILLET_DISTANCE_OVER_DIAMETER,
            geometry_relative_tolerance=APPLICABILITY_GEOMETRY_RELATIVE_TOLERANCE,
        ),
        "fillet_distance_over_diameter": distance_ratio_requirement_satisfied(
            distance_mm=distance_from_fillet,
            diameter_mm=diameter,
            minimum_distance_over_diameter=MIN_END_AND_FILLET_DISTANCE_OVER_DIAMETER,
            geometry_relative_tolerance=APPLICABILITY_GEOMETRY_RELATIVE_TOLERANCE,
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

    slab_results = []
    slab_metrics = []
    axial_values = []
    force_scale = float(np.linalg.norm(TOTAL_FORCE_N))
    moment_scale = force_scale * diameter
    for x_min, x_max in SLABS_MM:
        slab = integrate_curved_tet10_section_resultant_slab(
            nodes_mm=mesh.nodes_mm,
            elements=mesh.elements,
            mesh_sha256=mesh.mesh_sha256,
            integration_point_natural_coordinates=result.integration_point_natural_coordinates,
            integration_point_weights=result.integration_point_weights,
            integration_point_stress_mpa=result.integration_point_stress_mpa,
            coordinate_min_mm=x_min,
            coordinate_max_mm=x_max,
            section_area_mm2=section.area_mm2,
            section_centroid_mm=section.centroid_mm,
            section_normal=SECTION_NORMAL,
        )
        force = np.asarray(slab.resultant_force_n, dtype=float)
        moment = np.asarray(slab.resultant_moment_nmm, dtype=float)
        axial = float(force @ SECTION_NORMAL)
        shear = force - axial * SECTION_NORMAL
        torsion = float(moment @ SECTION_NORMAL)
        bending = moment - torsion * SECTION_NORMAL
        declared_thickness = x_max - x_min
        metrics = {
            "x_center_mm": 0.5 * (x_min + x_max),
            "axial_force_n": axial,
            "axial_relative_error": _relative(axial, force_scale),
            "shear_resultant_n": float(np.linalg.norm(shear)),
            "shear_over_applied_force": float(np.linalg.norm(shear)) / force_scale,
            "torsion_nmm": torsion,
            "bending_resultant_nmm": float(np.linalg.norm(bending)),
            "moment_resultant_nmm": float(np.linalg.norm(moment)),
            "moment_over_force_diameter": float(np.linalg.norm(moment)) / moment_scale,
            "declared_thickness_mm": declared_thickness,
            "sampled_effective_thickness_mm": slab.sampled_effective_thickness_mm,
            "effective_thickness_relative_error": _relative(slab.sampled_effective_thickness_mm, declared_thickness),
        }
        slab_results.append(slab)
        slab_metrics.append(metrics)
        axial_values.append(axial)

    axial_spread = (max(axial_values) - min(axial_values)) / force_scale
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
        "external_force_balance": bool(force_residual <= MAX_FORCE_RESIDUAL_N),
        "external_moment_balance": bool(moment_residual <= MAX_MOMENT_RESIDUAL_NMM),
        "all_axial_resultants_match_applied_force": all(
            m["axial_relative_error"] <= MAX_AXIAL_FORCE_RELATIVE_ERROR for m in slab_metrics
        ),
        "all_shear_resultants_small": all(
            m["shear_over_applied_force"] <= MAX_SHEAR_OVER_APPLIED_FORCE for m in slab_metrics
        ),
        "all_section_moments_small": all(
            m["moment_over_force_diameter"] <= MAX_MOMENT_OVER_FORCE_DIAMETER for m in slab_metrics
        ),
        "axial_resultant_spatial_consistency": bool(axial_spread <= MAX_AXIAL_SPREAD_OVER_APPLIED_FORCE),
        "all_effective_thicknesses_plausible": all(
            m["effective_thickness_relative_error"] <= MAX_EFFECTIVE_THICKNESS_RELATIVE_ERROR for m in slab_metrics
        ),
    }
    permitted = all(checks.values())

    payload = {
        "schema": "AsterMaxCurvedInternalSectionResultantCorroborationBenchmarkV1",
        "classification": "INTERNAL_SECTION_RESULTANT_NUMERICAL_CORROBORATION_VERIFICATION_FIXTURE_NOT_INDUSTRIAL_RESULT",
        "upstream_c14_reference": {
            "benchmark_sha256": C14_BENCHMARK_SHA256,
            "kinematic_corroboration_claim": True,
            "note": "Reference only; C15 independently reruns the final curved mesh and solve and does not inherit the C14 result as runtime proof.",
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
        "section_contract": {
            "cad_section": asdict(section),
            "section_normal": tuple(float(v) for v in SECTION_NORMAL),
            "slabs_mm": [list(v) for v in SLABS_MM],
            "small_diameter_mm": diameter,
            "small_diameter_tangency_x_mm": small_tangency_x,
            "minimum_end_and_fillet_distance_over_diameter": MIN_END_AND_FILLET_DISTANCE_OVER_DIAMETER,
            "geometry_relative_tolerance": APPLICABILITY_GEOMETRY_RELATIVE_TOLERANCE,
            "applicability_checks": applicability_checks,
            "method_boundary": (
                "Each QOI is a finite-slab physical-volume-weighted average of native TET10 integration-point traction/moment density, scaled by the exact CAD section area. It is not claimed to be exact integration over a reconstructed quadratic cut surface."
            ),
        },
        "slab_results": [asdict(v) for v in slab_results],
        "slab_metrics": slab_metrics,
        "comparison": {
            "expected_axial_force_n": force_scale,
            "max_axial_force_relative_error": MAX_AXIAL_FORCE_RELATIVE_ERROR,
            "max_shear_over_applied_force": MAX_SHEAR_OVER_APPLIED_FORCE,
            "max_moment_over_force_diameter": MAX_MOMENT_OVER_FORCE_DIAMETER,
            "axial_spread_over_applied_force": axial_spread,
            "max_axial_spread_over_applied_force": MAX_AXIAL_SPREAD_OVER_APPLIED_FORCE,
            "max_effective_thickness_relative_error": MAX_EFFECTIVE_THICKNESS_RELATIVE_ERROR,
        },
        "equilibrium": {
            "external_force_residual_n": force_residual,
            "external_moment_residual_nmm": moment_residual,
        },
        "gl5_jacobian_audit": {
            "minimum_det_jacobian": jac.minimum_det_jacobian,
            "invalid_element_count": jac.invalid_element_count,
            "nonpositive_point_count": jac.nonpositive_point_count,
        },
        "checks": checks,
        "internal_section_resultant_corroboration_claim": permitted,
        "exact_cut_surface_integration_claim": False,
        "experimental_validation_claim": False,
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
        "interpretation_boundary": (
            "C15 corroborates internal axial-force equilibrium and small parasitic shear/moment in three declared far-field section-centered slabs of this generated linear-elastic verification fixture. The QOI uses only native curved-TET10 integration-point stresses with w*det(J), the exact CAD section area and CAD centroid. No nodal stress recovery, averaging-to-nodes, smoothing or invented cut-surface field participates. This is numerical solution verification, not physical or industrial validation."
        ),
    }
    payload["benchmark_sha256"] = canonical_sha256(payload)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "internal_section_resultant_corroboration_claim": permitted,
        "axial_force_n_by_slab": [m["axial_force_n"] for m in slab_metrics],
        "axial_relative_error_by_slab": [m["axial_relative_error"] for m in slab_metrics],
        "shear_over_applied_force_by_slab": [m["shear_over_applied_force"] for m in slab_metrics],
        "moment_over_force_diameter_by_slab": [m["moment_over_force_diameter"] for m in slab_metrics],
        "effective_thickness_relative_error_by_slab": [m["effective_thickness_relative_error"] for m in slab_metrics],
        "axial_spread_over_applied_force": axial_spread,
        "force_residual_n": force_residual,
        "moment_residual_nmm": moment_residual,
        "benchmark_sha256": payload["benchmark_sha256"],
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
    }, indent=2, sort_keys=True))
    if not permitted:
        raise RuntimeError(f"C15 internal section resultant corroboration blocked: {checks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
