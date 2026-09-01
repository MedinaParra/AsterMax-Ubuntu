import math
import unittest

from astermax.feature_contact import (
    FeatureContactError,
    build_cylindrical_feature_contact_pairs,
)
from astermax.feature_surface import CylindricalSurfaceIntent, resolve_cylindrical_surface
from astermax.gmsh_ascii import SurfaceGroup, TetraMesh


def cylindrical_interface_mesh(segments: int, length: float = 5.0) -> TetraMesh:
    """Two concentric triangulated cylinders plus caps in one auditable boundary."""
    nodes = []
    triangles = []
    for radius in (1.0, 1.2):
        offset = len(nodes)
        for z in (0.0, length):
            for i in range(segments):
                angle = 2.0 * math.pi * i / segments
                nodes.append((radius * math.cos(angle), radius * math.sin(angle), z))
        # Side wall: two TRI3 per circumferential quad.
        for i in range(segments):
            j = (i + 1) % segments
            a, b = offset + i, offset + j
            c, d = offset + segments + i, offset + segments + j
            triangles.extend(((a, b, d), (a, d, c)))
        # Add cap triangles so feature resolution must reject axial-normal surfaces.
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


class CylindricalFeatureContactHarness(unittest.TestCase):
    def test_local_radial_normals_and_pairing_survive_major_remeshing(self):
        reports = []
        pair_counts = []
        for segments in (12, 36):
            mesh = cylindrical_interface_mesh(segments)
            slave, master = resolve_interfaces(mesh)
            pairs, report = build_cylindrical_feature_contact_pairs(
                mesh, slave, master,
                penalty_stiffness_n_per_mm=50000.0,
                search_distance_mm=0.25,
                master_normal_direction="outward",
            )
            self.assertEqual(report.slave_group, "CONTACT_SLAVE")
            self.assertEqual(report.master_group, "CONTACT_MASTER")
            self.assertEqual(report.slave_node_count, 2 * segments)
            self.assertEqual(report.master_triangle_count, 2 * segments)
            self.assertEqual(report.pair_count, 2 * segments)
            self.assertEqual(len(pairs), 2 * segments)
            self.assertLessEqual(report.max_reference_distance_mm, 0.25)
            self.assertGreater(report.minimum_master_radial_alignment, 0.95)
            self.assertTrue(all(pair.penalty_stiffness_n_per_mm == 50000.0 for pair in pairs))
            reports.append(report)
            pair_counts.append(report.pair_count)

        # The discretization changes 3x, proving pairing is reconstructed from
        # engineering feature intent rather than retained mesh/face IDs.
        self.assertEqual(pair_counts, [24, 72])
        self.assertNotEqual(reports[0].master_triangle_count, reports[1].master_triangle_count)
        self.assertAlmostEqual(reports[0].max_reference_distance_mm, 0.2, delta=0.02)
        self.assertAlmostEqual(reports[1].max_reference_distance_mm, 0.2, delta=0.005)

    def test_inward_orientation_is_also_local_and_deterministic(self):
        mesh = cylindrical_interface_mesh(24)
        slave, master = resolve_interfaces(mesh)
        first, report_a = build_cylindrical_feature_contact_pairs(
            mesh, slave, master,
            penalty_stiffness_n_per_mm=10000.0,
            search_distance_mm=0.25,
            master_normal_direction="inward",
        )
        second, report_b = build_cylindrical_feature_contact_pairs(
            mesh, slave, master,
            penalty_stiffness_n_per_mm=10000.0,
            search_distance_mm=0.25,
            master_normal_direction="inward",
        )
        self.assertEqual(first, second)
        self.assertEqual(report_a, report_b)
        self.assertEqual(report_a.master_normal_direction, "inward")
        self.assertGreater(report_a.minimum_master_radial_alignment, 0.98)

    def test_nonconcentric_features_and_too_small_search_fail_closed(self):
        mesh = cylindrical_interface_mesh(24)
        slave, master = resolve_interfaces(mesh)
        with self.assertRaises(FeatureContactError):
            build_cylindrical_feature_contact_pairs(
                mesh, slave, master,
                penalty_stiffness_n_per_mm=50000.0,
                search_distance_mm=0.05,
            )

        shifted_master = resolve_cylindrical_surface(
            mesh,
            CylindricalSurfaceIntent(
                "SHIFTED_MASTER", axis="z", center_fraction=(0.55, 0.5),
                radius_mm=1.0, radial_tolerance_fraction=0.12,
            ),
        )
        with self.assertRaises(FeatureContactError):
            build_cylindrical_feature_contact_pairs(
                mesh, slave, shifted_master,
                penalty_stiffness_n_per_mm=50000.0,
                search_distance_mm=0.25,
            )


if __name__ == "__main__":
    unittest.main()
