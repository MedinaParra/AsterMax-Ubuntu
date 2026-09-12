import math
import unittest

from astermax.friction import (
    FrictionError,
    evaluate_coulomb_friction,
    friction_force_is_tangential,
    project_tangential,
)


class CoulombFrictionTests(unittest.TestCase):
    def test_mu_zero_recovers_frictionless_contact(self):
        state = evaluate_coulomb_friction(
            (0.1, 0.0, 0.0),
            (0.0, 0.0, 1.0),
            normal_force_n=1000.0,
            friction_coefficient=0.0,
            tangential_penalty_n_per_mm=10000.0,
        )
        self.assertEqual(state.regime, "SLIP")
        self.assertAlmostEqual(state.friction_limit_n, 0.0)
        self.assertAlmostEqual(state.tangential_force_magnitude_n, 0.0)
        self.assertEqual(state.tangential_force_n, (0.0, 0.0, 0.0))

    def test_stick_matches_elastic_predictor(self):
        state = evaluate_coulomb_friction(
            (0.01, 0.0, 0.0),
            (0.0, 0.0, 1.0),
            normal_force_n=1000.0,
            friction_coefficient=0.3,
            tangential_penalty_n_per_mm=10000.0,
        )
        # Trial magnitude = kt * du_t = 100 N, below mu*Fn = 300 N.
        self.assertEqual(state.regime, "STICK")
        self.assertAlmostEqual(state.trial_magnitude_n, 100.0)
        self.assertAlmostEqual(state.friction_limit_n, 300.0)
        self.assertEqual(state.tangential_force_n, (-100.0, 0.0, 0.0))
        self.assertAlmostEqual(state.tangential_force_magnitude_n, 100.0)

    def test_slip_returns_exactly_to_coulomb_limit(self):
        state = evaluate_coulomb_friction(
            (0.05, 0.0, 0.0),
            (0.0, 0.0, 1.0),
            normal_force_n=1000.0,
            friction_coefficient=0.3,
            tangential_penalty_n_per_mm=10000.0,
        )
        # Trial = 500 N and Coulomb capacity = 300 N.
        self.assertEqual(state.regime, "SLIP")
        self.assertAlmostEqual(state.trial_magnitude_n, 500.0)
        self.assertAlmostEqual(state.tangential_force_magnitude_n, 300.0)
        self.assertEqual(state.tangential_force_n, (-300.0, 0.0, 0.0))

    def test_projection_removes_normal_motion(self):
        tangential = project_tangential((1.0, 2.0, 3.0), (0.0, 0.0, 2.0))
        self.assertAlmostEqual(tangential[0], 1.0)
        self.assertAlmostEqual(tangential[1], 2.0)
        self.assertAlmostEqual(tangential[2], 0.0)

    def test_oblique_normal_force_remains_tangential(self):
        normal = (1.0, 1.0, 1.0)
        state = evaluate_coulomb_friction(
            (0.04, -0.01, 0.02),
            normal,
            normal_force_n=750.0,
            friction_coefficient=0.25,
            tangential_penalty_n_per_mm=20000.0,
        )
        self.assertLessEqual(state.tangential_force_magnitude_n, 187.5 + 1e-10)
        self.assertLessEqual(friction_force_is_tangential(state, normal), 1e-10)

    def test_open_contact_cannot_generate_friction(self):
        state = evaluate_coulomb_friction(
            (1.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            normal_force_n=0.0,
            friction_coefficient=0.5,
            tangential_penalty_n_per_mm=10000.0,
        )
        self.assertEqual(state.regime, "OPEN")
        self.assertEqual(state.tangential_force_n, (0.0, 0.0, 0.0))

    def test_transition_is_analytically_known(self):
        # Fn=1000 N, mu=0.2 -> limit=200 N. kt=10000 N/mm gives
        # exact elastic transition at du_t = 200/10000 = 0.02 mm.
        at_limit = evaluate_coulomb_friction(
            (0.02, 0.0, 0.0),
            (0.0, 0.0, 1.0),
            normal_force_n=1000.0,
            friction_coefficient=0.2,
            tangential_penalty_n_per_mm=10000.0,
        )
        beyond = evaluate_coulomb_friction(
            (0.0201, 0.0, 0.0),
            (0.0, 0.0, 1.0),
            normal_force_n=1000.0,
            friction_coefficient=0.2,
            tangential_penalty_n_per_mm=10000.0,
        )
        self.assertEqual(at_limit.regime, "STICK")
        self.assertAlmostEqual(at_limit.tangential_force_magnitude_n, 200.0)
        self.assertEqual(beyond.regime, "SLIP")
        self.assertAlmostEqual(beyond.tangential_force_magnitude_n, 200.0)

    def test_invalid_inputs_fail_closed(self):
        invalid_calls = (
            dict(normal_force_n=-1.0, friction_coefficient=0.2, tangential_penalty_n_per_mm=1.0),
            dict(normal_force_n=1.0, friction_coefficient=-0.2, tangential_penalty_n_per_mm=1.0),
            dict(normal_force_n=1.0, friction_coefficient=0.2, tangential_penalty_n_per_mm=0.0),
        )
        for kwargs in invalid_calls:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(FrictionError):
                    evaluate_coulomb_friction((0.1, 0.0, 0.0), (0.0, 0.0, 1.0), **kwargs)
        with self.assertRaises(FrictionError):
            evaluate_coulomb_friction(
                (0.1, 0.0, 0.0),
                (0.0, 0.0, 0.0),
                normal_force_n=1.0,
                friction_coefficient=0.2,
                tangential_penalty_n_per_mm=1.0,
            )


if __name__ == "__main__":
    unittest.main()
