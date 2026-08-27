from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np

from astermax.contact import (
    RigidTri6TargetFace,
    Tri6SourceFace,
    solve_tet10_multiface_surface_contact,
    tri6_surface_operator,
    tri6_surface_pressure_generalized_force,
)
from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet4 import IsotropicMaterial


OUTPUT_DIR = Path("multiface_surface_search")
OUTPUT_JSON = OUTPUT_DIR / "multiface_surface_search.json"
OUTPUT_HTML = OUTPUT_DIR / "multiface_surface_search_viewer.html"
MATERIAL = IsotropicMaterial(young_modulus_mpa=200_000.0, poisson_ratio=0.30)
LOCAL_FACE = np.asarray([0, 1, 2, 4, 5, 6], dtype=int)
LOCAL_SUPPORT = np.asarray([3, 7, 8, 9], dtype=int)
NORMAL = np.asarray([0.0, 0.0, 1.0], dtype=float)
PRESSURE_TOL = 1.0e-9
GAP_TOL = 1.0e-10


def build_fixture():
    vertices = np.asarray(
        [
            [-5.0, -5.0, 10.0],
            [0.0, 5.0, 10.0],
            [5.0, -5.0, 10.0],
            [0.0, 0.0, 0.0],
        ],
        dtype=float,
    )
    first = straight_sided_tet10_from_vertices(vertices)
    second = first + np.asarray([20.0, 0.0, 0.0])
    nodes = np.vstack([first, second])
    elements = np.vstack([np.arange(10, dtype=int), np.arange(10, 20, dtype=int)])
    sources = [
        Tri6SourceFace("SOURCE_A", LOCAL_FACE.copy(), NORMAL.copy()),
        Tri6SourceFace("SOURCE_B", LOCAL_FACE.copy() + 10, NORMAL.copy()),
    ]
    support_nodes = np.concatenate([LOCAL_SUPPORT, LOCAL_SUPPORT + 10])
    fixed = np.asarray(
        [3 * int(node) + component for node in support_nodes for component in range(3)],
        dtype=int,
    )
    return nodes, elements, sources, fixed


def target_from_source(nodes, source_nodes, gap_mm, face_id, xy_shift=(0.0, 0.0)):
    xyz = nodes[source_nodes].copy()
    xyz[:, 0] += xy_shift[0]
    xyz[:, 1] += xy_shift[1]
    xyz[:, 2] += gap_mm
    xyz = xyz[np.asarray([0, 2, 1, 5, 4, 3], dtype=int)]
    return RigidTri6TargetFace(face_id, xyz)


def combined_operator(nodes, sources):
    rows = []
    weights = []
    for source in sources:
        operator, face_weights, _ = tri6_surface_operator(
            nodes_mm=nodes,
            face_nodes=source.node_indices,
            contact_normal=source.contact_normal,
        )
        rows.extend(operator)
        weights.extend(face_weights.tolist())
    return np.asarray(rows, dtype=float), np.asarray(weights, dtype=float)


def independent_pressure_influence(nodes, elements, fixed, operator, weights):
    influence = np.zeros((operator.shape[0], operator.shape[0]), dtype=float)
    for q in range(operator.shape[0]):
        result = solve_linear_static_tet10(
            nodes,
            elements,
            MATERIAL,
            operator[q] * weights[q],
            fixed,
        )
        influence[:, q] = operator @ result.displacement_mm.reshape(-1)
    return influence


def enumerate_lcp(free_ip, influence, gaps):
    valid = []
    masks_tested = 0
    for bits in itertools.product((False, True), repeat=len(gaps)):
        masks_tested += 1
        active = np.flatnonzero(np.asarray(bits, dtype=bool))
        pressure = np.zeros(len(gaps), dtype=float)
        if active.size:
            try:
                pressure[active] = np.linalg.solve(
                    influence[np.ix_(active, active)],
                    free_ip[active] - gaps[active],
                )
            except np.linalg.LinAlgError:
                continue
        displacement = free_ip - influence @ pressure
        signed_gap = gaps - displacement
        inactive = np.setdiff1d(np.arange(len(gaps), dtype=int), active)
        if active.size and np.any(pressure[active] < -1.0e-8):
            continue
        if active.size and np.any(np.abs(signed_gap[active]) > GAP_TOL):
            continue
        if inactive.size and np.any(signed_gap[inactive] < -GAP_TOL):
            continue
        pressure[np.abs(pressure) <= 1.0e-8] = 0.0
        canonical = tuple(int(i) for i in np.flatnonzero(pressure > 1.0e-8))
        valid.append((displacement, pressure, canonical))
    if not valid:
        raise SystemExit("GAP-H independent 2^6 reference found no admissible solution")
    canonical_sets = {entry[2] for entry in valid}
    if len(canonical_sets) != 1:
        raise SystemExit(f"GAP-H independent reference is not unique: {canonical_sets}")
    canonical = next(iter(canonical_sets))
    displacement, pressure, _ = next(entry for entry in valid if entry[2] == canonical)
    return displacement, pressure, canonical, masks_tested


def viewer(payload):
    rows = []
    for record, pressure, gap, state in zip(
        payload["pairing"],
        payload["production"]["contact_pressure_mpa"],
        payload["production"]["signed_gaps_mm"],
        payload["production"]["states"],
    ):
        rows.append(
            f"<tr><td>{record['source_face_id']}</td><td>IP{record['integration_point_index']}</td>"
            f"<td>{record['target_face_id']}</td><td>{record['initial_gap_mm']:.9f}</td>"
            f"<td>{pressure:.9f}</td><td>{gap:.9e}</td><td>{state}</td></tr>"
        )
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>AsterMax GAP-H</title>
<style>body{{font-family:system-ui;margin:30px;max-width:1100px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #aaa;padding:7px;text-align:right}}td:first-child,td:nth-child(3){{text-align:left}}.tag{{font-weight:700}}</style></head>
<body><h1>AsterMax GAP-H · multiface geometric surface search</h1>
<p class='tag'>SYNTHETIC VERIFICATION — NOT AN INDUSTRIAL RESULT</p>
<p>Two deformable TRI6 source faces are paired geometrically against rigid TRI6 target candidates. Primary pressure is solved globally across all six integration points.</p>
<table><thead><tr><th>Source</th><th>IP</th><th>Target</th><th>Initial gap mm</th><th>Pressure MPa</th><th>Final gap mm</th><th>State</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<p>Pair map frozen for this small-displacement verification. No friction, large sliding, deformable master surface, OT1613 pressure, industrial validation or ANSYS-equivalence claim.</p>
</body></html>"""


def main():
    nodes, elements, sources, fixed = build_fixture()
    targets = [
        target_from_source(nodes, sources[0].node_indices, 0.0002, "TARGET_A"),
        target_from_source(nodes, sources[1].node_indices, 0.0008, "TARGET_B"),
        target_from_source(nodes, sources[0].node_indices, 0.0001, "DECOY_OUTSIDE", xy_shift=(50.0, 0.0)),
    ]
    loads = np.zeros(nodes.shape[0] * 3, dtype=float)
    for source in sources:
        loads += tri6_surface_pressure_generalized_force(
            nodes_mm=nodes,
            face_nodes=source.node_indices,
            contact_normal=source.contact_normal,
            pressure_mpa=np.full(3, 10.0),
        )

    operator, weights = combined_operator(nodes, sources)
    free = solve_linear_static_tet10(nodes, elements, MATERIAL, loads, fixed)
    free_ip = operator @ free.displacement_mm.reshape(-1)
    designed_gaps = np.asarray([0.0002] * 3 + [0.0008] * 3, dtype=float)
    influence = independent_pressure_influence(nodes, elements, fixed, operator, weights)
    symmetry_error = float(np.max(np.abs(influence - influence.T)))
    reference_u, reference_p, reference_active, masks_tested = enumerate_lcp(
        free_ip, influence, designed_gaps
    )

    result = solve_tet10_multiface_surface_contact(
        nodes_mm=nodes,
        elements=elements,
        material=MATERIAL,
        loads_n=loads,
        fixed_dofs=fixed,
        source_faces=sources,
        target_faces=targets,
        max_search_distance_mm=0.01,
        ambiguity_tolerance_mm=1.0e-10,
        pressure_tolerance_mpa=PRESSURE_TOL,
        gap_tolerance_mm=GAP_TOL,
    )

    pair_ids = [record.target_face_id for record in result.pairing_records]
    expected_pair_ids = ["TARGET_A"] * 3 + ["TARGET_B"] * 3
    search_gaps = np.asarray([record.initial_gap_mm for record in result.pairing_records], dtype=float)
    pressure_error = float(np.max(np.abs(result.contact_pressure_mpa - reference_p)))
    displacement_error = float(np.max(np.abs(result.integration_displacements_mm - reference_u)))
    generalized_resultant = np.zeros(3, dtype=float)
    for row in result.contact_generalized_force_n:
        generalized_resultant += row
    point_resultant = np.zeros(3, dtype=float)
    for record, point_force in zip(result.pairing_records, result.contact_point_forces_n):
        point_resultant += point_force * record.source_normal
    resultant_error = float(np.linalg.norm(generalized_resultant - point_resultant))

    checks = {
        "geometric_search_executed": result.geometric_surface_search_executed,
        "multiple_source_faces_executed": result.multiple_source_faces_executed,
        "expected_pair_map_exact": pair_ids == expected_pair_ids,
        "decoy_not_selected": "DECOY_OUTSIDE" not in pair_ids,
        "search_gaps_match_geometry": bool(np.allclose(search_gaps, designed_gaps, rtol=0.0, atol=1.0e-12)),
        "independent_reference_enumerated_all_64_sets": masks_tested == 64,
        "independent_reference_unique_active_set": tuple(result.active_contact_indices) == reference_active,
        "expected_active_set_0_and_2": tuple(result.active_contact_indices) == (0, 2),
        "pressure_matches_independent_reference": pressure_error <= 1.0e-8,
        "displacement_matches_independent_reference": displacement_error <= 1.0e-10,
        "pressure_is_primary": result.pressure_is_primary_contact_unknown,
        "pressure_not_recovered_from_nodal_reactions": not result.contact_pressure_recovered_from_nodal_reactions,
        "nonnegative_pressure": bool(np.all(result.contact_pressure_mpa >= -PRESSURE_TOL)),
        "no_penetration": result.exact_no_penetration and bool(np.all(result.signed_gaps_mm >= -GAP_TOL)),
        "signorini_complementarity": bool(np.all(np.abs(result.complementarity_mpa_mm) <= 1.0e-10)),
        "free_dof_equilibrium": result.free_equilibrium_residual_norm_n <= 1.0e-5,
        "pressure_resultant_consistent": resultant_error <= 1.0e-8,
        "pressure_influence_symmetric": symmetry_error <= 1.0e-10,
        "target_surfaces_rigid_declared": result.target_surfaces_rigid,
        "pairing_frozen_small_displacement_declared": result.pairing_frozen_small_displacement,
        "penalty_method_not_used": not result.penalty_method_used,
        "friction_not_claimed": not result.friction_solved,
        "industrial_result_not_claimed": not result.industrial_validation_claimed and not result.ot1613_result_claimed,
        "ansys_equivalence_not_claimed": not result.ansys_equivalence_claimed,
        "real_tet10_ip_stress_recovered": bool(
            result.integration_point_stress_mpa.shape == (2, 4, 6)
            and np.isfinite(result.integration_point_stress_mpa).all()
            and float(np.max(result.integration_point_von_mises_mpa)) > 0.0
        ),
    }
    passed = all(bool(value) for value in checks.values())

    pairing = [
        {
            "source_face_id": record.source_face_id,
            "integration_point_index": record.integration_point_index,
            "target_face_id": record.target_face_id,
            "initial_gap_mm": record.initial_gap_mm,
            "source_point_mm": record.source_point_mm.tolist(),
            "target_point_mm": record.target_point_mm.tolist(),
            "target_barycentric": record.target_barycentric.tolist(),
        }
        for record in result.pairing_records
    ]
    payload = {
        "schema_version": "AsterMaxTet10MultifaceSurfaceSearchEvidenceV1",
        "classification": "SYNTHETIC_MULTIFACE_TRI6_GEOMETRIC_SEARCH_PRIMARY_PRESSURE_NOT_INDUSTRIAL_RESULT",
        "claim": "MULTIFACE_SMALL_DISPLACEMENT_GEOMETRIC_PAIRING_PLUS_GLOBAL_PRIMARY_PRESSURE_CONTACT",
        "passed": passed,
        "checks": {key: bool(value) for key, value in checks.items()},
        "pairing": pairing,
        "fixture": {
            "deformable_tet10_bodies": 2,
            "source_faces": [source.face_id for source in sources],
            "target_candidates": [target.face_id for target in targets],
            "expected_pair_ids": expected_pair_ids,
            "designed_geometric_gaps_mm": designed_gaps.tolist(),
            "driving_surface_pressure_mpa": 10.0,
            "search_distance_mm": 0.01,
        },
        "independent_reference": {
            "method": "SIX_UNIT_PRESSURE_TET10_SOLVES_PLUS_EXHAUSTIVE_2_POWER_6_ACTIVE_SET_ENUMERATION",
            "masks_tested": masks_tested,
            "active_contact_indices": list(reference_active),
            "contact_pressure_mpa": reference_p.tolist(),
            "integration_displacements_mm": reference_u.tolist(),
            "pressure_influence_symmetry_error_mm_per_mpa": symmetry_error,
        },
        "production": {
            "active_contact_indices": list(result.active_contact_indices),
            "states": [state.value for state in result.states],
            "contact_pressure_mpa": result.contact_pressure_mpa.tolist(),
            "initial_gaps_mm": result.initial_gaps_mm.tolist(),
            "signed_gaps_mm": result.signed_gaps_mm.tolist(),
            "contact_point_forces_n": result.contact_point_forces_n.tolist(),
            "free_equilibrium_residual_norm_n": result.free_equilibrium_residual_norm_n,
            "max_ip_von_mises_mpa": float(np.max(result.integration_point_von_mises_mpa)),
            "active_set_history": [list(item) for item in result.active_set_history],
            "iterations": result.iterations,
        },
        "comparison": {
            "max_pressure_error_mpa": pressure_error,
            "max_integration_displacement_error_mm": displacement_error,
            "contact_resultant_vector_error_n": resultant_error,
        },
        "solver_boundary": {
            "surface_search": "FORWARD_RAY_TO_NEAREST_OPPOSED_RIGID_TRI6_TARGET_WITH_TRIANGLE_CONTAINMENT",
            "ambiguous_equal_distance_pairing": "FAIL_CLOSED",
            "pair_map_update_during_deformation": False,
            "large_sliding": False,
            "deformable_master_surface": False,
            "pressure_primary_unknown": True,
            "nodal_reaction_to_pressure_projection": False,
            "friction": False,
            "preload": False,
            "industrial_validation": False,
            "ot1613_industrial_pressure": False,
            "ansys_equivalence": False,
            "next_gate": "DEFORMABLE_MASTER_AND_ITERATIVE_PAIR_MAP_UPDATE",
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
        raise SystemExit(f"GAP-H verification failed: {failed}")


if __name__ == "__main__":
    main()
