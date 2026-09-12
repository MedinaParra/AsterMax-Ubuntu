import unittest

from astermax.gmsh_ascii import SurfaceGroup, TetraMesh
from astermax.mesh_surface_contact import MeshSurfaceContactError, build_named_surface_contact_pairs


class MeshSurfaceContactPairingTests(unittest.TestCase):
    def _mesh(self):
        nodes = (
            (0.25, 0.25, 0.10),
            (0.75, 0.25, 0.10),
            (0.25, 0.75, 0.10),
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        )
        elements = ((0, 3, 4, 6), (1, 3, 4, 6), (2, 3, 5, 6))
        return TetraMesh(
            nodes=nodes,
            elements=elements,
            source_unit="mm",
            surface_groups=(
                SurfaceGroup("CONTACT_SLAVE", 10, ((0, 1, 2),)),
                SurfaceGroup("CONTACT_MASTER", 20, ((3, 5, 4),)),
            ),
        )

    def test_pairs_every_unique_slave_node_and_orients_master(self):
        pairs, report = build_named_surface_contact_pairs(
            self._mesh(),
            master_normal_hint=(0.0, 0.0, 1.0),
            penalty_stiffness_n_per_mm=50000.0,
            search_distance_mm=0.2,
        )
        self.assertEqual(len(pairs), 3)
        self.assertEqual(report.pair_count, 3)
        self.assertEqual(report.slave_node_count, 3)
        self.assertEqual(report.master_triangle_count, 1)
        self.assertAlmostEqual(report.max_reference_distance_mm, 0.1, places=12)
        self.assertEqual([pair.slave_node for pair in pairs], [0, 1, 2])
        self.assertEqual(pairs[0].master_nodes, (3, 4, 5))
        self.assertTrue(all(pair.penalty_stiffness_n_per_mm == 50000.0 for pair in pairs))

    def test_search_distance_is_fail_closed(self):
        with self.assertRaisesRegex(MeshSurfaceContactError, "no master TRI3 projection"):
            build_named_surface_contact_pairs(
                self._mesh(),
                master_normal_hint=(0.0, 0.0, 1.0),
                penalty_stiffness_n_per_mm=50000.0,
                search_distance_mm=0.05,
            )

    def test_unknown_named_surface_is_rejected(self):
        with self.assertRaises(MeshSurfaceContactError):
            build_named_surface_contact_pairs(
                self._mesh(),
                slave_group="MISSING",
                master_normal_hint=(0.0, 0.0, 1.0),
                penalty_stiffness_n_per_mm=50000.0,
                search_distance_mm=1.0,
            )

    def test_invalid_normal_penalty_and_distance_are_rejected(self):
        for kwargs in (
            dict(master_normal_hint=(0.0, 0.0, 0.0), penalty_stiffness_n_per_mm=1.0, search_distance_mm=1.0),
            dict(master_normal_hint=(0.0, 0.0, 1.0), penalty_stiffness_n_per_mm=0.0, search_distance_mm=1.0),
            dict(master_normal_hint=(0.0, 0.0, 1.0), penalty_stiffness_n_per_mm=1.0, search_distance_mm=-1.0),
        ):
            with self.assertRaises(MeshSurfaceContactError):
                build_named_surface_contact_pairs(self._mesh(), **kwargs)

    def test_pairing_is_deterministic_for_equal_candidates(self):
        mesh = self._mesh()
        duplicate_master = SurfaceGroup(
            "CONTACT_MASTER",
            20,
            ((3, 5, 4), (3, 4, 5)),
        )
        mesh = TetraMesh(mesh.nodes, mesh.elements, "mm", (mesh.surface_groups[0], duplicate_master))
        pairs, _ = build_named_surface_contact_pairs(
            mesh,
            master_normal_hint=(0.0, 0.0, 1.0),
            penalty_stiffness_n_per_mm=1000.0,
            search_distance_mm=1.0,
        )
        self.assertTrue(all(pair.master_nodes == (3, 4, 5) for pair in pairs))


if __name__ == "__main__":
    unittest.main()
