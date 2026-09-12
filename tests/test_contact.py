import unittest

from astermax.contact import (
    ContactError,
    evaluate_normal_penalty_contact,
    point_plane_gap_mm,
    rigid_stop_reference,
    solve_penalty_stop,
)


class NormalContactKinematicsTests(unittest.TestCase):
    def test_point_plane_gap_sign_convention(self):
        self.assertAlmostEqual(
            point_plane_gap_mm((0.0, 0.0, 0.4), (0.0, 0.0, 0.0), (0.0, 0.0, 2.0)),
            0.4,
            places=15,
        )
        self.assertAlmostEqual(
            point_plane_gap_mm((0.0, 0.0, -0.1), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
            -0.1,
            places=15,
        )

    def test_open_contact_carries_no_tension(self):
        state = evaluate_normal_penalty_contact(0.25, 100000.0)
        self.assertFalse(state.active)
        self.assertEqual(state.penetration_mm, 0.0)
        self.assertEqual(state.contact_force_n, 0.0)

    def test_penetration_generates_compression_only_force(self):
        state = evaluate_normal_penalty_contact(-0.02, 50000.0)
        self.assertTrue(state.active)
        self.assertAlmostEqual(state.penetration_mm, 0.02, places=15)
        self.assertAlmostEqual(state.contact_force_n, 1000.0, places=12)

    def test_invalid_normal_and_penalty_are_rejected(self):
        with self.assertRaises(ContactError):
            point_plane_gap_mm((0, 0, 0), (0, 0, 0), (0, 0, 0))
        with self.assertRaises(ContactError):
            evaluate_normal_penalty_contact(-0.1, 0.0)


class PenaltyRigidStopBenchmarkTests(unittest.TestCase):
    def test_open_branch_matches_linear_spring_exactly(self):
        result = solve_penalty_stop(
            structural_stiffness_n_per_mm=1000.0,
            penalty_stiffness_n_per_mm=100000.0,
            initial_gap_mm=0.4,
            compressive_load_n=300.0,
        )
        self.assertFalse(result.active)
        self.assertAlmostEqual(result.displacement_mm, 0.3, places=15)
        self.assertAlmostEqual(result.gap_mm, 0.1, places=15)
        self.assertEqual(result.contact_force_n, 0.0)
        self.assertAlmostEqual(result.residual_n, 0.0, places=12)

    def test_closed_branch_satisfies_equilibrium(self):
        result = solve_penalty_stop(
            structural_stiffness_n_per_mm=1000.0,
            penalty_stiffness_n_per_mm=100000.0,
            initial_gap_mm=0.4,
            compressive_load_n=1000.0,
        )
        self.assertTrue(result.active)
        self.assertGreater(result.displacement_mm, 0.4)
        self.assertGreater(result.contact_force_n, 0.0)
        self.assertAlmostEqual(
            result.spring_force_n + result.contact_force_n,
            1000.0,
            places=10,
        )
        self.assertAlmostEqual(result.residual_n, 0.0, places=10)

    def test_penalty_solution_approaches_rigid_stop_reference(self):
        k_s = 1000.0
        gap = 0.4
        load = 1000.0
        reference = rigid_stop_reference(k_s, gap, load)
        soft = solve_penalty_stop(k_s, 10000.0, gap, load)
        stiff = solve_penalty_stop(k_s, 1000000.0, gap, load)

        self.assertTrue(reference.active)
        self.assertAlmostEqual(reference.displacement_mm, 0.4, places=15)
        self.assertAlmostEqual(reference.contact_force_n, 600.0, places=12)
        self.assertLess(
            abs(stiff.displacement_mm - reference.displacement_mm),
            abs(soft.displacement_mm - reference.displacement_mm),
        )
        self.assertLess(
            abs(stiff.contact_force_n - reference.contact_force_n),
            abs(soft.contact_force_n - reference.contact_force_n),
        )
        self.assertLess(stiff.penetration_mm, soft.penetration_mm)

    def test_contact_activation_threshold_is_physical(self):
        before = rigid_stop_reference(1000.0, 0.4, 399.0)
        at = rigid_stop_reference(1000.0, 0.4, 400.0)
        after = rigid_stop_reference(1000.0, 0.4, 401.0)
        self.assertFalse(before.active)
        self.assertFalse(at.active)
        self.assertTrue(after.active)
        self.assertAlmostEqual(after.contact_force_n, 1.0, places=12)

    def test_invalid_stop_inputs_are_rejected(self):
        with self.assertRaises(ContactError):
            solve_penalty_stop(0.0, 1000.0, 0.1, 1.0)
        with self.assertRaises(ContactError):
            solve_penalty_stop(1000.0, 1000.0, -0.1, 1.0)
        with self.assertRaises(ContactError):
            rigid_stop_reference(1000.0, 0.1, -1.0)


if __name__ == "__main__":
    unittest.main()
