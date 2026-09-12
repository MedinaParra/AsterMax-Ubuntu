import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from astermax.browser_viewer import BrowserViewerError, write_self_contained_viewer
from astermax.demo_bundle import build_verified_multigap_case, generate_demo_bundle


class BrowserViewerHarness(unittest.TestCase):
    def test_bundle_contains_deterministic_dependency_free_astermax_viewer(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            first = generate_demo_bundle(a)
            second = generate_demo_bundle(b)
            self.assertEqual(first["format_version"], 2)
            self.assertEqual(first["viewer"], "astermax_viewer.html")
            self.assertIn("astermax_viewer.html", first["artifacts"])
            self.assertEqual(
                first["artifacts"]["astermax_viewer.html"]["sha256"],
                second["artifacts"]["astermax_viewer.html"]["sha256"],
            )

            root = Path(a)
            html = (root / "astermax_viewer.html").read_text(encoding="utf-8")
            summary_bytes = (root / "summary.json").read_bytes()
            summary_hash = sha256(summary_bytes).hexdigest()
            self.assertIn(summary_hash, html)
            self.assertIn("AsterMax", html)
            self.assertIn("Verified Engineering Viewer", html)
            self.assertIn("contact_pressure_MPa", html)
            self.assertIn("friction_utilization", html)
            self.assertIn("bolt_axial_force_N", html)
            self.assertIn("support_state", html)
            self.assertIn("Drag: rotate", html)
            self.assertNotIn("https://", html)
            self.assertNotIn("http://", html)
            self.assertNotIn("<script src=", html)

            payload_start = html.index('<script id="astermax-data" type="application/json">')
            payload_start = html.index('>', payload_start) + 1
            payload_end = html.index('</script>', payload_start)
            payload = json.loads(html[payload_start:payload_end])
            self.assertEqual(payload["unit_system"], "mm-N-MPa")
            self.assertEqual(payload["summary_sha256"], summary_hash)
            self.assertEqual(payload["case"]["support_state"], ["ACTIVE", "OPEN", "OPEN"])
            self.assertEqual(payload["case"]["initial_gap_mm"], [0.1, 0.2, 0.4])
            self.assertEqual(len(payload["nodes"]), 6)
            self.assertEqual(len(payload["elements"]), 3)

    def test_invalid_summary_digest_fails_closed(self):
        mesh, connectors, result = build_verified_multigap_case()
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(BrowserViewerError):
                write_self_contained_viewer(
                    Path(folder) / "bad.html",
                    mesh,
                    connectors,
                    result,
                    {"case_id": "test"},
                    summary_sha256="not-a-sha256",
                )


if __name__ == "__main__":
    unittest.main()
