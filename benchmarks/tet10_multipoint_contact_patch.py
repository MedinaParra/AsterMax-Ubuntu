from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np

from astermax.contact import solve_tet10_multipoint_unilateral_contact
from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet10 import straight_sided_tet10_from_vertices
from astermax.fea.tet4 import IsotropicMaterial


OUTPUT = Path("tet10_multipoint_contact_patch.json")
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
FORCE_TOLERANCE_N = 1.0e-7
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
    elements = np.arange(10, dtype=int).reshape(1, 10)
    if not np.allclose(nodes[CONTACT_NODES, 2], 10.0):
        raise SystemExit("TRI6 contact nodes are not coplanar on z=10")
    return nodes, elements


def full_load_vector(node_count: int, contact_loads_n: np.ndarray) -> np.ndarray:
    loads = np.zeros(node_count * 3, dtype=float)
    loads[CONTACT_DOFS] = contact_loads_n
    return loads


def contact_compliance(nodes: np.ndarray, elements: np.ndarray) -> np.ndarray:
    compliance = np.zeros((CONTACT_DOFS.size, CONTACT_DOFS.size), dtype=float)
    for column, dof in enumerate(CONTACT_DOFS):
        loads = np.zeros(nodes.shape[0] * 3, dtype=float)
        loads[int(dof)] = 1.0
        result = solve_linear_static_tet10(
            nodes,
            elements,
            MATERIAL,
            loads,
            FIXED_DOFS,
        )
        compliance[:, column] = result.displacement_mm.reshape(-1)[CONTACT_DOFS]
    return compliance


def enumerate_condensed_lcp(
    compliance: np.ndarray,
    loads_n: np.ndarray,
    gaps_mm: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, tuple[int, ...], int]:
    """Solve the six-constraint Signorini problem independently by 2^6 enumeration."""
    free_u = compliance @ loads_n
    n = gaps_mm.size
    valid: list[tuple[np.ndarray, np.ndarray, tuple[int, ...]]] = []
    masks_tested = 0

    for mask_bits in itertools.product((False, True), repeat=n):
        masks_tested += 1
        active = np.flatnonzero(np.asarray(mask_bits, dtype=bool))
        reaction = np.zeros(n, dtype=float)
        if active.size:
            try:
                reaction[active] = np.linalg.solve(
                    compliance[np.ix_(active, active)],
                    free_u[active] - gaps_mm[active],
                )
            except np.linalg.LinAlgError:
                continue

        displacement = free_u - compliance @ reaction
        inactive = np.setdiff1d(np.arange(n, dtype=int), active)
        if active.size and np.any(reaction[active] < -FORCE_TOLERANCE_N):
            continue
        if active.size and np.any(
            np.abs(displacement[active] - gaps_mm[active]) > GAP_TOLERANCE_MM
        ):
            continue
        if inactive.size and np.any(
            displacement[inactive] > gaps_mm[inactive] + GAP_TOLERANCE_MM
        ):
            continue

        reaction[np.abs(reaction) <= FORCE_TOLERANCE_N] = 0.0
        canonical = tuple(int(i) for i in np.flatnonzero(reaction > FORCE_TOLERANCE_N))
        valid.append((displacement, reaction, canonical))

    if not valid:
        raise SystemExit("condensed LCP enumeration found no admissible solution")
    canonical_sets = {entry[2] for entry in valid}
    if len(canonical_sets) != 1:
        raise SystemExit(f"condensed LCP reference is not physically unique: {canonical_sets}")
    canonical = next(iter(canonical_sets))
    displacement, reaction, _ = next(entry for entry in valid if entry[2] == canonical)
    return displacement, reaction, canonical, masks_tested


def main() -> None:
    nodes, elements = build_fixture()
    compliance = contact_compliance(nodes, elements)
    compliance_symmetry_error = float(np.max(np.abs(compliance - compliance.T)))
    if not np.all(np.isfinite(compliance)) or compliance_symmetry_error > 1.0e-10:
        raise SystemExit("condensed contact compliance is non-finite or non-symmetric")

    free_u = compliance @ CONTACT_LOADS_N
    if np.any(free_u <= 0.0):
        raise SystemExit("verification load design did not close every candidate gap direction")
    gaps = free_u * GAP_FACTORS

    reference_u, reference_r, reference_active, masks_tested = enumerate_condensed_lcp(
        compliance,
        CONTACT_LOADS_N,
        gaps,
    )

    result = solve_tet10_multipoint_unilateral_contact(
        nodes_mm=nodes,
        elements=elements,
        material=MATERIAL,
        loads_n=full_load_vector(nodes.shape[0], CONTACT_LOADS_N),
        fixed_dofs=FIXED_DOFS,
        contact_dofs=CONTACT_DOFS,
        initial_gaps_mm=gaps,
        force_tolerance_n=FORCE_TOLERANCE_N,
        gap_tolerance_mm=GAP_TOLERANCE_MM,
    )
    actual_u = result.displacement_mm.reshape(-1)[CONTACT_DOFS]

    displacement_error_mm = float(np.max(np.abs(actual_u - reference_u)))
    reaction_error_n = float(np.max(np.abs(result.contact_reactions_n - reference_r)))
    active_count = len(result.active_contact_indices)
    open_count = int(sum(state.value == "OPEN" for state in result.states))

    checks = {
        "compliance_symmetric": compliance_symmetry_error <= 1.0e-10,
        "independent_reference_enumerated_all_64_sets": masks_tested == 64,
        "unique_reference_active_set": tuple(result.active_contact_indices) == reference_active,
        "multipoint_displacement_matches_reference": displacement_error_mm <= 1.0e-9,
        "multipoint_reaction_matches_reference": reaction_error_n <= 1.0e-6,
        "partial_contact_exercised": active_count >= 2 and open_count >= 1,
        "active_set_converged": result.converged,
        "no_penetration": result.exact_no_penetration and np.all(result.signed_gaps_mm >= -GAP_TOLERANCE_MM),
        "nonnegative_reactions": np.all(result.contact_reactions_n >= -FORCE_TOLERANCE_N),
        "signorini_complementarity": np.all(np.abs(result.complementarity_n_mm) <= 1.0e-8),
        "free_dof_equilibrium": result.free_equilibrium_residual_norm_n <= 1.0e-5,
        "real_tet10_ip_stress_recovered": bool(
            result.integration_point_stress_mpa.shape == (1, 4, 6)
            and result.integration_point_von_mises_mpa.shape == (1, 4)
            and np.isfinite(result.integration_point_stress_mpa).all()
        ),
        "pressure_not_claimed": result.contact_pressure_recovered is False,
        "friction_not_claimed": result.friction_solved is False,
        "industrial_result_not_claimed": result.industrial_validation_claimed is False and result.ot1613_result_claimed is False,
        "ansys_equivalence_not_claimed": result.ansys_equivalence_claimed is False,
    }
    passed = all(bool(value) for value in checks.values())

    payload = {
        "schema_version": "AsterMaxTet10MultipointContactPatchEvidenceV1",
        "classification": "SYNTHETIC_TET10_MULTIPOINT_SURFACE_PATCH_CONTACT_NOT_INDUSTRIAL_RESULT",
        "claim": "SIX_NODE_TRI6_CONTACT_CONSTRAINT_SET_ON_DEFORMABLE_TET10_WITH_INDEPENDENT_CONDENSED_LCP_REFERENCE",
        "passed": passed,
        "checks": {key: bool(value) for key, value in checks.items()},
        "fixture": {
            "element_family": "TET10",
            "contact_face": "COMPLETE_PLANAR_TRI6_FACE",
            "contact_plane_z_mm": 10.0,
            "contact_nodes": CONTACT_NODES.tolist(),
            "contact_dofs": CONTACT_DOFS.tolist(),
            "support_nodes": SUPPORT_NODES.tolist(),
            "young_modulus_mpa": MATERIAL.young_modulus_mpa,
            "poisson_ratio": MATERIAL.poisson_ratio,
            "external_contact_loads_n": CONTACT_LOADS_N.tolist(),
            "gap_design": "SYNTHETIC_GAPS_EQUAL_FREE_TET10_RESPONSE_TIMES_DECLARED_FACTORS",
            "gap_factors": GAP_FACTORS.tolist(),
            "initial_gaps_mm": gaps.tolist(),
            "free_contact_displacements_mm": free_u.tolist(),
        },
        "independent_reference": {
            "method": "CONTACT_COMPLIANCE_FROM_SIX_UNIT_TET10_SOLVES_PLUS_EXHAUSTIVE_2_POWER_6_ACTIVE_SET_ENUMERATION",
            "masks_tested": masks_tested,
            "compliance_symmetry_error_mm_per_n": compliance_symmetry_error,
            "contact_compliance_mm_per_n": compliance.tolist(),
            "active_contact_indices": list(reference_active),
            "contact_displacements_mm": reference_u.tolist(),
            "contact_reactions_n": reference_r.tolist(),
        },
        "production_active_set": {
            "iterations": result.iterations,
            "history": [list(item) for item in result.active_set_history],
            "active_contact_indices": list(result.active_contact_indices),
            "states": [state.value for state in result.states],
            "signed_gaps_mm": result.signed_gaps_mm.tolist(),
            "contact_reactions_n": result.contact_reactions_n.tolist(),
            "raw_constraint_reactions_n": result.raw_constraint_reactions_n.tolist(),
            "complementarity_n_mm": result.complementarity_n_mm.tolist(),
            "free_equilibrium_residual_norm_n": result.free_equilibrium_residual_norm_n,
            "max_ip_von_mises_mpa": float(np.max(result.integration_point_von_mises_mpa)),
        },
        "comparison": {
            "max_contact_displacement_error_mm": displacement_error_mm,
            "max_contact_reaction_error_n": reaction_error_n,
        },
        "solver_boundary": {
            "global_matrix": "SPARSE_CSR",
            "contact_method": "DETERMINISTIC_MULTIPOINT_EXACT_DISPLACEMENT_ACTIVE_SET",
            "penalty_method_used": False,
            "artificial_penetration_permitted": False,
            "surface_to_surface_contact": False,
            "nodal_normal_reaction_distribution": True,
            "contact_pressure_recovered": False,
            "friction": False,
            "preload": False,
            "industrial_validation": False,
            "ot1613_industrial_result": False,
            "ansys_equivalence": False,
            "next_gate": "TRI6_CONTACT_PRESSURE_RECOVERY_AND_PATCH_RESULT_VISUALIZATION_VERIFICATION",
        },
    }

    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"wrote {OUTPUT.resolve()}")

    if not passed:
        failed = [key for key, value in checks.items() if not value]
        raise SystemExit(f"multipoint contact patch verification failed: {failed}")


if __name__ == "__main__":
    main()
