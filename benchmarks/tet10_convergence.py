from __future__ import annotations

import json
from pathlib import Path

from astermax.fea.benchmark import (
    ConvergencePolicy,
    analytical_cantilever_reference,
    benchmark_manifest,
    evaluate_convergence,
    run_cantilever_convergence_tet10,
)


def _write_box_step(path: Path) -> None:
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("tet10_convergence_benchmark")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, 100.0, 20.0, 10.0)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def main() -> int:
    step = Path("tet10_cantilever.step")
    output = Path("tet10_convergence.json")
    _write_box_step(step)

    policy = ConvergencePolicy()
    reference, samples = run_cantilever_convergence_tet10(
        step,
        (20.0, 15.0, 10.0, 8.0, 6.0),
    )
    decision = evaluate_convergence(samples, policy)
    payload = benchmark_manifest(reference, samples, policy=policy)
    eb_reference = analytical_cantilever_reference()
    payload["analytical_reference_model"] = {
        "theory": "TIMOSHENKO_BEAM_BENDING_PLUS_SHEAR",
        "geometry_and_load_unchanged_from_tet4": True,
        "poisson_ratio": 0.30,
        "shear_correction_factor": 5.0 / 6.0,
        "euler_bernoulli_bending_tip_mm": eb_reference.tip_displacement_y_mm,
        "timoshenko_shear_tip_mm": reference.tip_displacement_y_mm - eb_reference.tip_displacement_y_mm,
        "total_tip_mm": reference.tip_displacement_y_mm,
        "acceptance_thresholds_relaxed": False,
    }
    payload["element_family"] = "TET10"
    payload["gmsh_volume_element_type"] = 11
    payload["gmsh_surface_element_type"] = 9
    payload["integration_scope"] = "STRAIGHT_SIDED_TET10_FOUR_POINT_VERIFICATION"
    payload["industrial_validation"] = False
    payload["ansys_equivalence"] = False
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(json.dumps(payload, indent=2))
    return 0 if decision.converged else 2


if __name__ == "__main__":
    raise SystemExit(main())
