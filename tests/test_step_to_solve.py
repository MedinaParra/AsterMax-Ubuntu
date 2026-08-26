from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from astermax.fea.gmsh_bridge import (
    distribute_resultant_on_triangles,
    fixed_dofs_for_nodes,
    force_and_moment,
    mesh_step_tet4,
    unique_surface_nodes,
)
from astermax.fea.solver import solve_linear_static
from astermax.fea.tet4 import IsotropicMaterial


def _write_box_step(path: Path) -> None:
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("cantilever_box")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, 100.0, 20.0, 10.0)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def test_step_mesh_surface_load_solver_and_global_equilibrium() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        step = Path(tmp) / "cantilever.step"
        _write_box_step(step)
        mesh = mesh_step_tet4(step, 15.0)

        assert np.allclose(mesh.dimensions_mm, [100.0, 20.0, 10.0], atol=1e-5)
        assert mesh.elements.shape[1] == 4
        assert mesh.elements.shape[0] > 0

        fixed_nodes = unique_surface_nodes(mesh.surface_triangles["X_MIN"])
        fixed_dofs = fixed_dofs_for_nodes(fixed_nodes)
        loads = distribute_resultant_on_triangles(
            mesh.nodes_mm,
            mesh.surface_triangles["X_MAX"],
            [0.0, -1000.0, 0.0],
        )
        applied_force, applied_moment = force_and_moment(mesh.nodes_mm, loads)
        assert np.allclose(applied_force, [0.0, -1000.0, 0.0], rtol=1e-12, atol=1e-8)
        assert np.allclose(applied_moment, [5000.0, 0.0, -100000.0], rtol=1e-10, atol=1e-6)

        result = solve_linear_static(
            mesh.nodes_mm,
            mesh.elements,
            IsotropicMaterial(200000.0, 0.30),
            loads,
            fixed_dofs,
        )
        reaction_force, reaction_moment = force_and_moment(mesh.nodes_mm, result.reactions_n)

        assert np.all(np.isfinite(result.displacement_mm))
        assert np.linalg.norm(result.displacement_mm) > 0.0
        assert np.max(result.element_von_mises_mpa) > 0.0
        assert np.allclose(reaction_force + applied_force, np.zeros(3), rtol=1e-8, atol=1e-5)
        assert np.allclose(reaction_moment + applied_moment, np.zeros(3), rtol=1e-8, atol=1e-3)
