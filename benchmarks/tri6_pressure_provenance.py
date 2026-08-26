from __future__ import annotations

import html
import json
from pathlib import Path

import numpy as np

from astermax.contact import (
    Tri6PressureRecoveryStatus,
    recover_consistent_tri6_pressure,
    solve_tet10_multipoint_unilateral_contact,
)
from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet4 import IsotropicMaterial


OUTPUT_DIR = Path("tri6_pressure_provenance")
JSON_PATH = OUTPUT_DIR / "tri6_pressure_provenance.json"
HTML_PATH = OUTPUT_DIR / "tri6_pressure_provenance_viewer.html"
MATERIAL = IsotropicMaterial(young_modulus_mpa=200_000.0, poisson_ratio=0.30)
CONTACT_NODES = np.asarray([0, 1, 2, 4, 5, 6], dtype=int)
CONTACT_DOFS = 3 * CONTACT_NODES + 2
SUPPORT_NODES = np.asarray([3, 7, 8, 9], dtype=int)
FIXED_DOFS = np.asarray(
    [3 * node + component for node in SUPPORT_NODES for component in range(3)],
    dtype=int,
)
CONTACT_LOADS_N = np.asarray([420.0, 520.0, 610.0, 470.0, 560.0, 650.0], dtype=float)
GAP_FACTORS = np.asarray([0.55, 1.40, 0.75, 1.25, 0.65, 1.50], dtype=float)


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
    return straight_sided_tet10_from_vertices(vertices), np.arange(10, dtype=int).reshape(1, 10)


def full_load_vector(node_count: int, contact_loads_n: np.ndarray) -> np.ndarray:
    loads = np.zeros(node_count * 3, dtype=float)
    loads[CONTACT_DOFS] = contact_loads_n
    return loads


def build_gaps(nodes: np.ndarray, elements: np.ndarray) -> np.ndarray:
    compliance = np.zeros((CONTACT_DOFS.size, CONTACT_DOFS.size), dtype=float)
    for column, dof in enumerate(CONTACT_DOFS):
        loads = np.zeros(nodes.shape[0] * 3, dtype=float)
        loads[int(dof)] = 1.0
        result = solve_linear_static_tet10(nodes, elements, MATERIAL, loads, FIXED_DOFS)
        compliance[:, column] = result.displacement_mm.reshape(-1)[CONTACT_DOFS]
    free_u = compliance @ CONTACT_LOADS_N
    return free_u * GAP_FACTORS


def write_viewer(
    *,
    nodes: np.ndarray,
    reactions_n: np.ndarray,
    pressure_mpa: np.ndarray,
    status: str,
    minimum_pressure_mpa: float,
) -> None:
    xy = nodes[CONTACT_NODES, :2]
    x_min, y_min = np.min(xy, axis=0)
    x_max, y_max = np.max(xy, axis=0)

    def screen(point: np.ndarray) -> tuple[float, float]:
        x = 70.0 + 460.0 * (float(point[0]) - x_min) / max(x_max - x_min, 1.0)
        y = 530.0 - 430.0 * (float(point[1]) - y_min) / max(y_max - y_min, 1.0)
        return x, y

    screen_xy = [screen(point) for point in xy]
    # Quadratic edge ordering: corners 0,1,2 and midsides 3(0-1),4(1-2),5(2-0).
    polygon = " ".join(f"{screen_xy[i][0]:.3f},{screen_xy[i][1]:.3f}" for i in (0, 3, 1, 4, 2, 5))
    node_svg = []
    for index, ((x, y), reaction, pressure) in enumerate(zip(screen_xy, reactions_n, pressure_mpa)):
        node_svg.append(
            f'<circle cx="{x:.3f}" cy="{y:.3f}" r="10" class="node" />'
            f'<text x="{x + 14:.3f}" y="{y - 6:.3f}">N{index + 1}: R={reaction:.3f} N</text>'
            f'<text x="{x + 14:.3f}" y="{y + 13:.3f}">diagnostic p={pressure:.3f} MPa</text>'
        )

    body = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>AsterMax TRI6 pressure provenance</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 28px; max-width: 1050px; }}
.banner {{ border: 3px solid currentColor; padding: 16px; font-size: 24px; font-weight: 800; }}
.warning {{ font-weight: 700; }}
svg {{ width: 100%; max-width: 760px; border: 1px solid currentColor; margin-top: 16px; }}
.patch {{ fill: none; stroke: currentColor; stroke-width: 2; }}
.node {{ fill: white; stroke: currentColor; stroke-width: 2; }}
text {{ font-size: 12px; }}
code {{ white-space: pre-wrap; }}
</style>
</head>
<body>
<div class="banner">PRESSURE CLAIM BLOCKED — {html.escape(status)}</div>
<h1>AsterMax TRI6 contact provenance diagnostic</h1>
<p>The six values labelled <strong>R</strong> are valid nodal normal contact reactions from the synthetic GAP-E TET10 verification fixture.</p>
<p class="warning">The displayed p values are only the exact consistent quadratic projection diagnostic. They are not an accepted contact-pressure result because the reconstructed field becomes negative ({minimum_pressure_mpa:.6f} MPa minimum).</p>
<svg viewBox="0 0 760 600" role="img" aria-label="TRI6 reaction and pressure provenance diagnostic">
<polygon points="{polygon}" class="patch" />
{''.join(node_svg)}
</svg>
<h2>Interpretation</h2>
<p>A nodal active-set reaction vector is not automatically a distributed surface traction. AsterMax therefore refuses to relabel these nodal reactions as contact pressure. The next numerical gate must formulate normal contact traction at the surface/integration level.</p>
</body>
</html>
"""
    HTML_PATH.write_text(body, encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    nodes, elements = build_fixture()
    gaps = build_gaps(nodes, elements)
    contact = solve_tet10_multipoint_unilateral_contact(
        nodes_mm=nodes,
        elements=elements,
        material=MATERIAL,
        loads_n=full_load_vector(nodes.shape[0], CONTACT_LOADS_N),
        fixed_dofs=FIXED_DOFS,
        contact_dofs=CONTACT_DOFS,
        initial_gaps_mm=gaps,
        force_tolerance_n=1.0e-7,
        gap_tolerance_mm=1.0e-10,
    )

    corners = nodes[[0, 1, 2], :]
    blocked = recover_consistent_tri6_pressure(
        corner_vertices_mm=corners,
        nodal_reactions_n=contact.contact_reactions_n,
        reaction_tolerance_n=1.0e-8,
        pressure_tolerance_mpa=1.0e-10,
    )

    # Positive control: a constant known pressure must survive the exact same
    # recovery machinery. This prevents a gate that simply blocks everything.
    known_pressure_mpa = 10.0
    known_reactions = blocked.consistent_matrix_mm2 @ np.full(6, known_pressure_mpa)
    positive_control = recover_consistent_tri6_pressure(
        corner_vertices_mm=corners,
        nodal_reactions_n=known_reactions,
        reaction_tolerance_n=1.0e-8,
        pressure_tolerance_mpa=1.0e-10,
    )

    checks = {
        "upstream_gap_e_active_set_reproduced": contact.active_contact_indices == (0, 2, 3, 4),
        "upstream_nodal_reactions_nonnegative": bool(np.all(contact.contact_reactions_n >= -1.0e-8)),
        "consistent_projection_reproduces_generalized_forces": blocked.max_reaction_reproduction_error_n <= 1.0e-8,
        "resultant_force_conserved": blocked.resultant_error_n <= 1.0e-8,
        "negative_pressure_detected_analytically": blocked.minimum_pressure_mpa < -1.0e-6,
        "pressure_claim_blocked": blocked.status == Tri6PressureRecoveryStatus.BLOCKED_NEGATIVE_PRESSURE and not blocked.contact_pressure_claim_authorized,
        "nodal_reaction_claim_remains_valid": blocked.nodal_contact_reactions_remain_valid,
        "positive_control_authorized": positive_control.status == Tri6PressureRecoveryStatus.VALID_CONSISTENT_COMPRESSIVE_PRESSURE and positive_control.contact_pressure_claim_authorized,
        "positive_control_exact_10_mpa": bool(np.allclose(positive_control.projected_nodal_pressure_mpa, 10.0, atol=1.0e-10)),
        "industrial_pressure_not_claimed": not blocked.industrial_validation_claimed and not blocked.ot1613_pressure_claimed,
        "ansys_equivalence_not_claimed": not blocked.ansys_equivalence_claimed,
    }
    passed = all(checks.values())

    write_viewer(
        nodes=nodes,
        reactions_n=blocked.nodal_reactions_n,
        pressure_mpa=blocked.projected_nodal_pressure_mpa,
        status=blocked.status.value,
        minimum_pressure_mpa=blocked.minimum_pressure_mpa,
    )

    payload = {
        "schema_version": "AsterMaxTri6PressureProvenanceEvidenceV1",
        "classification": "PRESSURE_PROVENANCE_GATE_SYNTHETIC_TRI6",
        "passed": passed,
        "checks": checks,
        "upstream_gap_e": {
            "active_contact_indices": list(contact.active_contact_indices),
            "states": [state.value for state in contact.states],
            "nodal_normal_reactions_n": contact.contact_reactions_n.tolist(),
            "synthetic_initial_gaps_mm": gaps.tolist(),
            "contact_pressure_recovered_upstream": contact.contact_pressure_recovered,
        },
        "consistent_projection": {
            "status": blocked.status.value,
            "area_mm2": blocked.area_mm2,
            "projected_nodal_pressure_mpa": blocked.projected_nodal_pressure_mpa.tolist(),
            "minimum_pressure_mpa": blocked.minimum_pressure_mpa,
            "minimum_pressure_barycentric": blocked.minimum_pressure_barycentric.tolist(),
            "maximum_pressure_mpa": blocked.maximum_pressure_mpa,
            "maximum_pressure_barycentric": blocked.maximum_pressure_barycentric.tolist(),
            "max_reaction_reproduction_error_n": blocked.max_reaction_reproduction_error_n,
            "nodal_reaction_resultant_n": blocked.nodal_reaction_resultant_n,
            "projected_pressure_resultant_n": blocked.projected_pressure_resultant_n,
            "resultant_error_n": blocked.resultant_error_n,
            "contact_pressure_claim_authorized": blocked.contact_pressure_claim_authorized,
            "nodal_contact_reactions_remain_valid": blocked.nodal_contact_reactions_remain_valid,
        },
        "positive_control": {
            "known_uniform_pressure_mpa": known_pressure_mpa,
            "generalized_nodal_reactions_n": known_reactions.tolist(),
            "recovered_nodal_pressure_mpa": positive_control.projected_nodal_pressure_mpa.tolist(),
            "minimum_pressure_mpa": positive_control.minimum_pressure_mpa,
            "maximum_pressure_mpa": positive_control.maximum_pressure_mpa,
            "status": positive_control.status.value,
            "contact_pressure_claim_authorized": positive_control.contact_pressure_claim_authorized,
        },
        "engineering_decision": {
            "gap_e_nodal_contact_reactions_valid": True,
            "gap_e_contact_pressure_valid": False,
            "reason": "EXACT_CONSISTENT_TRI6_PROJECTION_REQUIRES_NEGATIVE_PRESSURE_REGION",
            "viewer_is_diagnostic_not_pressure_contour": True,
            "next_gate": "SURFACE_INTEGRATION_POINT_NORMAL_TRACTION_CONTACT_FORMULATION",
            "industrial_validation": False,
            "ot1613_pressure_result": False,
            "ansys_equivalence": False,
        },
    }

    JSON_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"wrote {JSON_PATH.resolve()}")
    print(f"wrote {HTML_PATH.resolve()}")

    if not passed:
        failed = [name for name, value in checks.items() if not value]
        raise SystemExit(f"TRI6 pressure provenance gate failed: {failed}")


if __name__ == "__main__":
    main()
