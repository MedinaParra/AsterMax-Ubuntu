"""Parser regression fixtures only; these are not solver executions or FEA evidence."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import h5py

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('fixture', HERE / 'test-c1007-med-bridge.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class PublicationTests(unittest.TestCase):
    def run_rejected(self, dataset=None, value=None, mode='production', existing=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            med, bundle, vtu = [root / name for name in ('input.rmed', 'bundle.json', 'result.vtu')]
            fixture.build_fixture(med, {'TE4': [[1, 2, 3, 4]]})
            if dataset:
                with h5py.File(med, 'r+') as h:
                    h[dataset][0] = value
            if existing:
                bundle.write_text('previous bundle')
                vtu.write_text('previous vtu')
            result = subprocess.run(
                [sys.executable, str(HERE / 'bridge-c964-med-results.py'), str(med), str(bundle), str(vtu)],
                env=dict(os.environ, ASTERMAX_MED_BRIDGE_MODE=mode), capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('gate failed before publication', result.stderr)
            if existing:
                self.assertEqual(bundle.read_text(), 'previous bundle')
                self.assertEqual(vtu.read_text(), 'previous vtu')
            else:
                self.assertFalse(bundle.exists(), result.stderr)
                self.assertFalse(vtu.exists(), result.stderr)

    def test_nonfinite_coordinates(self):
        self.run_rejected(f'{fixture.ROOT}/NOE/COO', float('nan'))

    def test_nonfinite_displacement(self):
        self.run_rejected(f'CHA/0000000eDEPL/{fixture.STEP}/NOE/MED_NO_PROFILE_INTERNAL/CO', float('inf'))

    def test_nonfinite_stress(self):
        self.run_rejected(f'CHA/0000000eSIGM_ELNO/{fixture.STEP}/NOE.TE4/MED_NO_PROFILE_INTERNAL/CO', float('nan'))

    def test_nonfinite_von_mises(self):
        self.run_rejected(f'CHA/0000000eSIEQ_ELNO/{fixture.STEP}/NOE.TE4/MED_NO_PROFILE_INTERNAL/CO', float('inf'))

    def test_wrong_regression_model(self):
        self.run_rejected(mode='regression')

    def test_rejection_preserves_existing_artifacts(self):
        self.run_rejected(f'{fixture.ROOT}/NOE/COO', float('nan'), existing=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
