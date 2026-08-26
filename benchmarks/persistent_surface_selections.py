from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from astermax.fea.gmsh_bridge import (
    distribute_resultant_on_tri6,
    fixed_dofs_for_nodes,
    force_and_moment,
    unique_surface_nodes,
)
from astermax.fea.selected_mesh import mesh_step_tet10_with_selections
from astermax.fea.selections import SurfaceSignature, inspect_step_surfaces, resolve_step_surface
from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet4 import IsotropicMaterial


def _write_rotated_step(path: Path) -> None:
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("persistent_selection_rotated_fixture")
        volume = gmsh.model.occ.addBox(0.0, 0.0, 0.0, 100.0, 20.0, 10.0)
        gmsh.model.occ.rotate([(3, volume)], 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, math.radians(17.0))
        gmsh.model.occ.rotate([(3, volume)], 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, math.radians(11.0))
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def _farthest_face_pair(records: list[tuple[int, SurfaceSignature]]) -> tuple[SurfaceSignature, SurfaceSignature]:
    best = None
    for i, (_, a) in enumerate(records):
        for _, b in records[i + 1 :]:
            distance = float(np.linalg.norm(np.asarray(a.centroid_mm) - np.asarray(b.centroid_mm)))
            key = (distance, a.fingerprint_sha256, b.fingerprint_sha256)
            if best is None or key > best[0]:
                best = (key, a, b)
    if best is None:
        raise RuntimeError("fixture contains fewer than two CAD surfaces")
    a, b = best[1], best[2]
    # Deterministic naming without relying on transient Gmsh tags.
    if tuple(a.centroid_mm) <= tuple(b.centroid_mm):
        return a, b
    return b, a


def _tri6_area_centroid(nodes: np.ndarray, tri6: np.ndarray) -> tuple[float, np.ndarray]:
    total_area = 0.0
    weighted = np.zeros(3, dtype=float)
    for conn in np.asarray(tri6, dtype=np.int64):
        corners = nodes[conn[:3]]
        area = 0.5 * float(np.linalg.norm(np.cross(corners[1] - corners[0], corners[2] - corners[0])))
        if area <= 0.0:
            raise RuntimeError("degenerate selected TRI6")
        centroid = corners.mean(axis=0)
        total_area += area
        weighted += area * centroid
    if total_area <= 0.0:
        raise RuntimeError("selected surface has zero area")
    return total_area, weighted / total_area


def _surface_mesh_matches_signature(nodes: np.ndarray, tri6: np.ndarray, signature: SurfaceSignature) -> dict:
    area, centroid = _tri6_area_centroid(nodes, tri6)
    scale = max(signature.model_diagonal_mm, 1.0)
    area_rel_error = abs(area - signature.area_mm2) / max(signature.area_mm2, 1.0)
    centroid_rel_error = float(np.linalg.norm(centroid - np.asarray(signature.centroid_mm))) / scale
    return {
        "area_mm2": area,
        "area_relative_error": area_rel_error,
        "centroid_mm": centroid.tolist(),
        "centroid_relative_error": centroid_rel_error,
        "matches": bool(area_rel_error <= 1.0e-8 and centroid_rel_error <= 1.0e-8),
    }


def main() -> int:
    step = Path("persistent_surface_fixture.step")
    report_path = Path("persistent_surface_selections.json")
    _write_rotated_step(step)

    records = inspect_step_surfaces(step)
    if len(records) != 6:
        raise RuntimeError(f"rotated box should expose six CAD surfaces; got {len(records)}")
    support, load_face = _farthest_face_pair(records)
    if support.fingerprint_sha256 == load_face.fingerprint_sha256:
        raise RuntimeError("support and load faces must have distinct persistent identities")

    # Prove the persisted signatures resolve in fresh OCC import sessions.
    support_resolved = resolve_step_surface(step, support)
    load_resolved = resolve_step_surface(step, load_face)
    if support_resolved.signature.fingerprint_sha256 != support.fingerprint_sha256:
        raise RuntimeError("support signature changed during fresh resolution")
    if load_resolved.signature.fingerprint_sha256 != load_face.fingerprint_sha256:
        raise RuntimeError("load signature changed during fresh resolution")

    material = IsotropicMaterial(200000.0, 0.30)
    samples = []
    for mesh_size in (20.0, 15.0, 10.0):
        mesh = mesh_step_tet10_with_selections(
            step,
            mesh_size,
            {"SUPPORT": support, "LOAD": load_face},
        )
        support_match = _surface_mesh_matches_signature(mesh.nodes_mm, mesh.surface_triangles["SUPPORT"], support)
        load_match = _surface_mesh_matches_signature(mesh.nodes_mm, mesh.surface_triangles["LOAD"], load_face)
        if not support_match["matches"] or not load_match["matches"]:
            raise RuntimeError("remeshed TRI6 surface no longer matches persisted CAD signature")

        fixed_nodes = unique_surface_nodes(mesh.surface_triangles["SUPPORT"])
        fixed_dofs = fixed_dofs_for_nodes(fixed_nodes)
        loads = distribute_resultant_on_tri6(
            mesh.nodes_mm,
            mesh.surface_triangles["LOAD"],
            [0.0, -1000.0, 0.0],
        )
        applied_force, applied_moment = force_and_moment(mesh.nodes_mm, loads)
        result = solve_linear_static_tet10(mesh.nodes_mm, mesh.elements, material, loads, fixed_dofs)
        reaction_force, reaction_moment = force_and_moment(mesh.nodes_mm, result.reactions_n)
        force_residual = float(np.linalg.norm(reaction_force + applied_force))
        moment_residual = float(np.linalg.norm(reaction_moment + applied_moment))
        checks = {
            "support_geometry_match": support_match["matches"],
            "load_geometry_match": load_match["matches"],
            "force_balance": force_residual <= 1.0e-5,
            "moment_balance": moment_residual <= 1.0e-3,
        }
        if not all(checks.values()):
            raise RuntimeError(f"persistent-selection solve gate failed at {mesh_size} mm: {checks}")
        samples.append(
            {
                "mesh_size_mm": mesh_size,
                "nodes": int(mesh.nodes_mm.shape[0]),
                "tet10": int(mesh.elements.shape[0]),
                "support_tri6": int(mesh.surface_triangles["SUPPORT"].shape[0]),
                "load_tri6": int(mesh.surface_triangles["LOAD"].shape[0]),
                "support_geometry": support_match,
                "load_geometry": load_match,
                "force_residual_n": force_residual,
                "moment_residual_nmm": moment_residual,
                "checks": checks,
            }
        )

    strict_refinement = all(samples[i + 1]["tet10"] > samples[i]["tet10"] for i in range(len(samples) - 1))
    decision = {
        "persistent_support_identity": True,
        "persistent_load_identity": True,
        "all_remesh_surface_matches": all(
            s["support_geometry"]["matches"] and s["load_geometry"]["matches"] for s in samples
        ),
        "all_force_balance": all(s["checks"]["force_balance"] for s in samples),
        "all_moment_balance": all(s["checks"]["moment_balance"] for s in samples),
        "strict_mesh_refinement": strict_refinement,
    }
    passed = all(decision.values())
    report = {
        "schema": "AsterMaxPersistentSurfaceSelectionGateV1",
        "classification": "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT",
        "claim": "CAD_SURFACE_IDENTITY_SURVIVES_TET10_REMESHING",
        "fixture": {
            "source": "100x20x10 mm OCC box rotated 17 deg about Z then 11 deg about Y",
            "purpose": "avoid axis-extrema face scoping and exercise CAD-persistent selections",
        },
        "selection_policy": {
            "identity_components": ["CAD surface type", "area", "centroid", "bounding box"],
            "transient_gmsh_tag_persisted": False,
            "mesh_node_or_element_ids_persisted": False,
            "ambiguity_policy": "FAIL_CLOSED",
            "relative_resolution_tolerance": 1.0e-8,
        },
        "support_signature": support.to_dict(),
        "load_signature": load_face.to_dict(),
        "samples": samples,
        "decision": {"checks": decision, "passed": passed},
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"wrote {report_path.resolve()}")
    if not passed:
        raise RuntimeError(f"persistent surface gate failed: {decision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
