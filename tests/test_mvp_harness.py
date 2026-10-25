import copy
import json
import unittest
from pathlib import Path

from src.astermax_harness import ModelValidationError, cantilever_reference, validate_project


PROJECT_PATH = Path(__file__).parents[1] / "examples" / "cantilever_mm.astermax.json"


class TestMvpHarness(unittest.TestCase):
    def setUp(self):
        self.project = json.loads(PROJECT_PATH.read_text(encoding="utf-8"))

    def test_reference_project_is_valid(self):
        report = validate_project(self.project)
        self.assertTrue(report.valid)
        self.assertEqual(len(report.sha256), 64)
        self.assertIn("units:mm", report.checks)
        self.assertIn("mesh:TET4", report.checks)

    def test_analytical_reference_has_known_values(self):
        result = cantilever_reference(self.project)
        self.assertAlmostEqual(result["second_moment_mm4"], 833.3333333333, places=6)
        self.assertAlmostEqual(result["tip_displacement_mm"], 2.0, places=12)
        self.assertAlmostEqual(result["root_bending_stress_mpa"], 600.0, places=12)
        self.assertAlmostEqual(result["reaction_force_n"], 1000.0, places=12)
        self.assertAlmostEqual(result["reaction_moment_nmm"], 100000.0, places=12)

    def test_non_mm_project_is_rejected(self):
        project = copy.deepcopy(self.project)
        project["units"]["length"] = "m"
        with self.assertRaises(ModelValidationError):
            validate_project(project)

    def test_advanced_object_is_not_silently_ignored(self):
        project = copy.deepcopy(self.project)
        project["unsupported_objects"] = ["frictional_contact"]
        with self.assertRaises(ModelValidationError):
            validate_project(project)


if __name__ == "__main__":
    unittest.main()
