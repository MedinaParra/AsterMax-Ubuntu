import unittest

from astermax.bolt_pretension import BoltPretensionConnector
from astermax.joint_redistribution import (
    JointRedistributionError,
    evaluate_joint_redistribution,
)
from astermax.preloaded_surface_joint import solve_preloaded_surface_joint_from_stiffness


class JointRedistributionHarness(unittest.TestCase):
    """Two-bolt/two-contact oracle with an independently solvable 2x2 normal system."""

    def _case(self, load_left=700.0, load_right=100.0):
        # Two slave nodes sit on one fixed master TRI3.  Two fixed anchor nodes carry
        # identical preloaded bolt connectors.  Only slave Z DOFs are free.
        nodes = (
            (-0.5, 0.5, 0.0),  # 0 slave left
            (0.5, 0.5, 0.0),   # 1 slave right
            (-0.5, 0.5, 1.0),  # 2 bolt anchor left
            (0.5, 0.5, 1.0),   # 3 bolt anchor right
            (-2.0, -1.0, 0.0), # 4 master
            (2.0, -1.0, 0.0),  # 5 master
            (0.0, 3.0, 0.0),   # 6 master
        )
        ndof = 3 * len(nodes)
        k = [[0.0] * ndof for _ in range(ndof)]
        # Structural support stiffness ks=1000 N/mm plus coupling kc=2000 N/mm.
        # The free normal block is [[ks+kc,-kc],[-kc,ks+kc]].
        z0, z1 = 2, 5
        k[z0][z0] = 3000.0
        k[z1][z1] = 3000.0
        k[z0][z1] = -2000.0
        k[z1][z0] = -2000.0

        constraints = {d: 0.0 for d in range(ndof) if d not in (z0, z1)}
        loads = {z0: float(load_left), z1: float(load_right)}
        connectors = (
            BoltPretensionConnector(2, 0, (0.0, 0.0, 1.0), 4000.0, 1000.0),
            BoltPretensionConnector(3, 1, (0.0, 0.0, 1.0), 4000.0, 1000.0),
        )
        result = solve_preloaded_surface_joint_from_stiffness(
            nodes, k, constraints, loads, connectors,
            slave_nodes=(0, 1),
            master_triangles=((4, 5, 6),),
            master_normal_hint=(0.0, 0.0, 1.0),
            normal_penalty_n_per_mm=5000.0,
            tangential_penalty_n_per_mm=4000.0,
            friction_coefficient=0.2,
            search_distance_mm=1.0,
        )
        return connectors, result

    def test_asymmetric_load_redistributes_bolt_and_contact_force(self):
        connectors, result = self._case()
        report = evaluate_joint_redistribution(connectors, result)

        # Independent closed-contact equations:
        # [12000 -2000] [zL] = [-300]
        # [-2000 12000] [zR]   [-900]
        # giving zL=-0.03857142857, zR=-0.08142857143 mm.
        self.assertTrue(result.contact_result.converged)
        self.assertAlmostEqual(result.displacements[2], -0.03857142857142857, places=8)
        self.assertAlmostEqual(result.displacements[5], -0.08142857142857143, places=8)

        # Bolt forces P=P0+kb*z and normal contact Fn=-kp*z.
        self.assertAlmostEqual(report.bolt_states[0].final_axial_force_n, 845.7142857142857, places=7)
        self.assertAlmostEqual(report.bolt_states[1].final_axial_force_n, 674.2857142857143, places=7)
        self.assertAlmostEqual(report.bolt_force_spread_n, 171.4285714285714, places=7)
        self.assertAlmostEqual(report.total_final_bolt_tension_n, 1520.0, places=7)
        self.assertAlmostEqual(report.total_normal_contact_force_n, 600.0, places=7)
        self.assertAlmostEqual(report.total_friction_capacity_n, 120.0, places=7)
        self.assertEqual(report.active_contact_count, 2)
        self.assertEqual(report.open_contact_count, 0)
        self.assertAlmostEqual(report.contact_active_fraction, 1.0, places=12)
        self.assertAlmostEqual(sum(s.tensile_load_share for s in report.bolt_states), 1.0, places=12)

    def test_mirror_load_mirrors_redistribution(self):
        connectors_a, result_a = self._case(700.0, 100.0)
        connectors_b, result_b = self._case(100.0, 700.0)
        a = evaluate_joint_redistribution(connectors_a, result_a)
        b = evaluate_joint_redistribution(connectors_b, result_b)
        self.assertAlmostEqual(a.bolt_states[0].final_axial_force_n, b.bolt_states[1].final_axial_force_n, places=7)
        self.assertAlmostEqual(a.bolt_states[1].final_axial_force_n, b.bolt_states[0].final_axial_force_n, places=7)
        self.assertAlmostEqual(a.total_normal_contact_force_n, b.total_normal_contact_force_n, places=7)

    def test_definition_state_mismatch_fails_closed(self):
        connectors, result = self._case()
        with self.assertRaises(JointRedistributionError):
            evaluate_joint_redistribution(connectors[:1], result)


if __name__ == "__main__":
    unittest.main()
