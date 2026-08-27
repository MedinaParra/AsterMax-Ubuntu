from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np

from astermax.contact import (
    solve_tet10_tri6_surface_pressure_contact,
    tri6_surface_operator,
    tri6_surface_pressure_generalized_force,
)
from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet4 import IsotropicMaterial


OUTPUT_DIR = Path("tri6_surface_pressure_contact")
OUTPUT_JSON = OUTPUT_DIR / "tri6_surface_pressure_contact.json"
OUTPUT_HTML = OUTPUT_DIR / "tri6_surface_pressure_contact_viewer.html"
MATERIAL = IsotropicMaterial(young_modulus_mpa=200_000.0, poisson_ratio=0.30)
FACE_NODES = np.asarray([0, 1, 2, 4, 5, 6], dtype=int)
SUPPORT_NODES = np.asarray([3, 7, 8, 9], dtype=int)
FIXED_DOFS = np.asarray(
    [3 * node + component for node in SUPPORT_NODES for component in range(3)],
    dtype=int,
)
NORMAL = np.asarray([0.0, 0.0, 1.0], dtype=float)
DRIVING_PRESSURE_MPA = np.full(3, 10.0, dtype=float)
GAP_FACTORS = np.asarray([0.55, 1.40, 0.75], dtype=float)
PRESSURE_TOLERANCE_MPA = 1.0e-8
GAP_TOLERANCE_MM = 1.0e-10


def build_fixture() -> tuple[np.ndarray, np.ndarray]:
    vertices = np.asarray(
        [
            [-5.0, -5.0, 10.0],
            [0.0, 5.0, 10.0],
            [5.0, -5.0, 10.0],
            [0.0, 0.0, 0.0],
        ],
        dtype=float,
    )
    nodes = straight_sided_tet10_from_vertices(vertices)
    return nodes, np.arange(10, dtype=int).reshape(1, 10)


def independent_pressure_influence(
    nodes: np.ndarray,
    elements: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    operator, barycentric, weights = tri6_surface_operator(
        nodes_mm=nodes,
        face_nodes=FACE_NODES,
        contact_normal=NORMAL,
    )
    influence = np.zeros((3, 3), dtype=float)
    for q in range(3):
        loads = operator[q] * weights[q]
        result = solve_linear_static_tet10(
            nodes,
            elements,
            MATERIAL,
            loads,
            FIXED_DOFS,
        )
        influence[:, q] = operator @ result.displacement_mm.reshape(-1)
    return operator, barycentric, weights, influence


def enumerate_pressure_lcp(
    free_ip_mm: np.ndarray,
    influence_mm_per_mpa: np.ndarray,
    gaps_mm: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, tuple[int, ...], int]:
    valid: list[tuple[np.ndarray, np.ndarray, tuple[int, ...]]] = []
    masks_tested = 0
    for mask_bits in itertools.product((False, True), repeat=3):
        masks_tested += 1
        active = np.flatnonzero(np.asarray(mask_bits, dtype=bool))
        pressure = np.zeros(3, dtype=float)
        if active.size:
            try:
                pressure[active] = np.linalg.solve(
                    influence_mm_per_mpa[np.ix_(active, active)],
                    free_ip_mm[active] - gaps_mm[active],
                )
            except np.linalg.LinAlgError:
                continue

        displacement = free_ip_mm - influence_mm_per_mpa @ pressure
        signed_gap = gaps_mm - displacement
        inactive = np.setdiff1d(np.arange(3, dtype=int), active)
        if active.size and np.any(pressure[active] < -PRESSURE_TOLERANCE_MPA):
            continue
        if active.size and np.any(np.abs(signed_gap[active]) > GAP_TOLERANCE_MM):
            continue
        if inactive.size and np.any(signed_gap[inactive] < -GAP_TOLERANCE_MM):
            continue

        pressure[np.abs(pressure) <= PRESSURE_TOLERANCE_MPA] = 0.0
        canonical = tuple(int(i) for i in np.flatnonzero(pressure > PRESSURE_TOLERANCE_MPA))
        valid.append((displacement, pressure, canonical))

    if not valid:
        raise SystemExit("independent integration-point LCP found no admissible solution")
    canonical_sets = {entry[2] for entry in valid}
    if len(canonical_sets) != 1:
        raise SystemExit(f"integration-point LCP reference is not physically unique: {canonical_sets}")
    canonical = next(iter(canonical_sets))
    displacement, pressure, _ = next(entry for entry in valid if entry[2] == canonical)
    return displacement, pressure, canonical, masks_tested


def viewer_html(payload: dict, nodes: np.ndarray) -> str:
    corners = nodes[FACE_NODES[:3], :2]
    barycentric = np.asarray(payload["surface_integration"]["barycentric"], dtype=float)
    xy = barycentric @ corners
    xmin, ymin = corners.min(axis=0)
    xmax, ymax = corners.max(axis=0)
    width = max(float(xmax - xmin), 1.0)
    height = max(float(ymax - ymin), 1.0)

    def sx(x: float) -> float:
        return 80.0 + 440.0 * (x - xmin) / width

    def sy(y: float) -> float:
        return 420.0 - 340.0 * (y - ymin) / height

    corner_points = " ".join(f"{sx(float(x)):.2f},{sy(float(y)):.2f}" for x, y in corners)
    pressure = payload["production_result"]["contact_pressure_mpa"]
    states = payload["production_result"]["states"]
    markers = []
    for index, ((x, y), value, state) in enumerate(zip(xy, pressure, states), start=1):
        radius = 14.0 + 3.0 * max(float(value), 0.0)
        markers.append(
            f'<circle cx="{sx(float(x)):.2f}" cy="{sy(float(y)):.2f}" r="{radius:.2f}" '
            f'fill="none" stroke="currentColor" stroke-width="3" />'
            f'<text x="{sx(float(x)):.2f}" y="{sy(float(y)) + 5:.2f}" text-anchor="middle" '
            f'font-size="14">IP{index}</text>'
            f'<text x="{sx(float(x)):.2f}" y="{sy(float(y)) + radius + 22:.2f}" text-anchor="middle" '
            f'font-size="13">{float(value):.6f} MPa · {state}</text>'
        )
    marker_html = "".join(markers)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>AsterMax GAP-G</title>
<style>body{{font-family:system-ui;margin:28px;max-width:980px}}code{{background:#eee;padding:2px 5px}}svg{{width:100%;max-width:620px;border:1px solid #aaa}}.ok{{font-weight:700}}li{{margin:6px 0}}</style></head>
<body><h1>AsterMax GAP-G · primary surface pressure contact</h1>
<p class="ok">VERIFICATION BENCHMARK — NOT AN INDUSTRIAL RESULT</p>
<p>Pressure is solved as the primary unilateral contact unknown at the three TRI6 surface integration points. It is not reconstructed from nodal reactions.</p>
<svg viewBox="0 0 600 500" role="img" aria-label="TRI6 contact pressure integration points">
<polygon points="{corner_points}" fill="none" stroke="currentColor" stroke-width="3" />{marker_html}</svg>
<ul><li>Active integration points: {payload['production_result']['active_contact_indices']}</li>
<li>Free-equilibrium residual: {payload['production_result']['free_equilibrium_residual_norm_n']:.6e} N</li>
<li>Independent reference: exhaustive 2^3 active-set enumeration</li>
<li>Penalty method: false</li><li>Friction: not solved</li><li>OT1613 industrial pressure: not claimed</li></ul>
</body></html>"""


def main() -> None:
    nodes, elements = build_fixture()
    operator, barycentric, weights, influence = independent_pressure_influence(nodes, elements)
    symmetry_error = float(np.max(np.abs(influence - influence.T)))
    if not np.all(np.isfinite(influence)) or symmetry_error > 1.0e-10:
        raise SystemExit("integration-point pressure influence is non-finite or non-symmetric")

    loads = tri6_surface_pressure_generalized_force(
        nodes_mm=nodes,
        face_nodes=FACE_NODES,
        contact_normal=NORMAL,
        pressure_mpa=DRIVING_PRESSURE_MPA,
    )
    free = solve_linear_static_tet10(nodes, elements, MATERIAL, loads, FIXED_DOFS)
    free_ip = operator @ free.displacement_mm.reshape(-1)
    if np.any(free_ip <= 0.0):
        raise SystemExit("driving pressure did not close all verification integration points")
    gaps = free_ip * GAP_FACTORS

    reference_u, reference_p, reference_active, masks_tested = enumerate_pressure_lcp(
        free_ip,
        influence,
        gaps,
    )
    result = solve_tet10_tri6_surface_pressure_contact(
        nodes_mm=nodes,
        elements=elements,
        material=MATERIAL,
        loads_n=loads,
        fixed_dofs=FIXED_DOFS,
        face_nodes=FACE_NODES,
        contact_normal=NORMAL,
        initial_gaps_mm=gaps,
        pressure_tolerance_mpa=1.0e-9,
        gap_tolerance_mm=GAP_TOLERANCE_MM,
        equilibrium_tolerance_n=1.0e-6,
    )

    pressure_error = float(np.max(np.abs(result.contact_pressure_mpa - reference_p)))
    displacement_error = float(np.max(np.abs(result.integration_displacements_mm - reference_u)))
    resultant_from_points = float(np.sum(result.contact_point_forces_n))
    resultant_from_generalized = float(np.sum(result.contact_generalized_force_n @ NORMAL))
    resultant_error = abs(resultant_from_points - resultant_from_generalized)
    active_count = len(result.active_contact_indices)
    open_count = int(sum(state.value == "OPEN" for state in result.states))

    checks = {
        "pressure_unknown_is_primary": result.pressure_is_primary_contact_unknown,
        "pressure_not_recovered_from_nodal_reactions": not result.contact_pressure_recovered_from_nodal_reactions,
        "independent_reference_enumerated_all_8_sets": masks_tested == 8,
        "independent_reference_unique_active_set": tuple(result.active_contact_indices) == reference_active,
        "pressure_matches_independent_reference": pressure_error <= 1.0e-8,
        "surface_displacement_matches_reference": displacement_error <= 1.0e-10,
        "partial_contact_exercised": active_count == 2 and open_count == 1,
        "expected_partial_active_set_0_and_2": tuple(result.active_contact_indices) == (0, 2),
        "nonnegative_pressure": bool(np.all(result.contact_pressure_mpa >= -1.0e-9)),
        "no_penetration": result.exact_no_penetration and bool(np.all(result.signed_gaps_mm >= -GAP_TOLERANCE_MM)),
        "signorini_complementarity": bool(np.all(np.abs(result.complementarity_mpa_mm) <= 1.0e-10)),
        "free_dof_equilibrium": result.free_equilibrium_residual_norm_n <= 1.0e-5,
        "pressure_resultant_is_consistently_integrated": resultant_error <= 1.0e-8,
        "surface_quadrature_area_is_exact": abs(float(np.sum(weights)) - 50.0) <= 1.0e-12,
        "pressure_influence_symmetric": symmetry_error <= 1.0e-10,
        "real_tet10_ip_stress_recovered": bool(
            result.integration_point_stress_mpa.shape == (1, 4, 6)
            and result.integration_point_von_mises_mpa.shape == (1, 4)
            and np.isfinite(result.integration_point_stress_mpa).all()
            and float(np.max(result.integration_point_von_mises_mpa)) > 0.0
        ),
        "penalty_method_not_used": result.penalty_method_used is False,
        "friction_not_claimed": result.friction_solved is False,
        "industrial_result_not_claimed": result.industrial_validation_claimed is False and result.ot1613_result_claimed is False,
        "ansys_equivalence_not_claimed": result.ansys_equivalence_claimed is False,
    }
    passed = all(bool(value) for value in checks.values())

    payload = {
        "schema_version": "AsterMaxTet10Tri6SurfacePressureContactEvidenceV1",
        "classification": "SYNTHETIC_TET10_TRI6_PRIMARY_SURFACE_PRESSURE_CONTACT_NOT_INDUSTRIAL_RESULT",
        "claim": "PRIMARY_INTEGRATION_POINT_NORMAL_PRESSURE_SIGNORINI_CONTACT_ON_DEFORMABLE_TET10",
        "passed": passed,
        "checks": {key: bool(value) for key, value in checks.items()},
        "fixture": {
            "element_family": "TET10",
            "contact_face": "STRAIGHT_PLANAR_TRI6",
            "face_nodes": FACE_NODES.tolist(),
            "support_nodes": SUPPORT_NODES.tolist(),
            "contact_normal": NORMAL.tolist(),
            "young_modulus_mpa": MATERIAL.young_modulus_mpa,
            "poisson_ratio": MATERIAL.poisson_ratio,
            "driving_pressure_mpa": DRIVING_PRESSURE_MPA.tolist(),
            "gap_factors": GAP_FACTORS.tolist(),
            "initial_gaps_mm": gaps.tolist(),
            "free_integration_displacements_mm": free_ip.tolist(),
        },
        "surface_integration": {
            "rule": "THREE_POINT_TRIANGLE_QUADRATIC_EXACT_FOR_TRI6_SHAPE_FUNCTIONS",
            "barycentric": barycentric.tolist(),
            "weights_mm2": weights.tolist(),
            "area_mm2": float(np.sum(weights)),
        },
        "independent_reference": {
            "method": "THREE_UNIT_PRESSURE_TET10_SOLVES_PLUS_EXHAUSTIVE_2_POWER_3_ACTIVE_SET_ENUMERATION",
            "masks_tested": masks_tested,
            "pressure_influence_mm_per_mpa": influence.tolist(),
            "symmetry_error_mm_per_mpa": symmetry_error,
            "active_contact_indices": list(reference_active),
            "integration_displacements_mm": reference_u.tolist(),
            "contact_pressure_mpa": reference_p.tolist(),
        },
        "production_result": {
            "iterations": result.iterations,
            "active_set_history": [list(item) for item in result.active_set_history],
            "active_contact_indices": list(result.active_contact_indices),
            "states": [state.value for state in result.states],
            "integration_displacements_mm": result.integration_displacements_mm.tolist(),
            "signed_gaps_mm": result.signed_gaps_mm.tolist(),
            "contact_pressure_mpa": result.contact_pressure_mpa.tolist(),
            "contact_point_forces_n": result.contact_point_forces_n.tolist(),
            "pressure_resultant_n": resultant_from_points,
            "generalized_contact_normal_resultant_n": resultant_from_generalized,
            "resultant_error_n": resultant_error,
            "complementarity_mpa_mm": result.complementarity_mpa_mm.tolist(),
            "free_equilibrium_residual_norm_n": result.free_equilibrium_residual_norm_n,
            "max_ip_von_mises_mpa": float(np.max(result.integration_point_von_mises_mpa)),
        },
        "comparison": {
            "max_pressure_error_mpa": pressure_error,
            "max_integration_displacement_error_mm": displacement_error,
        },
        "solver_boundary": {
            "equilibrium": "K_U_EQUALS_F_MINUS_H_TRANSPOSE_W_P",
            "gap": "G_EQUALS_G0_MINUS_H_U_GE_ZERO",
            "pressure": "P_GE_ZERO_PRIMARY_SURFACE_UNKNOWN",
            "complementarity": "G_TIMES_P_EQUALS_ZERO_AT_INTEGRATION_POINTS",
            "penalty_method_used": False,
            "artificial_penetration_permitted": False,
            "nodal_reaction_to_pressure_projection_used": False,
            "single_face_only": True,
            "surface_to_surface_search": False,
            "friction": False,
            "preload": False,
            "industrial_validation": False,
            "ot1613_industrial_pressure": False,
            "ansys_equivalence": False,
            "next_gate": "MULTI_FACE_TRI6_SURFACE_TO_SURFACE_CONTACT_WITH_GEOMETRIC_SEARCH",
        },
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    OUTPUT_HTML.write_text(viewer_html(payload, nodes), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"wrote {OUTPUT_JSON.resolve()}")
    print(f"wrote {OUTPUT_HTML.resolve()}")

    if not passed:
        failed = [key for key, value in checks.items() if not value]
        raise SystemExit(f"GAP-G primary surface pressure verification failed: {failed}")


if __name__ == "__main__":
    main()
