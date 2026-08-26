from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from astermax.fea.benchmark import (
    analytical_timoshenko_cantilever_reference,
    run_cantilever_convergence,
    run_cantilever_convergence_tet10,
)
from astermax.fea.efficiency import (
    AccuracyBudgetSample,
    AccuracyEfficiencyPolicy,
    evaluate_accuracy_efficiency,
    match_comparable_dofs,
)


# Candidate grids are declared up front.  They are intentionally not adapted after
# observing numerical error; only DOF counts are used by the pairing algorithm.
TET4_MESH_SIZES_MM = (6.0, 5.0, 4.0, 3.0, 2.5)
TET10_MESH_SIZES_MM = (20.0, 15.0, 10.0, 8.0, 6.0)
POLICY = AccuracyEfficiencyPolicy(
    min_pairs=3,
    max_pair_dof_ratio=1.50,
    min_geometric_mean_error_improvement=2.0,
    require_tet10_lower_error_each_pair=True,
)


def _write_box_step(path: Path) -> None:
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("tet4_vs_tet10_accuracy_budget")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, 100.0, 20.0, 10.0)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def _convert(family: str, samples, reference_tip_mm: float) -> list[AccuracyBudgetSample]:
    converted: list[AccuracyBudgetSample] = []
    for sample in samples:
        error = abs((sample.tip_displacement_y_mm - reference_tip_mm) / reference_tip_mm) * 100.0
        converted.append(
            AccuracyBudgetSample(
                element_family=family,
                mesh_size_mm=float(sample.mesh_size_mm),
                node_count=int(sample.node_count),
                element_count=int(sample.tet_count),
                dofs=int(sample.node_count) * 3,
                tip_displacement_y_mm=float(sample.tip_displacement_y_mm),
                tip_error_percent=float(error),
            )
        )
    return converted


def main() -> int:
    step = Path("tet4_vs_tet10_efficiency.step")
    output = Path("tet4_vs_tet10_efficiency.json")
    _write_box_step(step)

    common_reference = analytical_timoshenko_cantilever_reference()
    _, raw_tet4 = run_cantilever_convergence(step, TET4_MESH_SIZES_MM)
    _, raw_tet10 = run_cantilever_convergence_tet10(step, TET10_MESH_SIZES_MM)

    tet4 = _convert("TET4", raw_tet4, common_reference.tip_displacement_y_mm)
    tet10 = _convert("TET10", raw_tet10, common_reference.tip_displacement_y_mm)
    pairs = match_comparable_dofs(
        tet4,
        tet10,
        max_dof_ratio=POLICY.max_pair_dof_ratio,
    )
    decision = evaluate_accuracy_efficiency(pairs, POLICY)

    payload = {
        "classification": "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT",
        "claim": "COMPARABLE_DOF_ACCURACY_MEASUREMENT_ONLY",
        "performance_benchmark_claim": False,
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
        "common_physical_reference": {
            "theory": "TIMOSHENKO_BEAM_BENDING_PLUS_SHEAR",
            "tip_displacement_y_mm": common_reference.tip_displacement_y_mm,
            "length_mm": common_reference.length_mm,
            "width_y_mm": common_reference.width_y_mm,
            "height_z_mm": common_reference.height_z_mm,
            "force_y_n": common_reference.force_y_n,
            "young_mpa": common_reference.young_mpa,
            "poisson_ratio": 0.30,
        },
        "candidate_mesh_sizes_declared_before_pairing": {
            "TET4_mm": list(TET4_MESH_SIZES_MM),
            "TET10_mm": list(TET10_MESH_SIZES_MM),
        },
        "pairing_method": {
            "name": "MAX_PAIR_COUNT_THEN_MIN_TOTAL_ABS_LOG_DOF_RATIO",
            "uses_numerical_error_for_pair_selection": False,
            "one_to_one": True,
            "monotonic_in_dof": True,
            "max_dof_ratio": POLICY.max_pair_dof_ratio,
        },
        "tet4_samples": [asdict(sample) for sample in tet4],
        "tet10_samples": [asdict(sample) for sample in tet10],
        "comparable_pairs": [asdict(pair) for pair in pairs],
        "decision": asdict(decision),
        "interpretation_boundary": (
            "This gate compares displacement accuracy at similar algebraic DOF counts on one verification fixture. "
            "It does not claim general runtime, memory, nonlinear, contact, industrial, or ANSYS-equivalent performance."
        ),
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
    return 0 if decision.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
