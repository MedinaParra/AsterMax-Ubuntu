"""Failure lifecycle tests; fixture bytes below are not mesh/FEA results."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from brep_mesh import run


class FailureLifecycle(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.inputs = [self.root / name for name in ('input.brep', 'params', 'refinement')]
        for path in self.inputs:
            path.write_text('source fixture')
        self.target = self.root / 'mesh.vol'
        self.generated = [self.target, self.root / 'mesh.pending.vol',
                          self.root / 'mesh.brep-evidence.json']

    def execute(self):
        run(self.inputs[0], self.target, self.inputs[1], self.inputs[2])

    def test_failed_retry_removes_previous_output_and_success_evidence(self):
        for path in self.generated:
            path.write_text('stale fixture')
        # Exercise the real parser failure before invoking the native mesher.
        with self.assertRaises(ValueError):
            self.execute()
        self.assertTrue(all(not path.exists() for path in self.generated))
        self.assertTrue(all(path.read_text() == 'source fixture' for path in self.inputs))

    def test_partial_publication_and_interrupt_are_cleaned(self):
        def partial(*args):
            for path in self.generated:
                path.write_text('incomplete fixture')
            raise KeyboardInterrupt()
        with patch('brep_mesh._generate', side_effect=partial):
            with self.assertRaises(KeyboardInterrupt):
                self.execute()
        self.assertTrue(all(not path.exists() for path in self.generated))

    def test_output_alias_cannot_delete_source(self):
        for path in self.generated:
            path.write_text('source fixture')
            with self.assertRaisesRegex(ValueError, 'overwrite input'):
                run(path, self.target, self.inputs[1], self.inputs[2])
            self.assertEqual(path.read_text(), 'source fixture')


if __name__ == '__main__':
    unittest.main()
