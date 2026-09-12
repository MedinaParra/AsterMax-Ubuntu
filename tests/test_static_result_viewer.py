import hashlib
import tempfile
import unittest
from pathlib import Path

from astermax.global_static import solve_linear_static
from astermax.static_result_viewer import StaticResultViewerError, write_static_result_viewer


class StaticResultViewerHarness(unittest.TestCase):
    def setUp(self):
        self.nodes = ((0.0,0.0,0.0),(1.0,0.0,0.0),(0.0,1.0,0.0),(0.0,0.0,1.0))
        self.elements = ((0,1,2,3),)
        constraints = {0:0.0,1:0.0,2:0.0,4:0.0,5:0.0,7:0.0,8:0.0,10:0.0,11:0.0}
        self.result = solve_linear_static(
            self.nodes, self.elements, young=210000.0, poisson=0.30,
            constraints=constraints, loads={3:100.0},
        )
        self.summary = {
            "unit_system":"mm-N-MPa","step_unit":"mm","node_count":4,"tet4_count":1,
            "max_displacement_mm":max(abs(v) for v in self.result.displacements),
            "max_element_von_mises_MPa":100.0,"free_residual_max_N":0.0,
            "recovered_applied_force_N":[100.0,0.0,0.0],
        }
        self.sha = hashlib.sha256(b"summary").hexdigest()

    def test_viewer_is_offline_deterministic_and_embeds_solver_results(self):
        with tempfile.TemporaryDirectory() as folder:
            a = Path(folder) / "a.html"
            b = Path(folder) / "b.html"
            write_static_result_viewer(a, self.nodes, self.elements, self.result, self.summary, summary_sha256=self.sha)
            write_static_result_viewer(b, self.nodes, self.elements, self.result, self.summary, summary_sha256=self.sha)
            ta = a.read_text(encoding="utf-8")
            tb = b.read_text(encoding="utf-8")
            self.assertEqual(ta, tb)
            self.assertIn(self.sha, ta)
            self.assertIn("von_mises_MPa", ta)
            self.assertIn("displacement_mm", ta)
            self.assertIn("stress_MPa", ta)
            self.assertIn("STEP → Mesh → FEA → Evidence", ta)
            self.assertNotIn("<script src=", ta)
            self.assertNotIn("https://", ta)
            self.assertNotIn("http://", ta)

    def test_invalid_hash_and_connectivity_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(StaticResultViewerError):
                write_static_result_viewer(Path(folder)/"bad.html", self.nodes, self.elements, self.result, self.summary, summary_sha256="bad")
            with self.assertRaises(StaticResultViewerError):
                write_static_result_viewer(Path(folder)/"bad2.html", self.nodes, ((0,1,2,9),), self.result, self.summary, summary_sha256=self.sha)


if __name__ == "__main__":
    unittest.main()
