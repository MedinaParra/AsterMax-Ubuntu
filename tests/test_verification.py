import unittest

from astermax.verification import solve_axial_bar


class AxialBarVerificationTests(unittest.TestCase):
    def test_two_element_bar_matches_closed_form_and_equilibrium(self):
        result = solve_axial_bar(
            length_mm=1000.0,
            area_mm2=100.0,
            youngs_modulus_MPa=210000.0,
            end_force_N=10000.0,
            elements=2,
        )

        self.assertTrue(result.verified())
        self.assertAlmostEqual(result.free_end_displacement_mm, 10.0 / 21.0, places=12)
        self.assertAlmostEqual(result.analytical_displacement_mm, 10.0 / 21.0, places=12)
        self.assertEqual(len(result.element_stress_MPa), 2)
        for stress in result.element_stress_MPa:
            self.assertAlmostEqual(stress, 100.0, places=10)
        self.assertAlmostEqual(result.reaction_N, -10000.0, places=8)
        self.assertLessEqual(result.equilibrium_error_N, 1e-8)

    def test_unit_basis_is_mm_N_MPa(self):
        result = solve_axial_bar(
            length_mm=200.0,
            area_mm2=50.0,
            youngs_modulus_MPa=200000.0,
            end_force_N=5000.0,
            elements=4,
        )
        self.assertAlmostEqual(result.free_end_displacement_mm, 0.1, places=12)
        self.assertAlmostEqual(result.analytical_stress_MPa, 100.0, places=12)
        self.assertTrue(result.verified())

    def test_invalid_model_is_rejected(self):
        with self.assertRaises(ValueError):
            solve_axial_bar(
                length_mm=0.0,
                area_mm2=100.0,
                youngs_modulus_MPa=210000.0,
                end_force_N=1000.0,
            )


if __name__ == "__main__":
    unittest.main()
