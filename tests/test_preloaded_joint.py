import unittest

from astermax.preloaded_joint import PreloadedJoint, PreloadedJointError, solve_preloaded_joint


class PreloadedJointHarness(unittest.TestCase):
    def setUp(self):
        self.joint = PreloadedJoint(
            structural_normal_stiffness_n_per_mm=1000.0,
            bolt_axial_stiffness_n_per_mm=4000.0,
            contact_penalty_n_per_mm=5000.0,
            tangential_stick_stiffness_n_per_mm=10000.0,
            bolt_preload_n=1000.0,
            friction_coefficient=0.2,
        )

    def test_preload_generates_clamp_and_stick_capacity(self):
        result = solve_preloaded_joint(self.joint, normal_load_n=0.0, shear_load_n=100.0)
        # Closed-form normal branch:
        # z=(0-1000)/(1000+4000+5000)=-0.1 mm
        # Fn=-kp*z=500 N; Pb=1000+4000*(-0.1)=600 N
        # Coulomb capacity=0.2*500=100 N.
        self.assertEqual(result.normal_regime, "CLOSED")
        self.assertEqual(result.friction_regime, "STICK")
        self.assertAlmostEqual(result.normal_displacement_mm, -0.1, places=12)
        self.assertAlmostEqual(result.contact_normal_force_n, 500.0, places=9)
        self.assertAlmostEqual(result.bolt_force_n, 600.0, places=9)
        self.assertAlmostEqual(result.friction_capacity_n, 100.0, places=9)
        self.assertAlmostEqual(result.tangential_displacement_mm, 0.01, places=12)
        self.assertAlmostEqual(result.friction_force_n, -100.0, places=9)
        self.assertAlmostEqual(result.normal_residual_n, 0.0, places=9)
        self.assertAlmostEqual(result.tangential_residual_n, 0.0, places=9)
        self.assertTrue(result.clamp_retained)

    def test_separating_load_reduces_contact_and_friction_capacity(self):
        result = solve_preloaded_joint(self.joint, normal_load_n=500.0, shear_load_n=40.0)
        # z=(500-1000)/10000=-0.05 mm, Fn=250 N, capacity=50 N.
        self.assertEqual(result.normal_regime, "CLOSED")
        self.assertEqual(result.friction_regime, "STICK")
        self.assertAlmostEqual(result.normal_displacement_mm, -0.05, places=12)
        self.assertAlmostEqual(result.contact_normal_force_n, 250.0, places=9)
        self.assertAlmostEqual(result.friction_capacity_n, 50.0, places=9)
        self.assertAlmostEqual(result.friction_force_n, -40.0, places=9)
        self.assertAlmostEqual(result.tangential_residual_n, 0.0, places=9)

    def test_interface_opens_at_or_above_preload_threshold(self):
        result = solve_preloaded_joint(self.joint, normal_load_n=1000.0, shear_load_n=0.0)
        self.assertEqual(result.normal_regime, "OPEN")
        self.assertEqual(result.friction_regime, "OPEN")
        self.assertAlmostEqual(result.normal_displacement_mm, 0.0, places=12)
        self.assertAlmostEqual(result.contact_normal_force_n, 0.0, places=12)
        self.assertAlmostEqual(result.friction_capacity_n, 0.0, places=12)
        self.assertAlmostEqual(result.normal_residual_n, 0.0, places=9)

    def test_slip_caps_force_and_reports_unbalanced_shear(self):
        result = solve_preloaded_joint(self.joint, normal_load_n=0.0, shear_load_n=150.0)
        self.assertEqual(result.friction_regime, "SLIP")
        self.assertAlmostEqual(result.friction_capacity_n, 100.0, places=9)
        self.assertAlmostEqual(result.friction_force_n, -100.0, places=9)
        self.assertAlmostEqual(result.tangential_displacement_mm, 0.01, places=12)
        # The verification model intentionally has no post-slip tangential load path.
        self.assertAlmostEqual(result.tangential_residual_n, 50.0, places=9)

    def test_open_interface_rejects_nonzero_shear_without_load_path(self):
        with self.assertRaisesRegex(PreloadedJointError, "open interface cannot equilibrate shear"):
            solve_preloaded_joint(self.joint, normal_load_n=1200.0, shear_load_n=1.0)

    def test_zero_friction_yields_zero_capacity_and_slip(self):
        joint = PreloadedJoint(
            structural_normal_stiffness_n_per_mm=1000.0,
            bolt_axial_stiffness_n_per_mm=4000.0,
            contact_penalty_n_per_mm=5000.0,
            tangential_stick_stiffness_n_per_mm=10000.0,
            bolt_preload_n=1000.0,
            friction_coefficient=0.0,
        )
        result = solve_preloaded_joint(joint, shear_load_n=10.0)
        self.assertEqual(result.friction_regime, "SLIP")
        self.assertAlmostEqual(result.friction_capacity_n, 0.0, places=12)
        self.assertAlmostEqual(result.friction_force_n, 0.0, places=12)
        self.assertAlmostEqual(result.tangential_residual_n, 10.0, places=12)

    def test_invalid_inputs_fail_closed(self):
        invalid = [
            PreloadedJoint(-1.0, 4000.0, 5000.0, 10000.0, 1000.0, 0.2),
            PreloadedJoint(1000.0, 0.0, 5000.0, 10000.0, 1000.0, 0.2),
            PreloadedJoint(1000.0, 4000.0, 0.0, 10000.0, 1000.0, 0.2),
            PreloadedJoint(1000.0, 4000.0, 5000.0, 0.0, 1000.0, 0.2),
            PreloadedJoint(1000.0, 4000.0, 5000.0, 10000.0, -1.0, 0.2),
            PreloadedJoint(1000.0, 4000.0, 5000.0, 10000.0, 1000.0, -0.1),
        ]
        for joint in invalid:
            with self.subTest(joint=joint):
                with self.assertRaises(PreloadedJointError):
                    solve_preloaded_joint(joint)


if __name__ == "__main__":
    unittest.main()
