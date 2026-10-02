"""Synthetic contract regressions; these tests do not execute or certify FEA."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('contract', HERE / 'ws01_contract.py')
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.bundle = {
            'source': {'kind': 'REAL_CODE_ASTER_MED'},
            'integrity': {'fea_values_invented': False, 'von_mises_component_first_ansys_parity': True},
            'units': {'length': 'mm', 'force': 'N', 'stress': 'MPa'},
            'mesh': {'node_count': 10, 'element_count': 1, 'element_type': 'TETRA10'},
            'fields': {'displacement': {'total_max': 0.05}, 'von_mises': {'nodal_max': 300., 'raw_elno_max': 310.}},
        }
        self.analysis = {
            'tutorial': 'WS01 synthetic test only',
            'scope_binding': {'cad_sha256': contract.CAD_SHA256, 'mode': 'exact_cad_sha256_plus_face_manifest', 'verified': True, 'selected_face_count': 30},
            'scope': dict(copy.deepcopy(contract.SCOPES), pressure_face_count=17),
            'load': {'type': 'pressure', 'magnitude_mpa': 1.1},
            'supports': {'type': 'frictionless-normal', 'code_aster': 'FACE_IMPO/DNOR=0'},
            'material': {'E_mpa': 71000., 'nu': .33, 'yield_mpa_for_safety_factor': 280.},
            'mesh': {'nodes': 10, 'volume_elements': 1, 'order': 2},
        }

    def run_case(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in [('bundle', self.bundle), ('input', self.analysis)]:
                (root / (name + '.json')).write_text(json.dumps(data), encoding='utf-8-sig')
            proc = subprocess.run([sys.executable, str(HERE/'compare-ws01.py'), '--bundle', str(root/'bundle.json'), '--input', str(root/'input.json'), '--reference', str(HERE/'ws01-ansys-reference.json'), '--out', str(root/'out.json')], capture_output=True, text=True)
            output = root/'out.json'
            return proc.returncode, json.loads(output.read_text()) if output.exists() else None

    def test_valid_metadata_is_not_equivalence(self):
        code, report = self.run_case()
        self.assertEqual(code, 0)
        self.assertEqual(report['comparison']['evidence_status'], 'PASS')
        self.assertEqual(report['comparison']['benchmark_equivalence'], 'NOT_ESTABLISHED')
        self.assertFalse(report['comparison']['within_snapshot_tolerance'])

    def test_wrong_faces_same_count_blocked(self):
        self.analysis['scope']['counterbore_support'][0] = 23
        code, report = self.run_case()
        self.assertEqual(code, 2)
        self.assertFalse(report['comparison']['same_support_intent'])
        self.assertIsNone(report['comparison']['within_snapshot_tolerance'])

    def test_missing_or_wrong_evidence_blocked(self):
        mutations = [
            ('scope_binding', 'cad_sha256', 'different'),
            ('load', 'magnitude_mpa', 2.2),
            ('material', 'E_mpa', 200000.),
            ('mesh', 'nodes', 11),
            ('scope_binding', 'verified', False),
        ]
        for group, key, value in mutations:
            with self.subTest(key=key):
                original = self.analysis[group][key]
                self.analysis[group][key] = value
                self.assertEqual(self.run_case()[0], 2)
                self.analysis[group][key] = original

    def test_units_source_and_stress_method_blocked(self):
        for group, key, value in [('units', 'length', 'm'), ('source', 'kind', 'SYNTHETIC'), ('integrity', 'von_mises_component_first_ansys_parity', False)]:
            with self.subTest(key=key):
                original = self.bundle[group][key]
                self.bundle[group][key] = value
                self.assertEqual(self.run_case()[0], 2)
                self.bundle[group][key] = original

    def test_face_order_irrelevant_but_duplicates_blocked(self):
        self.analysis['scope']['pressure_faces'].reverse()
        self.assertEqual(self.run_case()[0], 0)
        self.analysis['scope']['pressure_faces'][0] = self.analysis['scope']['pressure_faces'][1]
        self.assertEqual(self.run_case()[0], 2)

    def test_nonfinite_negative_and_boolean_results_rejected(self):
        for value in [float('nan'), float('inf'), -1, True, '300']:
            with self.subTest(value=value):
                self.bundle['fields']['von_mises']['nodal_max'] = value
                code, report = self.run_case()
                self.assertNotEqual(code, 0)
                self.assertIsNone(report)

    def test_zero_stress_serializes_without_infinity(self):
        self.bundle['fields']['von_mises'] = {'nodal_max': 0., 'raw_elno_max': 0.}
        code, report = self.run_case()
        self.assertEqual(code, 0)
        self.assertIsNone(report['astermax_code_aster']['safety_factor_from_280mpa_yield_nodal'])
        self.assertFalse(report['comparison']['within_snapshot_tolerance'])

    def test_blocked_comparison_excluded_from_convergence(self):
        self.analysis['scope']['lip_support'] = [14]
        _, report = self.run_case()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'mesh-3mm').mkdir()
            (root/'mesh-3mm'/'ws01-comparison.json').write_text(json.dumps(report))
            subprocess.run([sys.executable, str(HERE/'summarize-ws01-convergence.py'), '--root', directory, '--out', str(root/'summary.json')], check=True, capture_output=True)
            summary = json.loads((root/'summary.json').read_text())
            self.assertEqual(summary['rows'][0]['state'], 'BLOCKED')


if __name__ == '__main__':
    unittest.main(verbosity=2)
