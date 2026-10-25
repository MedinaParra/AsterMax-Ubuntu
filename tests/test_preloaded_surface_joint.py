import unittest

from astermax.bolt_pretension import BoltPretensionConnector
from astermax.preloaded_surface_joint import (
    PreloadedSurfaceJointError,
    solve_preloaded_surface_joint_from_stiffness,
)


class PreloadedSurfaceJointHarness(unittest.TestCase):
    def setUp(self):
        # Fixed master TRI3 in z=0 and one slave node projected inside it.
        self.nodes = (
            (0.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (0.0, 2.0, 0.0),
            (0.5, 0.5, 0.0),
        )
        ndof = 12
        self.k = [[0.0] * ndof for _ in range(ndof)]
        for i in range(ndof):
            self.k[i][i] = 1.0
        self.k[9][9] = 1000.0   # slave tangential structural stiffness
        self.k[11][11] = 1000.0  # slave normal structural stiffness
        self.constraints = {i: 0.0 for i in range(9)}
        self.constraints[10] = 0.0  # slave y fixed; x and z free
        self.bolt = BoltPretensionConnector(
            node_a=0,
            node_b=3,
            direction=(0.0, 0.0, 1.0),
            axial_stiffness_n_per_mm=4000.0,
            preload_n=1000.0,
        )
        self.contact = dict(
            slave_nodes=(3,),
            master_triangles=((0, 1, 2),),
            master_normal_hint=(0.0, 0.0, 1.0),
            normal_penalty_n_per_mm=5000.0,
            tangential_penalty_n_per_mm=4000.0,
            friction_coefficient=0.2,
            search_distance_mm=1.0,
            max_iterations=100,
        )

    def solve(self, loads):
        return solve_preloaded_surface_joint_from_stiffness(
            self.nodes,
            self.k,
            self.constraints,
            loads,
            (self.bolt,),
            **self.contact,
        )

    def test_preload_generates_contact_pressure_and_stick_capacity(self):
        # Oracle, normal equilibrium at zero separating load:
        # (ks + kb + kp) z + P0 = 0
        # z=-1000/(1000+4000+5000)=-0.1 mm
        # Fn=kp*0.1=500 N; Pbolt=1000+4000*(-0.1)=600 N.
        # With Px=50 N and STICK: x=50/(ks_x+kt)=0.01 mm, Ft=40 N.
        result = self.solve({9: 50.0})
        self.assertTrue(result.contact_result.converged)
        self.assertAlmostEqual(result.displacements[11], -0.1, places=8)
        self.assertAlmostEqual(result.displacements[9], 0.01, places=8)

        state = result.contact_result.contact_states[0]
        self.assertTrue(state.active)
        self.assertEqual(state.regime, "STICK")
        self.assertAlmostEqual(state.penetration_mm, 0.1, places=8)
        self.assertAlmostEqual(state.normal_force_n, 500.0, places=7)
        self.assertAlmostEqual(state.friction_limit_n, 100.0, places=7)
        self.assertAlmostEqual(state.tangential_force_magnitude_n, 40.0, places=7)

        bolt = result.connector_states[0]
        self.assertAlmostEqual(bolt.relative_extension_mm, -0.1, places=8)
        self.assertAlmostEqual(bolt.axial_force_n, 600.0, places=7)
        for a, b in zip(bolt.force_on_a_n, bolt.force_on_b_n):
            self.assertAlmostEqual(a + b, 0.0, places=10)

        # Only slave x/z are free. A coupled solution must equilibrate both.
        self.assertLess(abs(result.residual[9]), 1e-6)
        self.assertLess(abs(result.residual[11]), 1e-6)

    def test_separating_load_reduces_contact_and_friction_capacity(self):
        # Fsep=500 N -> z=(500-1000)/10000=-0.05 mm.
        # Fn=250 N and mu*Fn=50 N; bolt force=800 N.
        result = self.solve({11: 500.0})
        state = result.contact_result.contact_states[0]
        bolt = result.connector_states[0]
        self.assertAlmostEqual(result.displacements[11], -0.05, places=8)
        self.assertAlmostEqual(state.normal_force_n, 250.0, places=7)
        self.assertAlmostEqual(state.friction_limit_n, 50.0, places=7)
        self.assertAlmostEqual(bolt.axial_force_n, 800.0, places=7)
        self.assertLess(abs(result.residual[11]), 1e-6)

    def test_preload_threshold_opens_interface_without_fake_contact_force(self):
        # At Fsep=P0 the open branch has z=0 and contact force must be zero.
        result = self.solve({11: 1000.0})
        state = result.contact_result.contact_states[0]
        self.assertAlmostEqual(result.displacements[11], 0.0, places=8)
        self.assertFalse(state.active)
        self.assertEqual(state.regime, "OPEN")
        self.assertAlmostEqual(state.normal_force_n, 0.0, places=10)
        self.assertAlmostEqual(state.tangential_force_magnitude_n, 0.0, places=10)
        self.assertLess(abs(result.residual[11]), 1e-6)

    def test_invalid_or_missing_bolt_definition_fails_closed(self):
        with self.assertRaises(PreloadedSurfaceJointError):
            solve_preloaded_surface_joint_from_stiffness(
                self.nodes, self.k, self.constraints, {}, (), **self.contact
            )
        bad = BoltPretensionConnector(0, 3, (0.0, 0.0, 1.0), 4000.0, -1.0)
        with self.assertRaises(PreloadedSurfaceJointError):
            solve_preloaded_surface_joint_from_stiffness(
                self.nodes, self.k, self.constraints, {}, (bad,), **self.contact
            )


if __name__ == "__main__":
    unittest.main()
