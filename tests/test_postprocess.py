import math
import tempfile
import unittest
from pathlib import Path

from astermax.global_static import GlobalStaticResult
from astermax.postprocess import PostprocessError, displacement_vectors, von_mises, write_legacy_vtk
from astermax.tet4 import Tet4Result


class PostprocessHarnessTests(unittest.TestCase):
    def _result(self, stress=(100.0, 0.0, 0.0, 0.0, 0.0, 0.0)):
        element = Tet4Result(
            volume=1.0 / 6.0,
            strain=(0.0,) * 6,
            stress=stress,
            strain_energy=0.0,
            internal_force=(0.0,) * 12,
        )
        return GlobalStaticResult(
            displacements=(0.0, 0.0, 0.0, 0.1, 0.0, 0.0, 0.0, 0.2, 0.0, 0.0, 0.0, 0.3),
            reactions=(0.0,) * 12,
            residual=(0.0,) * 12,
            element_results=(element,),
            total_strain_energy=0.0,
        )

    def test_von_mises_uniaxial_equals_axial_stress(self):
        self.assertAlmostEqual(von_mises((100.0, 0.0, 0.0, 0.0, 0.0, 0.0)), 100.0, places=12)

    def test_von_mises_hydrostatic_is_zero(self):
        self.assertAlmostEqual(von_mises((75.0, 75.0, 75.0, 0.0, 0.0, 0.0)), 0.0, places=12)

    def test_von_mises_pure_shear_is_sqrt3_tau(self):
        self.assertAlmostEqual(von_mises((0.0, 0.0, 0.0, 50.0, 0.0, 0.0)), math.sqrt(3.0) * 50.0, places=12)

    def test_displacement_vectors_preserve_xyz_dof_mapping(self):
        vectors = displacement_vectors(self._result(), 4)
        self.assertEqual(vectors[1], (0.1, 0.0, 0.0))
        self.assertEqual(vectors[2], (0.0, 0.2, 0.0))
        self.assertEqual(vectors[3], (0.0, 0.0, 0.3))

    def test_vtk_export_contains_tetra_displacement_stress_and_vm(self):
        nodes = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        elements = ((0, 1, 2, 3),)
        with tempfile.TemporaryDirectory() as directory:
            path = write_legacy_vtk(Path(directory) / "case.vtk", nodes, elements, self._result())
            text = path.read_text(encoding="utf-8")
        self.assertIn("DATASET UNSTRUCTURED_GRID", text)
        self.assertIn("POINTS 4 double", text)
        self.assertIn("CELLS 1 5", text)
        self.assertIn("CELL_TYPES 1\n10", text)
        self.assertIn("VECTORS displacement_mm double", text)
        self.assertIn("SCALARS von_mises_MPa double 1", text)
        self.assertIn("TENSORS stress_MPa double", text)
        self.assertIn("\n100\n", text)

    def test_export_rejects_result_element_count_mismatch(self):
        nodes = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(PostprocessError):
                write_legacy_vtk(Path(directory) / "bad.vtk", nodes, (), self._result())

    def test_von_mises_rejects_wrong_component_count(self):
        with self.assertRaises(PostprocessError):
            von_mises((1.0, 2.0, 3.0))


if __name__ == "__main__":
    unittest.main()
