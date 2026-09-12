import tempfile
import unittest
from pathlib import Path

from astermax.model_preparation import (
    ModelPreparationError,
    StaticPreparationSpec,
    approve_static_preparation,
    build_static_preparation_case,
    preparation_summary,
    write_preparation_evidence,
)


HEADER = "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n"
FOOTER = "\nENDSEC;\nEND-ISO-10303-21;\n"
MM = "#42=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));"


class ModelPreparationHarness(unittest.TestCase):
    def _spec(self, **overrides):
        td = tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup)
        step = Path(td.name) / "case.step"
        step.write_text(HEADER + MM + FOOTER, encoding="utf-8")
        values = dict(
            step_path=step,
            axis="x",
            fixed_side="min",
            load_side="max",
            force_n=(100.0, 0.0, 0.0),
            mesh_size_mm=2.0,
            young_mpa=210000.0,
            poisson=0.30,
            minimum_tet_quality=0.05,
            detected_unit="mm",
        )
        values.update(overrides)
        return StaticPreparationSpec(**values)

    def test_agent_proposals_are_never_approved_implicitly(self):
        case = build_static_preparation_case(self._spec())
        summary = preparation_summary(case)
        self.assertFalse(summary["solve_gate"]["ready"])
        self.assertEqual(summary["solve_gate"]["issues"], ["constraint_missing", "load_missing"])
        self.assertEqual(summary["approved_proposal_ids"], [])
        self.assertEqual(summary["pending_proposal_ids"], ["fixed-support-1", "resultant-force-1"])

    def test_explicit_engineer_approval_unlocks_basic_static_gate(self):
        case = build_static_preparation_case(self._spec())
        before = case.fingerprint()
        approve_static_preparation(case, approved_by="Verification Engineer")
        summary = preparation_summary(case)
        self.assertTrue(summary["solve_gate"]["ready"])
        self.assertEqual(summary["solve_gate"]["issues"], [])
        self.assertEqual(summary["approved_proposal_ids"], ["fixed-support-1", "resultant-force-1"])
        self.assertNotEqual(before, case.fingerprint())
        self.assertEqual([decision["by"] for decision in case.decisions], ["Verification Engineer", "Verification Engineer"])

    def test_non_mm_and_ambiguous_static_configuration_fail_closed(self):
        with self.assertRaisesRegex(ModelPreparationError, "resolved to mm"):
            build_static_preparation_case(self._spec(detected_unit="m"))
        with self.assertRaisesRegex(ModelPreparationError, "distinct"):
            build_static_preparation_case(self._spec(fixed_side="min", load_side="min"))
        with self.assertRaisesRegex(ModelPreparationError, "quality"):
            build_static_preparation_case(self._spec(minimum_tet_quality=0.0))

    def test_preparation_evidence_is_deterministic_for_same_approved_intent(self):
        spec = self._spec()
        first = build_static_preparation_case(spec, case_id="demo")
        second = build_static_preparation_case(spec, case_id="demo")
        approve_static_preparation(first, approved_by="Engineer")
        approve_static_preparation(second, approved_by="Engineer")
        td = tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup)
        a = write_preparation_evidence(first, Path(td.name) / "a")["summary"]
        b = write_preparation_evidence(second, Path(td.name) / "b")["summary"]
        self.assertEqual(a["engineering_intent_sha256"], b["engineering_intent_sha256"])
        self.assertEqual(a["preparation_evidence_sha256"], b["preparation_evidence_sha256"])
        self.assertTrue((Path(td.name) / "a" / "model_preparation.json").is_file())

    def test_empty_approver_cannot_unlock_solver(self):
        case = build_static_preparation_case(self._spec())
        with self.assertRaisesRegex(ModelPreparationError, "approver"):
            approve_static_preparation(case, approved_by="  ")
        self.assertFalse(case.solve_gate()["ready"])


if __name__ == "__main__":
    unittest.main()
