import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from astermax.global_static import solve_linear_static
from astermax.gmsh_pipeline import SurfaceBox, build_step_meshing_geo, mesh_step_with_gmsh
from astermax.mesh_bc import fixed_surface_constraints, resultant_from_nodal_loads, surface_total_force_loads
from astermax.postprocess import element_von_mises, write_legacy_vtk
from astermax.step_units import require_step_mm


GMSH = shutil.which("gmsh")


def _tet_volume(a, b, c, d):
    ab = [b[i] - a[i] for i in range(3)]
    ac = [c[i] - a[i] for i in range(3)]
    ad = [d[i] - a[i] for i in range(3)]
    cross = [
        ac[1] * ad[2] - ac[2] * ad[1],
        ac[2] * ad[0] - ac[0] * ad[2],
        ac[0] * ad[1] - ac[1] * ad[0],
    ]
    return abs(sum(ab[i] * cross[i] for i in range(3))) / 6.0


class GmshPipelineUnitTests(unittest.TestCase):
    def test_geo_builder_keeps_explicit_named_selection_and_msh2_ascii(self):
        geo = build_step_meshing_geo(
            "model.step",
            surface_boxes=[SurfaceBox("FIXED", (-1e-6, -1e-6, -1e-6), (1e-6, 2.000001, 1.000001))],
            mesh_size_mm=2.0,
        )
        self.assertIn('Physical Surface("FIXED")', geo)
        self.assertIn("Mesh.MshFileVersion = 2.2", geo)
        self.assertIn("Mesh.Binary = 0", geo)
        self.assertIn('Error("surface selector FIXED matched no faces")', geo)


@unittest.skipUnless(GMSH, "real CAD/mesh integration requires the Gmsh CLI")
class GmshStepRoundTripIntegrationTests(unittest.TestCase):
    def test_real_step_mesh_solve_and_vtk_pipeline(self):
        """Exercise CAD -> STEP -> mesh -> BC/load -> solve -> VM -> VTK with real Gmsh.

        No stress magnitude is asserted against an invented reference. Verification is
        instead based on independent geometric volume, applied/resultant force,
        equilibrium, free-DOF residual and artifact semantics.
        """
        with tempfile.TemporaryDirectory(prefix="astermax-step-e2e-") as temporary:
            root = Path(temporary)
            source_geo = root / "source.geo"
            step_path = root / "benchmark.step"
            msh_path = root / "benchmark.msh"
            vtk_path = root / "benchmark.vtk"

            source_geo.write_text(
                '\n'.join([
                    'SetFactory("OpenCASCADE");',
                    'Box(1) = {0, 0, 0, 10, 2, 1};',
                ]) + '\n',
                encoding="utf-8",
            )
            exported = subprocess.run(
                [GMSH, str(source_geo), "-0", "-format", "step", "-o", str(step_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(exported.returncode, 0, msg=exported.stderr or exported.stdout)
            self.assertTrue(step_path.is_file())

            step_unit = require_step_mm(step_path.read_text(encoding="utf-8"))
            self.assertEqual(step_unit.name, "mm")
            self.assertEqual(step_unit.scale_to_mm, 1.0)

            eps = 1e-5
            mesh = mesh_step_with_gmsh(
                step_path,
                msh_path,
                surface_boxes=[
                    SurfaceBox("FIXED", (-eps, -eps, -eps), (eps, 2 + eps, 1 + eps)),
                    SurfaceBox("LOAD", (10 - eps, -eps, -eps), (10 + eps, 2 + eps, 1 + eps)),
                ],
                mesh_size_mm=2.0,
                gmsh_executable=GMSH,
            )
            self.assertGreater(len(mesh.nodes), 4)
            self.assertGreater(len(mesh.elements), 1)
            self.assertGreater(len(mesh.surface_group("FIXED").triangles), 0)
            self.assertGreater(len(mesh.surface_group("LOAD").triangles), 0)

            volume = sum(
                _tet_volume(*(mesh.nodes[index] for index in tet))
                for tet in mesh.elements
            )
            self.assertAlmostEqual(volume, 20.0, places=7)

            constraints = fixed_surface_constraints(mesh, "FIXED")
            loads = surface_total_force_loads(mesh, "LOAD", (100.0, 0.0, 0.0))
            applied = resultant_from_nodal_loads(loads)
            self.assertAlmostEqual(applied[0], 100.0, places=12)
            self.assertAlmostEqual(applied[1], 0.0, places=12)
            self.assertAlmostEqual(applied[2], 0.0, places=12)

            result = solve_linear_static(
                mesh.nodes,
                mesh.elements,
                young=210000.0,
                poisson=0.30,
                constraints=constraints,
                loads=loads,
            )
            reaction = [0.0, 0.0, 0.0]
            for dof, value in enumerate(result.reactions):
                reaction[dof % 3] += value
            self.assertAlmostEqual(reaction[0], -100.0, places=7)
            self.assertAlmostEqual(reaction[1], 0.0, places=7)
            self.assertAlmostEqual(reaction[2], 0.0, places=7)

            free_residual = [
                abs(value)
                for dof, value in enumerate(result.residual)
                if dof not in constraints
            ]
            self.assertLess(max(free_residual, default=0.0), 1e-7)
            self.assertTrue(all(math.isfinite(value) for value in result.displacements))
            self.assertGreater(max(element_von_mises(result)), 0.0)

            write_legacy_vtk(vtk_path, mesh.nodes, mesh.elements, result)
            vtk = vtk_path.read_text(encoding="utf-8")
            self.assertIn("DATASET UNSTRUCTURED_GRID", vtk)
            self.assertIn("VECTORS displacement_mm", vtk)
            self.assertIn("SCALARS von_mises_MPa", vtk)
            self.assertIn("TENSORS stress_MPa", vtk)


if __name__ == "__main__":
    unittest.main()
