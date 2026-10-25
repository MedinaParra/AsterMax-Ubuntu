import unittest

from astermax.global_friction import (
    GlobalFrictionError,
    RigidPlaneFrictionContact,
    solve_rigid_plane_coulomb_from_stiffness,
)


class GlobalFrictionHarness(unittest.TestCase):
    def setUp(self):
        # One structural node attached to independent x/y/z springs.
        self.nodes = ((0.0, 0.0, 0.1),)
        self.k = (
            (1000.0, 0.0, 0.0),
            (0.0, 1000.0, 0.0),
            (0.0, 0.0, 1000.0),
        )
        self.contact = RigidPlaneFrictionContact(
            node=0,
            plane_point_mm=(0.0, 0.0, 0.0),
            normal=(0.0, 0.0, 1.0),
            normal_penalty_n_per_mm=9000.0,
            tangential_penalty_n_per_mm=4000.0,
            friction_coefficient=0.2,
        )

    def solve(self, px):
        return solve_rigid_plane_coulomb_from_stiffness(
            self.nodes, self.k, {}, {0: px, 2: -1000.0}, self.contact
        )

    def test_stick_matches_closed_form(self):
        result = self.solve(100.0)
        self.assertTrue(result.converged)
        self.assertTrue(result.contact_state.active)
        self.assertEqual(result.contact_state.regime, "STICK")
        # Normal: (ks+kp) uz = Pz-kp*g0 = -1900 -> uz=-0.19 mm.
        self.assertAlmostEqual(result.displacements[2], -0.19, places=10)
        self.assertAlmostEqual(result.contact_state.penetration_mm, 0.09, places=10)
        self.assertAlmostEqual(result.contact_state.normal_force_n, 810.0, places=8)
        # Stick: (ks+kt) ux = Px -> ux=0.02 mm, physical friction=-80 N.
        self.assertAlmostEqual(result.displacements[0], 0.02, places=10)
        self.assertAlmostEqual(result.contact_state.tangential_force_n[0], -80.0, places=8)
        self.assertLess(max(abs(x) for x in result.residual), 1e-8)

    def test_slip_matches_coulomb_cap_and_equilibrium(self):
        result = self.solve(500.0)
        self.assertTrue(result.converged)
        self.assertEqual(result.contact_state.regime, "SLIP")
        # Normal solution is uncoupled: Fn=810 N, Coulomb cap=162 N.
        self.assertAlmostEqual(result.contact_state.normal_force_n, 810.0, places=8)
        self.assertAlmostEqual(result.contact_state.tangential_force_magnitude_n, 162.0, places=8)
        # Slip equilibrium: ks*ux + 162 = 500 -> ux=0.338 mm.
        self.assertAlmostEqual(result.displacements[0], 0.338, places=9)
        self.assertAlmostEqual(result.contact_state.tangential_force_n[0], -162.0, places=8)
        self.assertLess(max(abs(x) for x in result.residual), 1e-8)

    def test_zero_mu_recovers_frictionless_tangential_response(self):
        c = RigidPlaneFrictionContact(
            node=0, plane_point_mm=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0),
            normal_penalty_n_per_mm=9000.0, tangential_penalty_n_per_mm=4000.0,
            friction_coefficient=0.0,
        )
        result = solve_rigid_plane_coulomb_from_stiffness(
            self.nodes, self.k, {}, {0: 500.0, 2: -1000.0}, c
        )
        self.assertAlmostEqual(result.displacements[0], 0.5, places=10)
        self.assertAlmostEqual(result.contact_state.tangential_force_magnitude_n, 0.0, places=12)
        self.assertLess(max(abs(x) for x in result.residual), 1e-8)

    def test_open_contact_has_no_friction(self):
        result = solve_rigid_plane_coulomb_from_stiffness(
            self.nodes, self.k, {}, {0: 200.0, 2: 10.0}, self.contact
        )
        self.assertFalse(result.contact_state.active)
        self.assertEqual(result.contact_state.regime, "OPEN")
        self.assertAlmostEqual(result.displacements[0], 0.2, places=10)
        self.assertAlmostEqual(result.contact_state.tangential_force_magnitude_n, 0.0, places=12)

    def test_invalid_parameters_fail_closed(self):
        bad = RigidPlaneFrictionContact(
            node=0, plane_point_mm=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 0.0),
            normal_penalty_n_per_mm=9000.0, tangential_penalty_n_per_mm=4000.0,
            friction_coefficient=0.2,
        )
        with self.assertRaises(GlobalFrictionError):
            solve_rigid_plane_coulomb_from_stiffness(self.nodes, self.k, {}, {}, bad)


if __name__ == "__main__":
    unittest.main()
