from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from astermax.contact import (
    ContactState,
    solve_unilateral_spring_contact_sweep,
)


OUTPUT = Path("unilateral_contact_law.json")
K_N_PER_MM = 10_000.0
INITIAL_GAP_MM = 0.20
LOADS_N = (-1_000.0, 0.0, 1_000.0, 2_000.0, 3_000.0, 5_000.0)
EXPECTED_STATES = (
    ContactState.OPEN,
    ContactState.OPEN,
    ContactState.OPEN,
    ContactState.TOUCHING_ZERO_REACTION,
    ContactState.ACTIVE,
    ContactState.ACTIVE,
)
FORCE_TOLERANCE_N = 1.0e-9
GAP_TOLERANCE_MM = 1.0e-12


def main() -> None:
    results = solve_unilateral_spring_contact_sweep(
        stiffness_n_per_mm=K_N_PER_MM,
        initial_gap_mm=INITIAL_GAP_MM,
        applied_loads_n=LOADS_N,
        force_tolerance_n=FORCE_TOLERANCE_N,
        gap_tolerance_mm=GAP_TOLERANCE_MM,
    )

    checks = {
        "expected_state_sequence": tuple(result.state for result in results) == EXPECTED_STATES,
        "nonnegative_gap": all(result.signed_gap_mm >= -GAP_TOLERANCE_MM for result in results),
        "nonnegative_contact_reaction": all(result.contact_reaction_n >= -FORCE_TOLERANCE_N for result in results),
        "exact_no_penetration": all(result.exact_no_penetration for result in results),
        "force_equilibrium": all(abs(result.force_residual_n) <= FORCE_TOLERANCE_N for result in results),
        "signorini_complementarity": all(abs(result.complementarity_n_mm) <= 1.0e-9 for result in results),
        "activation_load_exact": all(result.activation_load_n == 2_000.0 for result in results),
        "no_friction_claim": all(result.friction_solved is False for result in results),
        "no_contact_fea_claim": all(result.contact_fea_executed is False for result in results),
        "no_industrial_validation_claim": all(result.industrial_validation_claimed is False for result in results),
    }
    passed = all(checks.values())

    payload = {
        "schema_version": "AsterMaxUnilateralContactLawEvidenceV1",
        "classification": "SYNTHETIC_CONTACT_LAW_VERIFICATION_NOT_FEA",
        "claim": "ANALYTICAL_SIGNORINI_1DOF_ACTIVE_SET_VERIFICATION",
        "problem": {
            "stiffness_n_per_mm": K_N_PER_MM,
            "initial_gap_mm": INITIAL_GAP_MM,
            "activation_load_n": K_N_PER_MM * INITIAL_GAP_MM,
            "load_sweep_n": list(LOADS_N),
            "sign_convention": {
                "positive_displacement": "CLOSES_GAP",
                "gap_equation": "g = g0 - u >= 0",
                "contact_reaction": "R >= 0 OPPOSES_CLOSURE",
                "equilibrium": "k*u + R = F",
                "complementarity": "g*R = 0",
            },
        },
        "solver": {
            "method": "EXACT_SCALAR_ACTIVE_SET",
            "penalty_method_used": False,
            "artificial_penetration_permitted": False,
            "force_tolerance_n": FORCE_TOLERANCE_N,
            "gap_tolerance_mm": GAP_TOLERANCE_MM,
        },
        "checks": checks,
        "passed": passed,
        "records": [
            {
                **asdict(result),
                "state": result.state.value,
            }
            for result in results
        ],
        "engineering_boundary": {
            "finite_element_contact": False,
            "deformable_tet10_contact": False,
            "friction": False,
            "preload": False,
            "ot1613_contact_pressure": False,
            "industrial_validation": False,
            "ansys_equivalence": False,
            "next_gate": "COUPLE_SYNTHETIC_UNILATERAL_CONTACT_TO_DEFORMABLE_TET10_VERIFICATION_FIXTURE",
        },
    }

    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"wrote {OUTPUT.resolve()}")

    if not passed:
        failed = [name for name, value in checks.items() if not value]
        raise SystemExit(f"unilateral contact law verification failed: {failed}")


if __name__ == "__main__":
    main()
