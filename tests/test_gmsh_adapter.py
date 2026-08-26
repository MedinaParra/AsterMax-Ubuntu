from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.gmsh_adapter import GmshAdapterError, mesh_step_to_tet4


class GmshStepAdapterTests(unittest.TestCase):
    def _write_box_step(self, path: Path, length: float, width: float, height: float) -> None:
        import gmsh

        gmsh.initialize()
        try:
            gmsh.option.setNumber("General.Terminal", 0)
            gmsh.model.add("fixture_box")
            gmsh.model.occ.addBox(0.0, 0.0, 0.0, length, width, height)
            gmsh.model.occ.synchronize()
            gmsh.write(str(path))
        finally:
            gmsh.finalize()

    def test_step_box_imports_in_mm_and_generates_only_tet4(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            step = root / "cantilever_box.step"
            msh = root / "cantilever_box.msh"
            self._write_box_step(step, 100.0, 20.0, 10.0)

            manifest = mesh_step_to_tet4(step, 10.0, output_msh=msh)

            self.assertEqual(manifest.schema, "astermax.mesh_manifest.v1")
            self.assertEqual(manifest.length_unit, "mm")
            self.assertEqual(manifest.volume_count, 1)
            self.assertEqual(manifest.surface_count, 6)
            self.assertGreater(manifest.node_count, 0)
            self.assertGreater(manifest.tet4_count, 0)
            self.assertTrue(msh.is_file())
            self.assertAlmostEqual(manifest.dimensions_mm[0], 100.0, places=6)
            self.assertAlmostEqual(manifest.dimensions_mm[1], 20.0, places=6)
            self.assertAlmostEqual(manifest.dimensions_mm[2], 10.0, places=6)
            for group in ("X_MIN", "X_MAX", "Y_MIN", "Y_MAX", "Z_MIN", "Z_MAX"):
                self.assertEqual(len(manifest.surface_groups[group]), 1, group)
            self.assertEqual(len(manifest.sha256()), 64)

    def test_non_step_input_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "model.iges"
            bad.write_text("not a STEP model", encoding="utf-8")
            with self.assertRaises(GmshAdapterError):
                mesh_step_to_tet4(bad, 10.0)

    def test_non_positive_mesh_size_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            step = Path(tmp) / "box.step"
            step.write_text("placeholder", encoding="utf-8")
            with self.assertRaises(GmshAdapterError):
                mesh_step_to_tet4(step, 0.0)


if __name__ == "__main__":
    unittest.main()
