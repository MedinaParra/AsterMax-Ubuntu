from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from astermax.credibility import canonical_sha256
from astermax.fea.axisymmetric_shoulder import recognize_x_axis_shaft_shoulder
from astermax.fea.curved_feature_geometry import measure_curved_shoulder_geometry_error
from astermax.fea.feature_adaptivity import mesh_step_tet10_around_shoulder
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.tet10 import tet10_stiffness
from astermax.fea.tet10_isoparametric import (
    relative_matrix_difference,
    tet10_isoparametric_jacobian_audit,
    tet10_stiffness_isoparametric_reference,
)
from astermax.fea.tet4 import IsotropicMaterial


STEP = Path("curved_tet10_code_verification.step")
OUT = Path("curved_tet10_code_verification.json")
GLOBAL_SIZE_MM = 8.0
LOCAL_SIZE_MM = 2.5
PADDING_MM = 5.0
MAX_SAMPLED_SURFACE_ERROR_OVER_FILLET_RADIUS = 0.01
MAX_REFERENCE_ORDER4_VS5_RELATIVE_STIFFNESS = 1.0e-4


def _write_fixture() -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("curved_tet10_code_verification")
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


def _midside_geometry_deviation(coords: np.ndarray) -> float:
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


def main() -> int:
    _write_fixture()
    feature = recognize_x_axis_shaft_shoulder(STEP, feature_id="CURVED_TET10_VERIFY_SHOULDER")
    mesh = mesh_step_tet10_around_shoulder(
        STEP,
        feature,
        global_size_mm=GLOBAL_SIZE_MM,
        local_size_mm=LOCAL_SIZE_MM,
        padding_mm=PADDING_MM,
        second_order_linear=False,
    )
    if mesh.second_order_linear:
        raise RuntimeError("curved verification mesh unexpectedly reports straight-sided mode")
    geometry = measure_curved_shoulder_geometry_error(
        STEP,
        feature,
        global_size_mm=GLOBAL_SIZE_MM,
        local_size_mm=LOCAL_SIZE_MM,
        padding_mm=PADDING_MM,
    )
    if geometry.mesh_sha256 != mesh.mesh_sha256:
        raise RuntimeError(f"CURVED_GEOMETRY_AUDIT_MESH_IDENTITY_MISMATCH:{geometry.mesh_sha256}!={mesh.mesh_sha256}")

    curved_indices = []
    deviations = []
    scales = []
    for index, conn in enumerate(mesh.elements):
        coords = mesh.nodes_mm[conn]
        deviation = _midside_geometry_deviation(coords)
        scale = max(float(np.linalg.norm(coords[:4].max(axis=0) - coords[:4].min(axis=0))), 1.0)
        deviations.append(deviation)
        scales.append(scale)
        if deviation > scale * 1.0e-10:
            curved_indices.append(index)
    if not curved_indices:
        raise RuntimeError("GMSH_CURVED_MODE_PRODUCED_NO_CURVED_TET10_ELEMENTS")

    minimum_det = float("inf")
    minimum_ratio = float("inf")
    for index in curved_indices:
        audit = tet10_isoparametric_jacobian_audit(mesh.nodes_mm[mesh.elements[index]], quadrature_order=4)
        minimum_det = min(minimum_det, audit.minimum_det_jacobian)
        minimum_ratio = min(minimum_ratio, audit.minimum_over_maximum_ratio)

    worst_index = int(curved_indices[int(np.argmax(np.asarray(deviations)[curved_indices]))])
    worst_coords = mesh.nodes_mm[mesh.elements[worst_index]]
    material = IsotropicMaterial(young_modulus_mpa=200000.0, poisson_ratio=0.3)
    k_four = tet10_stiffness(worst_coords, material)
    k_ref4 = tet10_stiffness_isoparametric_reference(worst_coords, material, quadrature_order=4)
    k_ref5 = tet10_stiffness_isoparametric_reference(worst_coords, material, quadrature_order=5)
    four_vs_ref5 = relative_matrix_difference(k_four, k_ref5)
    ref4_vs_ref5 = relative_matrix_difference(k_ref4, k_ref5)

    checks = {
        "curved_elements_exist": len(curved_indices) > 0,
        "all_audited_curved_jacobians_positive": minimum_det > 0.0,
        "curved_geometry_audit_matches_mesh_sha": geometry.mesh_sha256 == mesh.mesh_sha256,
        "cad_projected_midside_nodes_on_fillet": geometry.max_midside_deviation_over_fillet_radius <= 1.0e-8,
        "sampled_interpolated_surface_within_internal_target": (
            geometry.max_sampled_surface_deviation_over_fillet_radius <= MAX_SAMPLED_SURFACE_ERROR_OVER_FILLET_RADIUS
        ),
        "independent_reference_quadrature_converged_on_worst_curved_element": (
            ref4_vs_ref5 <= MAX_REFERENCE_ORDER4_VS5_RELATIVE_STIFFNESS
        ),
        "historical_four_point_not_used_as_curved_reference": True,
    }
    passed = all(checks.values())

    report = {
        "schema": "AsterMaxCurvedTet10CodeVerificationBenchmarkV1",
        "classification": "CURVED_ISOPARAMETRIC_CODE_VERIFICATION_NOT_SOLVER_VALIDATION",
        "curved_tet10_solver_enabled": False,
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
        "geometry": {
            "source_sha256": feature.source_sha256,
            "feature_sha256": feature.feature_sha256,
            "fillet_radius_mm": feature.fillet_radius_mm,
            "mesh_sha256": mesh.mesh_sha256,
            "nodes": int(mesh.nodes_mm.shape[0]),
            "tet10": int(mesh.elements.shape[0]),
            "curved_tet10_count": len(curved_indices),
            "maximum_element_midside_offset_from_chord_midpoint_mm": float(np.max(deviations)),
            "fillet_midside_cad_deviation_max_mm": geometry.midside_nodes.maximum_mm,
            "fillet_sampled_interpolated_surface_deviation_max_mm": geometry.sampled_interpolated_surface.maximum_mm,
            "fillet_sampled_interpolated_surface_deviation_over_radius": geometry.max_sampled_surface_deviation_over_fillet_radius,
            "geometry_evidence_sha256": geometry.evidence_sha256,
        },
        "jacobian_audit": {
            "method": "DUFFY_GL4_64_POINTS_ON_EVERY_CURVED_ELEMENT",
            "minimum_det_jacobian": minimum_det,
            "minimum_det_over_maximum_ratio": minimum_ratio,
        },
        "quadrature_audit_worst_curved_element": {
            "element_index_runtime_only": worst_index,
            "four_point_vs_duffy_order5_relative_stiffness": four_vs_ref5,
            "duffy_order4_vs_order5_relative_stiffness": ref4_vs_ref5,
            "reference_acceptance_limit": MAX_REFERENCE_ORDER4_VS5_RELATIVE_STIFFNESS,
            "production_curved_quadrature_selected": False,
        },
        "internal_geometry_target": {
            "max_sampled_surface_deviation_over_fillet_radius": MAX_SAMPLED_SURFACE_ERROR_OVER_FILLET_RADIUS,
            "external_standard": False,
        },
        "checks": checks,
        "passed": passed,
        "interpretation_boundary": (
            "C10 verifies mathematical support for general TET10 isoparametric mapping and audits a CAD-projected Gmsh curved mesh. "
            "It does not enable a curved production solver. The historical four-point stiffness rule remains verified only for straight-sided geometry; Duffy GL4/GL5 are independent verification references, not yet a selected production integration policy."
        ),
    }
    report["benchmark_sha256"] = canonical_sha256(report)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    print(f"wrote {OUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
