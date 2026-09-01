import tempfile
import unittest
from pathlib import Path

from astermax.windows_demo_runner import (
    WindowsDemoRunnerError,
    run_verified_demo,
    verify_evidence_bundle,
)


class WindowsDemoRunnerHarness(unittest.TestCase):
    def test_runner_generates_and_verifies_reproducible_evidence_without_gui(self):
        with tempfile.TemporaryDirectory() as folder_a, tempfile.TemporaryDirectory() as folder_b:
            first = run_verified_demo(folder_a, open_viewer=False)
            second = run_verified_demo(folder_b, open_viewer=False)

            self.assertTrue(first.evidence_verified)
            self.assertFalse(first.viewer_launched)
            self.assertIsNone(first.viewer_executable)
            self.assertTrue(first.vtk_path.is_file())
            self.assertTrue(first.manifest_path.is_file())
            self.assertEqual(first.evidence_fingerprint_sha256, second.evidence_fingerprint_sha256)

            manifest = verify_evidence_bundle(folder_a)
            self.assertEqual(
                first.evidence_fingerprint_sha256,
                manifest["evidence_fingerprint_sha256"],
            )
            self.assertIn("verified_multigap_joint.vtk", manifest["artifacts"])
            self.assertIn("summary.json", manifest["artifacts"])
            self.assertIn("README.txt", manifest["artifacts"])

    def test_tampered_artifact_fails_closed_before_presentation(self):
        with tempfile.TemporaryDirectory() as folder:
            result = run_verified_demo(folder, open_viewer=False)
            summary = Path(folder) / "summary.json"
            summary.write_text(summary.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
            with self.assertRaises(WindowsDemoRunnerError):
                verify_evidence_bundle(folder)
            self.assertTrue(result.vtk_path.is_file())

    def test_missing_manifest_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(WindowsDemoRunnerError):
                verify_evidence_bundle(folder)


if __name__ == "__main__":
    unittest.main()
