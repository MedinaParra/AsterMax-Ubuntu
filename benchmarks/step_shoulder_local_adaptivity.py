from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import numpy as np

from astermax.credibility import canonical_sha256
from astermax.fea.axisymmetric_shoulder import recognize_x_axis_shaft_shoulder
from astermax.fea.feature_adaptivity import mesh_step_tet10_around_shoulder
from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.tet10_feature_sampling import sample_tet10_shoulder_neighborhood


STEP = Path("step_shoulder_local_adaptivity.step")
OUT = Path("step_shoulder_local_adaptivity.json")


def _write_fixture() -> None:
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("step_shoulder_local_adaptivity")
        small = gmsh.model.occ.addCylinder(0.0, 0.0, 0.0, 40.0, 0.0, 0.0, 10.0)
        large = gmsh.model.occ.addCylinder(40.0, 0.0, 0.0, 40.0, 0.0, 0.0, 15.0)
        gmsh.model.occ.fuse([(3, small)], [(3, large)])
        gmsh.model.occ.synchronize()

        volumes = gmsh.model.getEntities(3)
        if len(volumes) != 1:
            raise RuntimeError(f"expected one fused shaft volume, got {volumes}")
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
        if len(candidates) != 1:
            raise RuntimeError(f"expected one shoulder fillet edge, got {candidates}")

        gmsh.model.occ.fillet(
            [int(volumes[0][1])],
            [candidates[0]],
            [2.0],
            removeVolume=True,
        )
        gmsh.model.occ.synchronize()
        if len(gmsh.model.getEntities(3)) != 1:
            raise RuntimeError("fillet operation did not preserve one shaft solid")
        gmsh.write(str(STEP))
    finally:
        gmsh.finalize()


def main() -> int:
    _write_fixture()
    feature = recognize_x_axis_shaft_shoulder(STEP, feature_id="VERIFY_SHAFT_SHOULDER")
    if abs(feature.small_radius_mm - 10.0) > 1.0e-3:
        raise RuntimeError(f"unexpected small radius: {feature.small_radius_mm}")
    if abs(feature.large_radius_mm - 15.0) > 1.0e-3:
        raise RuntimeError(f"unexpected large radius: {feature.large_radius_mm}")
    if abs(feature.fillet_radius_mm - 2.0) > 1.0e-3:
        raise RuntimeError(f"unexpected fillet radius: {feature.fillet_radius_mm}")

    uniform = mesh_step_tet10_around_shoulder(
        STEP,
        feature,
        global_size_mm=6.0,
        local_size_mm=6.0,
        padding_mm=4.0,
    )
    refined = mesh_step_tet10_around_shoulder(
        STEP,
        feature,
        global_size_mm=6.0,
        local_size_mm=2.5,
        padding_mm=4.0,
    )
    neighborhood = sample_tet10_shoulder_neighborhood(
        refined,
        feature,
        padding_mm=2.0,
    )

    local_edge_ratio = refined.local_mean_max_corner_edge_mm / uniform.local_mean_max_corner_edge_mm
    if not (local_edge_ratio < 0.9):
        raise RuntimeError(f"local refinement did not materially reduce local edge metric: ratio={local_edge_ratio}")
    if refined.local_element_count <= uniform.local_element_count:
        raise RuntimeError(
            "feature refinement did not increase the number of elements whose centroids occupy the local box"
        )
    if neighborhood.sample_count <= 0:
        raise RuntimeError("refined mesh produced no TET10 integration points in the shoulder neighborhood")
    if neighborhood.stress_representation != "GEOMETRY_ONLY_NO_STRESS_VALUES":
        raise RuntimeError("geometry-only benchmark unexpectedly contains stress values")

    report = {
        "schema": "AsterMaxStepShoulderLocalAdaptivityBenchmarkV1",
        "classification": "GEOMETRY_MESH_VERIFICATION_NOT_FEA_RESULT",
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
        "solver_result_claim": False,
        "fixture": {
            "small_diameter_mm": 20.0,
            "large_diameter_mm": 30.0,
            "fillet_radius_mm": 2.0,
            "length_mm": 80.0,
            "axis": "X",
        },
        "recognized_feature": asdict(feature),
        "uniform_mesh": {
            "nodes": int(uniform.nodes_mm.shape[0]),
            "tet10": int(uniform.elements.shape[0]),
            "local_element_count": uniform.local_element_count,
            "local_mean_max_corner_edge_mm": uniform.local_mean_max_corner_edge_mm,
            "mesh_sha256": uniform.mesh_sha256,
        },
        "refined_mesh": {
            "nodes": int(refined.nodes_mm.shape[0]),
            "tet10": int(refined.elements.shape[0]),
            "local_element_count": refined.local_element_count,
            "outside_element_count": refined.outside_element_count,
            "local_mean_max_corner_edge_mm": refined.local_mean_max_corner_edge_mm,
            "outside_mean_max_corner_edge_mm": refined.outside_mean_max_corner_edge_mm,
            "mesh_sha256": refined.mesh_sha256,
            "second_order_linear": refined.second_order_linear,
        },
        "refinement_gate": {
            "local_edge_ratio_refined_over_uniform": local_edge_ratio,
            "local_edge_ratio_limit": 0.9,
            "local_element_count_increased": refined.local_element_count > uniform.local_element_count,
            "passed": True,
        },
        "tet10_neighborhood": {
            "stress_representation": neighborhood.stress_representation,
            "sample_count": neighborhood.sample_count,
            "neighborhood_sha256": neighborhood.neighborhood_sha256,
            "sampling_box_mm": neighborhood.sampling_box_mm,
        },
        "interpretation_boundary": (
            "This benchmark proves STEP feature recognition, feature-hash-bound local TET10 meshing and exact physical "
            "integration-point coordinate selection. It contains no loads, no solved stresses and no FEA credibility claim."
        ),
    }
    report["benchmark_sha256"] = canonical_sha256(report)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    print(f"wrote {OUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
