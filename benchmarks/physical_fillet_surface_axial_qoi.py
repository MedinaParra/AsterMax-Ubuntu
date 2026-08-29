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
from astermax.fea.surface_axial_qoi import (
    fillet_surface_axial_stress_measurement_evidence,
    measure_fillet_surface_axial_stress,
    physical_fillet_surface_axial_qoi_claim,
)
from astermax.fea.tet4 import IsotropicMaterial
from astermax.fea.tri6_isoparametric import consistent_tri6_resultant_load_isoparametric
from astermax.fea.tri6_traction import fixed_dofs_from_tri6


STEP = Path("physical_fillet_surface_axial_qoi.step")
OUT = Path("physical_fillet_surface_axial_qoi.json")
GLOBAL_SIZE_MM = 8.0
LOCAL_SIZE_MM = 1.4
PADDING_MM = 5.0
HIGH_ORDER_OPTIMIZE = 2
TOTAL_FORCE_N = np.asarray((1000.0, 0.0, 0.0), dtype=float)
FORCE_RESIDUAL_LIMIT_N = 1.0e-6
MOMENT_RESIDUAL_LIMIT_NMM = 1.0e-4
C18_BENCHMARK_SHA256 = "3ac5cdd4e8e7482bd4f4d40483353dc30f5185da7180ba14f92c4f709d567b51"
C18_DECISION_SHA256 = "cfc62974662f897ec35e5d942531c9bc0d3fd63b282b09258e5273c224a6ec0f"
C18_ARTIFACT_ZIP_SHA256 = "76a172470496034677dcec3ac786df3ed750845c0e88786edd3cff23dab0d6d4"


def _write_fixture() -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c19_physical_surface_qoi")
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
            raise RuntimeError(f"unexpected C19 fixture topology: volumes={volumes}, edges={candidates}")
        gmsh.model.occ.fillet([int(volumes[0][1])], [candidates[0]], [2.0], removeVolume=True)
        gmsh.model.occ.synchronize()
        gmsh.write(str(STEP))
    finally:
        gmsh.finalize()


def main() -> int:
    _write_fixture()
    feature = recognize_x_axis_shaft_shoulder(STEP, feature_id="C19_R10_R15_R2")
    ends = capture_x_axis_shaft_end_faces(STEP)
    transition = capture_face_selection(STEP, feature.transition_face_tag, "C19_TRANSITION_FILLET")
    material = IsotropicMaterial(young_modulus_mpa=200000.0, poisson_ratio=0.3)

    mesh = mesh_step_tet10_around_shoulder(
        STEP,
        feature,
        global_size_mm=GLOBAL_SIZE_MM,
        local_size_mm=LOCAL_SIZE_MM,
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
        raise RuntimeError("C19 mesh failed GL5 Jacobian audit")

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
    reaction_force = np.sum(result.reactions_n, axis=0)
    applied_force = np.asarray(applied.integrated_resultant_n, dtype=float)
    force_residual = float(np.linalg.norm(reaction_force + applied_force))
    load_moment = np.sum(np.cross(mesh.nodes_mm, applied.loads_n), axis=0)
    reaction_moment = np.sum(np.cross(mesh.nodes_mm, result.reactions_n), axis=0)
    moment_residual = float(np.linalg.norm(reaction_moment + load_moment))
    equilibrium_passed = bool(
        force_residual <= FORCE_RESIDUAL_LIMIT_N
        and moment_residual <= MOMENT_RESIDUAL_LIMIT_NMM
        and applied.relative_resultant_error <= 1.0e-12
    )
    equilibrium_payload = {
        "schema": "AsterMaxPhysicalLoadEquilibriumV1",
        "requested_force_n": [float(v) for v in TOTAL_FORCE_N],
        "integrated_force_n": [float(v) for v in applied_force],
        "reaction_force_n": [float(v) for v in reaction_force],
        "force_residual_n": force_residual,
        "moment_residual_nmm": moment_residual,
        "traction_relative_resultant_error": applied.relative_resultant_error,
        "force_residual_limit_n": FORCE_RESIDUAL_LIMIT_N,
        "moment_residual_limit_nmm": MOMENT_RESIDUAL_LIMIT_NMM,
        "passed": equilibrium_passed,
    }
    equilibrium_sha = canonical_sha256(equilibrium_payload)
    if not equilibrium_passed:
        raise RuntimeError(f"C19 equilibrium gate failed: {equilibrium_payload}")

    measurement, samples = measure_fillet_surface_axial_stress(
        measurement_id="C19_PHYSICAL_FILLET_SURFACE_SIGMA_X",
        nodes_mm=mesh.nodes_mm,
        elements=mesh.elements,
        displacement_mm=result.displacement_mm,
        material=material,
        transition_tri6=fillet,
        mesh_sha256=mesh.mesh_sha256,
        transition_selection_sha256=transition.selection_sha256,
    )

    context = ContextOfUse(
        context_id="COU_C19_PHYSICAL_FILLET_SURFACE_AXIAL_QOI",
        engineering_question="What direct sampled axial-normal stress QOI is obtained on the CAD fillet surface for the declared physical axial load case?",
        intended_decision="Establish a reproducible surface-stress measurement for later convergence study; do not claim a continuous peak or empirical corroboration.",
        quantities_of_interest=(measurement.qoi_id,),
        acceptance_criteria=(
            "C18 direct surface operator verification available",
            "positive curved TET10 Jacobians",
            "force and moment equilibrium pass frozen residual gates",
            "surface measurement uses frozen four-point interior TRI6 rule",
        ),
        consequence_level=ConsequenceLevel.HIGH,
        assumptions=("single mesh level is measurement only and cannot establish surface-peak convergence",),
    )
    graph = EvidenceGraph(context)
    c18_evidence = EvidenceRecord(
        evidence_id="C18_SURFACE_OPERATOR_VERIFICATION",
        kind="TET10_SURFACE_STRESS_AFFINE_VERIFICATION",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DOCUMENT,
        description="Exact upstream C18 Windows verification of the direct TET10 surface stress operator.",
        payload_sha256=C18_BENCHMARK_SHA256,
        metadata={
            "benchmark_sha256": C18_BENCHMARK_SHA256,
            "claim_decision_sha256": C18_DECISION_SHA256,
            "artifact_zip_sha256": C18_ARTIFACT_ZIP_SHA256,
        },
    )
    equilibrium_evidence = EvidenceRecord(
        evidence_id=f"PHYSICAL_EQUILIBRIUM:{equilibrium_sha[:16]}",
        kind="PHYSICAL_LOAD_EQUILIBRIUM",
        status=EvidenceStatus.VERIFIED,
        source=EvidenceSource.DETERMINISTIC_CHECK,
        description="Applied and reaction resultants satisfy frozen force and moment equilibrium gates.",
        payload_sha256=equilibrium_sha,
        metadata=equilibrium_payload,
    )
    measurement_evidence = fillet_surface_axial_stress_measurement_evidence(measurement)
    for evidence in (c18_evidence, equilibrium_evidence, measurement_evidence):
        graph.add(evidence)
    graph.link(measurement_evidence.evidence_id, c18_evidence.evidence_id, "USES_VERIFIED_OPERATOR")
    graph.link(measurement_evidence.evidence_id, equilibrium_evidence.evidence_id, "USES_EQUILIBRATED_SOLUTION")
    decision = ClaimEngine.evaluate(physical_fillet_surface_axial_qoi_claim(context.context_id), graph)
    if decision.state is not ClaimState.PERMITTED:
        raise RuntimeError(f"C19 measurement claim unexpectedly blocked: {decision.blockers}")
    passport = build_analysis_passport(graph, (decision,))

    report = {
        "schema": "AsterMaxPhysicalFilletSurfaceAxialQOIBenchmarkV1",
        "classification": "PHYSICAL_FILLET_SURFACE_SAMPLED_AXIAL_QOI_VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT",
        "source_sha256": feature.source_sha256,
        "feature_sha256": feature.feature_sha256,
        "transition_selection_sha256": transition.selection_sha256,
        "mesh_sha256": mesh.mesh_sha256,
        "mesh": {
            "global_size_mm": GLOBAL_SIZE_MM,
            "local_size_mm": LOCAL_SIZE_MM,
            "nodes": int(mesh.nodes_mm.shape[0]),
            "tet10": int(mesh.elements.shape[0]),
            "transition_tri6": int(fillet.shape[0]),
            "second_order_linear": mesh.second_order_linear,
            "high_order_optimize": mesh.high_order_optimize,
            "jacobian_gl5_minimum": jac.minimum_det_jacobian,
        },
        "material": {"young_modulus_mpa": material.young_modulus_mpa, "poisson_ratio": material.poisson_ratio},
        "equilibrium": equilibrium_payload,
        "equilibrium_sha256": equilibrium_sha,
        "measurement": asdict(measurement),
        "sample_sha256": [sample.sample_sha256 for sample in samples],
        "claim_state": decision.state.value,
        "claim_blockers": list(decision.blockers),
        "claim_decision_sha256": decision.decision_sha256,
        "evidence_graph_sha256": graph.fingerprint_sha256,
        "analysis_passport_sha256": passport["passport_sha256"],
        "physical_surface_qoi_computed": True,
        "continuous_surface_peak_claim": False,
        "surface_peak_convergence_claim": False,
        "empirical_fea_corroboration_eligible": False,
        "empirical_fea_corroboration_performed": False,
        "experimental_validation_claim": False,
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
    }
    report["benchmark_sha256"] = canonical_sha256(report)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "classification": report["classification"],
        "nodes": report["mesh"]["nodes"],
        "tet10": report["mesh"]["tet10"],
        "transition_tri6": report["mesh"]["transition_tri6"],
        "surface_sample_count": measurement.sample_count,
        "surface_sigma_x_min_mpa": measurement.minimum_axial_normal_stress_mpa,
        "surface_sigma_x_mean_mpa": measurement.mean_axial_normal_stress_mpa,
        "surface_sigma_x_sampled_max_mpa": measurement.maximum_axial_normal_stress_mpa,
        "maximum_point_mm": measurement.maximum_point_mm,
        "force_residual_n": force_residual,
        "moment_residual_nmm": moment_residual,
        "claim_state": decision.state.value,
        "surface_peak_convergence_claim": False,
        "benchmark_sha256": report["benchmark_sha256"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
