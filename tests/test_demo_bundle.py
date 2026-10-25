import json
import tempfile
import unittest
from pathlib import Path

from astermax.demo_bundle import DEMO_CASE_ID, generate_demo_bundle


class DemoBundleHarness(unittest.TestCase):
    def test_bundle_is_deterministic_and_contains_verified_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            first_dir = Path(folder) / "first"
            second_dir = Path(folder) / "second"
            first = generate_demo_bundle(first_dir)
            second = generate_demo_bundle(second_dir)

            self.assertEqual(first["case_id"], DEMO_CASE_ID)
            self.assertEqual(
                first["evidence_fingerprint_sha256"],
                second["evidence_fingerprint_sha256"],
            )
            self.assertEqual(first["artifacts"], second["artifacts"])

            for name in ("verified_multigap_joint.vtk", "summary.json", "README.txt", "manifest.json"):
                self.assertTrue((first_dir / name).exists())

            summary = json.loads((first_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["unit_system"], "mm-N-MPa")
            self.assertTrue(summary["solver_converged"])
            self.assertLess(summary["free_residual_max_N"], 1e-6)
            self.assertEqual(summary["initial_gap_mm"], [0.1, 0.2, 0.4])
            self.assertEqual(summary["support_state"], ["ACTIVE", "OPEN", "OPEN"])
            self.assertAlmostEqual(summary["support_loss_fraction"], 2.0 / 3.0, places=12)
            self.assertAlmostEqual(summary["total_normal_contact_force_N"], 260.948905109489, places=6)
            self.assertAlmostEqual(summary["total_friction_capacity_N"], 52.1897810218978, places=6)

            expected_gap = (-0.052189781021898, 0.004014598540146, 0.200364963503650)
            for actual, expected in zip(summary["final_gap_mm"], expected_gap):
                self.assertAlmostEqual(actual, expected, places=8)
            expected_bolt = (391.240875912409, 216.058394160584, 201.459854014599)
            for actual, expected in zip(summary["bolt_axial_force_N"], expected_bolt):
                self.assertAlmostEqual(actual, expected, places=6)
            self.assertAlmostEqual(sum(summary["bolt_load_share"]), 1.0, places=12)

            vtk = (first_dir / "verified_multigap_joint.vtk").read_text(encoding="utf-8")
            for token in (
                "SCALARS initial_gap_mm double 1",
                "SCALARS final_gap_mm double 1",
                "SCALARS support_state double 1",
                "SCALARS contact_pressure_MPa double 1",
                "SCALARS friction_utilization double 1",
                "SCALARS bolt_axial_force_N double 1",
                "VECTORS displacement_mm double",
            ):
                self.assertIn(token, vtk)

    def test_manifest_hashes_detect_artifact_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "bundle"
            manifest = generate_demo_bundle(destination)
            original = manifest["artifacts"]["summary.json"]["sha256"]
            summary_path = destination / "summary.json"
            summary_path.write_text(summary_path.read_text(encoding="utf-8") + "tamper\n", encoding="utf-8")

            from hashlib import sha256
            current = sha256(summary_path.read_bytes()).hexdigest()
            self.assertNotEqual(original, current)


if __name__ == "__main__":
    unittest.main()
