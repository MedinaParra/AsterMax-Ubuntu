import unittest

from astermax.benchmark import axial_bar_reference, mean_surface_displacement_x, relative_error


class AxialBenchmarkTests(unittest.TestCase):
    def test_closed_form_reference_matches_known_bar(self):
        reference = axial_bar_reference(
            length_mm=1000.0,
            area_mm2=100.0,
            young_mpa=210000.0,
            force_n=10000.0,
        )
        self.assertAlmostEqual(reference.displacement_mm, 0.47619047619047616, places=15)
        self.assertAlmostEqual(reference.stress_mpa, 100.0, places=15)

    def test_relative_error_is_dimensionless_and_absolute(self):
        self.assertAlmostEqual(relative_error(9.5, 10.0), 0.05, places=15)
        self.assertAlmostEqual(relative_error(10.5, 10.0), 0.05, places=15)

    def test_surface_average_uses_unique_nodes(self):
        displacements = [
            1.0, 9.0, 9.0,
            3.0, 8.0, 8.0,
            5.0, 7.0, 7.0,
        ]
        self.assertAlmostEqual(mean_surface_displacement_x(displacements, [0, 1, 1, 2]), 3.0)

    def test_invalid_reference_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            axial_bar_reference(length_mm=0.0, area_mm2=1.0, young_mpa=1.0, force_n=1.0)
        with self.assertRaises(ValueError):
            relative_error(1.0, 0.0)
        with self.assertRaises(ValueError):
            mean_surface_displacement_x([], [])


if __name__ == "__main__":
    unittest.main()
