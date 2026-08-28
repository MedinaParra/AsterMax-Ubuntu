from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from astermax.credibility import canonical_sha256
from astermax.fea.axisymmetric_shoulder import recognize_x_axis_shaft_shoulder
from astermax.fea.curved_feature_geometry import interpolated_tri6_points
from astermax.fea.feature_adaptivity import _mesh_hash, shoulder_local_box
from astermax.fea.feature_geometry_error import (
    _closest_point_deviations,
    _unique_transition_surface,
    summarize_deviations,
)
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.tet10 import tet10_shape_derivatives, tet10_stiffness
from astermax.fea.tet10_isoparametric import (
    duffy_tetra_gauss_rule,
    relative_matrix_difference,
    tet10_stiffness_isoparametric_reference,
)
from astermax.fea.tet4 import IsotropicMaterial


STEP = Path("curved_tet10_high_order_optimize.step")
OUT = Path("curved_tet10_high_order_optimize.json")
GLOBAL_SIZE_MM = 8.0
PADDING_MM = 5.0
MAX_SAMPLED_SURFACE_ERROR_OVER_FILLET_RADIUS = 0.01
MAX_MIDSIDE_CAD_ERROR_OVER_FILLET_RADIUS = 1.0e-8
MAX_REFERENCE_ORDER4_VS5_RELATIVE_STIFFNESS = 1.0e-4

# Predeclared before observing C10b results. Baseline is a control only.
CONTROL = {"candidate_id": "BASELINE_HO0_LOCAL2P5", "local_size_mm": 2.5, "high_order_optimize": 0}
ADMISSIBLE_SEQUENCE = (
    {"candidate_id": "ELASTIC_PLUS_OPT_HO2_LOCAL2P5", "local_size_mm": 2.5, "high_order_optimize": 2},
    {"candidate_id": "ELASTIC_PLUS_OPT_HO2_LOCAL2P0", "local_size_mm": 2.0, "high_order_optimize": 2},
)


def _write_fixture() -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("curved_tet10_high_order_optimize")
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


def _midside_offset_from_chords(coords: np.ndarray) -> float:
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


def _extract_tet10(gmsh, node_tags: np.ndarray) -> np.ndarray:
    tag_to_index = {int(tag): index for index, tag in enumerate(node_tags)}
    types, _, blocks = gmsh.model.mesh.getElements(3)
    raw_tets: list[np.ndarray] = []
    unsupported: list[int] = []
    for element_type, connectivity in zip(types, blocks):
        raw = np.asarray(connectivity, dtype=np.int64)
        if not raw.size:
            continue
        if int(element_type) == 11:
            raw_tets.append(raw.reshape((-1, 10)))
        else:
            unsupported.append(int(element_type))
    if unsupported:
        raise RuntimeError("NON_TET10_VOLUME_TYPES:" + ",".join(map(str, sorted(set(unsupported)))))
    if not raw_tets:
        raise RuntimeError("NO_TET10_VOLUME_ELEMENTS")
    return np.asarray(
        [[tag_to_index[int(tag)] for tag in row] for row in np.vstack(raw_tets)],
        dtype=np.int64,
    )


def _extract_transition_tri6(gmsh, transition_tag: int, node_tags: np.ndarray) -> np.ndarray:
    tag_to_index = {int(tag): index for index, tag in enumerate(node_tags)}
    types, _, blocks = gmsh.model.mesh.getElements(2, int(transition_tag))
    raw_faces: list[np.ndarray] = []
    unsupported: list[int] = []
    for element_type, connectivity in zip(types, blocks):
        raw = np.asarray(connectivity, dtype=np.int64)
        if not raw.size:
            continue
        if int(element_type) == 9:
            raw_faces.append(raw.reshape((-1, 6)))
        else:
            unsupported.append(int(element_type))
    if unsupported:
        raise RuntimeError("TRANSITION_NON_TRI6_TYPES:" + ",".join(map(str, sorted(set(unsupported)))))
    if not raw_faces:
        raise RuntimeError("TRANSITION_HAS_NO_TRI6")
    return np.asarray(
        [[tag_to_index[int(tag)] for tag in row] for row in np.vstack(raw_faces)],
        dtype=np.int64,
    )


def _raw_jacobian_audit(nodes: np.ndarray, elements: np.ndarray) -> dict:
    rule = duffy_tetra_gauss_rule(4)
    derivatives = tuple(tet10_shape_derivatives(point) for point in rule.points)
    minimum_det = float("inf")
    minimum_positive_ratio: float | None = None
    invalid_indices: list[int] = []
    nonpositive_sample_count = 0
    valid_indices: list[int] = []
    midside_offsets = np.empty(elements.shape[0], dtype=float)

    for element_index, conn in enumerate(elements):
        coords = nodes[conn]
        midside_offsets[element_index] = _midside_offset_from_chords(coords)
        dets = np.asarray([np.linalg.det(coords.T @ dndr) for dndr in derivatives], dtype=float)
        if not np.all(np.isfinite(dets)):
            raise RuntimeError(f"NONFINITE_DETJ:ELEMENT_{element_index}")
        minimum_det = min(minimum_det, float(np.min(dets)))
        nonpositive = int(np.count_nonzero(dets <= 0.0))
        nonpositive_sample_count += nonpositive
        if nonpositive:
            invalid_indices.append(element_index)
        else:
            valid_indices.append(element_index)
            ratio = float(np.min(dets) / np.max(dets))
            minimum_positive_ratio = ratio if minimum_positive_ratio is None else min(minimum_positive_ratio, ratio)

    return {
        "method": "DUFFY_GL4_64_POINTS_ON_ALL_TET10_RAW_DETJ",
        "minimum_det_jacobian": minimum_det,
        "minimum_positive_element_det_over_maximum_ratio": minimum_positive_ratio,
        "invalid_tet10_count": len(invalid_indices),
        "valid_tet10_count": len(valid_indices),
        "nonpositive_sample_count": nonpositive_sample_count,
        "first_invalid_element_indices_runtime_only": invalid_indices[:20],
        "valid_indices_runtime_only": valid_indices,
        "midside_offsets_mm_runtime_only": midside_offsets,
    }


def _run_candidate(feature, candidate: dict) -> dict:
    local_size = float(candidate["local_size_mm"])
    high_order_optimize = int(candidate["high_order_optimize"])
    box = shoulder_local_box(feature, padding_mm=PADDING_MM)
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_c10b_candidate")
        gmsh.model.occ.importShapes(str(STEP))
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        if len(volumes) != 1:
            raise RuntimeError(f"EXPECTED_ONE_SOLID:{len(volumes)}")
        transition_tag, bbox_error = _unique_transition_surface(gmsh, feature)

        gmsh.option.setNumber("Mesh.MeshSizeMin", local_size)
        gmsh.option.setNumber("Mesh.MeshSizeMax", GLOBAL_SIZE_MM)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.option.setNumber("Mesh.SecondOrderLinear", 0)
        gmsh.option.setNumber("Mesh.HighOrderOptimize", high_order_optimize)
        field_id = gmsh.model.mesh.field.add("Box")
        gmsh.model.mesh.field.setNumber(field_id, "VIn", local_size)
        gmsh.model.mesh.field.setNumber(field_id, "VOut", GLOBAL_SIZE_MM)
        for name, value in zip(("XMin", "YMin", "ZMin", "XMax", "YMax", "ZMax"), box):
            gmsh.model.mesh.field.setNumber(field_id, name, value)
        gmsh.model.mesh.field.setAsBackgroundMesh(field_id)
        gmsh.model.mesh.generate(3)

        node_tags, raw_coords, _ = gmsh.model.mesh.getNodes()
        nodes = np.asarray(raw_coords, dtype=float).reshape((-1, 3))
        elements = _extract_tet10(gmsh, node_tags)
        tri6 = _extract_transition_tri6(gmsh, transition_tag, node_tags)
        mesh_sha = _mesh_hash(nodes, elements, feature.feature_sha256, box)

        corner_nodes = np.unique(tri6[:, :3].reshape(-1))
        midside_nodes = np.unique(tri6[:, 3:].reshape(-1))
        corner_dev = summarize_deviations(_closest_point_deviations(gmsh, transition_tag, nodes[corner_nodes]))
        midside_dev = summarize_deviations(_closest_point_deviations(gmsh, transition_tag, nodes[midside_nodes]))
        sampled = interpolated_tri6_points(nodes, tri6)
        sampled_dev = summarize_deviations(_closest_point_deviations(gmsh, transition_tag, sampled))
        midside_ratio = midside_dev.maximum_mm / float(feature.fillet_radius_mm)
        sampled_ratio = sampled_dev.maximum_mm / float(feature.fillet_radius_mm)

        jac = _raw_jacobian_audit(nodes, elements)
        valid_indices = jac.pop("valid_indices_runtime_only")
        midside_offsets = jac.pop("midside_offsets_mm_runtime_only")

        quadrature_index: int | None = None
        four_vs_ref5: float | None = None
        ref4_vs_ref5: float | None = None
        if valid_indices:
            quadrature_index = int(max(valid_indices, key=lambda index: midside_offsets[index]))
            coords = nodes[elements[quadrature_index]]
            material = IsotropicMaterial(young_modulus_mpa=200000.0, poisson_ratio=0.3)
            k_four = tet10_stiffness(coords, material)
            k_ref4 = tet10_stiffness_isoparametric_reference(coords, material, quadrature_order=4)
            k_ref5 = tet10_stiffness_isoparametric_reference(coords, material, quadrature_order=5)
            four_vs_ref5 = relative_matrix_difference(k_four, k_ref5)
            ref4_vs_ref5 = relative_matrix_difference(k_ref4, k_ref5)

        checks = {
            "all_tet10_jacobians_positive": jac["invalid_tet10_count"] == 0,
            "cad_projected_midside_nodes_on_fillet": midside_ratio <= MAX_MIDSIDE_CAD_ERROR_OVER_FILLET_RADIUS,
            "sampled_interpolated_surface_within_internal_target": sampled_ratio <= MAX_SAMPLED_SURFACE_ERROR_OVER_FILLET_RADIUS,
            "independent_reference_quadrature_converged": (
                ref4_vs_ref5 is not None and ref4_vs_ref5 <= MAX_REFERENCE_ORDER4_VS5_RELATIVE_STIFFNESS
            ),
        }
        return {
            "candidate_id": candidate["candidate_id"],
            "local_size_mm": local_size,
            "global_size_mm": GLOBAL_SIZE_MM,
            "high_order_optimize": high_order_optimize,
            "gmsh_version": str(getattr(gmsh, "__version__", "unknown")),
            "mesh_sha256": mesh_sha,
            "nodes": int(nodes.shape[0]),
            "tet10": int(elements.shape[0]),
            "transition_tri6": int(tri6.shape[0]),
            "transition_surface_bbox_match_error_mm": float(bbox_error),
            "maximum_element_midside_offset_from_chord_midpoint_mm": float(np.max(midside_offsets)),
            "fillet_corner_cad_deviation_max_mm": corner_dev.maximum_mm,
            "fillet_midside_cad_deviation_max_mm": midside_dev.maximum_mm,
            "fillet_midside_cad_deviation_over_radius": float(midside_ratio),
            "fillet_sampled_surface_deviation_max_mm": sampled_dev.maximum_mm,
            "fillet_sampled_surface_deviation_over_radius": float(sampled_ratio),
            "jacobian_audit": jac,
            "quadrature_audit": {
                "element_index_runtime_only": quadrature_index,
                "four_point_vs_duffy_order5_relative_stiffness": four_vs_ref5,
                "duffy_order4_vs_order5_relative_stiffness": ref4_vs_ref5,
                "reference_acceptance_limit": MAX_REFERENCE_ORDER4_VS5_RELATIVE_STIFFNESS,
                "production_curved_quadrature_selected": False,
            },
            "checks": checks,
            "passed": all(checks.values()),
            "execution_error": None,
        }
    finally:
        gmsh.finalize()


def _safe_run(feature, candidate: dict) -> dict:
    try:
        return _run_candidate(feature, candidate)
    except Exception as exc:
        return {
            "candidate_id": candidate["candidate_id"],
            "local_size_mm": float(candidate["local_size_mm"]),
            "high_order_optimize": int(candidate["high_order_optimize"]),
            "passed": False,
            "execution_error": f"{type(exc).__name__}:{exc}",
        }


def main() -> int:
    _write_fixture()
    feature = recognize_x_axis_shaft_shoulder(STEP, feature_id="CURVED_TET10_HO_OPT_SHOULDER")

    control = _safe_run(feature, CONTROL)
    candidates = [_safe_run(feature, candidate) for candidate in ADMISSIBLE_SEQUENCE]
    selected = next((candidate for candidate in candidates if candidate.get("passed") is True), None)

    report = {
        "schema": "AsterMaxCurvedTet10HighOrderOptimizationBenchmarkV1",
        "classification": "CURVED_HIGH_ORDER_MESH_QUALITY_VERIFICATION_NOT_SOLVER_VALIDATION",
        "source_sha256": feature.source_sha256,
        "feature_sha256": feature.feature_sha256,
        "fillet_radius_mm": feature.fillet_radius_mm,
        "predeclared_policy": {
            "control_is_not_admissible_candidate": True,
            "admissible_sequence": [candidate["candidate_id"] for candidate in ADMISSIBLE_SEQUENCE],
            "selection_rule": "FIRST_CANDIDATE_IN_PREDECLARED_SEQUENCE_PASSING_ALL_GATES",
            "gmsh_high_order_optimize_mode": 2,
            "gmsh_mode_2_meaning": "ELASTIC_PLUS_OPTIMIZATION",
            "max_sampled_surface_error_over_fillet_radius": MAX_SAMPLED_SURFACE_ERROR_OVER_FILLET_RADIUS,
            "max_midside_cad_error_over_fillet_radius": MAX_MIDSIDE_CAD_ERROR_OVER_FILLET_RADIUS,
            "max_duffy_order4_vs_order5_relative_stiffness": MAX_REFERENCE_ORDER4_VS5_RELATIVE_STIFFNESS,
            "require_all_tet10_jacobians_positive": True,
            "thresholds_changed_after_observation": False,
        },
        "control": control,
        "candidates": candidates,
        "selected_candidate_id": None if selected is None else selected["candidate_id"],
        "curved_mesh_admissible_for_next_solver_gate": selected is not None,
        "curved_tet10_solver_enabled": False,
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
        "passed": selected is not None,
        "interpretation_boundary": (
            "C10b evaluates the documented Gmsh elastic+high-order optimization path against predeclared geometry, Jacobian and independent quadrature gates. "
            "A passing candidate only makes a curved mesh admissible for a separate solver-verification gate; it does not enable the curved solver, validate industrial use, or establish ANSYS equivalence."
        ),
    }
    report["benchmark_sha256"] = canonical_sha256(report)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    print(f"wrote {OUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
