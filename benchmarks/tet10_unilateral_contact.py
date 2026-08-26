from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from astermax.contact import ContactState, solve_tet10_single_dof_unilateral_contact
from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet4 import IsotropicMaterial


OUTPUT = Path("tet10_unilateral_contact.json")
MATERIAL = IsotropicMaterial(young_modulus_mpa=200_000.0, poisson_ratio=0.30)
INITIAL_GAP_MM = 0.01
CONTACT_NODE = 3
CONTACT_COMPONENT = 2
CONTACT_DOF = 3 * CONTACT_NODE + CONTACT_COMPONENT
BASE_NODES = np.asarray([0, 1, 2, 4, 5, 6], dtype=int)
FIXED_DOFS = np.asarray(
    [3 * node + component for node in BASE_NODES for component in range(3)],
    dtype=int,
)
FORCE_TOLERANCE_N = 1.0e-6
GAP_TOLERANCE_MM = 1.0e-9


def build_fixture() -> tuple[np.ndarray, np.ndarray]:
    vertices = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [0.0, 10.0, 0.0],
            [0.0, 0.0, 10.0],
        ],
        dtype=float,
    )
    nodes = straight_sided_tet10_from_vertices(vertices)
    elements = np.arange(10, dtype=int).reshape(1, 10)
    return nodes, elements


def load_vector(node_count: int, force_n: float) -> np.ndarray:
    loads = np.zeros(node_count * 3, dtype=float)
    loads[CONTACT_DOF] = float(force_n)
    return loads


def main() -> None:
    nodes, elements = build_fixture()

    unit = solve_linear_static_tet10(
        nodes,
        elements,
        MATERIAL,
        load_vector(nodes.shape[0], 1.0),
        FIXED_DOFS,
    )
    compliance_mm_per_n = float(unit.displacement_mm.reshape(-1)[CONTACT_DOF])
    if not np.isfinite(compliance_mm_per_n) or compliance_mm_per_n <= 0.0:
        raise SystemExit("TET10 unit compliance is not finite and positive")

    effective_stiffness_n_per_mm = 1.0 / compliance_mm_per_n
    activation_load_n = effective_stiffness_n_per_mm * INITIAL_GAP_MM
    multipliers = (-0.5, 0.0, 0.5, 1.0, 1.5, 2.0)
    loads_n = tuple(multiplier * activation_load_n for multiplier in multipliers)
    expected_states = (
        ContactState.OPEN,
        ContactState.OPEN,
        ContactState.OPEN,
        ContactState.TOUCHING_ZERO_REACTION,
        ContactState.ACTIVE,
        ContactState.ACTIVE,
    )

    results = []
    for force_n in loads_n:
        results.append(
            solve_tet10_single_dof_unilateral_contact(
                nodes_mm=nodes,
                elements=elements,
                material=MATERIAL,
                loads_n=load_vector(nodes.shape[0], force_n),
                fixed_dofs=FIXED_DOFS,
                contact_dof=CONTACT_DOF,
                initial_gap_mm=INITIAL_GAP_MM,
                force_tolerance_n=FORCE_TOLERANCE_N,
                gap_tolerance_mm=GAP_TOLERANCE_MM,
            )
        )

    reaction_errors_n = []
    for force_n, result in zip(loads_n, results):
        expected_reaction = max(force_n - activation_load_n, 0.0)
        reaction_errors_n.append(abs(result.contact_reaction_n - expected_reaction))

    checks = {
        "expected_state_sequence": tuple(result.state for result in results) == expected_states,
        "nonnegative_gap": all(result.signed_gap_mm >= -GAP_TOLERANCE_MM for result in results),
        "nonnegative_contact_reaction": all(result.contact_reaction_n >= -FORCE_TOLERANCE_N for result in results),
        "exact_no_penetration": all(result.exact_no_penetration for result in results),
        "signorini_complementarity": all(abs(result.complementarity_n_mm) <= 1.0e-9 for result in results),
        "free_dof_equilibrium": all(result.free_equilibrium_residual_norm_n <= 1.0e-5 for result in results),
        "condensed_reaction_reference": max(reaction_errors_n) <= max(1.0e-6, activation_load_n * 1.0e-9),
        "real_tet10_ip_stress_recovered": all(
            result.integration_point_stress_mpa.shape == (1, 4, 6)
            and result.integration_point_von_mises_mpa.shape == (1, 4)
            and np.isfinite(result.integration_point_stress_mpa).all()
            for result in results
        ),
        "contact_pressure_not_claimed": all(result.contact_pressure_recovered is False for result in results),
        "friction_not_claimed": all(result.friction_solved is False for result in results),
        "industrial_validation_not_claimed": all(result.industrial_validation_claimed is False for result in results),
        "ot1613_result_not_claimed": all(result.ot1613_result_claimed is False for result in results),
        "ansys_equivalence_not_claimed": all(result.ansys_equivalence_claimed is False for result in results),
    }
    passed = all(checks.values())

    records = []
    for force_n, result in zip(loads_n, results):
        records.append(
            {
                "applied_load_n": force_n,
                "state": result.state.value,
                "free_trial_contact_displacement_mm": result.free_trial_contact_displacement_mm,
                "contact_displacement_mm": float(result.displacement_mm.reshape(-1)[CONTACT_DOF]),
                "signed_gap_mm": result.signed_gap_mm,
                "contact_reaction_n": result.contact_reaction_n,
                "raw_constraint_reaction_n": result.raw_constraint_reaction_n,
                "expected_condensed_contact_reaction_n": max(force_n - activation_load_n, 0.0),
                "penetration_mm": result.penetration_mm,
                "complementarity_n_mm": result.complementarity_n_mm,
                "free_equilibrium_residual_norm_n": result.free_equilibrium_residual_norm_n,
                "max_ip_von_mises_mpa": float(np.max(result.integration_point_von_mises_mpa)),
            }
        )

    payload = {
        "schema_version": "AsterMaxTet10UnilateralContactEvidenceV1",
        "classification": "SYNTHETIC_DEFORMABLE_TET10_CONTACT_VERIFICATION_NOT_INDUSTRIAL_RESULT",
        "claim": "SINGLE_DOF_EXACT_SIGNORINI_CONSTRAINT_COUPLED_TO_DEFORMABLE_TET10",
        "passed": passed,
        "checks": checks,
        "fixture": {
            "geometry": "ONE_STRAIGHT_SIDED_TET10_TETRAHEDRON",
            "vertices_mm": nodes[:4].tolist(),
            "node_count": int(nodes.shape[0]),
            "element_count": int(elements.shape[0]),
            "fixed_base_nodes": BASE_NODES.tolist(),
            "contact_node": CONTACT_NODE,
            "contact_component": "+Z",
            "initial_gap_mm": INITIAL_GAP_MM,
            "young_modulus_mpa": MATERIAL.young_modulus_mpa,
            "poisson_ratio": MATERIAL.poisson_ratio,
        },
        "condensed_reference": {
            "unit_load_n": 1.0,
            "unit_compliance_mm_per_n": compliance_mm_per_n,
            "effective_stiffness_n_per_mm": effective_stiffness_n_per_mm,
            "activation_load_n": activation_load_n,
            "reference_relation_active": "R = F - k_eff*g0",
        },
        "solver": {
            "element_family": "TET10",
            "global_matrix": "SPARSE_CSR",
            "contact_method": "EXACT_SINGLE_DOF_ACTIVE_SET_WITH_NONZERO_PRESCRIBED_DISPLACEMENT",
            "penalty_method_used": False,
            "artificial_penetration_permitted": False,
            "force_tolerance_n": FORCE_TOLERANCE_N,
            "gap_tolerance_mm": GAP_TOLERANCE_MM,
        },
        "records": records,
        "engineering_boundary": {
            "finite_element_contact_executed": True,
            "deformable_tet10_contact": True,
            "surface_to_surface_contact": False,
            "contact_pressure_recovered": False,
            "friction": False,
            "preload": False,
            "ot1613_industrial_result": False,
            "industrial_validation": False,
            "ansys_equivalence": False,
            "next_gate": "MULTIPOINT_TET10_SURFACE_CONTACT_PATCH_VERIFICATION",
        },
    }

    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"wrote {OUTPUT.resolve()}")

    if not passed:
        failed = [name for name, value in checks.items() if not value]
        raise SystemExit(f"deformable TET10 unilateral contact verification failed: {failed}")


if __name__ == "__main__":
    main()
