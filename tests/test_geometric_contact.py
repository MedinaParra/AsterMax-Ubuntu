import math
import unittest

from astermax.geometric_contact import (
    GeometricContactError,
    NodePlaneContact,
    signed_node_plane_gap,
    solve_node_plane_contacts_from_stiffness,
    solve_tet4_with_node_plane_contacts,
)


def _diag(values):
    return [[value if i == j else 0.0 for j, _ in enumerate(values)] for i, value in enumerate(values)]


class GeometricContactKinematicsTests(unittest.TestCase):
    def test_signed_gap_uses_deformed_position_and_normalizes_normal(self):
        gap = signed_node_plane_gap(
            (1.0, 2.0, 3.0), (-0.25, 0.0, 0.0), (0.0, 0.0, 0.0), (2.0, 0.0, 0.0)
        )
        self.assertAlmostEqual(gap, 0.75, places=14)

    def test_oblique_plane_gap(self):
        root2 = math.sqrt(2.0)
        self.assertAlmostEqual(
            signed_node_plane_gap((1.0, 1.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 0.0)),
            root2,
            places=14,
        )

    def test_zero_normal_is_rejected(self):
        with self.assertRaises(GeometricContactError):
            signed_node_plane_gap((0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0))


class GeometricContactActiveSetTests(unittest.TestCase):
    def test_contact_remains_open_below_gap_closing_load(self):
        result = solve_node_plane_contacts_from_stiffness(
            _diag([100.0, 100.0, 100.0]),
            [(1.0, 0.0, 0.0)],
            {},
            {0: -50.0},
            [NodePlaneContact(0, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 1000.0)],
        )
        self.assertTrue(result.converged)
        self.assertFalse(result.contacts[0].active)
        self.assertAlmostEqual(result.displacements[0], -0.5, places=12)
        self.assertAlmostEqual(result.contacts[0].signed_gap_mm, 0.5, places=12)
        self.assertAlmostEqual(result.contacts[0].normal_force_n, 0.0, places=12)

    def test_axis_aligned_penalty_contact_matches_closed_form(self):
        # Structural spring k=100 N/mm, initial gap=1 mm, P=200 N toward plane.
        # Active penalty equation: (k+kp)u = -P-kp*g0.
        k = 100.0
        kp = 1000.0
        expected_u = (-200.0 - kp * 1.0) / (k + kp)
        expected_penetration = -(1.0 + expected_u)
        result = solve_node_plane_contacts_from_stiffness(
            _diag([k, 100.0, 100.0]),
            [(1.0, 0.0, 0.0)],
            {},
            {0: -200.0},
            [NodePlaneContact(0, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), kp)],
        )
        self.assertTrue(result.converged)
        self.assertTrue(result.contacts[0].active)
        self.assertAlmostEqual(result.displacements[0], expected_u, places=12)
        self.assertAlmostEqual(result.contacts[0].penetration_mm, expected_penetration, places=12)
        self.assertAlmostEqual(result.contacts[0].normal_force_n, kp * expected_penetration, places=10)
        self.assertLess(max(abs(v) for v in result.residual), 1e-10)

    def test_oblique_normal_creates_xyz_coupling(self):
        root2 = math.sqrt(2.0)
        n = (1.0 / root2, 1.0 / root2, 0.0)
        node = (n[0], n[1], 0.0)  # exactly 1 mm from plane along n
        load = (-200.0 * n[0], -200.0 * n[1], 0.0)
        k = 100.0
        kp = 1000.0
        expected_scalar_u = (-200.0 - kp) / (k + kp)
        result = solve_node_plane_contacts_from_stiffness(
            _diag([k, k, k]),
            [node],
            {},
            {0: load[0], 1: load[1]},
            [NodePlaneContact(0, (0.0, 0.0, 0.0), n, kp)],
        )
        self.assertTrue(result.contacts[0].active)
        self.assertAlmostEqual(result.displacements[0], expected_scalar_u * n[0], places=11)
        self.assertAlmostEqual(result.displacements[1], expected_scalar_u * n[1], places=11)
        self.assertAlmostEqual(result.contacts[0].force_vector_n[0], result.contacts[0].normal_force_n * n[0], places=11)
        self.assertAlmostEqual(result.contacts[0].force_vector_n[1], result.contacts[0].normal_force_n * n[1], places=11)
        self.assertLess(max(abs(v) for v in result.residual), 1e-9)

    def test_penalty_limit_reduces_penetration(self):
        penetrations = []
        for kp in (1e3, 1e4, 1e5):
            result = solve_node_plane_contacts_from_stiffness(
                _diag([100.0, 100.0, 100.0]), [(1.0, 0.0, 0.0)], {}, {0: -200.0},
                [NodePlaneContact(0, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), kp)],
            )
            penetrations.append(result.contacts[0].penetration_mm)
        self.assertGreater(penetrations[0], penetrations[1])
        self.assertGreater(penetrations[1], penetrations[2])
        self.assertLess(penetrations[2], 0.0011)

    def test_duplicate_contact_node_is_rejected(self):
        c = NodePlaneContact(0, (0, 0, 0), (1, 0, 0), 1000.0)
        with self.assertRaises(GeometricContactError):
            solve_node_plane_contacts_from_stiffness(_diag([1, 1, 1]), [(1, 0, 0)], {}, {}, [c, c])


class Tet4GeometricContactBridgeTests(unittest.TestCase):
    def test_tet4_solver_accepts_geometric_contact_and_reaches_equilibrium(self):
        nodes = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
        elements = [(0, 1, 2, 3)]
        # Minimal rigid-body suppression for the reference tetrahedron. Node 1 x is
        # deliberately free and initially penetrates a rigid plane at x=1.01 mm.
        constraints = {
            0: 0.0, 1: 0.0, 2: 0.0,
            4: 0.0, 5: 0.0,
            6: 0.0, 8: 0.0,
            9: 0.0, 10: 0.0,
        }
        result = solve_tet4_with_node_plane_contacts(
            nodes,
            elements,
            young=210000.0,
            poisson=0.30,
            constraints=constraints,
            loads={},
            contacts=[NodePlaneContact(1, (1.01, 0.0, 0.0), (1.0, 0.0, 0.0), 1e6)],
        )
        self.assertTrue(result.converged)
        self.assertTrue(result.contacts[0].active)
        self.assertGreater(result.contacts[0].normal_force_n, 0.0)
        free = [i for i in range(len(result.residual)) if i not in constraints]
        self.assertLess(max(abs(result.residual[i]) for i in free), 1e-7)


if __name__ == "__main__":
    unittest.main()
