import math
import unittest

from astermax.surface_contact import (
    SurfaceContactError,
    closest_point_to_triangle,
    project_point_to_triangle,
)


class TriangleClosestPointHarness(unittest.TestCase):
    def setUp(self):
        self.a = (0.0, 0.0, 0.0)
        self.b = (2.0, 0.0, 0.0)
        self.c = (0.0, 2.0, 0.0)

    def test_interior_matches_legacy_orthogonal_projection(self):
        point = (0.5, 0.5, 0.25)
        strict = project_point_to_triangle(point, self.a, self.b, self.c)
        robust = closest_point_to_triangle(point, self.a, self.b, self.c)
        self.assertTrue(strict.inside_triangle)
        self.assertEqual(robust.projected_point_mm, strict.projected_point_mm)
        for actual, expected in zip(robust.barycentric, strict.barycentric):
            self.assertAlmostEqual(actual, expected, places=14)
        self.assertAlmostEqual(robust.signed_gap_mm, 0.25, places=14)

    def test_edge_region_clamps_to_finite_edge_with_convex_weights(self):
        # Orthogonal plane projection is outside across edge BC (x+y=2).
        point = (1.5, 1.5, -0.2)
        strict = project_point_to_triangle(point, self.a, self.b, self.c)
        robust = closest_point_to_triangle(point, self.a, self.b, self.c)
        self.assertFalse(strict.inside_triangle)
        self.assertEqual(robust.projected_point_mm, (1.0, 1.0, 0.0))
        for actual, expected in zip(robust.barycentric, (0.0, 0.5, 0.5)):
            self.assertAlmostEqual(actual, expected, places=14)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in robust.barycentric))
        self.assertAlmostEqual(sum(robust.barycentric), 1.0, places=14)
        self.assertAlmostEqual(robust.signed_gap_mm, -0.2, places=14)
        distance = math.dist(point, robust.projected_point_mm)
        self.assertAlmostEqual(distance, math.sqrt(0.5**2 + 0.5**2 + 0.2**2), places=14)

    def test_vertex_region_clamps_exactly_to_vertex(self):
        point = (-0.4, -0.3, 0.1)
        robust = closest_point_to_triangle(point, self.a, self.b, self.c)
        self.assertEqual(robust.projected_point_mm, self.a)
        self.assertEqual(robust.barycentric, (1.0, 0.0, 0.0))
        self.assertAlmostEqual(robust.signed_gap_mm, 0.1, places=14)
        self.assertAlmostEqual(math.dist(point, robust.projected_point_mm), math.sqrt(0.26), places=14)

    def test_edge_point_has_conservative_master_weights(self):
        point = (1.0, 1.0, -0.02)
        robust = closest_point_to_triangle(point, self.a, self.b, self.c)
        self.assertAlmostEqual(robust.barycentric[0], 0.0, places=14)
        self.assertAlmostEqual(robust.barycentric[1], 0.5, places=14)
        self.assertAlmostEqual(robust.barycentric[2], 0.5, places=14)
        # A normal force distributed with these weights has the same point of action.
        recovered = tuple(
            robust.barycentric[0] * self.a[i]
            + robust.barycentric[1] * self.b[i]
            + robust.barycentric[2] * self.c[i]
            for i in range(3)
        )
        self.assertEqual(recovered, robust.projected_point_mm)

    def test_degenerate_and_nonfinite_geometry_fail_closed(self):
        with self.assertRaises(SurfaceContactError):
            closest_point_to_triangle((0, 0, 0), (0, 0, 0), (1, 0, 0), (2, 0, 0))
        with self.assertRaises(SurfaceContactError):
            closest_point_to_triangle((float("nan"), 0, 0), self.a, self.b, self.c)


if __name__ == "__main__":
    unittest.main()
