import unittest

from astermax.global_surface_contact import (
    GlobalSurfaceContactError,
    NodeTriangleContactPair,
    solve_small_sliding_surface_contact_from_stiffness,
    solve_tet4_with_surface_contacts,
)


def _diagonal(size, entries):
    matrix = [[0.0] * size for _ in range(size)]
    for index, value in entries.items():
        matrix[index][index] = float(value)
    return matrix


class GlobalSurfaceContactHarnessTests(unittest.TestCase):
    def setUp(self):
        # Slave node 0 starts 0.4 mm above a right-triangle master in z=0.
        # Master orientation gives +Z normal.  All master DOFs and slave X/Y are
        # constrained; slave Z is attached to a verified scalar structural spring.
        self.nodes = [
            (0.5, 0.5, 0.4),
            (0.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (0.0, 2.0, 0.0),
        ]
        self.ks = 1000.0
        self.kp = 50000.0
        self.stiffness = _diagonal(12, {2: self.ks})
        self.constraints = {0: 0.0, 1: 0.0}
        for node in (1, 2, 3):
            for component in range(3):
                self.constraints[3 * node + component] = 0.0
        self.contact = NodeTriangleContactPair(0, (1, 2, 3), self.kp)

    def test_open_contact_generates_no_artificial_force(self):
        result = solve_small_sliding_surface_contact_from_stiffness(
            self.nodes,
            self.stiffness,
            self.constraints,
            {2: 100.0},
            [self.contact],
        )
        state = result.contact_states[0]
        self.assertTrue(result.converged)
        self.assertFalse(state.active)
        self.assertAlmostEqual(result.displacements[2], 0.1, places=12)
        self.assertAlmostEqual(state.signed_gap_mm, 0.5, places=12)
        self.assertAlmostEqual(state.normal_force_n, 0.0, places=12)
        self.assertLess(abs(result.residual[2]), 1e-10)

    def test_closed_contact_matches_independent_spring_penalty_solution(self):
        load_n = -1000.0
        result = solve_small_sliding_surface_contact_from_stiffness(
            self.nodes,
            self.stiffness,
            self.constraints,
            {2: load_n},
            [self.contact],
        )
        state = result.contact_states[0]

        # Independent closed-form oracle from equilibrium:
        # ks*u - P + kp*(g0+u) = 0, with signed P=-1000 N.
        expected_u = (load_n - self.kp * 0.4) / (self.ks + self.kp)
        expected_gap = 0.4 + expected_u
        expected_force = self.kp * (-expected_gap)

        self.assertTrue(result.converged)
        self.assertTrue(state.active)
        self.assertAlmostEqual(result.displacements[2], expected_u, places=12)
        self.assertAlmostEqual(state.signed_gap_mm, expected_gap, places=12)
        self.assertAlmostEqual(state.normal_force_n, expected_force, places=9)
        self.assertLess(abs(result.residual[2]), 1e-8)

    def test_contact_pair_preserves_action_reaction(self):
        result = solve_small_sliding_surface_contact_from_stiffness(
            self.nodes,
            self.stiffness,
            self.constraints,
            {2: -1000.0},
            [self.contact],
        )
        state = result.contact_states[0]
        total = list(state.slave_force_n)
        for master_force in state.master_nodal_forces_n:
            for component in range(3):
                total[component] += master_force[component]
        for value in total:
            self.assertAlmostEqual(value, 0.0, places=10)
        self.assertAlmostEqual(sum(state.barycentric), 1.0, places=12)

    def test_higher_penalty_reduces_penetration(self):
        penetrations = []
        for penalty in (5000.0, 50000.0, 500000.0):
            result = solve_small_sliding_surface_contact_from_stiffness(
                self.nodes,
                self.stiffness,
                self.constraints,
                {2: -1000.0},
                [NodeTriangleContactPair(0, (1, 2, 3), penalty)],
            )
            penetrations.append(result.contact_states[0].penetration_mm)
        self.assertGreater(penetrations[0], penetrations[1])
        self.assertGreater(penetrations[1], penetrations[2])

    def test_projection_outside_finite_master_never_activates(self):
        nodes = list(self.nodes)
        nodes[0] = (3.0, 3.0, 0.4)
        result = solve_small_sliding_surface_contact_from_stiffness(
            nodes,
            self.stiffness,
            self.constraints,
            {2: -1000.0},
            [self.contact],
        )
        self.assertFalse(result.contact_states[0].active)
        self.assertAlmostEqual(result.displacements[2], -1.0, places=12)

    def test_invalid_self_contact_is_rejected(self):
        with self.assertRaises(GlobalSurfaceContactError):
            solve_small_sliding_surface_contact_from_stiffness(
                self.nodes,
                self.stiffness,
                self.constraints,
                {2: -1.0},
                [NodeTriangleContactPair(0, (0, 2, 3), self.kp)],
            )

    def test_real_tet4_stiffness_closes_gap_against_separate_master_tri3(self):
        nodes = [
            (0.25, 0.25, 1.0),
            (0.0, 0.0, 1.5),
            (1.0, 0.0, 1.5),
            (0.0, 1.0, 1.5),
            (-1.0, -1.0, 0.8),
            (2.0, -1.0, 0.8),
            (-1.0, 2.0, 0.8),
        ]
        elements = [(0, 1, 2, 3)]
        constraints = {}
        for node in (1, 2, 3, 4, 5, 6):
            for component in range(3):
                constraints[3 * node + component] = 0.0
        result = solve_tet4_with_surface_contacts(
            nodes,
            elements,
            young=210000.0,
            poisson=0.30,
            constraints=constraints,
            loads={2: -100000.0},
            contacts=[NodeTriangleContactPair(0, (4, 5, 6), 1_000_000.0)],
        )
        state = result.contact_states[0]
        self.assertTrue(result.converged)
        self.assertTrue(state.active)
        self.assertGreater(state.normal_force_n, 0.0)
        free = [dof for dof in range(len(result.residual)) if dof not in constraints]
        self.assertLess(max(abs(result.residual[dof]) for dof in free), 1e-6)


if __name__ == "__main__":
    unittest.main()
