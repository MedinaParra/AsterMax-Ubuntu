#!/usr/bin/env python3
"""C10.19 parser regressions for MED mesh identity and result-step selection.

Fixtures are deterministic parser data only, not solver evidence.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import h5py

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("fixture", HERE / "test-c1007-med-bridge.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
BRIDGE = HERE / "bridge-c964-med-results.py"


def run_bridge(med, bundle, vtu):
    return subprocess.run(
        [sys.executable, str(BRIDGE), str(med), str(bundle), str(vtu)],
        env=dict(os.environ, ASTERMAX_MED_BRIDGE_MODE="production"),
        capture_output=True,
        text=True,
    )


class MedSelectionTests(unittest.TestCase):
    def make_fixture(self, root):
        med = root / "case.rmed"
        fixture.build_fixture(med, {"TE4": [[1, 2, 3, 4]]})
        return med

    def test_mesh_name_is_discovered_and_recorded(self):
        with tempfile.TemporaryDirectory(prefix="astermax-c1019-mesh-") as directory:
            root = Path(directory)
            med = self.make_fixture(root)
            with h5py.File(med, "r+") as h:
                h.move("ENS_MAA/00000001", "ENS_MAA/ASTERMAX_DYNAMIC_MESH")
                for field in h["CHA"].values():
                    field.attrs["MAI"] = b"ASTERMAX_DYNAMIC_MESH"
            bundle, vtu = root / "bundle.json", root / "result.vtu"
            result = run_bridge(med, bundle, vtu)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(bundle.read_text(encoding="utf-8"))
            self.assertEqual(data["mesh"]["med_name"], "ASTERMAX_DYNAMIC_MESH")
            self.assertEqual(data["source"]["med_result_step"], fixture.STEP)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["med_mesh_name"], "ASTERMAX_DYNAMIC_MESH")
            self.assertEqual(summary["med_result_step"], fixture.STEP)

    def test_multiple_meshes_are_rejected_explicitly(self):
        with tempfile.TemporaryDirectory(prefix="astermax-c1019-multimesh-") as directory:
            root = Path(directory)
            med = self.make_fixture(root)
            with h5py.File(med, "r+") as h:
                h.copy("ENS_MAA/00000001", "ENS_MAA/00000002")
            bundle, vtu = root / "bundle.json", root / "result.vtu"
            result = run_bridge(med, bundle, vtu)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exactly one mesh under ENS_MAA", result.stderr)
            self.assertIn("00000001", result.stderr)
            self.assertIn("00000002", result.stderr)
            self.assertFalse(bundle.exists())
            self.assertFalse(vtu.exists())

    def test_multiple_steps_are_rejected_and_listed(self):
        with tempfile.TemporaryDirectory(prefix="astermax-c1019-multistep-") as directory:
            root = Path(directory)
            med = self.make_fixture(root)
            second = "0000000000000000000200000000000000000001"
            with h5py.File(med, "r+") as h:
                h.copy(f"CHA/0000000eDEPL/{fixture.STEP}", f"CHA/0000000eDEPL/{second}")
            bundle, vtu = root / "bundle.json", root / "result.vtu"
            result = run_bridge(med, bundle, vtu)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("multiple MED result steps found", result.stderr)
            self.assertIn(fixture.STEP, result.stderr)
            self.assertIn(second, result.stderr)
            self.assertIn("explicit step selection is required", result.stderr)
            self.assertFalse(bundle.exists())
            self.assertFalse(vtu.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
