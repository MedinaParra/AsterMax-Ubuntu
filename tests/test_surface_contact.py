import math
import unittest

from astermax.surface_contact import (
    SurfaceContactError,
    evaluate_node_triangle_penalty_contact,
    project_point_to_triangle,
    resultant_and_moment_about_origin,
    triangle_unit_normal,
)


class SurfaceContactGeometryTests(unittest.TestCase):
    def setUp(self):
        self.a = (0.0, 0.0, 0.0)
        self.b = (2.0, 0.0, 0.0)
        self.c = (0.0, 2.0, 0.0)

    def test_triangle_normal_is_unit_and_oriented(self):
        n = triangle_unit_normal(self.a, self.b, self.c)
        self.assertEqual(n, (0.0, 0.0, 1.0))
        self.assertAlmostEqual(math.sqrt(sum(value * value for value in n)), 1.0, places=15)

    def test_projection_recovers_barycentric_coordinates_and_gap(self):
        projection = project_point_to_triangle((0.5, 0.5, 0.2), self.a, self.b, self.c)
        self.assertTrue(projection.inside_triangle)
        self.assertAlmostEqual(projection.signed_gap_mm, 0.2, places=15)
        self.assertEqual(projection.projected_point_mm, (0.5, 0.5, 0.0))
        for actual, expected in zip(projection.barycentric, (0.5, 0.25, 0.25)):
            self.assertAlmostEqual(actual, expected, places=15)
        self.assertAlmostEqual(sum(projection.barycentric), 1.0, places=15)

    def test_projection_outside_finite_triangle_is_not_contact_candidate(self):
        projection = project_point_to_triangle((1.5, 1.5, -0.1), self.a, self.b, self.c)
        self.assertFalse(projection.inside_triangle)
        state = evaluate_node_triangle_penalty_contact(
            (1.5, 1.5, -0.1), self.a, self.b, self.c, penalty_stiffness_n_per_mm=10000.0
        )
        self.assertFalse(state.active)
        self.assertEqual(state.normal_force_n, 0.0)

    def test_penetrating_point_generates_compression_only_contact(self):
        state = evaluate_node_triangle_penalty_contact(
            (0.5, 0.5, -0.02),
            self.a,
            self.b,
            self.c,
            penalty_stiffness_n_per_mm=50000.0,
        )
        self.assertTrue(state.active)
        self.assertAlmostEqual(state.penetration_mm, 0.02, places=15)
        self.assertAlmostEqual(state.normal_force_n, 1000.0, places=10)
        self.assertAlmostEqual(state.slave_force_n[2], 1000.0, places=10)
        self.assertEqual(state.slave_force_n[:2], (0.0, 0.0))

    def test_open_point_generates_no_artificial_traction(self):
        state = evaluate_node_triangle_penalty_contact(
            (0.5, 0.5, 0.02),
            self.a,
            self.b,
            self.c,
            penalty_stiffness_n_per_mm=50000.0,
        )
        self.assertFalse(state.active)
        self.assertEqual(state.penetration_mm, 0.0)
        self.assertEqual(state.normal_force_n, 0.0)
        self.assertEqual(state.slave_force_n, (0.0, 0.0, 0.0))

    def test_barycentric_master_reactions_preserve_force_and_moment(self):
        slave = (0.5, 0.5, -0.02)
        state = evaluate_node_triangle_penalty_contact(
            slave,
            self.a,
            self.b,
            self.c,
            penalty_stiffness_n_per_mm=50000.0,
        )
        resultant, moment = resultant_and_moment_about_origin(
            slave,
            state.slave_force_n,
            (self.a, self.b, self.c),
            state.master_nodal_forces_n,
        )
        for value in resultant:
            self.assertAlmostEqual(value, 0.0, places=10)
        # Penalty force acts between the penetrating node and its orthogonal
        # projection. Their separation is parallel to the normal force, hence the
        # local pair must also have zero net moment.
        for value in moment:
            self.assertAlmostEqual(value, 0.0, places=10)

    def test_degenerate_triangle_and_invalid_penalty_are_rejected(self):
        with self.assertRaises(SurfaceContactError):
            triangle_unit_normal((0, 0, 0), (1, 0, 0), (2, 0, 0))
        with self.assertRaises(SurfaceContactError):
            evaluate_node_triangle_penalty_contact(
                (0, 0, -1), self.a, self.b, self.c, penalty_stiffness_n_per_mm=0.0
            )


if __name__ == "__main__":
    unittest.main()
