from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from astermax.contact import (
    DeformableTri6TargetFace,
    Tri6SourceFace,
    find_deformable_tri6_surface_pairs,
    solve_tet10_deformable_surface_contact,
    tri6_surface_pressure_generalized_force,
)
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet4 import IsotropicMaterial

OUTPUT_DIR = Path("deformable_master_switch")
OUTPUT_JSON = OUTPUT_DIR / "deformable_master_switch.json"
MATERIAL = IsotropicMaterial(young_modulus_mpa=200_000.0, poisson_ratio=0.30)
SOURCE = np.asarray([0, 1, 2, 4, 5, 6], dtype=int)
TARGET = np.asarray([0, 2, 1, 6, 5, 4], dtype=int)
SUPPORT = np.asarray([3, 7, 8, 9], dtype=int)
NORMAL = np.asarray([0.0, 0.0, 1.0], dtype=float)
REFERENCE_GAP_MM = 0.0036
SLOPE = 0.001
DRIVING_PRESSURE_MPA = 20.0
PATH = (-3.0, -2.0, -1.0, 1.0, 2.0, 3.0)


def build_fixture():
    src = straight_sided_tet10_from_vertices(np.asarray([
        [-1.0, -2.0, 0.0], [0.0, 2.0, 0.0], [1.0, -2.0, 0.0], [0.0, 0.0, -5.0]
    ]))
    xy = ((-8.0, -5.0), (0.0, 8.0), (8.0, -5.0))
    def p(xy0, slope):
        x, y = xy0
        return [x, y, REFERENCE_GAP_MM + slope * x]
    a, b, c = xy
    ma = straight_sided_tet10_from_vertices(np.asarray([
        p(a, SLOPE), p(c, SLOPE), p(b, SLOPE), [0.0, 0.0, 5.0 + REFERENCE_GAP_MM]
    ], dtype=float))
    mb = straight_sided_tet10_from_vertices(np.asarray([
        p(a, -SLOPE), p(c, -SLOPE), p(b, -SLOPE), [0.0, 0.0, 5.0 + REFERENCE_GAP_MM]
    ], dtype=float))
    nodes = np.vstack([src, ma, mb])
    elements = np.vstack([np.arange(0, 10), np.arange(10, 20), np.arange(20, 30)])
    source = Tri6SourceFace("SOURCE", SOURCE.copy(), NORMAL.copy())
    targets = (
        DeformableTri6TargetFace("MASTER_A", TARGET.copy() + 10),
        DeformableTri6TargetFace("MASTER_B", TARGET.copy() + 20),
    )
    support_nodes = np.concatenate([SUPPORT, SUPPORT + 10, SUPPORT + 20])
    fixed = np.asarray([3 * int(n) + c for n in support_nodes for c in range(3)], dtype=int)
    return nodes, elements, source, targets, fixed


def translated(nodes, x_mm):
    d = np.zeros_like(nodes)
    d[:10, 0] = float(x_mm)
    return d


def search_at(x_mm):
    nodes, _, source, targets, _ = build_fixture()
    rec = find_deformable_tri6_surface_pairs(
        nodes_mm=nodes,
        displacement_mm=translated(nodes, x_mm),
        source_faces=[source],
        target_faces=targets,
        max_tracking_distance_mm=0.01,
    )
    return {
        "x_mm": float(x_mm),
        "targets": [r.target_face_id for r in rec],
        "gaps_mm": [float(r.current_gap_mm) for r in rec],
        "max_newton_residual_mm": float(max(r.newton_residual_mm for r in rec)),
    }


def solve_at(x_mm, expected):
    nodes, elements, source, targets, fixed = build_fixture()
    nodes = nodes + translated(nodes, x_mm)
    loads = tri6_surface_pressure_generalized_force(
        nodes_mm=nodes,
        face_nodes=source.node_indices,
        contact_normal=NORMAL,
        pressure_mpa=np.full(3, DRIVING_PRESSURE_MPA),
    )
    r = solve_tet10_deformable_surface_contact(
        nodes_mm=nodes,
        elements=elements,
        material=MATERIAL,
        loads_n=loads,
        fixed_dofs=fixed,
        source_faces=[source],
        target_faces=targets,
        max_tracking_distance_mm=0.01,
    )
    selected = 1 if expected == "MASTER_A" else 2
    return {
        "x_mm": float(x_mm),
        "expected_master": expected,
        "targets": [p.target_face_id for p in r.pairing_records],
        "active": [int(i) for i in r.active_contact_indices],
        "pressure_mpa": r.contact_pressure_mpa.tolist(),
        "gaps_mm": r.signed_gaps_mm.tolist(),
        "complementarity": r.complementarity_mpa_mm.tolist(),
        "net_contact_n": r.net_contact_resultant_n.tolist(),
        "equilibrium_n": float(r.free_equilibrium_residual_norm_n),
        "source_vm_mpa": float(np.max(r.integration_point_von_mises_mpa[0])),
        "master_vm_mpa": float(np.max(r.integration_point_von_mises_mpa[selected])),
        "converged": bool(r.converged),
        "primary_pressure": bool(r.pressure_is_primary_contact_unknown),
        "reaction_projection": bool(r.contact_pressure_recovered_from_nodal_reactions),
        "equal_opposite": bool(r.equal_and_opposite_contact_traction),
        "penalty": bool(r.penalty_method_used),
        "friction": bool(r.friction_solved),
        "large_sliding_claim": bool(r.large_sliding_claimed),
        "finite_strain_claim": bool(r.finite_strain_claimed),
        "industrial_claim": bool(r.industrial_validation_claimed),
        "ot1613_claim": bool(r.ot1613_result_claimed),
        "ansys_equivalence_claim": bool(r.ansys_equivalence_claimed),
    }


def main():
    path = [search_at(x) for x in PATH]
    ambiguity = False
    try:
        search_at(0.0)
    except ValueError as exc:
        ambiguity = "ambiguous deformable target pairing" in str(exc)
    left = solve_at(-3.0, "MASTER_A")
    right = solve_at(3.0, "MASTER_B")
    p_err = float(np.max(np.abs(np.asarray(left["pressure_mpa"]) - np.asarray(right["pressure_mpa"])[::-1])))
    g_err = float(np.max(np.abs(np.asarray(left["gaps_mm"]) - np.asarray(right["gaps_mm"])[::-1])))
    expected = [["MASTER_A"] * 3] * 3 + [["MASTER_B"] * 3] * 3
    def endpoint_ok(e):
        return bool(
            e["converged"]
            and e["targets"] == [e["expected_master"]] * 3
            and np.any(np.asarray(e["pressure_mpa"]) > 0.0)
            and np.all(np.asarray(e["pressure_mpa"]) >= 0.0)
            and np.all(np.asarray(e["gaps_mm"]) >= -1.0e-10)
            and np.all(np.abs(np.asarray(e["complementarity"])) <= 1.0e-10)
            and np.linalg.norm(e["net_contact_n"]) <= 1.0e-8
            and e["equilibrium_n"] <= 1.0e-6
            and e["primary_pressure"] and not e["reaction_projection"] and e["equal_opposite"]
            and not e["penalty"] and not e["friction"]
            and not e["large_sliding_claim"] and not e["finite_strain_claim"]
            and not e["industrial_claim"] and not e["ot1613_claim"] and not e["ansys_equivalence_claim"]
        )
    checks = {
        "path_sequence": [r["targets"] for r in path] == expected,
        "path_residual": max(r["max_newton_residual_mm"] for r in path) <= 1.0e-11,
        "path_positive_gaps": all(min(r["gaps_mm"]) > 0.0 for r in path),
        "crossing_ambiguity_fails_closed": ambiguity,
        "left_endpoint": endpoint_ok(left),
        "right_endpoint": endpoint_ok(right),
        "active_count_symmetry": len(left["active"]) == len(right["active"]),
        "pressure_mirror_symmetry": p_err <= 1.0e-8,
        "gap_mirror_symmetry": g_err <= 1.0e-10,
        "source_stress_symmetry": abs(left["source_vm_mpa"] - right["source_vm_mpa"]) <= 1.0e-8,
        "master_stress_symmetry": abs(left["master_vm_mpa"] - right["master_vm_mpa"]) <= 1.0e-8,
    }
    payload = {
        "schema_version": "AsterMaxTet10DeformableMasterSwitchEvidenceV1",
        "classification": "SYNTHETIC_CONTROLLED_SWITCH_NOT_INDUSTRIAL_RESULT",
        "passed": all(checks.values()),
        "checks": checks,
        "path": path,
        "left_endpoint": left,
        "right_endpoint": right,
        "mirror_errors": {"pressure_mpa": p_err, "gap_mm": g_err},
        "boundary": {
            "general_large_sliding_claim": False,
            "friction": False,
            "finite_strain": False,
            "industrial_validation": False,
            "ot1613_result": False,
            "ansys_equivalence": False,
            "hardening_issue": 107,
        },
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"wrote {OUTPUT_JSON.resolve()}")
    if not payload["passed"]:
        raise SystemExit(f"GAP-J failed: {[k for k, v in checks.items() if not v]}")


if __name__ == "__main__":
    main()
