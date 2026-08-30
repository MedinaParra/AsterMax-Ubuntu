import unittest

from astermax.case_context import CaseValidationError, EngineeringCase


class EngineeringCaseHarnessTests(unittest.TestCase):
    def test_static_solve_gate_requires_engineer_approved_constraint_and_load(self):
        case = EngineeringCase("demo")
        case.set_geometry(path="CONJUNTO_A_MODELAR.step", detected_unit="mm")
        case.propose(
            id="bc-001",
            kind="fixed_support",
            target="face:mount",
            definition={"ux": 0, "uy": 0, "uz": 0},
            rationale="Candidate mounting interface detected from case intent.",
        )
        case.propose(
            id="load-001",
            kind="force",
            target="face:load",
            definition={"vector_N": [0, -1000, 0]},
            rationale="Candidate service load supplied by the case definition.",
        )

        self.assertFalse(case.solve_gate()["ready"])
        self.assertEqual(
            case.solve_gate()["issues"], ["constraint_missing", "load_missing"]
        )

        case.approve("bc-001", approved_by="engineer")
        case.approve("load-001", approved_by="engineer")
        self.assertTrue(case.solve_gate()["ready"])

    def test_mm_invariant_blocks_unresolved_cad_scale(self):
        case = EngineeringCase("unit-guard")
        with self.assertRaises(CaseValidationError):
            case.set_geometry(path="part.step", detected_unit="m")

    def test_fingerprint_changes_when_engineering_intent_changes(self):
        case = EngineeringCase("traceability")
        case.set_geometry(path="part.step", detected_unit="mm")
        before = case.fingerprint()
        case.add_assumption("Small-displacement linear static analysis.")
        after = case.fingerprint()
        self.assertNotEqual(before, after)

    def test_assistant_cannot_silently_create_unsupported_physics(self):
        case = EngineeringCase("physics-guard")
        with self.assertRaises(CaseValidationError):
            case.propose(
                id="contact-001",
                kind="frictional_contact",
                target="faces:A-B",
                definition={"mu": 0.2},
                rationale="Advanced physics must use a validated backend.",
            )


if __name__ == "__main__":
    unittest.main()
