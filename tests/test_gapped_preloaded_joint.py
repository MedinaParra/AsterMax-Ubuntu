import unittest

from astermax.bolt_pretension import BoltPretensionConnector
from astermax.gapped_preloaded_joint import (
    GappedPreloadedJointError,
    solve_gapped_preloaded_joint_from_stiffness,
)


class GappedPreloadedJointHarness(unittest.TestCase):
    def setUp(self):
        # Fixed master TRI3 in z=0; one slave initially coincident with the plane.
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
        self.k[9][9] = 1000.0
        self.k[11][11] = 1000.0
        self.constraints = {i: 0.0 for i in range(9)}
        self.constraints[10] = 0.0
        self.bolt = BoltPretensionConnector(
            node_a=0,
            node_b=3,
            direction=(0.0, 0.0, 1.0),
            axial_stiffness_n_per_mm=4000.0,
            preload_n=1000.0,
        )
        self.common = dict(
            slave_nodes=(3,),
            master_triangles=((0, 1, 2),),
            master_normal_hint=(0.0, 0.0, 1.0),
            normal_penalty_n_per_mm=5000.0,
            tangential_penalty_n_per_mm=4000.0,
            friction_coefficient=0.2,
            search_distance_mm=1.0,
            max_iterations=100,
        )

    def solve(self, gap):
        return solve_gapped_preloaded_joint_from_stiffness(
            self.nodes,
            self.k,
            self.constraints,
            {},
            (self.bolt,),
            gap_by_slave_mm={3: gap},
            **self.common,
        )

    def test_gap_reduces_contact_force_and_friction_capacity_by_closed_form_oracle(self):
        # Active-contact oracle with explicit initial gap g:
        # (ks+kb+kp)u + P0 + kp*g = 0
        # for ks=1000, kb=4000, kp=5000, P0=1000 and g=0.1:
        # u=-0.15 mm; final signed gap = g+u=-0.05 mm;
        # Fn=250 N; bolt force=1000+4000*(-0.15)=400 N;
        # Coulomb capacity mu*Fn=0.2*250=50 N.
        result = self.solve(0.1)
        joint = result.joint
        contact = joint.contact_result.contact_states[0]
        bolt = joint.connector_states[0]

        self.assertTrue(joint.contact_result.converged)
        self.assertAlmostEqual(joint.displacements[11], -0.15, places=8)
        self.assertAlmostEqual(contact.signed_gap_mm, -0.05, places=8)
        self.assertAlmostEqual(contact.penetration_mm, 0.05, places=8)
        self.assertAlmostEqual(contact.normal_force_n, 250.0, places=7)
        self.assertAlmostEqual(contact.friction_limit_n, 50.0, places=7)
        self.assertAlmostEqual(bolt.axial_force_n, 400.0, places=7)
        self.assertLess(abs(joint.residual[11]), 1e-6)

        # GAP is an analysis overlay only; the CAD/source node remains z=0.
        self.assertEqual(result.source_nodes, self.nodes)
        self.assertAlmostEqual(result.gap.nodes[3][2], 0.1, places=12)

    def test_zero_gap_recovers_existing_preloaded_joint_oracle(self):
        result = self.solve(0.0)
        contact = result.joint.contact_result.contact_states[0]
        bolt = result.joint.connector_states[0]
        self.assertAlmostEqual(result.joint.displacements[11], -0.1, places=8)
        self.assertAlmostEqual(contact.normal_force_n, 500.0, places=7)
        self.assertAlmostEqual(contact.friction_limit_n, 100.0, places=7)
        self.assertAlmostEqual(bolt.axial_force_n, 600.0, places=7)

    def test_gap_at_preload_closure_threshold_has_zero_contact_force(self):
        # Critical gap for the open branch is P0/(ks+kb)=1000/5000=0.2 mm.
        # The bolt/structure system closes exactly to the plane but cannot create
        # compressive contact pressure at that threshold.
        result = self.solve(0.2)
        contact = result.joint.contact_result.contact_states[0]
        self.assertAlmostEqual(result.joint.displacements[11], -0.2, places=8)
        self.assertAlmostEqual(contact.signed_gap_mm, 0.0, places=8)
        self.assertFalse(contact.active)
        self.assertEqual(contact.regime, "OPEN")
        self.assertAlmostEqual(contact.normal_force_n, 0.0, places=9)
        self.assertAlmostEqual(contact.friction_limit_n, 0.0, places=9)

    def test_gap_above_closure_threshold_remains_open(self):
        result = self.solve(0.3)
        contact = result.joint.contact_result.contact_states[0]
        # Open branch: u=-P0/(ks+kb)=-0.2 mm, leaving 0.1 mm physical gap.
        self.assertAlmostEqual(result.joint.displacements[11], -0.2, places=8)
        self.assertAlmostEqual(contact.signed_gap_mm, 0.1, places=8)
        self.assertFalse(contact.active)
        self.assertAlmostEqual(contact.normal_force_n, 0.0, places=9)

    def test_incomplete_or_negative_gap_field_fails_closed(self):
        with self.assertRaises(GappedPreloadedJointError):
            solve_gapped_preloaded_joint_from_stiffness(
                self.nodes, self.k, self.constraints, {}, (self.bolt,),
                gap_by_slave_mm={}, **self.common
            )
        with self.assertRaises(GappedPreloadedJointError):
            solve_gapped_preloaded_joint_from_stiffness(
                self.nodes, self.k, self.constraints, {}, (self.bolt,),
                gap_by_slave_mm={3: -0.01}, **self.common
            )


if __name__ == "__main__":
    unittest.main()
