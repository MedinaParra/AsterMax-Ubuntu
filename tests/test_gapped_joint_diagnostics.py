import unittest

from astermax.bolt_pretension import BoltPretensionConnector
from astermax.gapped_joint_diagnostics import evaluate_gapped_joint
from astermax.gapped_preloaded_joint import solve_gapped_preloaded_joint_from_stiffness


class MultiGapPartialOpeningHarness(unittest.TestCase):
    def setUp(self):
        # One fixed master TRI3 and three slave zones. Only slave z DOFs are free.
        self.nodes = (
            (0.0, 0.0, 0.0),
            (3.0, 0.0, 0.0),
            (0.0, 3.0, 0.0),
            (0.5, 0.5, 0.0),
            (1.0, 0.5, 0.0),
            (1.5, 0.5, 0.0),
        )
        ndof = 18
        self.k = [[0.0] * ndof for _ in range(ndof)]
        for i in range(ndof):
            self.k[i][i] = 1.0

        # Coupled structural normal stiffness on slave z DOFs [11,14,17].
        # Ks = [[1500,-500,0],[-500,2000,-500],[0,-500,1500]] N/mm.
        z = (11, 14, 17)
        block = (
            (1500.0, -500.0, 0.0),
            (-500.0, 2000.0, -500.0),
            (0.0, -500.0, 1500.0),
        )
        for a in range(3):
            for b in range(3):
                self.k[z[a]][z[b]] = block[a][b]

        # Fix master and slave x/y; leave slave z free.
        self.constraints = {i: 0.0 for i in range(9)}
        for node in (3, 4, 5):
            self.constraints[3 * node] = 0.0
            self.constraints[3 * node + 1] = 0.0

        self.connectors = tuple(
            BoltPretensionConnector(
                node_a=0,
                node_b=node,
                direction=(0.0, 0.0, 1.0),
                axial_stiffness_n_per_mm=4000.0,
                preload_n=1000.0,
            )
            for node in (3, 4, 5)
        )
        self.common = dict(
            slave_nodes=(3, 4, 5),
            master_triangles=((0, 1, 2),),
            master_normal_hint=(0.0, 0.0, 1.0),
            normal_penalty_n_per_mm=5000.0,
            tangential_penalty_n_per_mm=4000.0,
            friction_coefficient=0.2,
            search_distance_mm=1.0,
            max_iterations=100,
        )

    def test_spatial_gap_causes_verified_partial_support_loss_and_bolt_redistribution(self):
        # Explicit GAP field [0.1,0.2,0.4] mm. The converged active set is only
        # zone 3. Independent active-set oracle:
        # [10500 -500     0][u3]   [-1500]
        # [ -500 6000  -500][u4] = [-1000]
        # [    0 -500  5500][u5]   [-1000]
        # where the first row includes contact penalty and -kp*g=-500 N.
        expected_u = (-0.152189781021898, -0.195985401459854, -0.199635036496350)
        expected_final_gap = (-0.052189781021898, 0.004014598540146, 0.200364963503650)
        expected_bolt = (391.240875912409, 216.058394160584, 201.459854014599)

        result = solve_gapped_preloaded_joint_from_stiffness(
            self.nodes,
            self.k,
            self.constraints,
            {},
            self.connectors,
            gap_by_slave_mm={3: 0.1, 4: 0.2, 5: 0.4},
            **self.common,
        )
        report = evaluate_gapped_joint(self.connectors, result)

        self.assertTrue(result.joint.contact_result.converged)
        for dof, expected in zip((11, 14, 17), expected_u):
            self.assertAlmostEqual(result.joint.displacements[dof], expected, places=8)
            self.assertLess(abs(result.joint.residual[dof]), 1e-6)

        self.assertEqual(report.active_zone_count, 1)
        self.assertEqual(report.open_zone_count, 2)
        self.assertAlmostEqual(report.support_loss_fraction, 2.0 / 3.0, places=12)
        self.assertAlmostEqual(report.max_initial_gap_mm, 0.4, places=12)
        self.assertAlmostEqual(report.mean_initial_gap_mm, 0.7 / 3.0, places=12)

        for zone, final_gap in zip(report.zones, expected_final_gap):
            self.assertAlmostEqual(zone.final_signed_gap_mm, final_gap, places=8)
        self.assertTrue(report.zones[0].active)
        self.assertFalse(report.zones[1].active)
        self.assertFalse(report.zones[2].active)

        # Fn = kp*0.052189781... = 260.948905 N; Coulomb capacity = mu*Fn.
        self.assertAlmostEqual(report.total_normal_contact_force_n, 260.948905109489, places=6)
        self.assertAlmostEqual(report.total_friction_capacity_n, 52.189781021898, places=6)

        for state, expected in zip(result.joint.connector_states, expected_bolt):
            self.assertAlmostEqual(state.axial_force_n, expected, places=6)
        self.assertAlmostEqual(
            report.redistribution.bolt_force_spread_n,
            189.781021897810,
            places=6,
        )

        # Source CAD geometry must remain untouched by the GAP analysis overlay.
        self.assertEqual(result.source_nodes, self.nodes)

    def test_uniform_zero_gap_keeps_all_three_zones_supported(self):
        result = solve_gapped_preloaded_joint_from_stiffness(
            self.nodes,
            self.k,
            self.constraints,
            {},
            self.connectors,
            gap_by_slave_mm={3: 0.0, 4: 0.0, 5: 0.0},
            **self.common,
        )
        report = evaluate_gapped_joint(self.connectors, result)
        self.assertTrue(result.joint.contact_result.converged)
        self.assertEqual(report.active_zone_count, 3)
        self.assertEqual(report.open_zone_count, 0)
        self.assertAlmostEqual(report.support_loss_fraction, 0.0, places=12)
        self.assertGreater(report.total_normal_contact_force_n, 0.0)


if __name__ == "__main__":
    unittest.main()
