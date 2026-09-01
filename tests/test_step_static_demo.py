import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from astermax.benchmark import axial_bar_reference, relative_error
from astermax.gmsh_pipeline import SurfaceBox
from astermax.semantic_surface import SemanticSurfaceIntent
from astermax.step_static_demo import StepStaticDemoError, run_step_static_demo


GMSH = shutil.which("gmsh")


@unittest.skipUnless(GMSH, "real STEP demo harness requires Gmsh CLI")
class StepStaticDemoHarness(unittest.TestCase):
    @staticmethod
    def export_bar_step(root: Path, length=10.0, width=2.0, thickness=1.0) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        geo = root / "source.geo"
        step = root / "bar.step"
        geo.write_text(
            'SetFactory("OpenCASCADE");\n'
            f'Box(1) = {{0, 0, 0, {length}, {width}, {thickness}}};\n',
            encoding="utf-8",
        )
        completed = subprocess.run(
            [GMSH, str(geo), "-0", "-format", "step", "-o", str(step)],
            capture_output=True, text=True, check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stderr or completed.stdout)
        return step

    def run_case(self, step: Path, output: Path):
        eps = 1e-5
        return run_step_static_demo(
            step, output,
            fixed_box=SurfaceBox("FIXED", (-eps, -eps, -eps), (eps, 2.0 + eps, 1.0 + eps)),
            load_box=SurfaceBox("LOAD", (10.0 - eps, -eps, -eps), (10.0 + eps, 2.0 + eps, 1.0 + eps)),
            total_force_n=(100.0, 0.0, 0.0), mesh_size_mm=2.0,
            young_mpa=210000.0, poisson=0.30, gmsh_executable=GMSH,
        )

    def test_real_step_to_mesh_solve_viewer_and_fingerprint(self):
        with tempfile.TemporaryDirectory(prefix="astermax-real-step-demo-") as temporary:
            root = Path(temporary)
            step = self.export_bar_step(root)
            first = self.run_case(step, root / "first")
            second = self.run_case(step, root / "second")
            summary, manifest = first["summary"], first["manifest"]

            self.assertEqual(summary["step_unit"], "mm")
            self.assertEqual(summary["surface_selection_mode"], "explicit_bounding_boxes")
            self.assertGreater(summary["node_count"], 4)
            self.assertGreater(summary["tet4_count"], 1)
            self.assertGreater(summary["fixed_surface_triangle_count"], 0)
            self.assertGreater(summary["load_surface_triangle_count"], 0)
            self.assertEqual(summary["requested_force_N"], [100.0, 0.0, 0.0])
            self.assertAlmostEqual(summary["recovered_applied_force_N"][0], 100.0, places=10)
            self.assertAlmostEqual(summary["reaction_resultant_N"][0], -100.0, places=7)
            self.assertAlmostEqual(summary["reaction_resultant_N"][1], 0.0, places=7)
            self.assertAlmostEqual(summary["reaction_resultant_N"][2], 0.0, places=7)
            self.assertLess(summary["free_residual_max_N"], 1e-7)
            self.assertGreater(summary["max_displacement_mm"], 0.0)
            self.assertGreater(summary["max_element_von_mises_MPa"], 0.0)

            reference = axial_bar_reference(length_mm=10.0, area_mm2=2.0, young_mpa=210000.0, force_n=100.0)
            self.assertLess(relative_error(summary["max_displacement_mm"], reference.displacement_mm), 0.05)

            self.assertEqual(manifest["format_version"], 3)
            self.assertEqual(manifest["surface_selection_mode"], "explicit_bounding_boxes")
            self.assertEqual(manifest["source_step_sha256"], summary["step_sha256"])
            self.assertEqual(manifest["evidence_fingerprint_sha256"], second["manifest"]["evidence_fingerprint_sha256"])
            self.assertEqual(manifest["artifacts"], second["manifest"]["artifacts"])
            for name in ("model.msh", "result.vtk", "summary.json", "astermax_step_viewer.html", "manifest.json"):
                self.assertTrue((root / "first" / name).is_file())

            vtk = (root / "first" / "result.vtk").read_text(encoding="utf-8")
            self.assertIn("VECTORS displacement_mm", vtk)
            self.assertIn("SCALARS von_mises_MPa", vtk)
            self.assertIn("TENSORS stress_MPa", vtk)
            viewer = (root / "first" / "astermax_step_viewer.html").read_text(encoding="utf-8")
            self.assertIn("STEP → Mesh → FEA → Evidence", viewer)
            self.assertIn("von_mises_MPa", viewer)
            self.assertIn("displacement_mm", viewer)
            self.assertIn(manifest["artifacts"]["summary.json"]["sha256"], viewer)
            self.assertNotIn("<script src=", viewer)
            self.assertNotIn("https://", viewer)
            self.assertNotIn("http://", viewer)

            persisted = json.loads((root / "first" / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted, summary)
            self.assertTrue(math.isfinite(persisted["max_element_von_mises_MPa"]))

    def test_semantic_mode_runs_full_step_fea_viewer_pipeline(self):
        with tempfile.TemporaryDirectory(prefix="astermax-semantic-demo-") as temporary:
            root = Path(temporary)
            step = self.export_bar_step(root, length=10.0)
            evidence = run_step_static_demo(
                step, root / "semantic",
                fixed_intent=SemanticSurfaceIntent("FIXED", "x", "min"),
                load_intent=SemanticSurfaceIntent("LOAD", "x", "max"),
                total_force_n=(100.0, 0.0, 0.0), mesh_size_mm=1.7,
                young_mpa=210000.0, poisson=0.30, gmsh_executable=GMSH,
            )
            summary = evidence["summary"]
            self.assertEqual(summary["surface_selection_mode"], "semantic_normalized_boundary_intent")
            self.assertEqual(evidence["manifest"]["surface_selection_mode"], summary["surface_selection_mode"])
            self.assertEqual([item["name"] for item in summary["semantic_surfaces"]], ["FIXED", "LOAD"])
            self.assertAlmostEqual(summary["semantic_surfaces"][0]["selected_area_mm2"], 2.0, places=6)
            self.assertAlmostEqual(summary["semantic_surfaces"][1]["selected_area_mm2"], 2.0, places=6)
            self.assertAlmostEqual(summary["recovered_applied_force_N"][0], 100.0, places=10)
            self.assertAlmostEqual(summary["reaction_resultant_N"][0], -100.0, places=7)
            self.assertLess(summary["free_residual_max_N"], 1e-7)
            self.assertTrue((root / "semantic" / "astermax_step_viewer.html").is_file())

    def test_wrong_surface_semantics_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="astermax-step-demo-fail-") as temporary:
            root = Path(temporary)
            step = self.export_bar_step(root)
            eps = 1e-5
            with self.assertRaises(StepStaticDemoError):
                run_step_static_demo(
                    step, root / "bad",
                    fixed_box=SurfaceBox("CLAMP", (-eps, -eps, -eps), (eps, 2.0 + eps, 1.0 + eps)),
                    load_box=SurfaceBox("LOAD", (10.0 - eps, -eps, -eps), (10.0 + eps, 2.0 + eps, 1.0 + eps)),
                    total_force_n=(100.0, 0.0, 0.0), mesh_size_mm=2.0,
                    young_mpa=210000.0, poisson=0.30, gmsh_executable=GMSH,
                )
            with self.assertRaises(StepStaticDemoError):
                run_step_static_demo(
                    step, root / "mixed",
                    fixed_box=SurfaceBox("FIXED", (-eps, -eps, -eps), (eps, 2.0 + eps, 1.0 + eps)),
                    load_box=SurfaceBox("LOAD", (10.0 - eps, -eps, -eps), (10.0 + eps, 2.0 + eps, 1.0 + eps)),
                    fixed_intent=SemanticSurfaceIntent("FIXED", "x", "min"),
                    load_intent=SemanticSurfaceIntent("LOAD", "x", "max"),
                    total_force_n=(100.0, 0.0, 0.0), mesh_size_mm=2.0,
                    young_mpa=210000.0, poisson=0.30, gmsh_executable=GMSH,
                )


if __name__ == "__main__":
    unittest.main()
