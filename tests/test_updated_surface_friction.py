import math
import unittest

from astermax.updated_surface_friction import (
    UpdatedSurfaceFrictionError,
    solve_updated_surface_coulomb_from_stiffness,
)


class UpdatedSurfaceFrictionTests(unittest.TestCase):
    def _model(self, px):
        # Master TRI3 in z=0, fully fixed. Slave starts 0.1 mm above it.
        nodes = (
            (0.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (0.0, 2.0, 0.0),
            (0.25, 0.25, 0.1),
        )
        ndof = 12
        k = [[0.0]*ndof for _ in range(ndof)]
        for d in (9, 10, 11):
            k[d][d] = 1000.0
        fixed = {d: 0.0 for d in range(9)}
        loads = {9: float(px), 11: -1000.0}
        return nodes, k, fixed, loads

    def _solve(self, px, mu=0.2):
        nodes, k, fixed, loads = self._model(px)
        return solve_updated_surface_coulomb_from_stiffness(
            nodes, k, fixed, loads,
            slave_nodes=(3,), master_triangles=((0, 1, 2),),
            master_normal_hint=(0.0, 0.0, 1.0),
            normal_penalty_n_per_mm=9000.0,
            tangential_penalty_n_per_mm=4000.0,
            friction_coefficient=mu,
            search_distance_mm=1.0,
            displacement_tolerance_mm=1e-11,
        )

    def test_stick_matches_closed_form_and_transfers_force(self):
        r = self._solve(100.0)
        self.assertTrue(r.converged)
        s = r.contact_states[0]
        self.assertEqual(s.regime, "STICK")
        self.assertAlmostEqual(r.displacements[9], 0.02, places=10)
        self.assertAlmostEqual(r.displacements[11], -0.19, places=10)
        self.assertAlmostEqual(s.penetration_mm, 0.09, places=10)
        self.assertAlmostEqual(s.normal_force_n, 810.0, places=8)
        self.assertAlmostEqual(s.tangential_force_n[0], -80.0, places=8)
        self.assertAlmostEqual(s.tangential_force_magnitude_n, 80.0, places=8)
        self.assertAlmostEqual(sum(f[0] for f in s.master_nodal_tangential_forces_n), 80.0, places=8)
        self.assertAlmostEqual(max(abs(r.residual[d]) for d in (9, 10, 11)), 0.0, places=7)

    def test_slip_matches_closed_form_coulomb_cap(self):
        r = self._solve(500.0)
        self.assertTrue(r.converged)
        s = r.contact_states[0]
        self.assertEqual(s.regime, "SLIP")
        self.assertAlmostEqual(s.normal_force_n, 810.0, places=7)
        self.assertAlmostEqual(s.friction_limit_n, 162.0, places=7)
        self.assertAlmostEqual(s.tangential_force_magnitude_n, 162.0, places=7)
        self.assertAlmostEqual(s.tangential_force_n[0], -162.0, places=7)
        self.assertAlmostEqual(r.displacements[9], 0.338, places=8)
        self.assertAlmostEqual(max(abs(r.residual[d]) for d in (9, 10, 11)), 0.0, places=6)

    def test_geometry_safe_line_search_prevents_transient_master_loss(self):
        # The raw unconstrained/Picard predictor can temporarily overestimate Fn and
        # overshoot tangentially. Final Coulomb equilibrium remains inside the TRI3.
        r = self._solve(700.0)
        self.assertTrue(r.converged)
        self.assertEqual(r.unmatched_slave_nodes, ())
        s = r.contact_states[0]
        self.assertEqual(s.regime, "SLIP")
        self.assertEqual(s.master_nodes, (0, 1, 2))
        self.assertAlmostEqual(s.normal_force_n, 810.0, places=7)
        self.assertAlmostEqual(s.friction_limit_n, 162.0, places=7)
        self.assertAlmostEqual(r.displacements[9], 0.538, places=8)
        self.assertAlmostEqual(max(abs(r.residual[d]) for d in (9, 10, 11)), 0.0, places=6)

    def test_mu_zero_recovers_frictionless_tangent(self):
        r = self._solve(500.0, mu=0.0)
        s = r.contact_states[0]
        self.assertEqual(s.regime, "SLIP")
        self.assertAlmostEqual(s.tangential_force_magnitude_n, 0.0, places=12)
        self.assertAlmostEqual(r.displacements[9], 0.5, places=10)

    def test_master_reaction_preserves_tangential_resultant(self):
        r = self._solve(500.0)
        s = r.contact_states[0]
        total = [s.tangential_force_n[i] + sum(f[i] for f in s.master_nodal_tangential_forces_n) for i in range(3)]
        self.assertTrue(all(abs(v) < 1e-10 for v in total))
        self.assertAlmostEqual(sum(s.barycentric), 1.0, places=12)
        self.assertAlmostEqual(sum(s.tangential_force_n[i]*s.normal[i] for i in range(3)), 0.0, places=10)

    def test_invalid_friction_inputs_fail_closed(self):
        nodes, k, fixed, loads = self._model(100.0)
        common = dict(
            nodes=nodes, stiffness=k, constraints=fixed, loads=loads,
            slave_nodes=(3,), master_triangles=((0, 1, 2),),
            master_normal_hint=(0.0, 0.0, 1.0),
            normal_penalty_n_per_mm=9000.0,
            tangential_penalty_n_per_mm=4000.0,
            friction_coefficient=0.2, search_distance_mm=1.0,
        )
        for key, value in (
            ("master_normal_hint", (0.0, 0.0, 0.0)),
            ("normal_penalty_n_per_mm", 0.0),
            ("tangential_penalty_n_per_mm", 0.0),
            ("friction_coefficient", -0.1),
            ("search_distance_mm", -1.0),
            ("min_line_search_fraction", 0.0),
        ):
            args = dict(common)
            args[key] = value
            with self.assertRaises(UpdatedSurfaceFrictionError):
                solve_updated_surface_coulomb_from_stiffness(**args)


if __name__ == "__main__":
    unittest.main()
