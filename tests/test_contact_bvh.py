import math
import unittest

from astermax.contact_spatial_index import (
    ContactSpatialIndexError,
    build_triangle_aabb_tree,
)
from astermax.feature_contact import build_cylindrical_feature_contact_pairs
from astermax.feature_surface import CylindricalSurfaceIntent, resolve_cylindrical_surface
from astermax.gmsh_ascii import SurfaceGroup, TetraMesh


def cylindrical_interface_mesh(segments: int, length: float = 5.0) -> TetraMesh:
    nodes = []
    triangles = []
    for surface_index, radius in enumerate((1.0, 1.2)):
        offset = len(nodes)
        angular_offset = 0.0 if surface_index == 0 else math.pi / segments
        for z in (0.0, length):
            for i in range(segments):
                angle = 2.0 * math.pi * i / segments + angular_offset
                nodes.append((radius * math.cos(angle), radius * math.sin(angle), z))
        for i in range(segments):
            j = (i + 1) % segments
            a, b = offset + i, offset + j
            c, d = offset + segments + i, offset + segments + j
            triangles.extend(((a, b, d), (a, d, c)))
        bottom_center = len(nodes)
        nodes.append((0.0, 0.0, 0.0))
        top_center = len(nodes)
        nodes.append((0.0, 0.0, length))
        for i in range(segments):
            j = (i + 1) % segments
            triangles.append((bottom_center, offset + j, offset + i))
            triangles.append((top_center, offset + segments + i, offset + segments + j))
    return TetraMesh(
        nodes=tuple(nodes),
        elements=(),
        source_unit="mm",
        surface_groups=(SurfaceGroup("ALL_BOUNDARY", 1, tuple(triangles)),),
    )


def resolve_interfaces(mesh: TetraMesh):
    master = resolve_cylindrical_surface(
        mesh,
        CylindricalSurfaceIntent(
            "CONTACT_MASTER", axis="z", radius_mm=1.0,
            radial_tolerance_fraction=0.06,
            maximum_axis_normal_component=0.20,
        ),
    )
    slave = resolve_cylindrical_surface(
        mesh,
        CylindricalSurfaceIntent(
            "CONTACT_SLAVE", axis="z", radius_mm=1.2,
            radial_tolerance_fraction=0.06,
            maximum_axis_normal_component=0.20,
        ),
    )
    return slave, master


class ContactBVHHarness(unittest.TestCase):
    def test_bvh_matches_exhaustive_pairing_and_gap_oracle_exactly(self):
        for segments in (12, 36, 96):
            mesh = cylindrical_interface_mesh(segments)
            slave, master = resolve_interfaces(mesh)
            exhaustive_pairs, exhaustive_report = build_cylindrical_feature_contact_pairs(
                mesh, slave, master,
                penalty_stiffness_n_per_mm=50000.0,
                search_distance_mm=0.25,
                search_strategy="exhaustive",
            )
            bvh_pairs, bvh_report = build_cylindrical_feature_contact_pairs(
                mesh, slave, master,
                penalty_stiffness_n_per_mm=50000.0,
                search_distance_mm=0.25,
                search_strategy="bvh",
                bvh_leaf_size=4,
            )
            self.assertEqual(bvh_pairs, exhaustive_pairs)
            self.assertAlmostEqual(
                bvh_report.max_reference_distance_mm,
                exhaustive_report.max_reference_distance_mm,
                places=14,
            )
            self.assertAlmostEqual(
                bvh_report.mean_reference_distance_mm,
                exhaustive_report.mean_reference_distance_mm,
                places=14,
            )
            expected_gap = 1.2 - math.cos(math.pi / segments)
            self.assertAlmostEqual(bvh_report.max_reference_distance_mm, expected_gap, places=10)
            self.assertEqual(bvh_report.pair_count, 2 * segments)
            self.assertEqual(exhaustive_report.candidate_triangle_tests, 4 * segments * segments)
            self.assertLess(bvh_report.candidate_triangle_tests, exhaustive_report.candidate_triangle_tests)

    def test_bvh_candidate_work_grows_far_slower_than_exhaustive_oracle(self):
        reductions = []
        for segments in (24, 96):
            mesh = cylindrical_interface_mesh(segments)
            slave, master = resolve_interfaces(mesh)
            _, report = build_cylindrical_feature_contact_pairs(
                mesh, slave, master,
                penalty_stiffness_n_per_mm=10000.0,
                search_distance_mm=0.25,
                search_strategy="bvh",
                bvh_leaf_size=4,
            )
            self.assertEqual(report.exhaustive_triangle_tests, 4 * segments * segments)
            self.assertLess(report.candidate_triangle_tests, report.exhaustive_triangle_tests)
            reductions.append(report.candidate_reduction_fraction)
        # At the larger discretization the spatial index should reject the overwhelming
        # majority of master TRI3s before the expensive projection calculation.
        self.assertGreater(reductions[1], 0.90)
        self.assertGreaterEqual(reductions[1], reductions[0])

    def test_aabb_query_is_deterministic_and_invalid_inputs_fail_closed(self):
        nodes = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
                 (10.0, 0.0, 0.0), (11.0, 0.0, 0.0), (10.0, 1.0, 0.0))
        triangles = ((0, 1, 2), (3, 4, 5))
        tree = build_triangle_aabb_tree(nodes, triangles, leaf_size=1)
        self.assertEqual(tree.query_point((0.2, 0.2, 0.1), distance_mm=0.2), ((0, 1, 2),))
        self.assertEqual(
            tree.query_point((0.2, 0.2, 0.1), distance_mm=0.2),
            tree.query_point((0.2, 0.2, 0.1), distance_mm=0.2),
        )
        with self.assertRaises(ContactSpatialIndexError):
            tree.query_point((0.0, 0.0, 0.0), distance_mm=-1.0)
        with self.assertRaises(ContactSpatialIndexError):
            build_triangle_aabb_tree(nodes, ((0, 1, 99),))
        with self.assertRaises(ContactSpatialIndexError):
            build_triangle_aabb_tree(nodes, triangles, leaf_size=0)


if __name__ == "__main__":
    unittest.main()
