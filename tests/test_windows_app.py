import tempfile
import unittest
from pathlib import Path

from astermax.model_preparation import approve_static_preparation, preparation_summary
from astermax.windows_app import (
    StepCaseConfig,
    WindowsAppError,
    build_windows_preparation,
    run_windows_step_case,
    validate_step_mm_file,
)

HEADER="ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n"
FOOTER="\nENDSEC;\nEND-ISO-10303-21;\n"


class WindowsStepDesktopHarness(unittest.TestCase):
    def _step(self, entity):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup)
        path=Path(td.name)/"case.step"
        path.write_text(HEADER+entity+FOOTER,encoding="utf-8")
        return path

    def _mm_step(self):
        return self._step("#42=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));")

    def test_import_gate_accepts_explicit_mm_step(self):
        self.assertEqual(validate_step_mm_file(self._mm_step()),"mm")

    def test_import_gate_rejects_metre_step_instead_of_scaling_silently(self):
        path=self._step("#42=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT($,.METRE.));")
        with self.assertRaisesRegex(WindowsAppError,"mm gate failed"):
            validate_step_mm_file(path)

    def test_case_requires_distinct_semantic_fixed_and_load_sides(self):
        path=self._mm_step()
        config=StepCaseConfig(path, path.parent/"out", fixed_side="min", load_side="min")
        with self.assertRaisesRegex(WindowsAppError,"same semantic side"):
            config.validate()

    def test_case_rejects_invalid_material_mesh_and_quality(self):
        path=self._mm_step()
        with self.assertRaises(WindowsAppError): StepCaseConfig(path,path.parent/"a",mesh_size_mm=0).validate()
        with self.assertRaises(WindowsAppError): StepCaseConfig(path,path.parent/"b",young_mpa=-1).validate()
        with self.assertRaises(WindowsAppError): StepCaseConfig(path,path.parent/"c",poisson=.5).validate()
        with self.assertRaises(WindowsAppError): StepCaseConfig(path,path.parent/"d",minimum_tet_quality=0).validate()

    def test_desktop_preparation_is_unapproved_by_default(self):
        path=self._mm_step()
        case=build_windows_preparation(StepCaseConfig(path,path.parent/"out"))
        summary=preparation_summary(case)
        self.assertFalse(summary["solve_gate"]["ready"])
        self.assertEqual(summary["approved_proposal_ids"],[])
        self.assertEqual(summary["pending_proposal_ids"],["fixed-support-1","resultant-force-1"])

    def test_engineer_approval_unlocks_same_intent(self):
        path=self._mm_step()
        case=build_windows_preparation(StepCaseConfig(path,path.parent/"out"))
        before=preparation_summary(case)["engineering_intent_sha256"]
        approve_static_preparation(case,approved_by="Harness Engineer")
        after=preparation_summary(case)
        self.assertTrue(after["solve_gate"]["ready"])
        self.assertEqual(after["engineering_intent_sha256"],before)
        self.assertEqual(after["approved_proposal_ids"],["fixed-support-1","resultant-force-1"])

    def test_solve_rejects_missing_approval_before_gmsh_lookup(self):
        path=self._mm_step()
        config=StepCaseConfig(path,path.parent/"out")
        with self.assertRaisesRegex(WindowsAppError,"engineer approval is required"):
            run_windows_step_case(config,approved_by="")

    def test_changed_model_has_different_engineering_intent_fingerprint(self):
        path=self._mm_step()
        base=build_windows_preparation(StepCaseConfig(path,path.parent/"a",force_n=(100.0,0.0,0.0)))
        changed=build_windows_preparation(StepCaseConfig(path,path.parent/"b",force_n=(101.0,0.0,0.0)))
        self.assertNotEqual(
            preparation_summary(base)["engineering_intent_sha256"],
            preparation_summary(changed)["engineering_intent_sha256"],
        )


if __name__=="__main__": unittest.main()
