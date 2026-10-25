import math
import unittest

from astermax.mesh_quality import (
    MeshQualityError,
    assess_tet4_mesh_quality,
    require_tet4_mesh_quality,
    tet4_mean_ratio,
)


class Tet4MeshQualityTests(unittest.TestCase):
    def test_regular_tetrahedron_has_unit_quality(self):
        h = math.sqrt(3.0) / 2.0
        z = math.sqrt(2.0 / 3.0)
        nodes = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.5, h, 0.0),
            (0.5, h / 3.0, z),
        ]
        self.assertAlmostEqual(tet4_mean_ratio(nodes), 1.0, places=12)

    def test_collapsed_tetrahedron_tends_to_zero_quality(self):
        nodes = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (1e-9, 1e-9, 1e-12),
        ]
        self.assertLess(tet4_mean_ratio(nodes), 1e-6)

    def test_report_exposes_worst_cell_and_threshold_count(self):
        nodes = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (1e-9, 1e-9, 1e-12),
        ]
        elements = [(0, 1, 2, 3), (0, 1, 2, 4)]
        report = assess_tet4_mesh_quality(nodes, elements, minimum_quality=0.05)
        self.assertEqual(report.element_count, 2)
        self.assertEqual(report.worst_element, 1)
        self.assertEqual(report.below_threshold, 1)
        self.assertFalse(report.accepted)
        self.assertLessEqual(report.minimum, report.mean)
        self.assertLessEqual(report.mean, report.maximum)

    def test_gate_rejects_bad_mesh_instead_of_solving_silently(self):
        nodes = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (1e-9, 1e-9, 1e-12),
        ]
        with self.assertRaisesRegex(MeshQualityError, "quality gate failed"):
            require_tet4_mesh_quality(nodes, [(0, 1, 2, 3)], minimum_quality=0.05)

    def test_gate_accepts_a_well_shaped_tetrahedron(self):
        nodes = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        ]
        report = require_tet4_mesh_quality(nodes, [(0, 1, 2, 3)], minimum_quality=0.05)
        self.assertTrue(report.accepted)
        self.assertGreater(report.minimum, 0.05)

    def test_invalid_connectivity_and_threshold_are_rejected(self):
        nodes = [(0.0, 0.0, 0.0)] * 4
        with self.assertRaises(MeshQualityError):
            assess_tet4_mesh_quality(nodes, [(0, 1, 2, 8)])
        with self.assertRaises(MeshQualityError):
            assess_tet4_mesh_quality(nodes, [(0, 1, 2, 3)], minimum_quality=0.0)


if __name__ == "__main__":
    unittest.main()
