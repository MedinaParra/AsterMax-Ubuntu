from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import numpy as np

from astermax.credibility import canonical_sha256
from astermax.fea.axisymmetric_shoulder import recognize_x_axis_shaft_shoulder
from astermax.fea.feature_adaptivity import _mesh_hash, shoulder_local_box
from astermax.fea.feature_geometry_error import _unique_transition_surface
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.tri6_traction import tri6_shape_functions


OUT = Path("curved_tri6_surface_audit.json")
C10B_PATH = Path(__file__).with_name("curved_tet10_high_order_optimize.py")
SELECTED = {"candidate_id": "ELASTIC_PLUS_OPT_HO2_LOCAL2P0", "local_size_mm": 2.0, "high_order_optimize": 2}
ANOMALOUS_DIAGNOSTIC = {"candidate_id": "ELASTIC_PLUS_OPT_HO2_LOCAL2P5", "local_size_mm": 2.5, "high_order_optimize": 2}
GLOBAL_SIZE_MM = 8.0
PADDING_MM = 5.0

# The C10 fixture is explicitly constructed from a radius-10 cylinder meeting
# an x=40 shoulder plane, with a radius-2 fillet on that edge.  In the
# meridional (x,rho) plane its exact quarter-circle is centered at (38,12).
ANALYTIC_CENTER_X_MM = 38.0
ANALYTIC_CENTER_RHO_MM = 12.0
ANALYTIC_FILLET_RADIUS_MM = 2.0
ANALYTIC_START = np.asarray([38.0, 10.0])
ANALYTIC_END = np.asarray([40.0, 12.0])
MAX_SELECTED_SURFACE_ERROR_MM = 0.02
MAX_OCC_VS_ANALYTIC_DISTANCE_DISAGREEMENT_MM = 5.0e-6


def _load_c10b():
    spec = importlib.util.spec_from_file_location("astermax_c10b_benchmark", C10B_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load C10b benchmark module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _analytic_quarter_torus_distance(point_xyz: np.ndarray) -> tuple[float, float]:
    point = np.asarray(point_xyz, dtype=float).reshape(3)
    rho = float(math.hypot(point[1], point[2]))
    meridional = np.asarray([float(point[0]), rho])
    vector = meridional - np.asarray([ANALYTIC_CENTER_X_MM, ANALYTIC_CENTER_RHO_MM])
    theta = float(math.atan2(vector[1], vector[0]))
    if -0.5 * math.pi <= theta <= 0.0:
        distance = abs(float(np.linalg.norm(vector)) - ANALYTIC_FILLET_RADIUS_MM)
    else:
        distance = min(
            float(np.linalg.norm(meridional - ANALYTIC_START)),
            float(np.linalg.norm(meridional - ANALYTIC_END)),
        )
    return distance, theta


def _gmsh_type9_basis_contract(gmsh) -> dict:
    name, dim, order, num_nodes, local_coords, num_primary = gmsh.model.mesh.getElementProperties(9)
    local = np.asarray(local_coords, dtype=float).reshape((int(num_nodes), int(dim)))
    interpolation = np.vstack([tri6_shape_functions(point) for point in local])
    error = float(np.max(np.abs(interpolation - np.eye(6))))
    return {
        "element_name": str(name),
        "dimension": int(dim),
        "order": int(order),
        "num_nodes": int(num_nodes),
        "num_primary_nodes": int(num_primary),
        "local_node_coordinates": local.tolist(),
        "astermax_kronecker_max_abs_error": error,
        "ordering_contract_matches": error <= 2.0e-14,
    }


def _mesh_and_surface_diagnostic(c10b, feature, candidate: dict) -> dict:
    local_size = float(candidate["local_size_mm"])
    box = shoulder_local_box(feature, padding_mm=PADDING_MM)
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_c10c_surface_audit")
        gmsh.model.occ.importShapes(str(c10b.STEP))
        gmsh.model.occ.synchronize()
        transition_tag, _ = _unique_transition_surface(gmsh, feature)
        gmsh.option.setNumber("Mesh.MeshSizeMin", local_size)
        gmsh.option.setNumber("Mesh.MeshSizeMax", GLOBAL_SIZE_MM)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.option.setNumber("Mesh.SecondOrderLinear", 0)
        gmsh.option.setNumber("Mesh.HighOrderOptimize", int(candidate["high_order_optimize"]))
        field_id = gmsh.model.mesh.field.add("Box")
        gmsh.model.mesh.field.setNumber(field_id, "VIn", local_size)
        gmsh.model.mesh.field.setNumber(field_id, "VOut", GLOBAL_SIZE_MM)
        for name, value in zip(("XMin", "YMin", "ZMin", "XMax", "YMax", "ZMax"), box):
            gmsh.model.mesh.field.setNumber(field_id, name, value)
        gmsh.model.mesh.field.setAsBackgroundMesh(field_id)
        gmsh.model.mesh.generate(3)

        node_tags, raw_coords, _ = gmsh.model.mesh.getNodes()
        nodes = np.asarray(raw_coords, dtype=float).reshape((-1, 3))
        elements = c10b._extract_tet10(gmsh, node_tags)
        tri6 = c10b._extract_transition_tri6(gmsh, transition_tag, node_tags)
        mesh_sha = _mesh_hash(nodes, elements, feature.feature_sha256, box)
        basis_contract = _gmsh_type9_basis_contract(gmsh)

        sample_rs = np.asarray(
            [
                [1.0 / 3.0, 1.0 / 3.0],
                [0.25, 0.0], [0.75, 0.0],
                [0.25, 0.75], [0.75, 0.25],
                [0.0, 0.25], [0.0, 0.75],
                [0.25, 0.25], [0.50, 0.25], [0.25, 0.50],
            ],
            dtype=float,
        )
        shapes = np.vstack([tri6_shape_functions(point) for point in sample_rs])
        records: list[dict] = []
        max_corner_edge = 0.0
        for face_index, conn in enumerate(tri6):
            xyz = nodes[conn]
            max_corner_edge = max(
                max_corner_edge,
                float(np.linalg.norm(xyz[0] - xyz[1])),
                float(np.linalg.norm(xyz[1] - xyz[2])),
                float(np.linalg.norm(xyz[2] - xyz[0])),
            )
            for sample_index, (rs, shape) in enumerate(zip(sample_rs, shapes)):
                point = shape @ xyz
                closest, _ = gmsh.model.getClosestPoint(2, int(transition_tag), point.tolist())
                closest = np.asarray(closest, dtype=float).reshape(-1)[:3]
                occ_distance = float(np.linalg.norm(point - closest))
                analytic_distance, theta = _analytic_quarter_torus_distance(point)
                records.append(
                    {
                        "face_index_runtime_only": int(face_index),
                        "sample_index": int(sample_index),
                        "rs": [float(v) for v in rs],
                        "point_mm": [float(v) for v in point],
                        "occ_closest_point_mm": [float(v) for v in closest],
                        "occ_distance_mm": occ_distance,
                        "analytic_quarter_torus_distance_mm": analytic_distance,
                        "analytic_theta_rad": theta,
                        "occ_vs_analytic_abs_difference_mm": abs(occ_distance - analytic_distance),
                    }
                )

        worst_occ = max(records, key=lambda item: item["occ_distance_mm"])
        worst_analytic = max(records, key=lambda item: item["analytic_quarter_torus_distance_mm"])
        worst_disagreement = max(records, key=lambda item: item["occ_vs_analytic_abs_difference_mm"])
        return {
            "candidate_id": candidate["candidate_id"],
            "local_size_mm": local_size,
            "mesh_sha256": mesh_sha,
            "nodes": int(nodes.shape[0]),
            "tet10": int(elements.shape[0]),
            "transition_tri6": int(tri6.shape[0]),
            "max_transition_corner_edge_mm": max_corner_edge,
            "gmsh_type9_basis_contract": basis_contract,
            "worst_occ_surface_sample": worst_occ,
            "worst_analytic_surface_sample": worst_analytic,
            "worst_occ_vs_analytic_disagreement": worst_disagreement,
            "maximum_occ_distance_mm": float(worst_occ["occ_distance_mm"]),
            "maximum_analytic_distance_mm": float(worst_analytic["analytic_quarter_torus_distance_mm"]),
            "maximum_occ_vs_analytic_abs_difference_mm": float(worst_disagreement["occ_vs_analytic_abs_difference_mm"]),
        }
    finally:
        gmsh.finalize()


def main() -> int:
    c10b = _load_c10b()
    c10b._write_fixture()
    feature = recognize_x_axis_shaft_shoulder(c10b.STEP, feature_id="CURVED_TRI6_SURFACE_AUDIT_SHOULDER")

    selected_run_1 = c10b._run_candidate(feature, SELECTED)
    selected_run_2 = c10b._run_candidate(feature, SELECTED)
    selected_diagnostic = _mesh_and_surface_diagnostic(c10b, feature, SELECTED)
    anomalous_diagnostic = _mesh_and_surface_diagnostic(c10b, feature, ANOMALOUS_DIAGNOSTIC)

    selected_mesh_sha_reproducible = (
        selected_run_1["mesh_sha256"]
        == selected_run_2["mesh_sha256"]
        == selected_diagnostic["mesh_sha256"]
    )
    selected_metric_reproducible = (
        selected_run_1["fillet_sampled_surface_deviation_max_mm"]
        == selected_run_2["fillet_sampled_surface_deviation_max_mm"]
        and selected_run_1["jacobian_audit"]["minimum_det_jacobian"]
        == selected_run_2["jacobian_audit"]["minimum_det_jacobian"]
    )
    checks = {
        "gmsh_type9_ordering_matches_astermax_tri6_basis": selected_diagnostic["gmsh_type9_basis_contract"]["ordering_contract_matches"],
        "selected_mesh_sha_reproducible": selected_mesh_sha_reproducible,
        "selected_key_metrics_bitwise_reproducible": selected_metric_reproducible,
        "selected_c10b_candidate_still_passes": bool(selected_run_1["passed"] and selected_run_2["passed"]),
        "selected_occ_surface_error_within_0p02mm": selected_diagnostic["maximum_occ_distance_mm"] <= MAX_SELECTED_SURFACE_ERROR_MM,
        "selected_analytic_surface_error_within_0p02mm": selected_diagnostic["maximum_analytic_distance_mm"] <= MAX_SELECTED_SURFACE_ERROR_MM,
        "selected_occ_distance_agrees_with_analytic_fixture_distance": (
            selected_diagnostic["maximum_occ_vs_analytic_abs_difference_mm"]
            <= MAX_OCC_VS_ANALYTIC_DISTANCE_DISAGREEMENT_MM
        ),
    }

    report = {
        "schema": "AsterMaxCurvedTri6SurfaceAuditV1",
        "classification": "INSTRUMENT_AND_REPRODUCIBILITY_AUDIT_NOT_SOLVER_VALIDATION",
        "source_sha256": feature.source_sha256,
        "feature_sha256": feature.feature_sha256,
        "selected_candidate_id": SELECTED["candidate_id"],
        "selected_replay_1": selected_run_1,
        "selected_replay_2": selected_run_2,
        "selected_surface_diagnostic": selected_diagnostic,
        "anomalous_2p5_surface_diagnostic": anomalous_diagnostic,
        "analytic_fixture_contract": {
            "meridional_center_x_mm": ANALYTIC_CENTER_X_MM,
            "meridional_center_rho_mm": ANALYTIC_CENTER_RHO_MM,
            "fillet_radius_mm": ANALYTIC_FILLET_RADIUS_MM,
            "arc_theta_min_rad": -0.5 * math.pi,
            "arc_theta_max_rad": 0.0,
        },
        "acceptance": {
            "max_selected_surface_error_mm": MAX_SELECTED_SURFACE_ERROR_MM,
            "max_occ_vs_analytic_distance_disagreement_mm": MAX_OCC_VS_ANALYTIC_DISTANCE_DISAGREEMENT_MM,
            "thresholds_changed_after_c10b": False,
        },
        "checks": checks,
        "passed": all(checks.values()),
        "curved_tet10_solver_enabled": False,
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
        "interpretation_boundary": (
            "C10c audits the TRI6 interpolation instrument against the Gmsh type-9 runtime contract, independently checks the known analytic quarter-torus fixture distance, and replays the C10b selected HO2/local-2.0 candidate twice. Passing C10c can justify opening a separate curved-solver verification gate, but does not enable that solver or validate industrial use."
        ),
    }
    report["audit_sha256"] = canonical_sha256(report)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    print(f"wrote {OUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
