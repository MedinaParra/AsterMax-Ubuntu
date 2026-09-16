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

    def run_vtu_promotion_failure(self, existing_bundle=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            med = root / 'input.rmed'
            bundle = root / 'bundle.json'
            vtu = root / 'result.vtu'
            fixture.build_fixture(med, {'TE4': [[1, 2, 3, 4]]})
            if existing_bundle:
                bundle.write_text('previous bundle', encoding='utf-8')
            # A directory occupying the VTU destination makes publication fail after both
            # temporary artifacts have been written and validated, before any JSON is published.
            vtu.mkdir()
            result = subprocess.run(
                [sys.executable, str(HERE / 'bridge-c964-med-results.py'), str(med), str(bundle), str(vtu)],
                env=dict(os.environ, ASTERMAX_MED_BRIDGE_MODE='production'), capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertTrue(vtu.is_dir())
            if existing_bundle:
                self.assertEqual(bundle.read_text(encoding='utf-8'), 'previous bundle')
            else:
                self.assertFalse(bundle.exists(), result.stderr)
            self.assertEqual(list(root.glob('.bundle.json.*.tmp')), [], 'bundle temporary was not cleaned')
            self.assertEqual(list(root.glob('.result.vtu.*.tmp')), [], 'VTU temporary was not cleaned')

    def test_second_promotion_failure_restores_previous_vtu(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            med = root / 'input.rmed'
            bundle = root / 'bundle.json'
            vtu = root / 'result.vtu'
            fixture.build_fixture(med, {'TE4': [[1, 2, 3, 4]]})
            vtu.write_text('previous vtu', encoding='utf-8')
            # Occupying the JSON destination with a directory lets the VTU promotion occur first,
            # then forces the second os.replace to fail. The old VTU must be restored by rollback.
            bundle.mkdir()
            result = subprocess.run(
                [sys.executable, str(HERE / 'bridge-c964-med-results.py'), str(med), str(bundle), str(vtu)],
                env=dict(os.environ, ASTERMAX_MED_BRIDGE_MODE='production'), capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertTrue(bundle.is_dir())
            self.assertEqual(vtu.read_text(encoding='utf-8'), 'previous vtu')
            self.assertEqual(list(root.glob('.bundle.json.*.tmp')), [], 'bundle temporary was not cleaned')
            self.assertEqual(list(root.glob('.result.vtu.*.tmp')), [], 'VTU temporary was not cleaned')
            self.assertEqual(list(root.glob('.result.vtu.previous.*.tmp')), [], 'rollback link was not cleaned')

    def test_nonfinite_coordinates(self):
        self.run_rejected(f'{fixture.ROOT}/NOE/COO', float('nan'))

    def test_nonfinite_displacement(self):
        self.run_rejected(f'CHA/0000000eDEPL/{fixture.STEP}/NOE/MED_NO_PROFILE_INTERNAL/CO', float('inf'))

    def test_nonfinite_stress(self):
        self.run_rejected(f'CHA/0000000eSIGM_ELNO/{fixture.STEP}/NOE.TE4/MED_NO_PROFILE_INTERNAL/CO', float('nan'))

    def test_total_deformation_overflow(self):
        self.run_rejected(f'CHA/0000000eDEPL/{fixture.STEP}/NOE/MED_NO_PROFILE_INTERNAL/CO', 1e308)

    def test_nonfinite_von_mises(self):
        self.run_rejected(f'CHA/0000000eSIEQ_ELNO/{fixture.STEP}/NOE.TE4/MED_NO_PROFILE_INTERNAL/CO', float('inf'))

    def test_wrong_regression_model(self):
        self.run_rejected(mode='regression')

    def test_rejection_preserves_existing_artifacts(self):
        self.run_rejected(f'{fixture.ROOT}/NOE/COO', float('nan'), existing=True)

    def test_vtu_promotion_failure_does_not_publish_new_bundle(self):
        self.run_vtu_promotion_failure(existing_bundle=False)

    def test_vtu_promotion_failure_preserves_existing_bundle(self):
        self.run_vtu_promotion_failure(existing_bundle=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
