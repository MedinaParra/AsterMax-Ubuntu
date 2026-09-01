import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from astermax.global_static import solve_linear_static
from astermax.gmsh_pipeline import mesh_step_with_gmsh
from astermax.mesh_bc import fixed_surface_constraints, resultant_from_nodal_loads, surface_total_force_loads
from astermax.semantic_surface import (
    SemanticSurfaceError,
    SemanticSurfaceIntent,
    apply_semantic_surfaces,
)


GMSH = shutil.which("gmsh")


@unittest.skipUnless(GMSH, "semantic STEP harness requires Gmsh CLI")
class SemanticSurfaceHarness(unittest.TestCase):
    @staticmethod
    def export_bar_step(root: Path, *, length: float) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        geo = root / "source.geo"
        step = root / "bar.step"
        geo.write_text(
            'SetFactory("OpenCASCADE");\n'
            f'Box(1) = {{0, 0, 0, {length}, 2, 1}};\n',
            encoding="utf-8",
        )
        completed = subprocess.run(
            [GMSH, str(geo), "-0", "-format", "step", "-o", str(step)],
            capture_output=True, text=True, check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stderr or completed.stdout)
        return step

    @staticmethod
    def solve_semantic(step: Path, msh: Path, mesh_size: float):
        mesh = mesh_step_with_gmsh(
            step, msh,
            surface_boxes=(),
            include_all_boundary=True,
            mesh_size_mm=mesh_size,
            gmsh_executable=GMSH,
        )
        intents = (
            SemanticSurfaceIntent("FIXED", "x", "min", band_fraction=0.02),
            SemanticSurfaceIntent("LOAD", "x", "max", band_fraction=0.02),
        )
        prepared, resolutions = apply_semantic_surfaces(mesh, intents)
        constraints = fixed_surface_constraints(prepared, "FIXED")
        loads = surface_total_force_loads(prepared, "LOAD", (100.0, 0.0, 0.0))
        result = solve_linear_static(
            prepared.nodes, prepared.elements,
            young=210000.0, poisson=0.30,
            constraints=constraints, loads=loads,
        )
        return prepared, resolutions, constraints, loads, result

    def test_semantic_faces_survive_remesh_and_parametric_length_change(self):
        with tempfile.TemporaryDirectory(prefix="astermax-semantic-step-") as temporary:
            root = Path(temporary)
            step_a = self.export_bar_step(root / "a", length=10.0)
            step_b = self.export_bar_step(root / "b", length=11.0)
            case_a = self.solve_semantic(step_a, root / "a.msh", 2.0)
            case_b = self.solve_semantic(step_b, root / "b.msh", 1.5)

            for expected_length, case in ((10.0, case_a), (11.0, case_b)):
                mesh, resolutions, constraints, loads, result = case
                self.assertEqual([r.intent.name for r in resolutions], ["FIXED", "LOAD"])
                self.assertGreater(resolutions[0].selected_triangle_count, 0)
                self.assertGreater(resolutions[1].selected_triangle_count, 0)
                self.assertAlmostEqual(resolutions[0].selected_area, 2.0, places=6)
                self.assertAlmostEqual(resolutions[1].selected_area, 2.0, places=6)

                fixed_nodes = mesh.surface_group("FIXED").node_indices
                load_nodes = mesh.surface_group("LOAD").node_indices
                self.assertTrue(all(abs(mesh.nodes[i][0]) < 1e-9 for i in fixed_nodes))
                self.assertTrue(all(abs(mesh.nodes[i][0] - expected_length) < 1e-9 for i in load_nodes))

                applied = resultant_from_nodal_loads(loads)
                self.assertAlmostEqual(applied[0], 100.0, places=10)
                reaction_x = sum(float(v) for dof, v in enumerate(result.reactions) if dof % 3 == 0)
                self.assertAlmostEqual(reaction_x, -100.0, places=7)
                free_residual = max(
                    abs(float(v)) for dof, v in enumerate(result.residual) if dof not in constraints
                )
                self.assertLess(free_residual, 1e-7)

            # The two cases deliberately have different topology/mesh density.
            self.assertNotEqual(len(case_a[0].nodes), len(case_b[0].nodes))
            self.assertNotEqual(len(case_a[0].elements), len(case_b[0].elements))

    def test_invalid_or_unresolvable_semantic_intent_fails_closed(self):
        with self.assertRaises(SemanticSurfaceError):
            SemanticSurfaceIntent("FIXED", "bad-axis", "min")

        with tempfile.TemporaryDirectory(prefix="astermax-semantic-fail-") as temporary:
            root = Path(temporary)
            step = self.export_bar_step(root, length=10.0)
            mesh = mesh_step_with_gmsh(
                step, root / "model.msh", surface_boxes=(), include_all_boundary=True,
                mesh_size_mm=2.0, gmsh_executable=GMSH,
            )
            # End faces are normal to X, so requiring a Z-aligned face at X-min is impossible.
            impossible = SemanticSurfaceIntent(
                "IMPOSSIBLE", "x", "min", band_fraction=0.02,
                minimum_normal_alignment=0.999,
            )
            # This is actually resolvable because axis controls both position and normal.
            prepared, resolutions = apply_semantic_surfaces(mesh, (impossible,))
            self.assertGreater(resolutions[0].selected_triangle_count, 0)

            with self.assertRaises(SemanticSurfaceError):
                apply_semantic_surfaces(
                    prepared,
                    (SemanticSurfaceIntent("IMPOSSIBLE", "x", "min"),),
                )


if __name__ == "__main__":
    unittest.main()
