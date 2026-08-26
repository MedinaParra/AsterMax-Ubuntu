from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from astermax.fea.benchmark import (
    ConvergencePolicy,
    evaluate_convergence,
    run_cantilever_convergence_tet10,
)
from astermax.fea.gmsh_bridge import (
    distribute_resultant_on_tri6,
    fixed_dofs_for_nodes,
    force_and_moment,
    mesh_step_tet10,
    unique_surface_nodes,
)
from astermax.fea.solver import solve_linear_static_tet10
from astermax.fea.tet4 import IsotropicMaterial


def _write_box_step(path: Path) -> None:
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("tet10_cantilever_box")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, 100.0, 20.0, 10.0)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def test_step_tet10_sparse_solve_preserves_resultant_moment_and_equilibrium() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        step = Path(tmp) / "cantilever.step"
        _write_box_step(step)
        mesh = mesh_step_tet10(step, 15.0)

        assert np.allclose(mesh.dimensions_mm, [100.0, 20.0, 10.0], atol=1e-5)
        assert mesh.elements.ndim == 2 and mesh.elements.shape[1] == 10
        assert mesh.elements.shape[0] > 0
        assert mesh.surface_triangles["X_MAX"].shape[1] == 6

        fixed_nodes = unique_surface_nodes(mesh.surface_triangles["X_MIN"])
        fixed_dofs = fixed_dofs_for_nodes(fixed_nodes)
        loads = distribute_resultant_on_tri6(
            mesh.nodes_mm,
            mesh.surface_triangles["X_MAX"],
            [0.0, -1000.0, 0.0],
        )
        applied_force, applied_moment = force_and_moment(mesh.nodes_mm, loads)
        assert np.allclose(applied_force, [0.0, -1000.0, 0.0], rtol=1e-12, atol=1e-8)
        assert np.allclose(applied_moment, [5000.0, 0.0, -100000.0], rtol=1e-10, atol=1e-6)

        result = solve_linear_static_tet10(
            mesh.nodes_mm,
            mesh.elements,
            IsotropicMaterial(200000.0, 0.30),
            loads,
            fixed_dofs,
        )
        reaction_force, reaction_moment = force_and_moment(mesh.nodes_mm, result.reactions_n)

        assert np.all(np.isfinite(result.displacement_mm))
        assert np.linalg.norm(result.displacement_mm) > 0.0
        assert result.integration_point_stress_mpa.shape == (mesh.elements.shape[0], 4, 6)
        assert result.integration_point_von_mises_mpa.shape == (mesh.elements.shape[0], 4)
        assert np.max(result.integration_point_von_mises_mpa) > 0.0
        assert np.allclose(reaction_force + applied_force, np.zeros(3), rtol=1e-8, atol=1e-5)
        assert np.allclose(reaction_moment + applied_moment, np.zeros(3), rtol=1e-8, atol=1e-3)


def test_tet10_uses_the_unchanged_cantilever_convergence_policy() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        step = Path(tmp) / "cantilever.step"
        _write_box_step(step)
        _, samples = run_cantilever_convergence_tet10(step, (20.0, 15.0, 10.0))

        assert len(samples) == 3
        assert all(sample.node_count > 0 and sample.tet_count > 0 for sample in samples)
        assert all(np.isfinite(sample.tip_error_percent) for sample in samples)
        decision = evaluate_convergence(samples, ConvergencePolicy())
        assert decision.policy["max_final_tip_error_percent"] == 10.0
        assert decision.policy["max_last_refinement_change_percent"] == 5.0
        assert decision.checks["global_force_balance"] is True
        assert decision.checks["global_moment_balance"] is True
