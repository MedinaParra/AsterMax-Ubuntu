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
    build_analysis_passport,
    canonical_sha256,
)
from astermax.fea.axisymmetric_shoulder import recognize_x_axis_shaft_shoulder
from astermax.fea.curved_tet10_solver import audit_curved_tet10_mesh_jacobians
from astermax.fea.feature_adaptivity import mesh_step_tet10_around_shoulder
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.persistent_geometry import capture_face_selection
from astermax.fea.surface_stress_verification import (
    surface_stress_affine_verification_evidence,
    tet10_surface_stress_affine_verification_claim,
    verify_affine_surface_axial_stress,
)
from astermax.fea.tet10_surface_stress import evaluate_tri6_surface_stress_sample
from astermax.fea.tet4 import IsotropicMaterial


STEP = Path("tet10_surface_axial_stress_affine.step")
OUT = Path("tet10_surface_axial_stress_affine.json")
MATERIAL = IsotropicMaterial(young_modulus_mpa=200000.0, poisson_ratio=0.3)
AXIAL_STRAIN = 2.5e-4
EXPECTED_SIGMA_X_MPA = MATERIAL.young_modulus_mpa * AXIAL_STRAIN


def _write_fixture() -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c18_surface_affine")
        small = gmsh.model.occ.addCylinder(0.0, 0.0, 0.0, 40.0, 0.0, 0.0, 10.0)
        large = gmsh.model.occ.addCylinder(40.0, 0.0, 0.0, 40.0, 0.0, 0.0, 15.0)
        gmsh.model.occ.fuse([(3, small)], [(3, large)])
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        fillet_edges = []
        for _, tag in gmsh.model.getEntities(1):
            box = tuple(float(v) for v in gmsh.model.getBoundingBox(1, int(tag)))
            x_mid = 0.5 * (box[0] + box[3])
            if (
                abs(x_mid - 40.0) <= 1.0e-4
                and box[3] - box[0] <= 1.0e-4
                and abs(0.5 * (box[4] - box[1]) - 10.0) <= 1.0e-4
                and abs(0.5 * (box[5] - box[2]) - 10.0) <= 1.0e-4
            ):
                fillet_edges.append(int(tag))
        if len(volumes) != 1 or len(fillet_edges) != 1:
            raise RuntimeError(f"unexpected C18 fixture topology: volumes={volumes}, edges={fillet_edges}")
        gmsh.model.occ.fillet([int(volumes[0][1])], fillet_edges, [2.0], removeVolume=True)
        gmsh.model.occ.synchronize()
        gmsh.write(str(STEP))
    finally:
        gmsh.finalize()


def main() -> int:
    _write_fixture()
    feature = recognize_x_axis_shaft_shoulder(STEP, feature_id="C18_R10_R15_R2")
    transition = capture_face_selection(
        STEP,
        feature.transition_face_tag,
        "C18_TRANSITION_FILLET_SURFACE",
        relative_tolerance=1.0e-8,
    )
    mesh = mesh_step_tet10_around_shoulder(
        STEP,
        feature,
        global_size_mm=8.0,
        local_size_mm=2.0,
        padding_mm=4.0,
        face_selections=(transition,),
        second_order_linear=False,
        high_order_optimize=2,
    )
    tri6 = mesh.surface_tri6_by_selection[transition.selection_id]
    if tri6.shape[0] < 4:
        raise RuntimeError(f"C18 transition surface unexpectedly sparse: {tri6.shape}")

    jac = audit_curved_tet10_mesh_jacobians(mesh.nodes_mm, mesh.elements, quadrature_order=5)
    if not jac.all_positive:
        raise RuntimeError(f"C18 curved TET10 mesh contains invalid Jacobians: {asdict(jac)}")

    displacement = np.zeros_like(mesh.nodes_mm)
    displacement[:, 0] = AXIAL_STRAIN * mesh.nodes_mm[:, 0]
    displacement[:, 1] = -MATERIAL.poisson_ratio * AXIAL_STRAIN * mesh.nodes_mm[:, 1]
    displacement[:, 2] = -MATERIAL.poisson_ratio * AXIAL_STRAIN * mesh.nodes_mm[:, 2]

    samples = tuple(
        evaluate_tri6_surface_stress_sample(
            mesh.nodes_mm,
            mesh.elements,
            displacement,
            MATERIAL,
            face,
            (1.0 / 3.0, 1.0 / 3.0),
        )
        for face in tri6
    )
    verification = verify_affine_surface_axial_stress(
        "C18_CURVED_CAD_FILLET_AFFINE_PATCH",
        samples,
        expected_axial_normal_stress_mpa=EXPECTED_SIGMA_X_MPA,
        maximum_absolute_error_mpa=1.0e-7,
        maximum_relative_error=2.0e-9,
    )
    if not verification.passed:
        raise RuntimeError(f"C18 affine surface stress verification failed: {asdict(verification)}")

    context = ContextOfUse(
        context_id="COU_C18_TET10_SURFACE_AXIAL_STRESS_AFFINE",
        engineering_question="Does the direct TET10 boundary stress operator reproduce an exact affine uniaxial field on the curved CAD fillet surface?",
        intended_decision="Permit the direct surface stress operator for later QOI studies; do not infer physical validation or local-stress convergence.",
        quantities_of_interest=("direct CAD-surface axial normal stress",),
        acceptance_criteria=(
            "all curved TET10 Jacobians positive at GL5 audit points",
            "every selected transition TRI6 resolves to exactly one TET10 parent",
            "maximum affine sigma_x error within frozen absolute and relative tolerances",
            "no nodal recovery, smoothing or IP-stress extrapolation",
        ),
        consequence_level=ConsequenceLevel.HIGH,
        assumptions=("affine displacement field is a code-verification fixture, not a physical shoulder solution",),
    )
    graph = EvidenceGraph(context)
    evidence = surface_stress_affine_verification_evidence(verification)
    graph.add(evidence)
    decision = ClaimEngine.evaluate(
        tet10_surface_stress_affine_verification_claim(context.context_id), graph
    )
    if decision.state is not ClaimState.PERMITTED:
        raise RuntimeError(f"C18 claim unexpectedly blocked: {decision.blockers}")
    passport = build_analysis_passport(graph, (decision,))

    report = {
        "schema": "AsterMaxTet10SurfaceAxialStressAffineBenchmarkV1",
        "classification": "CURVED_CAD_TET10_SURFACE_STRESS_AFFINE_CODE_VERIFICATION_NOT_PHYSICAL_RESULT",
        "source_sha256": feature.source_sha256,
        "feature_sha256": feature.feature_sha256,
        "transition_selection_sha256": transition.selection_sha256,
        "transition_surface_tri6_count": int(tri6.shape[0]),
        "mesh_sha256": mesh.mesh_sha256,
        "mesh_nodes": int(mesh.nodes_mm.shape[0]),
        "mesh_tet10": int(mesh.elements.shape[0]),
        "mesh_policy": {
            "global_size_mm": mesh.global_size_mm,
            "local_size_mm": mesh.local_size_mm,
            "second_order_linear": mesh.second_order_linear,
            "high_order_optimize": mesh.high_order_optimize,
        },
        "jacobian_audit": asdict(jac),
        "affine_reference": {
            "young_modulus_mpa": MATERIAL.young_modulus_mpa,
            "poisson_ratio": MATERIAL.poisson_ratio,
            "axial_strain": AXIAL_STRAIN,
            "expected_sigma_x_mpa": EXPECTED_SIGMA_X_MPA,
        },
        "verification": asdict(verification),
        "sample_sha256": [sample.sample_sha256 for sample in samples],
        "claim_state": decision.state.value,
        "claim_blockers": list(decision.blockers),
        "claim_decision_sha256": decision.decision_sha256,
        "evidence_graph_sha256": graph.fingerprint_sha256,
        "analysis_passport_sha256": passport["passport_sha256"],
        "surface_stress_operator_affine_verified": True,
        "physical_shoulder_solution_claim": False,
        "surface_peak_convergence_claim": False,
        "empirical_fea_corroboration_claim": False,
        "experimental_validation_claim": False,
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
        "interpretation_boundary": (
            "C18 verifies only direct stress evaluation from the TET10 displacement gradient on the CAD-projected transition surface under an exact affine field. "
            "It does not solve the physical shoulder load case and does not establish surface-peak convergence."
        ),
    }
    report["benchmark_sha256"] = canonical_sha256(report)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "classification": report["classification"],
        "tri6_count": report["transition_surface_tri6_count"],
        "tet10": report["mesh_tet10"],
        "minimum_det_jacobian": verification.minimum_det_jacobian,
        "expected_sigma_x_mpa": EXPECTED_SIGMA_X_MPA,
        "minimum_sigma_x_mpa": verification.minimum_axial_normal_stress_mpa,
        "maximum_sigma_x_mpa": verification.maximum_axial_normal_stress_mpa,
        "maximum_absolute_error_mpa": verification.maximum_absolute_error_mpa,
        "maximum_relative_error": verification.maximum_relative_error,
        "claim_state": decision.state.value,
        "benchmark_sha256": report["benchmark_sha256"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
