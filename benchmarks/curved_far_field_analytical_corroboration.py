from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from astermax.credibility import (
    ClaimEngine,
    ClaimState,
    ConsequenceLevel,
    ContextOfUse,
    EvidenceGraph,
    build_analysis_passport,
    canonical_sha256,
)
from astermax.fea.analytical_comparison import compare_scalar_qoi, scalar_qoi_comparison_evidence
from astermax.fea.analytical_witness import (
    analytical_section_chain_evidence,
    analytical_section_witness_evidence,
    build_linear_normal_stress_witness,
)
from astermax.fea.axisymmetric_shoulder import recognize_x_axis_shaft_shoulder
from astermax.fea.curved_far_field_stress import (
    curved_far_field_stress_evidence,
    integrate_curved_tet10_far_field_stress,
)
from astermax.fea.curved_tet10_solver import audit_curved_tet10_mesh_jacobians, solve_linear_static_curved_tet10
from astermax.fea.far_field_corroboration import (
    analytical_fea_corroboration_chain,
    far_field_analytical_corroboration_claim,
    far_field_uniformity_evidence,
)
from astermax.fea.feature_adaptivity import mesh_step_tet10_around_shoulder
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.persistent_geometry import resolve_face_selection
from astermax.fea.section_evidence import (
    persistent_face_identity_evidence,
    planar_section_properties,
    section_properties_evidence,
)
from astermax.fea.shaft_end_faces import capture_x_axis_shaft_end_faces
from astermax.fea.tet4 import IsotropicMaterial
from astermax.fea.tri6_isoparametric import consistent_tri6_resultant_load_isoparametric
from astermax.fea.tri6_traction import fixed_dofs_from_tri6


STEP = Path("curved_far_field_analytical_corroboration.step")
OUT = Path("curved_far_field_analytical_corroboration.json")
GLOBAL_SIZE_MM = 8.0
LOCAL_SIZE_MM = 1.4
HIGH_ORDER_OPTIMIZE = 2
PADDING_MM = 5.0
TOTAL_FORCE_N = np.asarray((1000.0, 0.0, 0.0), dtype=float)
FAR_FIELD_X_MIN_MM = 19.0
FAR_FIELD_X_MAX_MM = 21.0
MIN_END_AND_FILLET_DISTANCE_OVER_DIAMETER = 0.75
MAX_QOI_RELATIVE_ERROR = 0.02
MAX_SIGMA_X_STD_OVER_NOMINAL = 0.05
MAX_SLAB_VOLUME_RELATIVE_ERROR = 0.10
MAX_TRACTION_RESULTANT_RELATIVE_ERROR = 1.0e-12
MAX_FORCE_RESIDUAL_N = 1.0e-5
MAX_MOMENT_RESIDUAL_NMM = 1.0e-3

C12B_BENCHMARK_SHA256 = "eb3452c7714e10bba30ea3ae5e85c0b593b1f1ce80d7857807a16f1e04a6d5b5"
C12B_DECISION_SHA256 = "586e756807bfae7006ae24f0dde417dd5f84eb5647ec9a426df7a87b4efd69f9"

QOI_IDS = (
    "SIGMA_X_MEAN",
    "VON_MISES_MEAN",
    "SIGMA_Y_MEAN",
    "SIGMA_Z_MEAN",
    "TAU_XY_MEAN",
    "TAU_YZ_MEAN",
    "TAU_XZ_MEAN",
)


def _write_fixture() -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("curved_far_field_analytical_corroboration")
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
    return abs(float(a) - float(b)) / max(abs(float(a)), abs(float(b)), 1.0e-12)


def main() -> int:
    _write_fixture()
    feature = recognize_x_axis_shaft_shoulder(STEP, feature_id="C13_FAR_FIELD_ANALYTICAL_CORROBORATION")
    ends = capture_x_axis_shaft_end_faces(STEP)
    small_face = ends.x_min
    small_face_resolution = resolve_face_selection(STEP, small_face)
    section = planar_section_properties(STEP, small_face)
    analytical = build_linear_normal_stress_witness(
        section,
        axial_force_n=float(TOTAL_FORCE_N[0]),
        moment_u_nmm=0.0,
        moment_v_nmm=0.0,
    )
    sigma_nominal = float(analytical.sigma0_mpa)
    if sigma_nominal <= 0.0:
        raise RuntimeError("C13 expected a positive tensile analytical stress")

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

    material = IsotropicMaterial(young_modulus_mpa=200000.0, poisson_ratio=0.3)
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
    numerical_preflight = {
        "selected_meshing_contract": bool(
            mesh.global_size_mm == GLOBAL_SIZE_MM
            and mesh.local_size_mm == LOCAL_SIZE_MM
            and mesh.second_order_linear is False
            and mesh.high_order_optimize == HIGH_ORDER_OPTIMIZE
        ),
        "all_gl5_jacobians_positive": bool(jac.all_positive),
        "traction_resultant_within_limit": bool(
            applied.relative_resultant_error <= MAX_TRACTION_RESULTANT_RELATIVE_ERROR
        ),
    }

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
    equilibrium_checks = {
        "force_balance": force_residual <= MAX_FORCE_RESIDUAL_N,
        "moment_balance": moment_residual <= MAX_MOMENT_RESIDUAL_NMM,
    }

    far_field = integrate_curved_tet10_far_field_stress(
        nodes_mm=mesh.nodes_mm,
        elements=mesh.elements,
        mesh_sha256=mesh.mesh_sha256,
        integration_point_natural_coordinates=result.integration_point_natural_coordinates,
        integration_point_weights=result.integration_point_weights,
        integration_point_stress_mpa=result.integration_point_stress_mpa,
        integration_point_von_mises_mpa=result.integration_point_von_mises_mpa,
        x_min_mm=FAR_FIELD_X_MIN_MM,
        x_max_mm=FAR_FIELD_X_MAX_MM,
    )
    analytical_slab_volume = section.area_mm2 * (FAR_FIELD_X_MAX_MM - FAR_FIELD_X_MIN_MM)
    slab_volume_relative_error = _relative(far_field.sampled_physical_volume_mm3, analytical_slab_volume)
    volume_check = slab_volume_relative_error <= MAX_SLAB_VOLUME_RELATIVE_ERROR

    face_record = persistent_face_identity_evidence(small_face, small_face_resolution)
    section_record = section_properties_evidence(section)
    analytical_record = analytical_section_witness_evidence(analytical)
    analytical_chain = analytical_section_chain_evidence(face_record, section_record, analytical_record)
    fea_record = curved_far_field_stress_evidence(far_field)
    uniformity_record = far_field_uniformity_evidence(
        far_field,
        reference_stress_mpa=sigma_nominal,
        max_sigma_x_std_over_reference=MAX_SIGMA_X_STD_OVER_NOMINAL,
    )

    abs_limit = MAX_QOI_RELATIVE_ERROR * abs(sigma_nominal)
    mean = far_field.weighted_mean_stress_mpa
    comparison_specs = (
        ("SIGMA_X_MEAN", sigma_nominal, mean[0], abs(sigma_nominal)),
        ("VON_MISES_MEAN", abs(sigma_nominal), far_field.weighted_mean_von_mises_mpa, abs(sigma_nominal)),
        ("SIGMA_Y_MEAN", 0.0, mean[1], abs(sigma_nominal)),
        ("SIGMA_Z_MEAN", 0.0, mean[2], abs(sigma_nominal)),
        ("TAU_XY_MEAN", 0.0, mean[3], abs(sigma_nominal)),
        ("TAU_YZ_MEAN", 0.0, mean[4], abs(sigma_nominal)),
        ("TAU_XZ_MEAN", 0.0, mean[5], abs(sigma_nominal)),
    )
    comparison_records = []
    comparison_payloads = []
    for qoi_id, analytical_value, fea_value, scale in comparison_specs:
        comparison = compare_scalar_qoi(
            qoi_id=qoi_id,
            units="MPa",
            analytical_evidence_sha256=analytical_record.payload_sha256,
            fea_evidence_sha256=fea_record.payload_sha256,
            analytical_value=analytical_value,
            fea_value=fea_value,
            max_absolute_error=abs_limit,
            max_relative_error=MAX_QOI_RELATIVE_ERROR,
            relative_scale_floor=scale,
        )
        comparison_records.append(scalar_qoi_comparison_evidence(comparison))
        comparison_payloads.append(asdict(comparison))

    all_prerequisites = (
        all(applicability_checks.values())
        and all(numerical_preflight.values())
        and all(equilibrium_checks.values())
        and volume_check
        and uniformity_record.claim_grade
        and all(record.claim_grade for record in comparison_records)
    )
    corroboration_chain = None
    if all_prerequisites:
        corroboration_chain = analytical_fea_corroboration_chain(
            analytical_section_chain=analytical_chain,
            analytical_witness=analytical_record,
            fea_far_field=fea_record,
            uniformity=uniformity_record,
            comparisons=comparison_records,
            required_qoi_ids=QOI_IDS,
        )

    context = ContextOfUse(
        context_id="COU_C13_CURVED_FAR_FIELD_ANALYTICAL_CORROBORATION",
        engineering_question="Does the converged curved-TET10 far-field stress scale agree with the exact CAD axial-stress witness F/A?",
        intended_decision="Permit analytical corroboration only for this verification fixture; do not infer local Kt validation, physical validation, industrial validation or ANSYS equivalence.",
        quantities_of_interest=("far-field sigma_x", "far-field von Mises", "non-axial mean stress components"),
        acceptance_criteria=("all seven QOI comparisons pass", "far-field sigma_x uniformity passes", "CAD/FEA evidence chain is hash-bound"),
        consequence_level=ConsequenceLevel.HIGH,
        assumptions=("linear elasticity", "small deformation", "centered axial resultant", "far-field slab lies in the constant-diameter region"),
    )
    graph = EvidenceGraph(context)
    base_records = (face_record, section_record, analytical_record, analytical_chain, fea_record, uniformity_record, *comparison_records)
    for record in base_records:
        graph.add(record)
    if corroboration_chain is not None:
        graph.add(corroboration_chain)

    graph.link(section_record.evidence_id, face_record.evidence_id, "USES_FACE")
    graph.link(analytical_record.evidence_id, section_record.evidence_id, "USES_SECTION")
    graph.link(analytical_chain.evidence_id, analytical_record.evidence_id, "BINDS_WITNESS")
    for record in comparison_records:
        graph.link(record.evidence_id, analytical_record.evidence_id, "COMPARES_ANALYTICAL")
        graph.link(record.evidence_id, fea_record.evidence_id, "COMPARES_FEA")
    graph.link(uniformity_record.evidence_id, fea_record.evidence_id, "ASSESSES_FEA_REGION")
    if corroboration_chain is not None:
        graph.link(corroboration_chain.evidence_id, analytical_chain.evidence_id, "BINDS_ANALYTICAL_CHAIN")
        graph.link(corroboration_chain.evidence_id, fea_record.evidence_id, "BINDS_FEA")
        graph.link(corroboration_chain.evidence_id, uniformity_record.evidence_id, "BINDS_UNIFORMITY")

    claim = far_field_analytical_corroboration_claim(context.context_id, qoi_count=len(QOI_IDS))
    decision = ClaimEngine.evaluate(claim, graph)
    passport = build_analysis_passport(graph, (decision,))
    claim_permitted = decision.state is ClaimState.PERMITTED and all_prerequisites

    payload: dict[str, Any] = {
        "schema": "AsterMaxCurvedFarFieldAnalyticalCorroborationBenchmarkV1",
        "classification": "ANALYTICAL_CORROBORATION_VERIFICATION_FIXTURE_NOT_INDUSTRIAL_RESULT",
        "upstream_c12b_reference": {
            "benchmark_sha256": C12B_BENCHMARK_SHA256,
            "decision_sha256": C12B_DECISION_SHA256,
            "local_stress_convergence_claim": True,
            "note": "Reference to separately verified upstream evidence; C13 reruns the final mesh rather than treating this reference as runtime proof.",
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
        "analytical_witness": asdict(analytical),
        "nominal_axial_stress_mpa": sigma_nominal,
        "numerical_preflight": {
            "checks": numerical_preflight,
            "gl5_minimum_det_jacobian": jac.minimum_det_jacobian,
            "gl5_invalid_element_count": jac.invalid_element_count,
            "traction_relative_resultant_error": applied.relative_resultant_error,
        },
        "equilibrium": {
            "force_residual_n": force_residual,
            "moment_residual_nmm": moment_residual,
            "checks": equilibrium_checks,
        },
        "far_field_tensor": asdict(far_field),
        "far_field_uniformity": dict(uniformity_record.metadata),
        "slab_volume": {
            "analytical_volume_mm3": analytical_slab_volume,
            "sampled_volume_mm3": far_field.sampled_physical_volume_mm3,
            "relative_error": slab_volume_relative_error,
            "max_relative_error": MAX_SLAB_VOLUME_RELATIVE_ERROR,
            "passed": volume_check,
        },
        "qoi_policy": {
            "max_relative_error": MAX_QOI_RELATIVE_ERROR,
            "max_absolute_error_mpa": abs_limit,
            "zero_reference_relative_scale_floor_mpa": abs(sigma_nominal),
            "required_qoi_ids": list(QOI_IDS),
        },
        "qoi_comparisons": comparison_payloads,
        "all_prerequisites_passed": all_prerequisites,
        "corroboration_chain_built": corroboration_chain is not None,
        "claim_state": decision.state.value,
        "claim_blockers": list(decision.blockers),
        "claim_decision_sha256": decision.decision_sha256,
        "evidence_graph_sha256": graph.fingerprint_sha256,
        "analysis_passport_sha256": passport["passport_sha256"],
        "analytical_corroboration_claim": claim_permitted,
        "local_stress_convergence_claim_inherited_as_runtime_claim": False,
        "empirical_kt_validation_claim": False,
        "experimental_validation_claim": False,
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
        "interpretation_boundary": (
            "C13 compares a physical-volume-weighted far-field tensor from one C12b-contract final curved mesh against the exact CAD axial witness sigma=F/A. "
            "It is analytical corroboration of stress scale for this verification fixture, not a local stress-concentration validation and not physical or industrial validation."
        ),
    }
    payload["benchmark_sha256"] = canonical_sha256(payload)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "analytical_corroboration_claim": claim_permitted,
        "claim_state": decision.state.value,
        "nominal_axial_stress_mpa": sigma_nominal,
        "fea_sigma_x_mean_mpa": far_field.weighted_mean_stress_mpa[0],
        "fea_von_mises_mean_mpa": far_field.weighted_mean_von_mises_mpa,
        "sigma_x_std_over_nominal": uniformity_record.metadata["sigma_x_std_over_reference"],
        "slab_volume_relative_error": slab_volume_relative_error,
        "benchmark_sha256": payload["benchmark_sha256"],
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
