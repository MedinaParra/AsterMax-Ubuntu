import math
import unittest

from astermax.bolt_pretension import (
    BoltPretensionConnector,
    BoltPretensionError,
    solve_tet4_with_bolt_pretension,
    solve_with_bolt_pretension,
)


class BoltPretensionHarnessTests(unittest.TestCase):
    def _spring_matrix(self, kx=1000.0):
        # Two 3D nodes. Node A is the bolt anchor. Node B has a structural
        # grounding spring only in x; all other DOFs are constrained in tests.
        k = [[0.0] * 6 for _ in range(6)]
        k[3][3] = kx
        return k

    def _connector(self, preload=500.0, kb=4000.0):
        return BoltPretensionConnector(
            node_a=0,
            node_b=1,
            direction=(1.0, 0.0, 0.0),
            axial_stiffness_n_per_mm=kb,
            preload_n=preload,
        )

    def test_preload_relaxes_against_joint_compliance_closed_form(self):
        result = solve_with_bolt_pretension(
            self._spring_matrix(),
            constraints={0: 0.0, 1: 0.0, 2: 0.0, 4: 0.0, 5: 0.0},
            loads={},
            connectors=[self._connector()],
        )
        # (ks+kb) u = -P0 => u=-500/5000=-0.1 mm.
        # Bolt tension = P0 + kb*u = 500-400 = 100 N.
        self.assertAlmostEqual(result.displacements[3], -0.1, places=12)
        state = result.connector_states[0]
        self.assertAlmostEqual(state.relative_extension_mm, -0.1, places=12)
        self.assertAlmostEqual(state.axial_force_n, 100.0, places=9)
        self.assertEqual(state.force_on_a_n, (100.0, 0.0, 0.0))
        self.assertEqual(state.force_on_b_n, (-100.0, -0.0, -0.0))
        self.assertAlmostEqual(result.reactions[0], -100.0, places=9)
        self.assertAlmostEqual(result.residual[3], 0.0, places=9)

    def test_external_separating_load_increases_bolt_force_closed_form(self):
        result = solve_with_bolt_pretension(
            self._spring_matrix(),
            constraints={0: 0.0, 1: 0.0, 2: 0.0, 4: 0.0, 5: 0.0},
            loads={3: 1000.0},
            connectors=[self._connector()],
        )
        # (ks+kb)u = Pext-P0 = 500 -> u=0.1 mm.
        # Bolt tension = 500 + 4000*0.1 = 900 N.
        self.assertAlmostEqual(result.displacements[3], 0.1, places=12)
        self.assertAlmostEqual(result.connector_states[0].axial_force_n, 900.0, places=9)
        self.assertAlmostEqual(result.residual[3], 0.0, places=9)
        self.assertAlmostEqual(result.reactions[0], -900.0, places=9)

    def test_direction_is_normalized_and_action_reaction_is_exact(self):
        connector = BoltPretensionConnector(0, 1, (2.0, 0.0, 0.0), 4000.0, 500.0)
        result = solve_with_bolt_pretension(
            self._spring_matrix(),
            constraints={0: 0.0, 1: 0.0, 2: 0.0, 4: 0.0, 5: 0.0},
            loads={},
            connectors=[connector],
        )
        state = result.connector_states[0]
        for a, b in zip(state.force_on_a_n, state.force_on_b_n):
            self.assertAlmostEqual(a + b, 0.0, places=12)

    def test_zero_preload_reduces_to_ordinary_axial_connector(self):
        result = solve_with_bolt_pretension(
            self._spring_matrix(),
            constraints={0: 0.0, 1: 0.0, 2: 0.0, 4: 0.0, 5: 0.0},
            loads={3: 500.0},
            connectors=[self._connector(preload=0.0)],
        )
        self.assertAlmostEqual(result.displacements[3], 0.1, places=12)
        self.assertAlmostEqual(result.connector_states[0].axial_force_n, 400.0, places=9)
        self.assertAlmostEqual(result.residual[3], 0.0, places=9)

    def test_tet4_bridge_solves_and_balances_free_dof(self):
        nodes = (
            (0.0, 0.0, 0.0),
            (10.0, 0.0, 0.0),
            (0.0, 10.0, 0.0),
            (0.0, 0.0, 10.0),
        )
        elements = ((0, 1, 2, 3),)
        # Fix nodes 0,1,2 and x/y of node 3, leaving only node-3 z free.
        constraints = {dof: 0.0 for dof in range(9)}
        constraints.update({9: 0.0, 10: 0.0})
        connector = BoltPretensionConnector(0, 3, (0.0, 0.0, 1.0), 10000.0, 1000.0)
        result = solve_tet4_with_bolt_pretension(
            nodes, elements, 210000.0, 0.3, constraints, {}, [connector]
        )
        self.assertTrue(math.isfinite(result.displacements[11]))
        self.assertTrue(math.isfinite(result.connector_states[0].axial_force_n))
        self.assertAlmostEqual(result.residual[11], 0.0, places=7)

    def test_invalid_definitions_fail_closed(self):
        constraints = {0: 0.0, 1: 0.0, 2: 0.0, 4: 0.0, 5: 0.0}
        bad = (
            BoltPretensionConnector(0, 0, (1, 0, 0), 1.0, 1.0),
            BoltPretensionConnector(0, 1, (0, 0, 0), 1.0, 1.0),
            BoltPretensionConnector(0, 1, (1, 0, 0), 0.0, 1.0),
            BoltPretensionConnector(0, 1, (1, 0, 0), 1.0, -1.0),
            BoltPretensionConnector(0, 2, (1, 0, 0), 1.0, 1.0),
        )
        for connector in bad:
            with self.subTest(connector=connector):
                with self.assertRaises(BoltPretensionError):
                    solve_with_bolt_pretension(self._spring_matrix(), constraints, {}, [connector])
        with self.assertRaises(BoltPretensionError):
            solve_with_bolt_pretension(self._spring_matrix(), constraints, {}, [])


if __name__ == "__main__":
    unittest.main()
