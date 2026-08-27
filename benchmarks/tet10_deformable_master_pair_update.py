from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np

from astermax.contact import (
    TRI6_GAUSS_BARYCENTRIC,
    DeformableTri6TargetFace,
    Tri6SourceFace,
    find_deformable_tri6_surface_pairs,
    solve_tet10_deformable_surface_contact,
    tri6_shape_functions,
    tri6_surface_pressure_generalized_force,
)
from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet4 import IsotropicMaterial


OUTPUT_DIR = Path("deformable_master_pair_update")
OUTPUT_JSON = OUTPUT_DIR / "deformable_master_pair_update.json"
OUTPUT_HTML = OUTPUT_DIR / "deformable_master_pair_update_viewer.html"
MATERIAL = IsotropicMaterial(young_modulus_mpa=200_000.0, poisson_ratio=0.30)
SOURCE_FACE = np.asarray([0, 1, 2, 4, 5, 6], dtype=int)
TARGET_FACE_LOCAL = np.asarray([0, 2, 1, 6, 5, 4], dtype=int)
SUPPORT_LOCAL = np.asarray([3, 7, 8, 9], dtype=int)
NORMAL = np.asarray([0.0, 0.0, 1.0], dtype=float)
PRESSURE_TOL = 1.0e-9
GAP_TOL = 1.0e-10


def build_fixture(gap_mm: float = 0.0003):
    a = np.asarray([-5.0, -5.0, 0.0])
    b = np.asarray([0.0, 5.0, 0.0])
    c = np.asarray([5.0, -5.0, 0.0])
    source_vertices = np.vstack([a, b, c, np.asarray([0.0, 0.0, -10.0])])
    source_nodes = straight_sided_tet10_from_vertices(source_vertices)

    at = a + np.asarray([0.0, 0.0, gap_mm])
    bt = b + np.asarray([0.0, 0.0, gap_mm])
    ct = c + np.asarray([0.0, 0.0, gap_mm])
    target_vertices = np.vstack(
        [at, ct, bt, np.asarray([0.0, 0.0, 10.0 + gap_mm])]
    )
    target_nodes = straight_sided_tet10_from_vertices(target_vertices)

    nodes = np.vstack([source_nodes, target_nodes])
    elements = np.vstack([np.arange(10, dtype=int), np.arange(10, 20, dtype=int)])
    source = Tri6SourceFace("SOURCE", SOURCE_FACE.copy(), NORMAL.copy())
    target = DeformableTri6TargetFace("MASTER", TARGET_FACE_LOCAL.copy() + 10)
    support_nodes = np.concatenate([SUPPORT_LOCAL, SUPPORT_LOCAL + 10])
    fixed = np.asarray(
        [3 * int(node) + component for node in support_nodes for component in range(3)],
        dtype=int,
    )
    return nodes, elements, source, target, fixed


def consistent_tri6_traction_load(nodes, face_nodes, traction_mpa):
    face = np.asarray(face_nodes, dtype=int)
    xyz = np.asarray(nodes, dtype=float)[face]
    corners = xyz[:3]
    area = 0.5 * float(
        np.linalg.norm(np.cross(corners[1] - corners[0], corners[2] - corners[0]))
    )
    traction = np.asarray(traction_mpa, dtype=float).reshape(3)
    force = np.zeros(nodes.shape[0] * 3, dtype=float)
    weight = area / 3.0
    for bary in TRI6_GAUSS_BARYCENTRIC:
        shape = tri6_shape_functions(bary)
        for local_index, node in enumerate(face):
            force[3 * int(node) : 3 * int(node) + 3] += (
                shape[local_index] * weight * traction
            )
    return force


def build_loads(nodes, source, target):
    loads = np.zeros(nodes.shape[0] * 3, dtype=float)
    loads += tri6_surface_pressure_generalized_force(
        nodes_mm=nodes,
        face_nodes=source.node_indices,
        contact_normal=NORMAL,
        pressure_mpa=np.full(3, 10.0),
    )
    loads += tri6_surface_pressure_generalized_force(
        nodes_mm=nodes,
        face_nodes=target.node_indices,
        contact_normal=-NORMAL,
        pressure_mpa=np.full(3, 10.0),
    )
    loads += consistent_tri6_traction_load(
        nodes,
        target.node_indices,
        np.asarray([0.5, 0.0, 0.0]),
    )
    return loads


def barycentric_from_corners(point, corners):
    a, b, c = np.asarray(corners, dtype=float)
    p = np.asarray(point, dtype=float)
    v0 = b - a
    v1 = c - a
    v2 = p - a
    d00 = float(v0 @ v0)
    d01 = float(v0 @ v1)
    d11 = float(v1 @ v1)
    d20 = float(v2 @ v0)
    d21 = float(v2 @ v1)
    denominator = d00 * d11 - d01 * d01
    l2 = (d11 * d20 - d01 * d21) / denominator
    l3 = (d00 * d21 - d01 * d20) / denominator
    return np.asarray([1.0 - l2 - l3, l2, l3], dtype=float)


def analytic_translation_search_control(nodes, source, target):
    displacement = np.zeros_like(nodes)
    displacement[10:, 0] = 0.2
    records = find_deformable_tri6_surface_pairs(
        nodes_mm=nodes,
        displacement_mm=displacement,
        source_faces=[source],
        target_faces=[target],
        max_tracking_distance_mm=1.0,
    )
    shifted_target_xyz = nodes[target.node_indices] + displacement[target.node_indices]
    corners = shifted_target_xyz[:3]
    source_xyz = nodes[source.node_indices]
    expected = []
    for bary in TRI6_GAUSS_BARYCENTRIC:
        source_point = tri6_shape_functions(bary) @ source_xyz
        expected.append(barycentric_from_corners(source_point, corners))
    expected = np.asarray(expected, dtype=float)
    actual = np.asarray([record.target_barycentric for record in records], dtype=float)
    gaps = np.asarray([record.current_gap_mm for record in records], dtype=float)
    return {
        "translation_x_mm": 0.2,
        "expected_barycentric": expected,
        "actual_barycentric": actual,
        "max_barycentric_error": float(np.max(np.abs(actual - expected))),
        "max_gap_error_mm": float(np.max(np.abs(gaps - 0.0003))),
        "max_newton_residual_mm": float(max(record.newton_residual_mm for record in records)),
    }


def independent_pressure_reference(nodes, elements, fixed, loads, result):
    relative = np.asarray(result.relative_operator, dtype=float)
    weights = np.asarray(result.integration_weights_mm2, dtype=float)
    reference_gaps = np.asarray(result.reference_gaps_mm, dtype=float)
    free = solve_linear_static_tet10(nodes, elements, MATERIAL, loads, fixed)
    free_u = free.displacement_mm.reshape(-1)
    free_closure = relative @ free_u
    influence = np.zeros((relative.shape[0], relative.shape[0]), dtype=float)
    for q in range(relative.shape[0]):
        unit_load = relative[q] * weights[q]
        unit = solve_linear_static_tet10(nodes, elements, MATERIAL, unit_load, fixed)
        influence[:, q] = relative @ unit.displacement_mm.reshape(-1)

    valid = []
    masks_tested = 0
    for bits in itertools.product((False, True), repeat=relative.shape[0]):
        masks_tested += 1
        active = np.flatnonzero(np.asarray(bits, dtype=bool))
        pressure = np.zeros(relative.shape[0], dtype=float)
        if active.size:
            try:
                pressure[active] = np.linalg.solve(
                    influence[np.ix_(active, active)],
                    free_closure[active] - reference_gaps[active],
                )
            except np.linalg.LinAlgError:
                continue
        closure = free_closure - influence @ pressure
        signed_gap = reference_gaps - closure
        inactive = np.setdiff1d(np.arange(relative.shape[0], dtype=int), active)
        if active.size and np.any(pressure[active] < -1.0e-8):
            continue
        if active.size and np.any(np.abs(signed_gap[active]) > GAP_TOL):
            continue
        if inactive.size and np.any(signed_gap[inactive] < -GAP_TOL):
            continue
        pressure[np.abs(pressure) <= 1.0e-8] = 0.0
        canonical = tuple(int(i) for i in np.flatnonzero(pressure > 1.0e-8))
        valid.append((closure, signed_gap, pressure, canonical))

    if not valid:
        raise SystemExit("GAP-I independent 2^3 reference found no admissible solution")
    canonical_sets = {entry[3] for entry in valid}
    if len(canonical_sets) != 1:
        raise SystemExit(f"GAP-I independent active set is not unique: {canonical_sets}")
    canonical = next(iter(canonical_sets))
    closure, signed_gap, pressure, _ = next(entry for entry in valid if entry[3] == canonical)
    return {
        "masks_tested": masks_tested,
        "active_contact_indices": canonical,
        "contact_pressure_mpa": pressure,
        "relative_closure_mm": closure,
        "signed_gaps_mm": signed_gap,
        "pressure_influence_mm_per_mpa": influence,
    }


def viewer(payload):
    rows = []
    production = payload["production"]
    for index, (pressure, gap, bary) in enumerate(
        zip(
            production["contact_pressure_mpa"],
            production["signed_gaps_mm"],
            production["target_barycentric"],
        )
    ):
        rows.append(
            f"<tr><td>{index}</td><td>{pressure:.9f}</td><td>{gap:.3e}</td>"
            f"<td>{bary[0]:.9f}, {bary[1]:.9f}, {bary[2]:.9f}</td></tr>"
        )
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>AsterMax GAP-I</title>
<style>body{{font-family:system-ui;margin:30px;max-width:1050px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #aaa;padding:7px;text-align:right}}.tag{{font-weight:700}}</style></head>
<body><h1>AsterMax GAP-I · deformable TRI6 master</h1>
<p class='tag'>SYNTHETIC SMALL-STRAIN VERIFICATION — NOT AN INDUSTRIAL RESULT</p>
<p>Primary pressure acts through a relative source/master operator. The quadratic master surface is re-searched on deformed geometry until pairing converges.</p>
<table><thead><tr><th>IP</th><th>Pressure MPa</th><th>Gap mm</th><th>Master barycentric</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<p>No friction, preload, general large-sliding, finite-strain, OT1613 industrial pressure, industrial validation or ANSYS-equivalence claim.</p>
</body></html>"""


def main():
    nodes, elements, source, target, fixed = build_fixture()
    loads = build_loads(nodes, source, target)
    translation_control = analytic_translation_search_control(nodes, source, target)
    result = solve_tet10_deformable_surface_contact(
        nodes_mm=nodes,
        elements=elements,
        material=MATERIAL,
        loads_n=loads,
        fixed_dofs=fixed,
        source_faces=[source],
        target_faces=[target],
        max_tracking_distance_mm=0.02,
    )
    reference = independent_pressure_reference(nodes, elements, fixed, loads, result)

    pressure_error = float(
        np.max(np.abs(result.contact_pressure_mpa - reference["contact_pressure_mpa"]))
    )
    closure_error = float(
        np.max(np.abs(result.relative_closure_mm - reference["relative_closure_mm"]))
    )
    production_active = tuple(result.active_contact_indices)
    history = result.pairing_barycentric_history
    history_motion = 0.0
    if len(history) >= 2:
        history_motion = float(np.max(np.abs(history[-1] - history[0])))

    checks = {
        "deterministic_primary_pressure_reference_enumerated_all_8_sets": reference["masks_tested"] == 8,
        "independent_reference_unique_active_set_matches": production_active == reference["active_contact_indices"],
        "pressure_matches_independent_reference": pressure_error <= 1.0e-8,
        "relative_closure_matches_independent_reference": closure_error <= 1.0e-10,
        "analytic_translated_master_barycentric_exact": translation_control["max_barycentric_error"] <= 1.0e-10,
        "analytic_translated_master_gap_exact": translation_control["max_gap_error_mm"] <= 1.0e-10,
        "quadratic_search_newton_residual_small": translation_control["max_newton_residual_mm"] <= 1.0e-11,
        "deformable_master_pair_update_executed": result.pairing_updated_iteratively and result.outer_iterations >= 2,
        "production_pairing_history_changed": history_motion > 1.0e-12,
        "final_pairing_barycentric_converged": result.max_pairing_barycentric_delta <= 1.0e-9,
        "geometric_gap_consistency": result.max_geometric_gap_consistency_error_mm <= 1.0e-9,
        "pressure_is_primary": result.pressure_is_primary_contact_unknown,
        "pressure_not_recovered_from_nodal_reactions": not result.contact_pressure_recovered_from_nodal_reactions,
        "nonnegative_pressure": bool(np.all(result.contact_pressure_mpa >= -PRESSURE_TOL)),
        "contact_is_exercised": bool(np.any(result.contact_pressure_mpa > PRESSURE_TOL)),
        "no_penetration": result.exact_no_penetration and bool(np.all(result.signed_gaps_mm >= -GAP_TOL)),
        "signorini_complementarity": bool(np.all(np.abs(result.complementarity_mpa_mm) <= 1.0e-10)),
        "equal_and_opposite_contact_traction": result.equal_and_opposite_contact_traction and float(np.linalg.norm(result.net_contact_resultant_n)) <= 1.0e-8,
        "free_dof_equilibrium": result.free_equilibrium_residual_norm_n <= 1.0e-6,
        "both_deformable_tet10_bodies_stressed": bool(
            result.integration_point_von_mises_mpa.shape == (2, 4)
            and np.isfinite(result.integration_point_von_mises_mpa).all()
            and float(np.max(result.integration_point_von_mises_mpa[0])) > 0.0
            and float(np.max(result.integration_point_von_mises_mpa[1])) > 0.0
        ),
        "penalty_not_used": not result.penalty_method_used,
        "friction_not_claimed": not result.friction_solved,
        "large_sliding_not_claimed": not result.large_sliding_claimed,
        "finite_strain_not_claimed": not result.finite_strain_claimed,
        "industrial_result_not_claimed": not result.industrial_validation_claimed and not result.ot1613_result_claimed,
        "ansys_equivalence_not_claimed": not result.ansys_equivalence_claimed,
    }
    passed = all(bool(value) for value in checks.values())

    payload = {
        "schema_version": "AsterMaxTet10DeformableMasterPairUpdateEvidenceV1",
        "classification": "SYNTHETIC_TET10_TRI6_DEFORMABLE_MASTER_UPDATED_PAIRING_NOT_INDUSTRIAL_RESULT",
        "claim": "DEFORMABLE_TRI6_MASTER_PRIMARY_PRESSURE_WITH_ITERATIVE_QUADRATIC_GEOMETRIC_PAIR_UPDATE",
        "passed": passed,
        "checks": {key: bool(value) for key, value in checks.items()},
        "fixture": {
            "deformable_tet10_bodies": 2,
            "source_face": source.face_id,
            "master_face": target.face_id,
            "reference_gap_mm": 0.0003,
            "normal_closing_traction_each_side_mpa": 10.0,
            "master_tangential_traction_x_mpa": 0.5,
            "source_side_gauss_points": 3,
        },
        "analytic_translation_search_control": {
            "translation_x_mm": translation_control["translation_x_mm"],
            "max_barycentric_error": translation_control["max_barycentric_error"],
            "max_gap_error_mm": translation_control["max_gap_error_mm"],
            "max_newton_residual_mm": translation_control["max_newton_residual_mm"],
        },
        "independent_reference": {
            "method": "THREE_EQUAL_OPPOSITE_UNIT_PRESSURE_TET10_SOLVES_PLUS_EXHAUSTIVE_2_POWER_3_ACTIVE_SET_ENUMERATION",
            "masks_tested": reference["masks_tested"],
            "active_contact_indices": list(reference["active_contact_indices"]),
            "contact_pressure_mpa": reference["contact_pressure_mpa"].tolist(),
            "relative_closure_mm": reference["relative_closure_mm"].tolist(),
            "signed_gaps_mm": reference["signed_gaps_mm"].tolist(),
        },
        "production": {
            "active_contact_indices": list(production_active),
            "contact_pressure_mpa": result.contact_pressure_mpa.tolist(),
            "signed_gaps_mm": result.signed_gaps_mm.tolist(),
            "relative_closure_mm": result.relative_closure_mm.tolist(),
            "target_barycentric": [record.target_barycentric.tolist() for record in result.pairing_records],
            "target_ids": [record.target_face_id for record in result.pairing_records],
            "outer_iterations": result.outer_iterations,
            "inner_iterations": result.inner_iterations,
            "pairing_history_motion": history_motion,
            "max_pairing_barycentric_delta": result.max_pairing_barycentric_delta,
            "max_geometric_gap_consistency_error_mm": result.max_geometric_gap_consistency_error_mm,
            "net_contact_resultant_n": result.net_contact_resultant_n.tolist(),
            "free_equilibrium_residual_norm_n": result.free_equilibrium_residual_norm_n,
            "max_ip_von_mises_source_mpa": float(np.max(result.integration_point_von_mises_mpa[0])),
            "max_ip_von_mises_master_mpa": float(np.max(result.integration_point_von_mises_mpa[1])),
        },
        "comparison": {
            "max_pressure_error_mpa": pressure_error,
            "max_relative_closure_error_mm": closure_error,
        },
        "solver_boundary": {
            "master_surface": "DEFORMABLE_QUADRATIC_TRI6",
            "surface_search": "NEWTON_INTERSECTION_OF_FIXED_SOURCE_NORMAL_RAY_WITH_DEFORMED_TRI6",
            "pairing_update": "ITERATIVE_SMALL_STRAIN_TOTAL_LAGRANGIAN_BARYCENTRIC_UPDATE",
            "pressure": "PRIMARY_SOURCE_GAUSS_POINT_UNKNOWN_MPA",
            "contact_virtual_work": "G_EQUALS_H_SOURCE_MINUS_H_MASTER_EQUAL_AND_OPPOSITE",
            "integration": "ONE_PASS_SOURCE_SIDE_THREE_POINT_TRI6",
            "penalty_method": False,
            "nodal_reaction_to_pressure_projection": False,
            "friction": False,
            "preload": False,
            "large_sliding_claim": False,
            "finite_strain_claim": False,
            "industrial_validation": False,
            "ot1613_industrial_pressure": False,
            "ansys_equivalence": False,
            "next_gate": "MULTIFACE_DEFORMABLE_MASTER_CANDIDATE_SWITCH_AND_SLIDING_PATH_VERIFICATION",
        },
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    OUTPUT_HTML.write_text(viewer(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"wrote {OUTPUT_JSON.resolve()}")
    print(f"wrote {OUTPUT_HTML.resolve()}")
    if not passed:
        failed = [key for key, value in checks.items() if not value]
        raise SystemExit(f"GAP-I verification failed: {failed}")


if __name__ == "__main__":
    main()
