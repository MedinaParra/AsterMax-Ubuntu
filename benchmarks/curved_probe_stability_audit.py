from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from astermax.credibility import canonical_sha256
from astermax.fea.axisymmetric_shoulder import recognize_x_axis_shaft_shoulder
from astermax.fea.curved_neighborhood_integral import integrate_curved_tet10_fixed_tangency_neighborhood
from astermax.fea.curved_shoulder_sector_probe import sample_curved_tet10_sectorized_small_diameter_fillet_ring
from astermax.fea.curved_tet10_solver import audit_curved_tet10_mesh_jacobians, solve_linear_static_curved_tet10
from astermax.fea.feature_adaptivity import mesh_step_tet10_around_shoulder
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.shaft_end_faces import capture_x_axis_shaft_end_faces
from astermax.fea.tet4 import IsotropicMaterial
from astermax.fea.tri6_isoparametric import consistent_tri6_resultant_load_isoparametric
from astermax.fea.tri6_traction import fixed_dofs_from_tri6


STEP = Path("curved_probe_stability_audit.step")
OUT = Path("curved_probe_stability_audit.json")
GLOBAL_SIZE_MM = 8.0
REPLAY_LOCAL_TARGETS_MM = (1.6, 1.4)
HIGH_ORDER_OPTIMIZE = 2
PADDING_MM = 5.0
TOTAL_FORCE_N = np.asarray((1000.0, 0.0, 0.0), dtype=float)
SECTOR_COUNT = 12
NEAREST_IP_DISTANCE_LIMIT_MM = 2.0
FIXED_NEIGHBORHOOD_RADIUS_MM = 0.5  # R/4 for the declared R2 fillet fixture.
INHERITED_NEIGHBORHOOD_STABILITY_TOLERANCE = 0.03
FIXED_NEIGHBORHOOD_VOLUME_STABILITY_TOLERANCE = 0.05


def _json_native(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _json_native(value.item())
    if isinstance(value, dict):
        return {str(key): _json_native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_native(item) for item in value]
    return value


def _relative_change(a: float, b: float) -> float:
    return abs(float(b) - float(a)) / max(abs(float(a)), abs(float(b)), 1.0e-12)


def _wrapped_angle_delta(a: float, b: float) -> float:
    return abs((float(a) - float(b) + math.pi) % (2.0 * math.pi) - math.pi)


def _write_fixture() -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("curved_probe_stability_audit")
        small = gmsh.model.occ.addCylinder(0.0, 0.0, 0.0, 40.0, 0.0, 0.0, 10.0)
        large = gmsh.model.occ.addCylinder(40.0, 0.0, 0.0, 40.0, 0.0, 0.0, 15.0)
        gmsh.model.occ.fuse([(3, small)], [(3, large)])
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        edges = []
        for _, tag in gmsh.model.getEntities(1):
            box = tuple(float(v) for v in gmsh.model.getBoundingBox(1, int(tag)))
            x_mid = 0.5 * (box[0] + box[3])
            if (
                abs(x_mid - 40.0) <= 1.0e-4
                and box[3] - box[0] <= 1.0e-4
                and abs(0.5 * (box[4] - box[1]) - 10.0) <= 1.0e-4
                and abs(0.5 * (box[5] - box[2]) - 10.0) <= 1.0e-4
            ):
                edges.append(int(tag))
        if len(volumes) != 1 or len(edges) != 1:
            raise RuntimeError(f"fixture topology unexpected: volumes={volumes}, fillet_edges={edges}")
        gmsh.model.occ.fillet([int(volumes[0][1])], [edges[0]], [2.0], removeVolume=True)
        gmsh.model.occ.synchronize()
        gmsh.write(str(STEP))
    finally:
        gmsh.finalize()


def _probe_sample_payload(probe) -> list[dict[str, Any]]:
    width = 2.0 * math.pi / probe.sector_count
    out = []
    for sample in probe.samples:
        center = (sample.sector_index + 0.5) * width
        out.append(
            {
                "sector_index": sample.sector_index,
                "element_index_runtime_only": sample.element_index,
                "integration_point_index": sample.integration_point_index,
                "coordinate_mm": list(sample.coordinate_mm),
                "azimuth_rad": sample.azimuth_rad,
                "sector_center_rad": center,
                "angular_offset_from_sector_center_rad": _wrapped_angle_delta(sample.azimuth_rad, center),
                "distance_to_probe_ring_mm": sample.distance_to_probe_ring_mm,
                "von_mises_mpa": sample.von_mises_mpa,
            }
        )
    return out


def _probe_statistics(probe) -> dict[str, float]:
    stress = np.asarray([sample.von_mises_mpa for sample in probe.samples], dtype=float)
    distance = np.asarray([sample.distance_to_probe_ring_mm for sample in probe.samples], dtype=float)
    width = 2.0 * math.pi / probe.sector_count
    angular_offsets = np.asarray(
        [
            _wrapped_angle_delta(sample.azimuth_rad, (sample.sector_index + 0.5) * width)
            for sample in probe.samples
        ],
        dtype=float,
    )
    stress_mean = float(np.mean(stress))
    stress_std = float(np.std(stress, ddof=0))
    if float(np.std(distance)) > 0.0 and stress_std > 0.0:
        corr = float(np.corrcoef(distance, stress)[0, 1])
    else:
        corr = 0.0
    return {
        "stress_mean_mpa": stress_mean,
        "stress_std_mpa": stress_std,
        "stress_coefficient_of_variation": stress_std / max(abs(stress_mean), 1.0e-12),
        "stress_range_mpa": float(np.max(stress) - np.min(stress)),
        "distance_mean_mm": float(np.mean(distance)),
        "distance_std_mm": float(np.std(distance, ddof=0)),
        "distance_max_mm": float(np.max(distance)),
        "max_angular_offset_from_sector_center_rad": float(np.max(angular_offsets)),
        "mean_angular_offset_from_sector_center_rad": float(np.mean(angular_offsets)),
        "distance_stress_pearson_correlation": corr,
    }


def main() -> int:
    _write_fixture()
    feature = recognize_x_axis_shaft_shoulder(STEP, feature_id="C12A_PROBE_STABILITY")
    ends = capture_x_axis_shaft_end_faces(STEP)
    material = IsotropicMaterial(young_modulus_mpa=200000.0, poisson_ratio=0.3)
    replays = []

    for local_size in REPLAY_LOCAL_TARGETS_MM:
        mesh = mesh_step_tet10_around_shoulder(
            STEP,
            feature,
            global_size_mm=GLOBAL_SIZE_MM,
            local_size_mm=local_size,
            padding_mm=PADDING_MM,
            face_selections=(ends.x_min, ends.x_max),
            second_order_linear=False,
            high_order_optimize=HIGH_ORDER_OPTIMIZE,
        )
        jac = audit_curved_tet10_mesh_jacobians(mesh.nodes_mm, mesh.elements, quadrature_order=5)
        if not jac.all_positive:
            raise RuntimeError(f"C12a replay mesh has non-positive GL5 Jacobian at local {local_size}")
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
        probe = sample_curved_tet10_sectorized_small_diameter_fillet_ring(
            mesh,
            feature,
            integration_point_natural_coordinates=result.integration_point_natural_coordinates,
            integration_point_von_mises_mpa=result.integration_point_von_mises_mpa,
            sector_count=SECTOR_COUNT,
            maximum_allowed_distance_mm=NEAREST_IP_DISTANCE_LIMIT_MM,
        )
        integral = integrate_curved_tet10_fixed_tangency_neighborhood(
            mesh,
            feature,
            integration_point_natural_coordinates=result.integration_point_natural_coordinates,
            integration_point_weights=result.integration_point_weights,
            integration_point_von_mises_mpa=result.integration_point_von_mises_mpa,
            maximum_meridional_distance_mm=FIXED_NEIGHBORHOOD_RADIUS_MM,
        )
        replays.append(
            {
                "local_target_size_mm": float(local_size),
                "mesh_sha256": mesh.mesh_sha256,
                "nodes": int(mesh.nodes_mm.shape[0]),
                "tet10": int(mesh.elements.shape[0]),
                "local_mean_max_corner_edge_mm": mesh.local_mean_max_corner_edge_mm,
                "jacobian_gl5": {
                    "all_positive": jac.all_positive,
                    "minimum_det_jacobian": jac.minimum_det_jacobian,
                    "invalid_element_count": jac.invalid_element_count,
                    "nonpositive_point_count": jac.nonpositive_point_count,
                },
                "nearest_actual_ip_sector_probe": {
                    "probe_sha256": probe.probe_sha256,
                    "statistics": _probe_statistics(probe),
                    "samples": _probe_sample_payload(probe),
                },
                "fixed_physical_neighborhood_integral": {
                    "integral_sha256": integral.integral_sha256,
                    "maximum_meridional_distance_mm": integral.maximum_meridional_distance_mm,
                    "selected_integration_point_count": integral.selected_integration_point_count,
                    "sampled_physical_volume_mm3": integral.sampled_physical_volume_mm3,
                    "weighted_mean_von_mises_mpa": integral.weighted_mean_von_mises_mpa,
                    "weighted_rms_von_mises_mpa": integral.weighted_rms_von_mises_mpa,
                    "weighted_std_von_mises_mpa": integral.weighted_std_von_mises_mpa,
                    "minimum_von_mises_mpa": integral.minimum_von_mises_mpa,
                    "maximum_von_mises_mpa": integral.maximum_von_mises_mpa,
                    "maximum_selected_distance_mm": integral.maximum_selected_distance_mm,
                    "quadrature_sha256": integral.quadrature_sha256,
                },
            }
        )

    coarse, fine = replays
    coarse_probe = coarse["nearest_actual_ip_sector_probe"]
    fine_probe = fine["nearest_actual_ip_sector_probe"]
    paired = []
    for a, b in zip(coarse_probe["samples"], fine_probe["samples"]):
        if a["sector_index"] != b["sector_index"]:
            raise RuntimeError("sector ordering changed during C12a replay")
        paired.append(
            {
                "sector_index": a["sector_index"],
                "coarse_stress_mpa": a["von_mises_mpa"],
                "fine_stress_mpa": b["von_mises_mpa"],
                "relative_stress_change": _relative_change(a["von_mises_mpa"], b["von_mises_mpa"]),
                "coarse_distance_mm": a["distance_to_probe_ring_mm"],
                "fine_distance_mm": b["distance_to_probe_ring_mm"],
                "azimuth_change_rad": _wrapped_angle_delta(a["azimuth_rad"], b["azimuth_rad"]),
            }
        )

    nearest_mean_change = _relative_change(
        coarse_probe["statistics"]["stress_mean_mpa"],
        fine_probe["statistics"]["stress_mean_mpa"],
    )
    coarse_integral = coarse["fixed_physical_neighborhood_integral"]
    fine_integral = fine["fixed_physical_neighborhood_integral"]
    fixed_mean_change = _relative_change(
        coarse_integral["weighted_mean_von_mises_mpa"],
        fine_integral["weighted_mean_von_mises_mpa"],
    )
    fixed_volume_change = _relative_change(
        coarse_integral["sampled_physical_volume_mm3"],
        fine_integral["sampled_physical_volume_mm3"],
    )

    nearest_stable = nearest_mean_change <= INHERITED_NEIGHBORHOOD_STABILITY_TOLERANCE
    fixed_mean_stable = fixed_mean_change <= INHERITED_NEIGHBORHOOD_STABILITY_TOLERANCE
    fixed_volume_stable = fixed_volume_change <= FIXED_NEIGHBORHOOD_VOLUME_STABILITY_TOLERANCE
    if not nearest_stable and fixed_mean_stable and fixed_volume_stable:
        classification = "NEAREST_IP_PROBE_UNSTABLE_FIXED_PHYSICAL_INTEGRAL_STABLE"
    elif nearest_stable and fixed_mean_stable and fixed_volume_stable:
        classification = "BOTH_OBSERVATION_METHODS_STABLE"
    elif not fixed_mean_stable or not fixed_volume_stable:
        classification = "FIXED_PHYSICAL_NEIGHBORHOOD_NOT_YET_STABLE"
    else:
        classification = "INCONCLUSIVE"

    report = {
        "schema": "AsterMaxCurvedProbeStabilityAuditV1",
        "classification": classification,
        "diagnostic_only": True,
        "c12_result_preserved": "LOCAL_STRESS_NOT_CONVERGED",
        "local_stress_convergence_claim": False,
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
        "source_sha256": feature.source_sha256,
        "feature_sha256": feature.feature_sha256,
        "physics_contract": {
            "geometry": "AXISYMMETRIC_R10_TO_R15_R2_FILLET",
            "material": "ISOTROPIC_LINEAR_ELASTIC",
            "load": "1000_N_AXIAL_RESULTANT",
            "continuum_expectation": "AZIMUTHALLY_INVARIANT_STRESS_FIELD",
        },
        "predeclared_replay": {
            "local_targets_mm": list(REPLAY_LOCAL_TARGETS_MM),
            "global_target_mm": GLOBAL_SIZE_MM,
            "high_order_optimize": HIGH_ORDER_OPTIMIZE,
            "nearest_ip_sector_count": SECTOR_COUNT,
            "fixed_physical_neighborhood_radius_mm": FIXED_NEIGHBORHOOD_RADIUS_MM,
            "fixed_radius_basis": "R_OVER_4_FOR_DECLARED_R2_FILLET",
            "inherited_stress_stability_tolerance": INHERITED_NEIGHBORHOOD_STABILITY_TOLERANCE,
            "fixed_neighborhood_volume_stability_tolerance": FIXED_NEIGHBORHOOD_VOLUME_STABILITY_TOLERANCE,
        },
        "replays": replays,
        "paired_sector_diagnostic": paired,
        "comparison": {
            "nearest_ip_sector_mean_relative_change": nearest_mean_change,
            "nearest_ip_sector_mean_stable_at_inherited_3pct": nearest_stable,
            "fixed_physical_integral_mean_relative_change": fixed_mean_change,
            "fixed_physical_integral_mean_stable_at_inherited_3pct": fixed_mean_stable,
            "fixed_physical_integral_volume_relative_change": fixed_volume_change,
            "fixed_physical_integral_volume_stable_at_5pct": fixed_volume_stable,
            "max_paired_sector_stress_relative_change": max(item["relative_stress_change"] for item in paired),
            "mean_paired_sector_stress_relative_change": float(np.mean([item["relative_stress_change"] for item in paired])),
            "max_paired_sector_azimuth_change_rad": max(item["azimuth_change_rad"] for item in paired),
        },
        "interpretation_boundary": (
            "C12a is a diagnostic of the observation operator after C12 failed its nearest-actual-IP sector-ring mean gate. "
            "It replays only the two already-declared final mesh levels and cannot enable local_stress_convergence_claim. "
            "The fixed physical neighborhood is a volume-weighted integral over actual Duffy GL4 integration points within R/4=0.5 mm meridional distance of the tangency ring. "
            "Its purpose is to distinguish remesh-dependent point-selection scatter from instability of a fixed physical neighborhood; it is not a surface peak estimate or physical validation."
        ),
    }
    native = _json_native(report)
    native["audit_sha256"] = canonical_sha256(native)
    OUT.write_text(json.dumps(native, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(native, indent=2, sort_keys=True, allow_nan=False))
    print(f"wrote {OUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
