from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import numpy as np

from astermax.fea.benchmark import ConvergencePolicy, evaluate_convergence, run_cantilever_convergence


def _write_proof_step(path: Path) -> None:
    """Create the deterministic STEP cantilever fixture used by the verification harness."""
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_tet4_refinement_fixture")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, 100.0, 20.0, 10.0)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def _log_slope(mesh_sizes: list[float], errors: list[float]) -> float | None:
    """Return a diagnostic log-log error slope over the last three samples.

    This is not a formal convergence-order proof because Gmsh target size does not
    guarantee a uniform family of geometrically similar meshes. It is reported only
    as a trend diagnostic and never drives the convergence claim.
    """
    if len(mesh_sizes) < 3 or len(errors) < 3:
        return None
    h = np.asarray(mesh_sizes[-3:], dtype=float)
    e = np.asarray(errors[-3:], dtype=float)
    if np.any(h <= 0.0) or np.any(e <= 0.0) or not np.all(np.isfinite(h)) or not np.all(np.isfinite(e)):
        return None
    slope = np.polyfit(np.log(h), np.log(e), 1)[0]
    return float(slope)


if __name__ == "__main__":
    step_path = Path("astermax_tet4_refinement_fixture.step")
    _write_proof_step(step_path)

    mesh_sizes = (25.0, 20.0, 15.0, 12.0, 10.0, 8.0)
    policy = ConvergencePolicy(
        min_samples=3,
        max_final_tip_error_percent=10.0,
        max_last_refinement_change_percent=5.0,
        max_force_balance_norm_n=1.0e-5,
        max_moment_balance_norm_nmm=1.0e-3,
        require_nonincreasing_tip_error=True,
    )
    reference, samples = run_cantilever_convergence(step_path, mesh_sizes)
    decision = evaluate_convergence(samples, policy)

    slope = _log_slope(
        [sample.mesh_size_mm for sample in samples],
        [sample.tip_error_percent for sample in samples],
    )
    report = {
        "classification": "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT",
        "claim": "TET4_REFINEMENT_ENVELOPE_MEASUREMENT_ONLY",
        "element": "TET4_FIRST_ORDER",
        "units": {"length": "mm", "force": "N", "stress": "MPa"},
        "mesh_sizes_mm": list(mesh_sizes),
        "analytical_reference": asdict(reference),
        "samples": [asdict(sample) for sample in samples],
        "declared_policy": asdict(policy),
        "decision": asdict(decision),
        "diagnostics": {
            "last_three_log_error_vs_target_size_slope": slope,
            "slope_drives_acceptance": False,
        },
        "tet4_gate_status": (
            "MEETS_DECLARED_GATE" if decision.converged else "TET10_OR_FURTHER_REFINEMENT_REQUIRED"
        ),
        "industrial_validation_claim": False,
        "ansys_equivalence_claim": False,
    }
    out = Path("tet4_refinement_envelope.json")
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"wrote {out.resolve()}")
