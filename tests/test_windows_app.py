import tempfile
import unittest
from pathlib import Path

from astermax.windows_app import StepCaseConfig, WindowsAppError, validate_step_mm_file

HEADER="ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n"
FOOTER="\nENDSEC;\nEND-ISO-10303-21;\n"


class WindowsStepDesktopHarness(unittest.TestCase):
    def _step(self, entity):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup)
        path=Path(td.name)/"case.step"
        path.write_text(HEADER+entity+FOOTER,encoding="utf-8")
        return path

    def test_import_gate_accepts_explicit_mm_step(self):
        path=self._step("#42=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));")
        self.assertEqual(validate_step_mm_file(path),"mm")

    def test_import_gate_rejects_metre_step_instead_of_scaling_silently(self):
        path=self._step("#42=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT($,.METRE.));")
        with self.assertRaisesRegex(WindowsAppError,"mm gate failed"):
            validate_step_mm_file(path)

    def test_case_requires_distinct_semantic_fixed_and_load_sides(self):
        path=self._step("#42=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));")
        config=StepCaseConfig(path, path.parent/"out", fixed_side="min", load_side="min")
        with self.assertRaisesRegex(WindowsAppError,"same semantic side"):
            config.validate()

    def test_case_rejects_invalid_material_mesh_and_quality(self):
        path=self._step("#42=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));")
        with self.assertRaises(WindowsAppError): StepCaseConfig(path,path.parent/"a",mesh_size_mm=0).validate()
        with self.assertRaises(WindowsAppError): StepCaseConfig(path,path.parent/"b",young_mpa=-1).validate()
        with self.assertRaises(WindowsAppError): StepCaseConfig(path,path.parent/"c",poisson=.5).validate()
        with self.assertRaises(WindowsAppError): StepCaseConfig(path,path.parent/"d",minimum_tet_quality=0).validate()


if __name__=="__main__": unittest.main()
