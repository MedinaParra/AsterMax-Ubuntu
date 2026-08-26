from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from astermax.fea.benchmark import (
    analytical_cantilever_reference,
    benchmark_manifest,
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

        manifest = benchmark_manifest(ref, samples)
        assert manifest["result_class"] == "VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT"
        assert manifest["converged_claim"] is False
        assert manifest["units"] == {"length": "mm", "force": "N", "stress": "MPa"}
