import math
import unittest

from astermax.updated_surface_contact import (
    UpdatedSurfaceContactError,
    solve_updated_surface_contact_from_stiffness,
)


def diagonal_matrix(values):
    n = len(values)
    return [[float(values[i]) if i == j else 0.0 for j in range(n)] for i in range(n)]


class UpdatedSurfaceContactHarness(unittest.TestCase):
    def moving_slave_model(self):
        # Slave starts over TRI3 A, but a tangential structural load moves it 1 mm
        # in +X so the deformed projection belongs to TRI3 B. Master nodes are fixed.
        nodes = (
            (0.25, 0.25, 0.20),  # 0 slave
            (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),  # A: 1,2,3
            (1.0, 0.0, 0.0), (2.0, 0.0, 0.0), (1.0, 1.0, 0.0),  # B: 4,5,6
        )
        # Only slave X/Z are free. kx=100 N/mm, kz=1000 N/mm.
        diag = [100.0, 1.0, 1000.0] + [1.0] * 18
        k = diagonal_matrix(diag)
        fixed = {1: 0.0}
        for node in range(1, 7):
            for component in range(3):
                fixed[3 * node + component] = 0.0
        loads = {0: 100.0, 2: -1000.0}
        return nodes, k, fixed, loads

    def test_research_uses_deformed_geometry_and_switches_master_region(self):
        nodes, k, fixed, loads = self.moving_slave_model()
        result = solve_updated_surface_contact_from_stiffness(
            nodes, k, fixed, loads,
            slave_nodes=(0,),
            master_triangles=((1, 2, 3), (4, 5, 6)),
            master_normal_hint=(0.0, 0.0, 1.0),
            penalty_stiffness_n_per_mm=50000.0,
            search_distance_mm=2.0,
        )
        self.assertTrue(result.converged)
        self.assertEqual(result.unmatched_slave_nodes, ())
        self.assertEqual(len(result.contact_states), 1)
        state = result.contact_states[0]
        self.assertEqual(state.master_nodes, (4, 5, 6))
        self.assertTrue(state.active)
        # Tangential frictionless motion remains the structural solution ux=F/k=1 mm.
        self.assertAlmostEqual(result.displacements[0], 1.0, places=10)
        # Closed-form Z solution for fixed planar master:
        # (ks+kp) uz = P - kp*g0, with g0=0.2 mm.
        expected_uz = (-1000.0 - 50000.0 * 0.2) / 51000.0
        self.assertAlmostEqual(result.displacements[2], expected_uz, places=9)
        self.assertAlmostEqual(state.signed_gap_mm, 0.2 + expected_uz, places=9)
        self.assertGreater(state.normal_force_n, 0.0)
        self.assertLess(max(abs(result.residual[d]) for d in (0, 2)), 1e-7)

    def test_master_normal_is_reoriented_from_hint(self):
        nodes, k, fixed, loads = self.moving_slave_model()
        result = solve_updated_surface_contact_from_stiffness(
            nodes, k, fixed, loads,
            slave_nodes=(0,),
            # B intentionally reversed.
            master_triangles=((1, 2, 3), (4, 6, 5)),
            master_normal_hint=(0.0, 0.0, 2.0),
            penalty_stiffness_n_per_mm=50000.0,
            search_distance_mm=2.0,
        )
        state = result.contact_states[0]
        self.assertGreater(state.normal[2], 0.999999999)
        self.assertEqual(state.master_nodes, (4, 5, 6))

    def test_contact_force_transfer_is_equal_and_opposite(self):
        nodes, k, fixed, loads = self.moving_slave_model()
        result = solve_updated_surface_contact_from_stiffness(
            nodes, k, fixed, loads,
            slave_nodes=(0,), master_triangles=((1, 2, 3), (4, 5, 6)),
            master_normal_hint=(0, 0, 1), penalty_stiffness_n_per_mm=50000,
            search_distance_mm=2.0,
        )
        state = result.contact_states[0]
        total = list(state.slave_force_n)
        for force in state.master_nodal_forces_n:
            for i in range(3):
                total[i] += force[i]
        self.assertLess(max(abs(x) for x in total), 1e-9)
        self.assertAlmostEqual(sum(state.barycentric), 1.0, places=12)

    def test_out_of_range_search_reports_unmatched_without_fake_contact(self):
        nodes, k, fixed, loads = self.moving_slave_model()
        result = solve_updated_surface_contact_from_stiffness(
            nodes, k, fixed, loads,
            slave_nodes=(0,), master_triangles=((1, 2, 3), (4, 5, 6)),
            master_normal_hint=(0, 0, 1), penalty_stiffness_n_per_mm=50000,
            search_distance_mm=0.01,
        )
        self.assertTrue(result.converged)
        self.assertEqual(result.contact_states, ())
        self.assertEqual(result.unmatched_slave_nodes, (0,))
        # No master found means no fabricated contact reaction.
        self.assertAlmostEqual(result.displacements[2], -1.0, places=12)

    def test_invalid_inputs_fail_closed(self):
        nodes, k, fixed, loads = self.moving_slave_model()
        base = dict(
            nodes=nodes, stiffness=k, constraints=fixed, loads=loads,
            slave_nodes=(0,), master_triangles=((1, 2, 3),),
            master_normal_hint=(0, 0, 1), penalty_stiffness_n_per_mm=50000,
            search_distance_mm=2.0,
        )
        for key, bad in (
            ("master_normal_hint", (0, 0, 0)),
            ("penalty_stiffness_n_per_mm", 0.0),
            ("search_distance_mm", -1.0),
        ):
            kwargs = dict(base)
            kwargs[key] = bad
            with self.assertRaises(UpdatedSurfaceContactError):
                solve_updated_surface_contact_from_stiffness(**kwargs)


if __name__ == "__main__":
    unittest.main()
