import math
import unittest

from astermax.global_surface_contact import (
    GlobalSurfaceContactError,
    NodeTriangleContactPair,
    solve_small_sliding_surface_contact_from_stiffness,
)
from astermax.surface_contact import resultant_and_moment_about_origin


def _isotropic_slave_stiffness(node_count, slave, stiffness):
    ndof = 3 * node_count
    matrix = [[0.0] * ndof for _ in range(ndof)]
    for component in range(3):
        matrix[3 * slave + component][3 * slave + component] = float(stiffness)
    return matrix


def _unit(values):
    magnitude = math.sqrt(sum(float(v) ** 2 for v in values))
    return tuple(float(v) / magnitude for v in values)


class ClosestFeatureGlobalContactHarness(unittest.TestCase):
    def setUp(self):
        # Right master TRI3 in z=0. Slave projection (1.2, 1.2, 0.4) lies outside
        # the face, but its exact finite-triangle closest point is the BC edge midpoint
        # q=(1,1,0), with barycentric weights (0, 0.5, 0.5).
        self.nodes = (
            (1.2, 1.2, 0.4),
            (0.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (0.0, 2.0, 0.0),
        )
        self.ks = 1000.0
        self.kp = 50000.0
        self.stiffness = _isotropic_slave_stiffness(4, 0, self.ks)
        self.constraints = {
            3 * node + component: 0.0
            for node in (1, 2, 3)
            for component in range(3)
        }
        self.closest_point = (1.0, 1.0, 0.0)
        self.normal = _unit(tuple(self.nodes[0][i] - self.closest_point[i] for i in range(3)))
        self.g0 = math.sqrt(sum((self.nodes[0][i] - self.closest_point[i]) ** 2 for i in range(3)))

    def _loads(self, magnitude=-1000.0):
        return {component: magnitude * self.normal[component] for component in range(3)}

    def test_strict_mode_preserves_legacy_outside_triangle_behavior(self):
        result = solve_small_sliding_surface_contact_from_stiffness(
            self.nodes,
            self.stiffness,
            self.constraints,
            self._loads(),
            [NodeTriangleContactPair(0, (1, 2, 3), self.kp)],
        )
        state = result.contact_states[0]
        self.assertTrue(result.converged)
        self.assertFalse(state.active)
        for component in range(3):
            self.assertAlmostEqual(result.displacements[component], -self.normal[component], places=10)

    def test_edge_closest_feature_matches_scalar_penalty_oracle(self):
        result = solve_small_sliding_surface_contact_from_stiffness(
            self.nodes,
            self.stiffness,
            self.constraints,
            self._loads(),
            [NodeTriangleContactPair(
                0,
                (1, 2, 3),
                self.kp,
                projection_mode="closest_feature",
                max_reference_distance_mm=0.6,
            )],
        )
        state = result.contact_states[0]

        # Independent 1D oracle along the frozen closest-feature normal:
        # (ks+kp)*u_n = -P - kp*g0.
        expected_un = (-1000.0 - self.kp * self.g0) / (self.ks + self.kp)
        expected_gap = self.g0 + expected_un
        expected_force = self.kp * (-expected_gap)

        self.assertTrue(result.converged)
        self.assertTrue(state.active)
        self.assertAlmostEqual(state.reference_gap_mm, self.g0, places=12)
        self.assertEqual(state.barycentric, (0.0, 0.5, 0.5))
        for actual, expected in zip(state.normal, self.normal):
            self.assertAlmostEqual(actual, expected, places=12)
        for component in range(3):
            self.assertAlmostEqual(
                result.displacements[component], expected_un * self.normal[component], places=9
            )
        self.assertAlmostEqual(state.signed_gap_mm, expected_gap, places=10)
        self.assertAlmostEqual(state.normal_force_n, expected_force, places=7)
        self.assertLess(max(abs(result.residual[i]) for i in range(3)), 1e-7)

    def test_edge_feature_contact_preserves_resultant_and_moment(self):
        result = solve_small_sliding_surface_contact_from_stiffness(
            self.nodes,
            self.stiffness,
            self.constraints,
            self._loads(),
            [NodeTriangleContactPair(
                0,
                (1, 2, 3),
                self.kp,
                projection_mode="closest_feature",
                max_reference_distance_mm=0.6,
            )],
        )
        state = result.contact_states[0]
        deformed_slave = tuple(
            self.nodes[0][i] + result.displacements[i] for i in range(3)
        )
        resultant, moment = resultant_and_moment_about_origin(
            deformed_slave,
            state.slave_force_n,
            self.nodes[1:4],
            state.master_nodal_forces_n,
        )
        self.assertLess(max(abs(value) for value in resultant), 1e-9)
        self.assertLess(max(abs(value) for value in moment), 1e-8)

    def test_vertex_region_uses_convex_single_node_transfer(self):
        nodes = list(self.nodes)
        nodes[0] = (-0.2, -0.2, 0.4)
        closest = (0.0, 0.0, 0.0)
        normal = _unit(tuple(nodes[0][i] - closest[i] for i in range(3)))
        loads = {component: -1000.0 * normal[component] for component in range(3)}
        result = solve_small_sliding_surface_contact_from_stiffness(
            nodes,
            self.stiffness,
            self.constraints,
            loads,
            [NodeTriangleContactPair(
                0,
                (1, 2, 3),
                self.kp,
                projection_mode="closest_feature",
                max_reference_distance_mm=0.6,
            )],
        )
        state = result.contact_states[0]
        self.assertTrue(state.active)
        self.assertEqual(state.barycentric, (1.0, 0.0, 0.0))
        self.assertGreater(state.normal_force_n, 0.0)
        self.assertLess(max(abs(result.residual[i]) for i in range(3)), 1e-7)

    def test_closest_feature_requires_explicit_association_gate(self):
        with self.assertRaises(GlobalSurfaceContactError):
            solve_small_sliding_surface_contact_from_stiffness(
                self.nodes,
                self.stiffness,
                self.constraints,
                self._loads(),
                [NodeTriangleContactPair(
                    0, (1, 2, 3), self.kp, projection_mode="closest_feature"
                )],
            )

    def test_too_small_reference_distance_gate_prevents_activation(self):
        result = solve_small_sliding_surface_contact_from_stiffness(
            self.nodes,
            self.stiffness,
            self.constraints,
            self._loads(),
            [NodeTriangleContactPair(
                0,
                (1, 2, 3),
                self.kp,
                projection_mode="closest_feature",
                max_reference_distance_mm=0.1,
            )],
        )
        self.assertFalse(result.contact_states[0].active)

    def test_invalid_projection_mode_fails_closed(self):
        with self.assertRaises(GlobalSurfaceContactError):
            solve_small_sliding_surface_contact_from_stiffness(
                self.nodes,
                self.stiffness,
                self.constraints,
                self._loads(),
                [NodeTriangleContactPair(
                    0, (1, 2, 3), self.kp, projection_mode="guess"
                )],
            )


if __name__ == "__main__":
    unittest.main()
