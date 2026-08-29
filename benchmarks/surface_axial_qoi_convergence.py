from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import numpy as np

from astermax.credibility import (
    ClaimEngine,
    ClaimState,
    ConsequenceLevel,
    ContextOfUse,
    EvidenceGraph,
    EvidenceRecord,
    EvidenceSource,
    EvidenceStatus,
    build_analysis_passport,
    canonical_sha256,
)
from astermax.fea.axisymmetric_shoulder import recognize_x_axis_shaft_shoulder
from astermax.fea.curved_tet10_solver import audit_curved_tet10_mesh_jacobians, solve_linear_static_curved_tet10
from astermax.fea.feature_adaptivity import mesh_step_tet10_around_shoulder
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.persistent_geometry import capture_face_selection
from astermax.fea.shaft_end_faces import capture_x_axis_shaft_end_faces
from astermax.fea.surface_axial_qoi import measure_fillet_surface_axial_stress
from astermax.fea.surface_qoi_convergence import (
    SurfaceAxialQOIConvergencePolicy,
    SurfaceAxialQOIRefinementSample,
    evaluate_surface_axial_qoi_convergence,
    surface_axial_qoi_convergence_evidence,
    surface_sampled_axial_qoi_converged_claim,
)
from astermax.fea.tet4 import IsotropicMaterial
from astermax.fea.tri6_isoparametric import consistent_tri6_resultant_load_isoparametric
from astermax.fea.tri6_traction import fixed_dofs_from_tri6


STEP = Path("surface_axial_qoi_convergence.step")
OUT = Path("surface_axial_qoi_convergence.json")
GLOBAL_SIZE_MM = 8.0
LOCAL_TARGETS_MM = (2.0, 1.8, 1.6, 1.4)
PADDING_MM = 5.0
HIGH_ORDER_OPTIMIZE = 2
TOTAL_FORCE_N = np.asarray((1000.0, 0.0, 0.0), dtype=float)
FORCE_RESIDUAL_LIMIT_N = 1.0e-6
MOMENT_RESIDUAL_LIMIT_NMM = 1.0e-4
C18_BENCHMARK_SHA256 = "3ac5cdd4e8e7482bd4f4d40483353dc30f5185da7180ba14f92c4f709d567b51"
C18_DECISION_SHA256 = "cfc62974662f897ec35e5d942531c9bc0d3fd63b282b09258e5273c224a6ec0f"
C18_ARTIFACT_ZIP_SHA256 = "76a172470496034677dcec3ac786df3ed750845c0e88786edd3cff23dab0d6d4"
C19_BENCHMARK_SHA256 = "5526280f4cdc2b9b615f5940f68c07139d488bd01eb8f50184ddfa371aa76f5f"
C19_MEASUREMENT_SHA256 = "d23f7d8abd14d8aac8798a26ada804ae76db2aee7d5ca15c8ffa60e05c449b3f"
C19_PASSPORT_SHA256 = "915702cc0b17fa4201b18a9ce2cd643c0929f9b9ebdbede53198dbdff5448703"


def _write_fixture() -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c20_surface_axial_qoi_convergence")
        small = gmsh.model.occ.addCylinder(0.0, 0.0, 0.0, 40.0, 0.0, 0.0, 10.0)
        large = gmsh.model.occ.addCylinder(40.0, 0.0, 0.0, 40.0, 0.0, 0.0, 15.0)
        gmsh.model.occ.fuse([(3, small)], [(3, large)])
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        candidates = []
        for _, tag in gmsh.model.getEntities(1):
            box = tuple(float(v) for v in gmsh.model.getBoundingBox(1, int(tag)))
            if (
                abs(0.5 * (box[0] + box[3]) - 40.0) <= 1.0e-4
                and box[3] - box[0] <= 1.0e-4
                and abs(0.5 * (box[4] - box[1]) - 10.0) <= 1.0e-4
                and abs(0.5 * (box[5] - box[2]) - 10.0) <= 1.0e-4
            ):
                candidates.append(int(tag))
        if len(volumes) != 1 or len(candidates) != 1:
            raise RuntimeError(f"unexpected C20 fixture topology: volumes={volumes}, edges={candidates}")
        gmsh.model.occ.fillet([int(volumes[0][1])], [candidates[0]], [2.0], removeVolume=True)
        gmsh.model.occ.synchronize()
        gmsh.write(str(STEP))
    finally:
        gmsh.finalize()


def _equilibrium_payload(mesh, applied, result) -> dict:
    reaction_force = np.sum(result.reactions_n, axis=0)
    applied_force = np.asarray(applied.integrated_resultant_n, dtype=float)
    force_residual = float(np.linalg.norm(reaction_force + applied_force))
    load_moment = np.sum(np.cross(mesh.nodes_mm, applied.loads_n), axis=0)
    reaction_moment = np.sum(np.cross(mesh.nodes_mm, result.reactions_n), axis=0)
    moment_residual = float(np.linalg.norm(reaction_moment + load_moment))
    passed = bool(
        force_residual <= FORCE_RESIDUAL_LIMIT_N
        and moment_residual <= MOMENT_RESIDUAL_LIMIT_NMM
        and applied.relative_resultant_error <= 1.0e-12
    )
    return {
        "schema": "AsterMaxPhysicalLoadEquilibriumV1",
        "requested_force_n": [float(v) for v in TOTAL_FORCE_N],
        "integrated_force_n": [float(v) for v in applied_force],
        "reaction_force_n": [float(v) for v in reaction_force],
        "force_residual_n": force_residual,
        "moment_residual_nmm": moment_residual,
        "traction_relative_resultant_error": applied.relative_resultant_error,
        "force_residual_limit_n": FORCE_RESIDUAL_LIMIT_N,
        "moment_residual_limit_nmm": MOMENT_RESIDUAL_LIMIT_NMM,
        "passed": passed,
    }


def main() -> int:
    _write_fixture()
    feature = recognize_x_axis_shaft_shoulder(STEP, feature_id="C20_R10_R15_R2")
    ends = capture_x_axis_shaft_end_faces(STEP)
    transition = capture_face_selection(STEP, feature.transition_face_tag, "C20_TRANSITION_FILLET")
    material = IsotropicMaterial(young_modulus_mpa=200000.0, poisson_ratio=0.3)
    policy = SurfaceAxialQOIConvergencePolicy()

    refinement_samples: list[SurfaceAxialQOIRefinementSample] = []
    sample_reports: list[dict] = []
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
        support = mesh.surface_tri6_by_selection[ends.x_min.selection_id]
        load = mesh.surface_tri6_by_selection[ends.x_max.selection_id]
        fillet = mesh.surface_tri6_by_selection[transition.selection_id]
        jac = audit_curved_tet10_mesh_jacobians(mesh.nodes_mm, mesh.elements, quadrature_order=5)
        if not jac.all_positive:
            raise RuntimeError(f"C20 GL5 Jacobian audit failed at local size {local_size}")

        applied = consistent_tri6_resultant_load_isoparametric(
            mesh.nodes_mm, load, total_force_n=TOTAL_FORCE_N, quadrature_order=4
        )
        result = solve_linear_static_curved_tet10(
            mesh.nodes_mm,
            mesh.elements,
            material,
            applied.loads_n,
            fixed_dofs_from_tri6(support),
        )
        equilibrium = _equilibrium_payload(mesh, applied, result)
        equilibrium_sha = canonical_sha256(equilibrium)
        if not equilibrium["passed"]:
            raise RuntimeError(f"C20 equilibrium gate failed at local size {local_size}: {equilibrium}")

        measurement, _ = measure_fillet_surface_axial_stress(
            measurement_id=f"C20_SURFACE_SIGMA_X_LOCAL_{local_size:.1f}",
            nodes_mm=mesh.nodes_mm,
            elements=mesh.elements,
            displacement_mm=result.displacement_mm,
            material=material,
            transition_tri6=fillet,
            mesh_sha256=mesh.mesh_sha256,
            transition_selection_sha256=transition.selection_sha256,
        )
        max_displacement = float(np.max(np.linalg.norm(result.displacement_mm, axis=1)))
        refinement = SurfaceAxialQOIRefinementSample(
            local_target_size_mm=float(local_size),
            local_mean_max_corner_edge_mm=float(mesh.local_mean_max_corner_edge_mm),
            node_count=int(mesh.nodes_mm.shape[0]),
            tet10_count=int(mesh.elements.shape[0]),
            transition_tri6_count=int(fillet.shape[0]),
            surface_sample_count=int(measurement.sample_count),
            sampled_max_axial_normal_stress_mpa=float(measurement.maximum_axial_normal_stress_mpa),
            maximum_point_mm=tuple(float(v) for v in measurement.maximum_point_mm),
            max_displacement_mm=max_displacement,
            force_residual_n=float(equilibrium["force_residual_n"]),
            moment_residual_nmm=float(equilibrium["moment_residual_nmm"]),
            mesh_sha256=mesh.mesh_sha256,
            measurement_sha256=measurement.measurement_sha256,
            equilibrium_sha256=equilibrium_sha,
        )
        refinement_samples.append(refinement)
        sample_reports.append(
            {
                **asdict(refinement),
                "minimum_axial_normal_stress_mpa": measurement.minimum_axial_normal_stress_mpa,
                "mean_axial_normal_stress_mpa": measurement.mean_axial_normal_stress_mpa,
                "maximum_sample_sha256": measurement.maximum_sample_sha256,
                "jacobian_gl5_minimum": jac.minimum_det_jacobian,
                "traction_relative_resultant_error": applied.relative_resultant_error,
                "second_order_linear": mesh.second_order_linear,
                "high_order_optimize": mesh.high_order_optimize,
            }
        )

    convergence = evaluate_surface_axial_qoi_convergence(refinement_samples, policy=policy)
    convergence_evidence = surface_axial_qoi_convergence_evidence(convergence)
    context = ContextOfUse(
        context_id="COU_C20_SURFACE_SAMPLED_AXIAL_QOI_CONVERGENCE",
        engineering_question="Does the declared discrete sampled fillet-surface axial-normal stress QOI satisfy the frozen mesh-refinement convergence gates?",
        intended_decision="Decide whether this sampled surface QOI has sufficient numerical refinement evidence to enter a later, separately governed empirical corroboration eligibility assessment.",
        quantities_of_interest=("SURFACE_SAMPLED_MAX_AXIAL_NORMAL_STRESS_MPA",),
        acceptance_criteria=(
            "four predeclared local mesh targets 2.0, 1.8, 1.6, 1.4 mm",
            "penultimate QOI change <= 5 percent",
            "last QOI change <= 3 percent",
            "last displacement change <= 1 percent",
            "force residual <= 1e-6 N and moment residual <= 1e-4 Nmm at every level",
            "last maximum meridional (x,rho) shift <= one final local mean edge metric",
            "continuous surface peak convergence remains explicitly unclaimed",
        ),
        consequence_level=ConsequenceLevel.HIGH,
        assumptions=(
            "convergence applies only to the declared discrete four-interior-points-per-TRI6 operator",
            "axisymmetric load permits maximum-location comparison in meridional coordinates independent of azimuth",
        ),
    )
    graph = EvidenceGraph(context)
    c18 = EvidenceRecord(
        evidence_id="C18_SURFACE_OPERATOR_VERIFICATION",
        kind="TET10_SURFACE_STRESS_AFFINE_VERIFICATION",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DOCUMENT,
        description="Exact upstream C18 Windows verification of the direct TET10 surface stress operator.",
        payload_sha256=C18_BENCHMARK_SHA256,
        metadata={
            "claim_decision_sha256": C18_DECISION_SHA256,
            "artifact_zip_sha256": C18_ARTIFACT_ZIP_SHA256,
        },
    )
    c19 = EvidenceRecord(
        evidence_id="C19_SINGLE_LEVEL_SURFACE_QOI",
        kind="PHYSICAL_FILLET_SURFACE_AXIAL_STRESS_MEASUREMENT_REFERENCE",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DOCUMENT,
        description="Upstream C19 single-level physical sampled surface QOI evidence retained as provenance, not used to tune the C20 convergence thresholds.",
        payload_sha256=C19_BENCHMARK_SHA256,
        metadata={
            "measurement_sha256": C19_MEASUREMENT_SHA256,
            "analysis_passport_sha256": C19_PASSPORT_SHA256,
        },
    )
    for evidence in (c18, c19, convergence_evidence):
        graph.add(evidence)
    graph.link(convergence_evidence.evidence_id, c18.evidence_id, "USES_VERIFIED_OPERATOR")
    graph.link(convergence_evidence.evidence_id, c19.evidence_id, "EXTENDS_SINGLE_LEVEL_QOI")

    claim = surface_sampled_axial_qoi_converged_claim(context.context_id)
    decision = ClaimEngine.evaluate(claim, graph)
    expected_state = ClaimState.PERMITTED if convergence.passed else ClaimState.BLOCKED
    if decision.state is not expected_state:
        raise RuntimeError(
            f"C20 claim engine state {decision.state.value} inconsistent with convergence {convergence.classification}"
        )
    passport = build_analysis_passport(graph, (decision,))

    report = {
        "schema": "AsterMaxSurfaceAxialQOIConvergenceBenchmarkV1",
        "classification": convergence.classification,
        "source_sha256": feature.source_sha256,
        "feature_sha256": feature.feature_sha256,
        "transition_selection_sha256": transition.selection_sha256,
        "material": {"young_modulus_mpa": material.young_modulus_mpa, "poisson_ratio": material.poisson_ratio},
        "requested_force_n": [float(v) for v in TOTAL_FORCE_N],
        "mesh_sequence": {
            "global_size_mm": GLOBAL_SIZE_MM,
            "local_targets_mm": list(LOCAL_TARGETS_MM),
            "padding_mm": PADDING_MM,
            "second_order_linear": False,
            "high_order_optimize": HIGH_ORDER_OPTIMIZE,
            "declared_before_c20_result_observation": True,
        },
        "measurement_contract": {
            "qoi_id": "SURFACE_SAMPLED_MAX_AXIAL_NORMAL_STRESS_MPA",
            "operator": "MAX_DIRECT_TET10_SIGMA_X_AT_FROZEN_4_INTERIOR_POINTS_PER_TRANSITION_TRI6",
            "no_nodal_stress_recovery": True,
            "no_stress_smoothing": True,
            "no_integration_point_stress_extrapolation": True,
            "continuous_surface_peak_claim": False,
        },
        "policy": asdict(policy),
        "samples": sample_reports,
        "convergence": {
            "passed": convergence.passed,
            "classification": convergence.classification,
            "checks": convergence.checks,
            "metrics": convergence.metrics,
            "decision_sha256": convergence.decision_sha256,
        },
        "claim_state": decision.state.value,
        "claim_blockers": list(decision.blockers),
        "claim_decision_sha256": decision.decision_sha256,
        "evidence_graph_sha256": graph.fingerprint_sha256,
        "analysis_passport_sha256": passport["passport_sha256"],
        "surface_sampled_qoi_convergence_claim": bool(
            convergence.passed and decision.state is ClaimState.PERMITTED
        ),
        "continuous_surface_peak_convergence_claim": False,
        "empirical_fea_corroboration_eligible": False,
        "empirical_fea_corroboration_performed": False,
        "experimental_validation_claim": False,
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
    }
    report["benchmark_sha256"] = canonical_sha256(report)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "classification": convergence.classification,
        "sampled_surface_qoi_mpa": [sample.sampled_max_axial_normal_stress_mpa for sample in refinement_samples],
        "local_mean_edge_mm": [sample.local_mean_max_corner_edge_mm for sample in refinement_samples],
        "penultimate_qoi_relative_change": convergence.metrics["penultimate_qoi_relative_change"],
        "last_qoi_relative_change": convergence.metrics["last_qoi_relative_change"],
        "last_maximum_meridional_shift_mm": convergence.metrics["last_maximum_meridional_shift_mm"],
        "last_maximum_meridional_shift_over_final_local_metric": convergence.metrics["last_maximum_meridional_shift_over_final_local_metric"],
        "claim_state": decision.state.value,
        "surface_sampled_qoi_convergence_claim": report["surface_sampled_qoi_convergence_claim"],
        "continuous_surface_peak_convergence_claim": False,
        "benchmark_sha256": report["benchmark_sha256"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
