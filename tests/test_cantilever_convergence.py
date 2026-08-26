from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from astermax.fea.benchmark import (
    ConvergencePolicy,
    ConvergenceSample,
    analytical_cantilever_reference,
    benchmark_manifest,
    evaluate_convergence,
    run_cantilever_convergence,
)


def _write_box_step(path: Path) -> None:
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("cantilever_convergence")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, 100.0, 20.0, 10.0)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def test_analytical_reference_is_independent_and_dimensionally_explicit() -> None:
    ref = analytical_cantilever_reference()
    assert np.isclose(ref.tip_displacement_y_mm, -0.25)
    assert np.isclose(ref.root_bending_stress_mpa, 150.0)
    assert np.isclose(ref.reaction_force_n, 1000.0)
    assert np.isclose(ref.reaction_moment_nmm, 100000.0)


def test_step_cantilever_mesh_refinement_emits_raw_error_and_equilibrium_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        step = Path(tmp) / "cantilever.step"
        _write_box_step(step)
        ref, samples = run_cantilever_convergence(step, (25.0, 20.0, 15.0))

        assert len(samples) == 3
        assert [s.mesh_size_mm for s in samples] == [25.0, 20.0, 15.0]
        assert all(s.node_count > 0 and s.tet_count > 0 for s in samples)
        assert all(np.isfinite(s.tip_displacement_y_mm) for s in samples)
        assert all(np.isfinite(s.tip_error_percent) for s in samples)
        assert all(s.force_balance_norm_n < 1e-5 for s in samples)
        assert all(s.moment_balance_norm_nmm < 1e-3 for s in samples)

        policy = ConvergencePolicy()
        decision = evaluate_convergence(samples, policy)
        assert decision.checks["minimum_sample_count"] is True
        assert decision.checks["finite_metrics"] is True
        assert decision.checks["strict_mesh_refinement"] is True
        assert decision.checks["global_force_balance"] is True
        assert decision.checks["global_moment_balance"] is True
        assert decision.converged == all(decision.checks.values())

        manifest = benchmark_manifest(ref, samples, policy=policy)
        assert manifest["result_class"] == "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT"
        assert manifest["converged_claim"] == decision.converged
        assert manifest["convergence_decision"]["policy"]["max_final_tip_error_percent"] == 10.0
        assert manifest["units"] == {"length": "mm", "force": "N", "stress": "MPa"}


def test_convergence_gate_passes_only_when_every_declared_check_passes() -> None:
    samples = [
        ConvergenceSample(30.0, 10, 20, -0.2200, 12.0, 1e-9, 1e-7),
        ConvergenceSample(20.0, 20, 50, -0.2380, 4.8, 1e-9, 1e-7),
        ConvergenceSample(10.0, 40, 100, -0.2470, 1.2, 1e-9, 1e-7),
    ]
    policy = ConvergencePolicy(max_last_refinement_change_percent=5.0)
    decision = evaluate_convergence(samples, policy)
    assert decision.converged is True

    failed = list(samples)
    failed[-1] = ConvergenceSample(10.0, 40, 100, -0.2200, 12.0, 1e-9, 1e-7)
    decision = evaluate_convergence(failed, policy)
    assert decision.converged is False
    assert decision.checks["final_tip_error"] is False
    assert decision.checks["nonincreasing_tip_error"] is False
