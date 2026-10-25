import unittest

from astermax.interface_gap import InterfaceGapError, apply_interface_gap_field
from astermax.surface_contact import project_point_to_triangle


class InterfaceGapHarness(unittest.TestCase):
    def setUp(self):
        # Master TRI3 lies in z=0; slave nodes start exactly on the master plane.
        self.nodes = (
            (0.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (0.0, 2.0, 0.0),
            (0.5, 0.5, 0.0),
            (1.0, 0.5, 0.0),
        )
        self.master = (0, 1, 2)
        self.slaves = (3, 4)

    def test_spatial_gap_matches_signed_projection_exactly(self):
        result = apply_interface_gap_field(
            self.nodes, self.slaves, (0.0, 0.0, 2.0), {3: 0.10, 4: 0.40}
        )
        left = project_point_to_triangle(result.nodes[3], *(result.nodes[i] for i in self.master))
        right = project_point_to_triangle(result.nodes[4], *(result.nodes[i] for i in self.master))
        self.assertAlmostEqual(left.signed_gap_mm, 0.10, places=12)
        self.assertAlmostEqual(right.signed_gap_mm, 0.40, places=12)
        self.assertAlmostEqual(result.max_gap_mm, 0.40, places=12)
        self.assertAlmostEqual(result.mean_gap_mm, 0.25, places=12)
        self.assertEqual(result.gapped_slave_count, 2)

    def test_base_geometry_is_not_mutated(self):
        original = tuple(tuple(p) for p in self.nodes)
        result = apply_interface_gap_field(
            self.nodes, self.slaves, (0.0, 0.0, 1.0), {3: 0.10, 4: 0.00}
        )
        self.assertEqual(self.nodes, original)
        self.assertEqual(result.nodes[4], self.nodes[4])
        self.assertAlmostEqual(result.nodes[3][2], 0.10, places=12)

    def test_zero_gap_is_identity(self):
        result = apply_interface_gap_field(
            self.nodes, self.slaves, (0.0, 0.0, 1.0), {3: 0.0, 4: 0.0}
        )
        self.assertEqual(result.nodes, self.nodes)
        self.assertEqual(result.gapped_slave_count, 0)

    def test_gap_follows_normal_not_global_z(self):
        result = apply_interface_gap_field(
            self.nodes, (3,), (0.0, 2.0, 0.0), {3: 0.30}
        )
        self.assertAlmostEqual(result.nodes[3][0], 0.5, places=12)
        self.assertAlmostEqual(result.nodes[3][1], 0.8, places=12)
        self.assertAlmostEqual(result.nodes[3][2], 0.0, places=12)

    def test_invalid_gap_fields_fail_closed(self):
        with self.assertRaises(InterfaceGapError):
            apply_interface_gap_field(self.nodes, self.slaves, (0, 0, 1), {3: 0.1})
        with self.assertRaises(InterfaceGapError):
            apply_interface_gap_field(self.nodes, self.slaves, (0, 0, 1), {3: 0.1, 4: -0.1})
        with self.assertRaises(InterfaceGapError):
            apply_interface_gap_field(self.nodes, self.slaves, (0, 0, 0), {3: 0.1, 4: 0.2})
        with self.assertRaises(InterfaceGapError):
            apply_interface_gap_field(self.nodes, (99,), (0, 0, 1), {99: 0.1})


if __name__ == "__main__":
    unittest.main()
